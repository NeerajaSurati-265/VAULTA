import os
import re
import json
import hashlib
import logging
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional, Set, Tuple
import numpy as np
import faiss
import fitz
from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import HashingVectorizer

from app.config import (
    DOCUMENTS_DIR, INDEX_DIR, RETRIEVAL_MODE, EMBED_MODEL, HYBRID_CANDIDATES, RRF_K, RETRIEVAL_TOP_K,
)
from app.main_services.ollama_service import ask_local_ai, embed_texts, MODEL


logger = logging.getLogger(__name__)

EMBEDDING_DIM = 1024
RETRIEVAL_MODES = ("hashing", "bm25", "semantic", "hybrid")
INDEX_FILENAME = "knowledge.faiss"
META_FILENAME = "knowledge_meta.json"

# A token is a run of letters/digits, optionally joined by ".", "-" or "/", so
# IDs and numbers like "P-402", "4.5" and "mm/s" stay whole instead of being
# split into meaningless pieces.
_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[.\-/][a-z0-9]+)*")


def tokenize(text: str) -> List[str]:
    """Lowercased BM25 tokens. Hyphenated IDs also yield their parts ("p-402" -> "p", "402")."""
    tokens = []
    for token in _TOKEN_RE.findall(text.lower()):
        tokens.append(token)
        if "-" in token:
            tokens.extend(part for part in token.split("-") if part)
    return tokens


def describe_chunk(chunk: Dict[str, Any]) -> str:
    """One-line provenance for traces, e.g. "SOP-PUMP-402.pdf p.2 | score 0.0325 | BM25 #1 | vector #3"."""
    def rank(r):
        return f"#{r}" if r else "-"
    return (
        f"{chunk['doc_name']} p.{chunk['page_number']} | score {chunk.get('score')} | "
        f"BM25 {rank(chunk.get('bm25_rank'))} | vector {rank(chunk.get('vector_rank'))}"
    )


def chunk_provenance(chunk: Dict[str, Any]) -> Dict[str, Any]:
    """The fields of a retrieved chunk that explain why it was picked (no text)."""
    return {k: chunk.get(k) for k in ("doc_name", "page_number", "score", "bm25_rank", "vector_rank")}


def rrf_merge(ranked_lists: List[List[int]], k: int = RRF_K) -> List[Tuple[int, float]]:
    """Reciprocal Rank Fusion: score(item) = sum over lists of 1 / (k + rank), rank from 1.

    Uses only ranks, so BM25 scores and cosine similarities (different scales)
    can be combined without normalisation. Returns (item, score), best first.
    """
    scores: Dict[int, float] = {}
    for ranked in ranked_lists:
        for rank, item in enumerate(ranked, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)


class HashingEmbedder:
    """Hashed word/bigram vectors: deterministic, no model, but keyword-only."""

    def __init__(self, dimension: int = EMBEDDING_DIM):
        self.name = f"hashing-{dimension}"
        self.vectorizer = HashingVectorizer(
            n_features=dimension,
            norm="l2",
            ngram_range=(1, 2),
            alternate_sign=False,
        )

    def embed_documents(self, texts: List[str]) -> np.ndarray:
        matrix = self.vectorizer.transform(texts).toarray().astype("float32")
        faiss.normalize_L2(matrix)
        return matrix

    def embed_query(self, text: str) -> np.ndarray:
        return self.embed_documents([text])


class OllamaEmbedder:
    """Semantic vectors from a local Ollama embedding model (e.g. nomic-embed-text)."""

    def __init__(self, model: str = EMBED_MODEL):
        self.name = model
        # nomic-embed models are trained with task prefixes and retrieve noticeably
        # worse without them; other models get the raw text.
        uses_prefixes = model.startswith("nomic-embed")
        self.document_prefix = "search_document: " if uses_prefixes else ""
        self.query_prefix = "search_query: " if uses_prefixes else ""

    def _embed(self, texts: List[str]) -> np.ndarray:
        matrix = np.array(embed_texts(texts), dtype="float32")
        faiss.normalize_L2(matrix)  # unit length, so inner product == cosine similarity
        return matrix

    def embed_documents(self, texts: List[str]) -> np.ndarray:
        return self._embed([self.document_prefix + t for t in texts])

    def embed_query(self, text: str) -> np.ndarray:
        return self._embed([self.query_prefix + text])


class LocalKnowledgeBase:
    """
    Sovereign, local document knowledge base using local embeddings + FAISS.
    """

    def __init__(
        self,
        dimension: int = EMBEDDING_DIM,
        index_dir: Optional[Path] = None,
        documents_dir: Optional[Path] = None,
        retrieval_mode: Optional[str] = None,
    ):
        self.retrieval_mode = (retrieval_mode or RETRIEVAL_MODE).lower()
        if self.retrieval_mode not in RETRIEVAL_MODES:
            raise ValueError(
                f"Unknown retrieval mode {self.retrieval_mode!r}; expected one of {RETRIEVAL_MODES}"
            )
        self.index_dir = Path(index_dir or INDEX_DIR)
        # bm25 needs no vectors; hybrid pairs BM25 with semantic vectors
        if self.retrieval_mode == "hashing":
            self.embedder = HashingEmbedder(dimension)
        elif self.retrieval_mode in ("semantic", "hybrid"):
            self.embedder = OllamaEmbedder()
        else:
            self.embedder = None
        self.uses_bm25 = self.retrieval_mode in ("bm25", "hybrid")
        self._bm25: Optional[BM25Okapi] = None
        # Created on the first add: the dimension comes from the embedding model
        self.index: Optional[faiss.Index] = None
        self.chunks: List[Dict[str, Any]] = []
        # filename -> {"chunks": count, "sha256": hash of the PDF bytes}
        self.indexed_files: Dict[str, Dict[str, Any]] = {}
        # FastAPI may run requests in parallel threads; index, chunks and
        # indexed_files must always change together.
        self._lock = threading.Lock()
        self._load_from_disk()
        self._auto_load_documents(Path(documents_dir or DOCUMENTS_DIR))

    def _load_from_disk(self):
        """Restores the knowledge base saved by _save_to_disk.

        Chunks are always restored. The saved vectors are reused only if they came
        from the same embedding model and line up with the chunks; otherwise the
        chunk texts are re-embedded, so uploaded PDFs survive a mode/model switch.
        """
        index_path = self.index_dir / INDEX_FILENAME
        meta_path = self.index_dir / META_FILENAME
        if not meta_path.exists():
            return

        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            chunks = meta["chunks"]
            indexed_files = meta["indexed_files"]
        except Exception:
            logger.exception("Could not read saved knowledge base in %s; rebuilding it.", self.index_dir)
            return

        self.chunks = chunks
        # Older saves stored just the chunk count; an unknown hash never counts as
        # unchanged, so the file is re-indexed once (and hashed) the next time it is ingested
        self.indexed_files = {
            name: info if isinstance(info, dict) else {"chunks": info, "sha256": None}
            for name, info in indexed_files.items()
        }
        if not self.chunks:
            return
        self._rebuild_bm25_locked()  # BM25 is not saved; it is rebuilt from the chunk texts

        if self.embedder is None:
            logger.info(
                "Loaded knowledge base from %s: %d documents, %d chunks (mode=%s)",
                self.index_dir, len(self.indexed_files), len(self.chunks), self.retrieval_mode,
            )
            return

        # Saves from before retrieval modes existed were always hashing-1024
        saved_model = meta.get("embed_model", f"hashing-{EMBEDDING_DIM}")
        index = None
        if saved_model == self.embedder.name and index_path.exists():
            try:
                index = faiss.read_index(str(index_path))
            except Exception:
                logger.exception("Could not read saved vectors in %s.", index_path)

        # chunk i must describe vector i, otherwise retrieval returns the wrong text
        if index is not None and index.ntotal == len(self.chunks):
            self.index = index
            logger.info(
                "Loaded knowledge base from %s: %d documents, %d chunks (mode=%s, vectors=%s)",
                self.index_dir, len(self.indexed_files), len(self.chunks),
                self.retrieval_mode, saved_model,
            )
            return

        # Re-embedding needs the current embedder (Ollama for semantic). If that
        # fails we let it raise: starting with an empty knowledge base and saving
        # over the old one would silently lose uploaded documents.
        logger.warning(
            "Saved vectors in %s do not match (saved %s mode=%s, now %s mode=%s); re-embedding %d chunks.",
            self.index_dir, saved_model, meta.get("retrieval_mode", "hashing"),
            self.embedder.name, self.retrieval_mode, len(self.chunks),
        )
        embeddings = self.embedder.embed_documents([c["text"] for c in self.chunks])
        self.index = faiss.IndexFlatIP(embeddings.shape[1])
        self.index.add(embeddings)
        with self._lock:
            self._save_to_disk()

    def _save_to_disk(self):
        """Writes index + metadata. Caller must hold self._lock."""
        self.index_dir.mkdir(parents=True, exist_ok=True)
        index_path = self.index_dir / INDEX_FILENAME
        meta_path = self.index_dir / META_FILENAME
        meta = {
            "retrieval_mode": self.retrieval_mode,
            "embed_model": self.embedder.name if self.embedder else None,
            "dimension": self.index.d if self.index is not None else None,
            "chunks": self.chunks,
            "indexed_files": self.indexed_files,
        }

        # Write to temp files, then rename: a crash mid-write cannot leave a half-written index
        tmp_meta = meta_path.with_suffix(".tmp")
        tmp_meta.write_text(json.dumps(meta), encoding="utf-8")
        if self.index is not None:
            tmp_index = index_path.with_suffix(".tmp")
            faiss.write_index(self.index, str(tmp_index))
            os.replace(tmp_index, index_path)
        os.replace(tmp_meta, meta_path)

    def _auto_load_documents(self, dir_path: Path):
        if not dir_path.is_dir():
            return
        for full_p in sorted(dir_path.iterdir()):
            fname = full_p.name
            # Already-indexed files go through ingest_pdf too: it skips them if the
            # SHA-256 is unchanged and replaces their chunks if the PDF was updated
            # (e.g. a regenerated sample doc), so a saved index never serves stale text.
            if not fname.lower().endswith(".pdf"):
                continue
            try:
                self.ingest_pdf(full_p.read_bytes(), fname)
            except Exception:
                # Log and keep going so one broken PDF does not block the others
                logger.exception("Failed to auto-ingest %s", full_p)


    def chunk_document_text(
        self,
        text: str,
        doc_name: str,
        page_number: int,
        chunk_size: int = 500,
        chunk_overlap: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Splits text into chunks preserving page and document metadata.
        """
        cleaned = text.strip()
        if not cleaned:
            return []

        paragraphs = [p.strip() for p in cleaned.split("\n\n") if p.strip()]

        # A paragraph longer than chunk_size becomes overlapping windows, so no
        # single chunk is oversized and text cut at a window edge appears in both.
        pieces = []
        step = chunk_size - chunk_overlap
        for p in paragraphs:
            if len(p) <= chunk_size:
                pieces.append(p)
                continue
            start = 0
            while True:
                pieces.append(p[start:start + chunk_size])
                if start + chunk_size >= len(p):
                    break
                start += step

        chunks = []
        current_chunk = ""
        for p in pieces:
            # +2 for the "\n\n" separator added when joining
            if not current_chunk or len(current_chunk) + 2 + len(p) <= chunk_size:
                # no .strip() here: it would trim the edges of windows and break the overlap
                current_chunk = f"{current_chunk}\n\n{p}" if current_chunk else p
            else:
                chunks.append({
                    "doc_name": doc_name,
                    "page_number": page_number,
                    "text": current_chunk,
                })
                current_chunk = p

        if current_chunk:
            chunks.append({
                "doc_name": doc_name,
                "page_number": page_number,
                "text": current_chunk,
            })

        return chunks

    def ingest_pdf(self, file_bytes: bytes, filename: str) -> Dict[str, Any]:
        """
        Extracts, chunks, and indexes a PDF document into the FAISS index.
        """
        if not file_bytes:
            raise ValueError(f"File {filename} is empty.")

        sha256 = hashlib.sha256(file_bytes).hexdigest()
        if self._is_unchanged(filename, sha256):
            return self._already_indexed(filename)

        doc = fitz.open(stream=file_bytes, filetype="pdf")
        try:
            total_pages = len(doc)
            new_chunks = []

            for page_num, page in enumerate(doc, start=1):
                text = page.get_text().strip()
                if text:
                    page_chunks = self.chunk_document_text(
                        text=text,
                        doc_name=filename,
                        page_number=page_num,
                    )
                    new_chunks.extend(page_chunks)
        finally:
            doc.close()

        if not new_chunks:
            return {
                "filename": filename,
                "pages": total_pages,
                "chunks_added": 0,
                "total_chunks": len(self.chunks),
                "message": "No selectable text was extracted from this PDF.",
            }

        # Embed outside the lock: for semantic mode this is a (slow) Ollama call
        embeddings = None
        if self.embedder is not None:
            embeddings = self.embedder.embed_documents([c["text"] for c in new_chunks])

        with self._lock:
            # Re-check: another thread may have ingested the same file meanwhile
            if self._is_unchanged(filename, sha256):
                return self._already_indexed(filename)

            # Same filename, different content: the new version replaces the old one
            replaced = filename in self.indexed_files
            if replaced:
                self._remove_file_locked(filename)

            start_idx = len(self.chunks)
            for i, c in enumerate(new_chunks):
                c["chunk_id"] = start_idx + i

            if embeddings is not None:
                if self.index is None:
                    self.index = faiss.IndexFlatIP(embeddings.shape[1])
                self.index.add(embeddings)
            self.chunks.extend(new_chunks)
            self._rebuild_bm25_locked()
            self.indexed_files[filename] = {"chunks": len(new_chunks), "sha256": sha256}
            self._save_to_disk()
            total_chunks = len(self.chunks)

        logger.info(
            "%s %s: pages=%d chunks=%d",
            "Replaced" if replaced else "Ingested", filename, total_pages, len(new_chunks),
        )

        return {
            "filename": filename,
            "pages": total_pages,
            "chunks_added": len(new_chunks),
            "total_chunks": total_chunks,
            "status": "replaced" if replaced else "completed",
        }

    def _is_unchanged(self, filename: str, sha256: str) -> bool:
        info = self.indexed_files.get(filename)
        return info is not None and info.get("sha256") == sha256

    def _remove_file_locked(self, filename: str):
        """Drops a file's vectors and chunks. Caller must hold self._lock."""
        ids = [i for i, c in enumerate(self.chunks) if c["doc_name"] == filename]
        # IndexFlat.remove_ids shifts the remaining vectors down but keeps their
        # order, so filtering self.chunks the same way keeps vector i == chunk i.
        if self.index is not None:
            self.index.remove_ids(np.array(ids, dtype="int64"))
        self.chunks = [c for c in self.chunks if c["doc_name"] != filename]
        for i, c in enumerate(self.chunks):
            c["chunk_id"] = i
        del self.indexed_files[filename]

    def _already_indexed(self, filename: str) -> Dict[str, Any]:
        return {
            "filename": filename,
            "chunks_added": 0,
            "total_chunks": len(self.chunks),
            "status": "already_indexed",
            "message": f"{filename} is already in the knowledge base; skipped.",
        }

    def _rebuild_bm25_locked(self):
        """Rebuilds the BM25 model from all chunk texts. Caller holds the lock (or is __init__)."""
        if self.uses_bm25:
            self._bm25 = BM25Okapi([tokenize(c["text"]) for c in self.chunks]) if self.chunks else None

    def _vector_ranking_locked(self, q_vec: np.ndarray, n: int) -> List[Tuple[int, float]]:
        """(chunk index, cosine similarity) for the top n chunks."""
        if self.index is None or not self.chunks:
            return []
        scores, indices = self.index.search(q_vec, min(n, len(self.chunks)))
        return [(int(i), float(sc)) for sc, i in zip(scores[0], indices[0]) if 0 <= i < len(self.chunks)]

    def _bm25_ranking_locked(self, query: str, n: int) -> List[Tuple[int, float]]:
        """(chunk index, BM25 score) for the top n chunks that share at least one term."""
        if self._bm25 is None:
            return []
        scores = self._bm25.get_scores(tokenize(query))
        order = np.argsort(scores)[::-1][:n]
        return [(int(i), float(scores[i])) for i in order if scores[i] > 0]

    def retrieve(
        self, query: str, top_k: int = RETRIEVAL_TOP_K, doc_names: Optional[Set[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieves the top_k most relevant chunks using the configured retrieval mode.

        Every returned chunk carries "score" (cosine, BM25 or RRF depending on the
        mode) plus "bm25_rank" and "vector_rank" (1-based, or None) to show why it
        was picked. With doc_names, only chunks of those documents are ranked
        (ranks are then within those documents).
        """
        if not query or not query.strip() or len(self.chunks) == 0:
            return []
        query = query.strip()
        mode = self.retrieval_mode

        # Embed outside the lock: in semantic modes this is an Ollama call
        q_vec = self.embedder.embed_query(query) if self.embedder is not None else None

        # One lock for all rankings so chunk indices cannot shift between them
        with self._lock:
            # When filtering, rank every chunk and then drop the other documents,
            # so the wanted chunks are not cut off by the candidate limit first.
            allowed = None
            if doc_names is not None:
                allowed = {i for i, c in enumerate(self.chunks) if c["doc_name"] in doc_names}

            def ranking(rank_fn, n):
                if allowed is None:
                    return rank_fn(n)
                return [(i, s) for i, s in rank_fn(len(self.chunks)) if i in allowed][:n]

            def bm25_ranking(n):
                return ranking(lambda m: self._bm25_ranking_locked(query, m), n)

            def vector_ranking(n):
                return ranking(lambda m: self._vector_ranking_locked(q_vec, m), n)

            if mode == "bm25":
                bm25 = bm25_ranking(top_k)
                vector: List[Tuple[int, float]] = []
                picked = bm25
            elif mode == "hybrid":
                bm25 = bm25_ranking(HYBRID_CANDIDATES)
                vector = vector_ranking(HYBRID_CANDIDATES)
                picked = rrf_merge([[i for i, _ in bm25], [i for i, _ in vector]])[:top_k]
            else:  # hashing / semantic
                bm25 = []
                vector = vector_ranking(top_k)
                picked = vector

            bm25_rank = {i: r for r, (i, _) in enumerate(bm25, start=1)}
            vector_rank = {i: r for r, (i, _) in enumerate(vector, start=1)}
            results = []
            for idx, score in picked:
                chunk = dict(self.chunks[idx])
                chunk["score"] = round(score, 4)
                chunk["bm25_rank"] = bm25_rank.get(idx)
                chunk["vector_rank"] = vector_rank.get(idx)
                chunk["retrieval_mode"] = mode
                results.append(chunk)

        logger.info(
            "Retrieved %d chunks (mode=%s) for query %r: %s",
            len(results), mode, query[:200],
            ", ".join(
                f"{c['doc_name']} p.{c['page_number']} score={c['score']} "
                f"bm25_rank={c['bm25_rank']} vector_rank={c['vector_rank']}"
                for c in results
            ),
        )
        return results

    def query(self, query: str, top_k: int = RETRIEVAL_TOP_K) -> Dict[str, Any]:
        """
        Retrieves context and asks local Ollama to synthesize an answer.
        """
        retrieved = self.retrieve(query, top_k=top_k)

        if not retrieved:
            return {
                "query": query,
                "response": "No relevant documents found in the local knowledge base. Please upload/ingest internal documents first.",
                "retrieved_chunks": [],
                "model": MODEL,
                "local": True,
                "external_calls": 0,
            }

        # Build grounded prompt
        context_blocks = []
        for i, chunk in enumerate(retrieved, start=1):
            context_blocks.append(
                f"[Source {i}: {chunk['doc_name']} | Page: {chunk['page_number']} | Relevance: {chunk['score']}]\n"
                f"{chunk['text']}"
            )

        context_str = "\n\n".join(context_blocks)

        prompt = f"""You are VAULTA, a sovereign industrial knowledge assistant.
Answer the user's question using ONLY the provided reference excerpts from internal SOPs and manuals.

RULES:
- Use only the provided context excerpts.
- Cite the source document name and page number for key facts and procedures.
- If the context does not contain enough information to answer, state that clearly.
- Do not invent facts or external procedures.
- Keep the response professional, structured, and concise.

USER QUESTION:
{query}

REFERENCE EXCERPTS FROM LOCAL KNOWLEDGE BASE:
{context_str}

Provide your grounded response:"""

        response = ask_local_ai(prompt)

        return {
            "query": query,
            "response": response,
            "retrieved_chunks": retrieved,
            "model": MODEL,
            "local": True,
            "external_calls": 0,
        }

    def get_status(self) -> Dict[str, Any]:
        return {
            "total_chunks": len(self.chunks),
            "indexed_documents": list(self.indexed_files.keys()),
            "documents_count": len(self.indexed_files),
            "index_dimension": self.index.d if self.index is not None else None,
            "faiss_total": self.index.ntotal if self.index is not None else 0,
            "retrieval_mode": self.retrieval_mode,
            "embed_model": self.embedder.name if self.embedder else None,
            "processor": {
                "hashing": "FAISS (IndexFlatIP) + HashingVectorizer",
                "bm25": "BM25 (rank_bm25)",
                "semantic": f"FAISS (IndexFlatIP) + {self.embedder.name if self.embedder else ''}",
                "hybrid": f"BM25 + FAISS ({self.embedder.name if self.embedder else ''}) with Reciprocal Rank Fusion",
            }[self.retrieval_mode],
        }


# Global singleton knowledge base instance
knowledge_base = LocalKnowledgeBase()
