"""
Central configuration for VAULTA.

Every setting can be overridden with an environment variable, so the app runs
on any machine without editing code. Data paths are built from the repo root
(not the current working directory), so it does not matter where you start
the backend or the UI from.
"""
import os
from pathlib import Path

# Local LLM (Ollama)
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
MODEL = os.getenv("VAULTA_MODEL", "qwen2.5:3b")
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "300"))

# FastAPI backend, as seen from the Streamlit UI
BACKEND_URL = os.getenv("VAULTA_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
# How long the UI waits for the backend. /agent/run can make two Ollama calls
# (router + answer) of up to OLLAMA_TIMEOUT each, plus some slack.
UI_REQUEST_TIMEOUT = float(os.getenv("VAULTA_UI_REQUEST_TIMEOUT", str(2 * OLLAMA_TIMEOUT + 30)))

LOG_LEVEL = os.getenv("VAULTA_LOG_LEVEL", "INFO").upper()

# app/config.py -> parent is app/, parent.parent is the repo root
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
DOCUMENTS_DIR = DATA_DIR / "documents"
SPREADSHEETS_DIR = DATA_DIR / "spreadsheets"
# Overridable so tests and the eval can use a throwaway index
INDEX_DIR = Path(os.getenv("VAULTA_INDEX_DIR", str(DATA_DIR / "index")))
