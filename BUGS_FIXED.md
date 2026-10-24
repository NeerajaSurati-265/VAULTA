# VAULTA — Bug Tracker (MVP hardening)

| ID | Description | Status | Files changed |
|----|-------------|--------|---------------|
| A1 | `requirements.txt` missing although README installs from it | Fixed | `requirements.txt`, `requirements-dev.txt` |
| A2 | Settings (URLs, model, timeouts, data paths) hard-coded across modules | Fixed | `app/config.py` (new), `app/main_services/ollama_service.py`, `app/main_services/report_generator.py`, `app/ui.py` |
| A3 | One-click demo file paths hard-coded to `/home/nsurati/VAULTA/...` | Fixed | `app/ui.py` |
| A4 | `backend_url`, `OLLAMA_URL`, `MODEL` hard-coded in UI / Ollama service | Fixed | `app/ui.py`, `app/main_services/ollama_service.py`, `app/main_services/report_generator.py` |
| A5 | README only starts Streamlit; FastAPI backend is never started | Fixed | `run.sh` (new) |
| A6 | README install/setup steps not in code blocks, diagram block never closed | Fixed | `README.md` |
| B1 | `/investigate` returns raw DOCX bytes in JSON → 500 | Fixed | `app/main_services/investigation_service.py` |
| B2 | Ollama `requests` exceptions bubble up as unhandled 500s | Fixed | `app/main_services/ollama_service.py`, `app/main.py` |
| B3 | `_auto_load_documents` swallows errors and uses a CWD-relative path | Fixed | `app/main_services/rag_service.py` |
| B4 | Re-ingesting the same PDF duplicates its chunks | Fixed | `app/main_services/rag_service.py` |
| B5 | Knowledge base is in-memory only; uploads lost on restart | Fixed | `app/main_services/rag_service.py`, `.gitignore` |
| B6 | Concurrent ingests can corrupt the index (no lock) | Fixed | `app/main_services/rag_service.py` |
| B7 | Long paragraphs not split; `chunk_overlap` unused; `fitz` doc not closed on error | Fixed | `app/main_services/rag_service.py`, `app/main_services/pdf_service.py` (same unclosed-`fitz` pattern) |
| B8 | `/agent/run` KNOWLEDGE_ANALYST retrieves twice | Fixed | `app/main.py` |
| B9 | Router can pick an agent that doesn't match the attached file type | Fixed | `app/main.py` |
| B10 | No logging of Ollama calls, retrieval, or ingestion | Fixed | `app/main.py`, `app/main_services/ollama_service.py`, `app/main_services/rag_service.py` |
| C1 | No automated tests | Fixed | `tests/` (new), `pytest.ini` (new), `requirements-dev.txt` (+`httpx`), `app/config.py` (`VAULTA_INDEX_DIR`) |
| C3 | Clean-install check (fresh venv, `pip install -r requirements-dev.txt`, run tests) | Open (in progress; PyPI downloads keep timing out on this network) | |
| D1 | UI HTTP timeouts (180–300 s) are shorter than the worst case backend time: `/agent/run` makes 2 Ollama calls of up to `OLLAMA_TIMEOUT` (300 s) each, so the UI can give up while the backend is still working | Fixed | `app/config.py` (`UI_REQUEST_TIMEOUT`), `app/ui.py` (`post_backend` helper) |
| D2 | UI status bar shows the *first* model Ollama lists, not the configured `VAULTA_MODEL` | Fixed | `app/ui.py` |
| D3 | `/investigate`, `/agent/run`, `/analyze-pdf` and `/knowledge/ingest` are `async def` but do blocking work (Ollama calls take ~60 s), so they block the event loop: while one investigation runs, every other request (including `/health` and the UI status bar) hangs | Fixed | `app/main.py` (`run_in_threadpool`) |
| D4 | UI uses `raise_for_status()`, so a backend 503 shows as `503 Server Error: Service Unavailable for url ...` instead of the backend's helpful `{"error": ...}` message | Fixed | `app/ui.py` (`post_backend` shows backend `error`/`detail`) |
| D5 | Because of B4 (skip by filename), uploading an *updated* PDF with the same filename is silently skipped, and there is no way to remove or replace a document; the UI also reports it as "Indexed (0 chunks added)" | Fixed | `app/main_services/rag_service.py` (SHA-256 per file; changed content replaces old chunks), `app/ui.py` |
| D6 | B7 chunk merge used `.strip()` on the joined text, trimming the edges of overlap windows (found by the new chunking test) | Fixed | `app/main_services/rag_service.py` |

## Upgrades

| ID | Description | Status | Files changed |
|----|-------------|--------|---------------|
| U1 | Retrieval eval: 5 synthetic docs (reproducible script), 40-question eval set (15 lexical / 15 paraphrase / 10 exact), `eval/run_eval.py`, hashing baseline (hit@3 55%) | Done | `scripts/make_sample_docs.py`, `data/documents/*.pdf` (5 new), `eval/questions.jsonl`, `eval/run_eval.py`, `eval/results/hashing.json`, `app/main_services/rag_service.py` (`retrieval_mode` param) |
| U2 | Local semantic embeddings via Ollama `/api/embed` (`nomic-embed-text`, task prefixes, batching, dimension from model, re-embed on model change). Eval hit@3 55% → 90% | Done | `app/config.py`, `app/main_services/ollama_service.py` (`embed_texts`, shared `_post_ollama`), `app/main_services/rag_service.py` (embedders, metadata), `run.sh`, `README.md`, `eval/run_eval.py`, `eval/results/semantic.json` |
| U3 | BM25 (`rank_bm25`, ID/number-preserving tokenizer) + hybrid retrieval (top-20 BM25 + top-20 vector, Reciprocal Rank Fusion k=60); chunks carry `bm25_rank`/`vector_rank`; default mode `hybrid` (hit@3 90%, MRR 0.792, hit@5 95%) | Done | `app/main_services/rag_service.py`, `app/config.py`, `requirements.txt`, `tests/conftest.py`, `README.md`, `eval/results/*.json` |
| U4 | Retrieval provenance (score, BM25 rank, vector rank) in KB tab, investigation evidence and execution traces; mode + embedding model in status bar, KB tab, Sovereignty tab and `/knowledge/status`; README "How retrieval works" + "Evaluation"; 6 new tests (tokenizer, RRF, bm25/semantic/hybrid with mocked embeddings, mode-switch rebuild) | Done | `app/ui.py`, `app/main.py`, `app/main_services/investigation_service.py`, `app/main_services/rag_service.py` (`describe_chunk`, `chunk_provenance`), `README.md`, `tests/test_retrieval.py` |
| U5 | `/agent/run` and `/investigate` hard-code `top_k=3`. For the demo prompts the SOP-PUMP-402 p.2 vibration-threshold page ranks 4th, so the answer says no vibration limits were found. The eval suggests top_k=5 (hit@5 95% vs hit@3 90%), but that changes how much context goes to the LLM | Open | |
| U6 | Hybrid (equal-weight RRF) is weaker than pure semantic on paraphrase questions (80% vs 93% hit@3): BM25 latches onto incidental shared words. Tune weights only on a larger, independent eval set | Open | |
| U7 | `SOP-PUMP-402.pdf` page 2 text is cut off mid-sentence ("immediately trip the e"); the source PDF itself overflows its text box | Open | |
