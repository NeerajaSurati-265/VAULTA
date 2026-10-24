# VAULTA — Bug Tracker (MVP hardening)

| ID | Description | Status | Files changed |
|----|-------------|--------|---------------|
| A1 | `requirements.txt` missing although README installs from it | Fixed | `requirements.txt`, `requirements-dev.txt` |
| A2 | Settings (URLs, model, timeouts, data paths) hard-coded across modules | Fixed | `app/config.py` (new), `app/main_services/ollama_service.py`, `app/main_services/report_generator.py`, `app/ui.py` |
| A3 | One-click demo file paths hard-coded to `/home/nsurati/VAULTA/...` | Fixed | `app/ui.py` |
| A4 | `backend_url`, `OLLAMA_URL`, `MODEL` hard-coded in UI / Ollama service | Fixed | `app/ui.py`, `app/main_services/ollama_service.py`, `app/main_services/report_generator.py` |
| A5 | README only starts Streamlit; FastAPI backend is never started | Fixed | `run.sh` (new) |
| A6 | README install/setup steps not in code blocks, diagram block never closed | Fixed | `README.md` |
| B1 | `/investigate` returns raw DOCX bytes in JSON → 500 | Open | |
| B2 | Ollama `requests` exceptions bubble up as unhandled 500s | Open | |
| B3 | `_auto_load_documents` swallows errors and uses a CWD-relative path | Open | |
| B4 | Re-ingesting the same PDF duplicates its chunks | Open | |
| B5 | Knowledge base is in-memory only; uploads lost on restart | Open | |
| B6 | Concurrent ingests can corrupt the index (no lock) | Open | |
| B7 | Long paragraphs not split; `chunk_overlap` unused; `fitz` doc not closed on error | Open | |
| B8 | `/agent/run` KNOWLEDGE_ANALYST retrieves twice | Open | |
| B9 | Router can pick an agent that doesn't match the attached file type | Open | |
| B10 | No logging of Ollama calls, retrieval, or ingestion | Open | |
| C1 | No automated tests | Open | |
| D1 | UI HTTP timeouts (180–300 s) are shorter than the worst case backend time: `/agent/run` makes 2 Ollama calls of up to `OLLAMA_TIMEOUT` (300 s) each, so the UI can give up while the backend is still working | Open | |
| D2 | UI status bar shows the *first* model Ollama lists, not the configured `VAULTA_MODEL` | Open | |
