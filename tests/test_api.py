from fastapi.testclient import TestClient

import app.main
from app.main_services import ollama_service
from tests.conftest import DOCUMENTS, SPREADSHEETS

client = TestClient(app.main.app)


def test_investigate_returns_json_with_demo_files(fake_llm):
    """Regression test for B1: raw DOCX bytes in the response caused a 500."""
    with open(DOCUMENTS / "pump_inspection.pdf", "rb") as insp, \
         open(SPREADSHEETS / "maintenance_metrics.csv", "rb") as data, \
         open(DOCUMENTS / "SOP-PUMP-402.pdf", "rb") as sop:
        resp = client.post(
            "/investigate",
            data={"prompt": "Investigate vibration on Pump P-402"},
            files={
                "inspection_file": ("pump_inspection.pdf", insp, "application/pdf"),
                "data_file": ("maintenance_metrics.csv", data, "text/csv"),
                "sop_file": ("SOP-PUMP-402.pdf", sop, "application/pdf"),
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["response"] == "Mocked local AI answer."
    assert "docx_bytes" not in body
    stages = [t["stage"] for t in body["execution_trace"]]
    assert "APPROVAL_NOTE_GENERATION" in stages


def test_chat_returns_503_with_help_when_ollama_is_down(monkeypatch):
    """B2: an unreachable Ollama must give a clear 503, not an unhandled 500."""
    monkeypatch.setattr(ollama_service, "OLLAMA_URL", "http://127.0.0.1:1")
    resp = client.post("/chat", json={"prompt": "hello"})

    assert resp.status_code == 503
    assert "ollama serve" in resp.json()["error"]


def test_route_is_corrected_to_match_attached_csv(fake_llm, monkeypatch):
    """B9: a CSV must go to DATA_ANALYST even if the LLM router says otherwise."""
    monkeypatch.setattr(
        app.main.TaskRouter, "route",
        staticmethod(lambda **kw: {"route": "DOC_ANALYST", "confidence": 0.9, "reason": "LLM guess."}),
    )
    with open(SPREADSHEETS / "maintenance_metrics.csv", "rb") as f:
        resp = client.post(
            "/agent/run",
            data={"prompt": "Summarize this report"},
            files={"file": ("maintenance_metrics.csv", f, "text/csv")},
        )

    body = resp.json()
    assert body["route"] == "DATA_ANALYST"
    assert "corrected from DOC_ANALYST to DATA_ANALYST" in body["reason"]
    assert body["rows"] > 0
