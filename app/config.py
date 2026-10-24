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

LOG_LEVEL = os.getenv("VAULTA_LOG_LEVEL", "INFO").upper()

# app/config.py -> parent is app/, parent.parent is the repo root
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
DOCUMENTS_DIR = DATA_DIR / "documents"
SPREADSHEETS_DIR = DATA_DIR / "spreadsheets"
INDEX_DIR = DATA_DIR / "index"
