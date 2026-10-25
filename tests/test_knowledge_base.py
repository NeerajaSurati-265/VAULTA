from tests.conftest import DOCUMENTS

SOP = "SOP-PUMP-402.pdf"


def sop_bytes():
    return (DOCUMENTS / SOP).read_bytes()


def test_ingest_adds_chunks_and_reingest_adds_none(make_kb):
    kb = make_kb()
    first = kb.ingest_pdf(sop_bytes(), SOP)
    assert first["status"] == "completed"
    assert first["chunks_added"] > 0

    second = kb.ingest_pdf(sop_bytes(), SOP)
    assert second["status"] == "already_indexed"
    assert second["chunks_added"] == 0
    assert len(kb.chunks) == first["chunks_added"] == kb.index.ntotal


def test_vibration_query_returns_chunks_from_the_sop(make_kb):
    kb = make_kb()
    kb.ingest_pdf(sop_bytes(), SOP)
    results = kb.retrieve("What is the pump vibration threshold?", top_k=3)

    assert results
    assert all(r["doc_name"] == SOP for r in results)
    assert any("vibration" in r["text"].lower() for r in results)


def test_index_is_saved_and_reloaded(make_kb):
    kb = make_kb()
    kb.ingest_pdf(sop_bytes(), SOP)
    reloaded = make_kb()  # same tmp index_dir

    assert len(reloaded.chunks) == len(kb.chunks)
    assert reloaded.index.ntotal == kb.index.ntotal
    assert list(reloaded.indexed_files) == [SOP]


def test_changed_file_with_same_name_replaces_old_chunks(make_kb):
    kb = make_kb()
    kb.ingest_pdf((DOCUMENTS / "pump_inspection.pdf").read_bytes(), "pump_inspection.pdf")
    kb.ingest_pdf(sop_bytes(), SOP)
    other = (DOCUMENTS / "pump_inspection.pdf").read_bytes()

    result = kb.ingest_pdf(other, SOP)  # new content under the SOP's name

    assert result["status"] == "replaced"
    sop_chunks = [c for c in kb.chunks if c["doc_name"] == SOP]
    assert len(sop_chunks) == result["chunks_added"]
    assert all("INSPECTION REPORT" in c["text"] or "PUMP-402" in c["text"] for c in sop_chunks[:1])
    # vectors and chunks still line up one-to-one
    assert kb.index.ntotal == len(kb.chunks)
    assert [c["chunk_id"] for c in kb.chunks] == list(range(len(kb.chunks)))
    # same content again is a no-op
    assert kb.ingest_pdf(other, SOP)["status"] == "already_indexed"


def test_startup_reindexes_a_changed_document(make_kb, tmp_path):
    """E1: a PDF updated in the documents dir must replace its stale chunks in a saved index."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / SOP).write_bytes((DOCUMENTS / "pump_inspection.pdf").read_bytes())  # stale content
    make_kb(documents_dir=docs)

    (docs / SOP).write_bytes(sop_bytes())  # the document is updated on disk
    restarted = make_kb(documents_dir=docs)  # same saved index

    texts = " ".join(c["text"] for c in restarted.chunks if c["doc_name"] == SOP)
    assert "emergency stop circuit" in texts
    assert "INSPECTION REPORT" not in texts
    assert restarted.index.ntotal == len(restarted.chunks)


def test_legacy_entry_without_hash_is_reindexed(make_kb, tmp_path):
    """E1: saves from before D5 have no SHA-256; they must not hide a changed file forever."""
    import json
    from app.main_services.rag_service import META_FILENAME

    kb = make_kb()
    kb.ingest_pdf((DOCUMENTS / "pump_inspection.pdf").read_bytes(), SOP)  # stale content under the SOP name
    meta_path = tmp_path / "index" / META_FILENAME
    meta = json.loads(meta_path.read_text())
    meta["indexed_files"][SOP] = meta["indexed_files"][SOP]["chunks"]  # old format: chunk count only
    meta_path.write_text(json.dumps(meta))

    result = make_kb().ingest_pdf(sop_bytes(), SOP)

    assert result["status"] == "replaced"
