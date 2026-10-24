import json
import zlib

import pytest

from app.main_services import rag_service
from app.main_services.rag_service import rrf_merge, tokenize
from tests.conftest import DOCUMENTS

FAKE_DIM = 256
PREFIXES = ("search_document: ", "search_query: ")


def fake_embed(texts):
    """Deterministic bag-of-words vectors standing in for nomic-embed-text.

    Like the real model, the task prefix is an instruction, not content, so it is
    left out of the vector (the recorded calls still include it).
    """
    vectors = []
    for text in texts:
        for prefix in PREFIXES:
            text = text.removeprefix(prefix)
        vec = [0.0] * FAKE_DIM
        for token in tokenize(text):
            vec[zlib.crc32(token.encode()) % FAKE_DIM] += 1.0
        vectors.append(vec)
    return vectors


@pytest.fixture
def embed_calls(monkeypatch):
    """Mocks the Ollama embedding call and records every batch of texts sent to it."""
    calls = []

    def _embed(texts):
        calls.append(list(texts))
        return fake_embed(texts)

    monkeypatch.setattr(rag_service, "embed_texts", _embed)
    return calls


def ingest_corpus(kb, names=("SOP-PUMP-402.pdf", "SOP-COMP-210.pdf", "MAN-BRG-115.pdf")):
    for name in names:
        kb.ingest_pdf((DOCUMENTS / name).read_bytes(), name)


def test_tokenizer_keeps_ids_and_numbers_intact():
    tokens = tokenize("Pump P-402: trip above 4.5 mm/s RMS.")
    assert "p-402" in tokens
    assert "4.5" in tokens
    assert "mm/s" in tokens
    assert {"p", "402"} <= set(tokens)  # parts of the hyphenated ID too
    assert "rms" in tokens and "rms." not in tokens


def test_rrf_merge_orders_by_summed_reciprocal_rank():
    bm25 = [1, 2, 3]
    vector = [3, 1, 4]
    merged = rrf_merge([bm25, vector], k=60)

    assert [item for item, _ in merged] == [1, 3, 2, 4]
    scores = dict(merged)
    assert scores[1] == pytest.approx(1 / 61 + 1 / 62)
    assert scores[3] == pytest.approx(1 / 63 + 1 / 61)
    assert scores[4] == pytest.approx(1 / 63)


def test_bm25_mode_finds_exact_ids_without_embeddings(make_kb, monkeypatch):
    def no_embeddings(texts):
        raise AssertionError("bm25 mode must not call the embedding model")

    monkeypatch.setattr(rag_service, "embed_texts", no_embeddings)
    kb = make_kb(retrieval_mode="bm25")
    ingest_corpus(kb)

    top = kb.retrieve("When is valve V-211 opened?", top_k=3)[0]
    assert (top["doc_name"], top["page_number"]) == ("SOP-COMP-210.pdf", 1)
    assert top["bm25_rank"] == 1 and top["vector_rank"] is None


def test_semantic_mode_uses_prefixes_and_model_dimension(make_kb, embed_calls):
    kb = make_kb(retrieval_mode="semantic")
    ingest_corpus(kb)

    assert kb.index.d == FAKE_DIM  # dimension detected from the embeddings
    assert all(t.startswith("search_document: ") for batch in embed_calls for t in batch)

    results = kb.retrieve("grease lithium complex NLGI", top_k=3)
    assert embed_calls[-1] == ["search_query: grease lithium complex NLGI"]
    assert results[0]["doc_name"] == "MAN-BRG-115.pdf"
    assert results[0]["vector_rank"] == 1 and results[0]["bm25_rank"] is None


def test_hybrid_mode_reports_both_ranks(make_kb, embed_calls):
    kb = make_kb(retrieval_mode="hybrid")
    ingest_corpus(kb)

    results = kb.retrieve("ISO VG 46 compressor oil change interval", top_k=5)
    top = results[0]
    assert (top["doc_name"], top["page_number"]) == ("SOP-COMP-210.pdf", 3)
    assert top["bm25_rank"] is not None and top["vector_rank"] is not None
    assert top["retrieval_mode"] == "hybrid"
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)


def test_switching_mode_rebuilds_vectors_from_saved_chunks(make_kb, embed_calls, tmp_path):
    hashing_kb = make_kb(retrieval_mode="hashing")
    ingest_corpus(hashing_kb)
    n_chunks = len(hashing_kb.chunks)
    assert embed_calls == []  # hashing never calls the embedding model

    semantic_kb = make_kb(retrieval_mode="semantic")  # same index dir

    # every saved chunk was re-embedded with the new model...
    assert sum(len(batch) for batch in embed_calls) == n_chunks
    assert semantic_kb.index.d == FAKE_DIM and semantic_kb.index.ntotal == n_chunks
    meta = json.loads((tmp_path / "index" / rag_service.META_FILENAME).read_text())
    assert meta["retrieval_mode"] == "semantic"
    assert meta["embed_model"] == semantic_kb.embedder.name

    # ...and loading again in the same mode reuses the saved vectors
    embed_calls.clear()
    make_kb(retrieval_mode="semantic")
    assert embed_calls == []
