"""
Shared test setup. Runs before any test module imports `app`, so the global
knowledge base (built at import time) writes to a throwaway index directory
instead of data/index.
"""
import os
import tempfile
from pathlib import Path

os.environ["VAULTA_INDEX_DIR"] = tempfile.mkdtemp(prefix="vaulta-test-index-")

import pytest  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCUMENTS = REPO_ROOT / "data" / "documents"
SPREADSHEETS = REPO_ROOT / "data" / "spreadsheets"


@pytest.fixture
def make_kb(tmp_path):
    """Builds an empty knowledge base in tmp_path (no auto-loaded documents)."""
    from app.main_services.rag_service import LocalKnowledgeBase

    def _make(**kwargs):
        kwargs.setdefault("index_dir", tmp_path / "index")
        kwargs.setdefault("documents_dir", tmp_path / "no-documents")
        return LocalKnowledgeBase(**kwargs)

    return _make


@pytest.fixture
def fake_llm(monkeypatch):
    """Replaces every imported ask_local_ai with a canned answer (no Ollama needed)."""
    import app.main
    from app.agents import router
    from app.main_services import investigation_service, rag_service

    calls = []

    def _fake(prompt: str) -> str:
        calls.append(prompt)
        return "Mocked local AI answer."

    for module in (app.main, router, investigation_service, rag_service):
        monkeypatch.setattr(module, "ask_local_ai", _fake)
    return calls
