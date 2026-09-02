import os
import io
import json
from typing import List, Dict, Any, Optional
import numpy as np
import faiss
import fitz
from sklearn.feature_extraction.text import HashingVectorizer

from app.main_services.ollama_service import ask_local_ai, MODEL


EMBEDDING_DIM = 1024


class LocalKnowledgeBase:
    """
    Sovereign, local document knowledge base using deterministic local embeddings + FAISS.
    """

    def __init__(self, dimension: int = EMBEDDING_DIM):
        self.dimension = dimension
        self.vectorizer = HashingVectorizer(
            n_features=dimension,
            norm="l2",
            ngram_range=(1, 2),
            alternate_sign=False,
        )
        self.index = faiss.IndexFlatIP(dimension)
        self.chunks: List[Dict[str, Any]] = []
        self.indexed_files: Dict[str, int] = {}  # filename -> chunk count
        self._auto_load_documents()

    def _auto_load_documents(self, dir_path: str = "data/documents"):
        if os.path.exists(dir_path) and os.path.isdir(dir_path):
            for fname in sorted(os.listdir(dir_path)):
                if fname.lower().endswith(".pdf"):
                    full_p = os.path.join(dir_path, fname)
                    try:
                        with open(full_p, "rb") as f:
                            self.ingest_pdf(f.read(), fname)
                    except Exception:
                        pass


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

        chunks = []
        # Split by paragraphs or sliding window
        paragraphs = [p.strip() for p in cleaned.split("\n\n") if p.strip()]

        current_chunk = ""
        for p in paragraphs:
            if len(current_chunk) + len(p) <= chunk_size:
                current_chunk = f"{current_chunk}\n\n{p}".strip()
            else:
                if current_chunk:
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

        # Fallback to simple windowing if paragraph split resulted in nothing
        if not chunks and len(cleaned) > 0:
            start = 0
            while start < len(cleaned):
                end = min(start + chunk_size, len(cleaned))
                chunks.append({
                    "doc_name": doc_name,
                    "page_number": page_number,
                    "text": cleaned[start:end],
                })
                start += chunk_size - chunk_overlap

        return chunks

    def ingest_pdf(self, file_bytes: bytes, filename: str) -> Dict[str, Any]:
        """
        Extracts, chunks, and indexes a PDF document into the FAISS index.
        """
        if not file_bytes:
            raise ValueError(f"File {filename} is empty.")

        doc = fitz.open(stream=file_bytes, filetype="pdf")
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

        start_idx = len(self.chunks)
        for i, c in enumerate(new_chunks):
            c["chunk_id"] = start_idx + i

        self.index.add(embeddings)
        self.chunks.extend(new_chunks)
        self.indexed_files[filename] = self.indexed_files.get(filename, 0) + len(new_chunks)

        return {
            "filename": filename,
            "pages": total_pages,
            "chunks_added": len(new_chunks),
            "total_chunks": len(self.chunks),
            "status": "completed",
        }

    def retrieve(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """
        Retrieves top_k most relevant chunks using FAISS cosine similarity.
        """
        if not query or not query.strip() or len(self.chunks) == 0:
            return []

        q_vec = self._embed_texts([query.strip()])
        k = min(top_k, len(self.chunks))

        scores, indices = self.index.search(q_vec, k)
        results = []

        for score, idx in zip(scores[0], indices[0]):
            if idx >= 0 and idx < len(self.chunks):
                chunk = dict(self.chunks[idx])
                chunk["score"] = round(float(score), 4)
                results.append(chunk)

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
