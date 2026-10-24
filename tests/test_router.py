import pytest

from app.agents.router import _parse_router_response


def test_plain_json():
    out = _parse_router_response('{"route": "DATA_ANALYST", "confidence": 0.9, "reason": "CSV"}')
    assert out == {"route": "DATA_ANALYST", "confidence": 0.9, "reason": "CSV"}


def test_json_inside_code_fences():
    raw = '```json\n{"route": "knowledge_analyst", "confidence": 1.7, "reason": "SOP question"}\n```'
    out = _parse_router_response(raw)
    assert out["route"] == "KNOWLEDGE_ANALYST"
    assert out["confidence"] == 1.0  # clamped


@pytest.mark.parametrize("raw", ["", "I think this is a data question.", '{"route": "MAGIC"}'])
def test_invalid_text_raises(raw):
    with pytest.raises(ValueError):
        _parse_router_response(raw)
