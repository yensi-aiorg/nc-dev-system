# tests/test_grounded_verify/test_judge.py
from ncdev.pipeline.grounded_verify.judge import parse_verdict


def test_parse_fenced_json():
    text = 'Here is my verdict:\n```json\n{"verdict": "PASS", "confidence": 0.9}\n```\n'
    v = parse_verdict(text)
    assert v is not None and v.verdict == "PASS" and v.confidence == 0.9


def test_parse_bare_object():
    text = 'reasoning... {"verdict": "FAIL", "reasons": ["real bug"]} done'
    v = parse_verdict(text)
    assert v is not None and v.verdict == "FAIL" and v.reasons == ["real bug"]


def test_parse_garbage_returns_none():
    assert parse_verdict("no json here") is None


def test_parse_invalid_schema_returns_none():
    assert parse_verdict('{"verdict": "MAYBE"}') is None
