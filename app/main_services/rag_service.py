import os
import json
import logging
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional
import numpy as np
import faiss
import fitz
from sklearn.feature_extraction.text import HashingVectorizer

from app.config import DOCUMENTS_DIR, INDEX_DIR
from app.main_services.ollama_service import ask_local_ai, MODEL


logger = logging.getLogger(__name__)

EMBEDDING_DIM = 1024
INDEX_FILENAME = "knowledge.faiss"
META_FILENAME = "knowledge_meta.json"


class LocalKnowledgeBase:
    """
    Sovereign, local document knowledge base using deterministic local embeddings + FAISS.
    """

    def __init__(
        self,
        dimension: int = EMBEDDING_DIM,
        index_dir: Optional[Path] = None,
        documents_dir: Optional[Path] = None,
    ):
        self.dimension = dimension
        self.index_dir = Path(index_dir or INDEX_DIR)
        self.vectorizer = HashingVectorizer(
            n_features=dimension,
            norm="l2",
            ngram_range=(1, 2),
            alternate_sign=False,
        )
        self.index = faiss.IndexFlatIP(dimension)
        self.chunks: List[Dict[str, Any]] = []
        self.indexed_files: Dict[str, int] = {}  # filename -> chunk count
        # FastAPI may run requests in parallel threads; index, chunks and
        # indexed_files must always change together.
        self._lock = threading.Lock()
        self._load_from_disk()
        self._auto_load_documents(Path(documents_dir or DOCUMENTS_DIR))

    def _load_from_disk(self):
        """Restores the index saved by _save_to_disk, if it exists and is consistent."""
        index_path = self.index_dir / INDEX_FILENAME
        meta_path = self.index_dir / META_FILENAME
        if not (index_path.exists() and meta_path.exists()):
            return

        try:
            index = faiss.read_index(str(index_path))
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            chunks = meta["chunks"]
            indexed_files = meta["indexed_files"]
        except Exception:
            logger.exception("Could not read saved knowledge base in %s; rebuilding it.", self.index_dir)
            return

        # chunk i must describe vector i, otherwise retrieval returns the wrong text
        if index.d != self.dimension or index.ntotal != len(chunks):
            logger.warning(
                "Saved knowledge base in %s is inconsistent (dim %d vs %d, vectors %d vs chunks %d); rebuilding it.",
                self.index_dir, index.d, self.dimension, index.ntotal, len(chunks),
            )
            return

        self.index = index
        self.chunks = chunks
        self.indexed_files = indexed_files
        logger.info(
            "Loaded knowledge base from %s: %d documents, %d chunks",
            self.index_dir, len(self.indexed_files), len(self.chunks),
        )

    def _save_to_disk(self):
        """Writes index + metadata. Caller must hold self._lock."""
        self.index_dir.mkdir(parents=True, exist_ok=True)
        index_path = self.index_dir / INDEX_FILENAME
        meta_path = self.index_dir / META_FILENAME

        # Write to temp files, then rename: a crash mid-write cannot leave a half-written index
        tmp_index = index_path.with_suffix(".tmp")
        tmp_meta = meta_path.with_suffix(".tmp")
        faiss.write_index(self.index, str(tmp_index))
        tmp_meta.write_text(
            json.dumps({"chunks": self.chunks, "indexed_files": self.indexed_files}),
            encoding="utf-8",
        )
        os.replace(tmp_index, index_path)
        os.replace(tmp_meta, meta_path)

    def _auto_load_documents(self, dir_path: Path):
        if not dir_path.is_dir():
            return
        for full_p in sorted(dir_path.iterdir()):
            fname = full_p.name
            if not fname.lower().endswith(".pdf") or fname in self.indexed_files:
                continue
            try:
                self.ingest_pdf(full_p.read_bytes(), fname)
            except Exception:
                # Log and keep going so one broken PDF does not block the others
                logger.exception("Failed to auto-ingest %s", full_p)


    def _embed_texts(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dimension), dtype="float32")
        matrix = self.vectorizer.transform(texts).toarray().astype("float32")
        faiss.normalize_L2(matrix)
        return matrix

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
                current_chunk = f"{current_chunk}\n\n{p}".strip()
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

        if filename in self.indexed_files:
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

        texts_to_embed = [c["text"] for c in new_chunks]
        embeddings = self._embed_texts(texts_to_embed)

        with self._lock:
            # Re-check: another thread may have ingested the same file meanwhile
            if filename in self.indexed_files:
                return self._already_indexed(filename)

            start_idx = len(self.chunks)
            for i, c in enumerate(new_chunks):
                c["chunk_id"] = start_idx + i

            self.index.add(embeddings)
            self.chunks.extend(new_chunks)
            self.indexed_files[filename] = len(new_chunks)
            self._save_to_disk()
            total_chunks = len(self.chunks)

        logger.info("Ingested %s: pages=%d chunks=%d", filename, total_pages, len(new_chunks))

        return {
            "filename": filename,
            "pages": total_pages,
            "chunks_added": len(new_chunks),
            "total_chunks": total_chunks,
            "status": "completed",
        }

    def _already_indexed(self, filename: str) -> Dict[str, Any]:
        return {
            "filename": filename,
            "chunks_added": 0,
            "total_chunks": len(self.chunks),
            "status": "already_indexed",
            "message": f"{filename} is already in the knowledge base; skipped.",
        }

    def retrieve(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """
        Retrieves top_k most relevant chunks using FAISS cosine similarity.
        """
        if not query or not query.strip() or len(self.chunks) == 0:
            return []

        q_vec = self._embed_texts([query.strip()])

        # Searching while another thread adds vectors is not safe in FAISS
        with self._lock:
            k = min(top_k, len(self.chunks))
            scores, indices = self.index.search(q_vec, k)
            results = []

            for score, idx in zip(scores[0], indices[0]):
                if idx >= 0 and idx < len(self.chunks):
                    chunk = dict(self.chunks[idx])
                    chunk["score"] = round(float(score), 4)
                    results.append(chunk)

        logger.info(
            "Retrieved %d chunks for query %r: %s",
            len(results), query.strip()[:200],
            ", ".join(f"{c['doc_name']} p.{c['page_number']} score={c['score']}" for c in results),
        )
        return results

    def query(self, query: str, top_k: int = 3) -> Dict[str, Any]:
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
            "index_dimension": self.dimension,
            "faiss_total": self.index.ntotal,
            "processor": "FAISS (IndexFlatIP) + Local HashingVectorizer",
        }


# Global singleton knowledge base instance
knowledge_base = LocalKnowledgeBase()
