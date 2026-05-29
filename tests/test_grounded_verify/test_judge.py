# tests/test_grounded_verify/test_judge.py
from pathlib import Path
from dataclasses import dataclass

from ncdev.pipeline.grounded_verify.judge import parse_verdict, judge, build_prompt, VERIFIER_TOOLS
from ncdev.pipeline.grounded_verify.models import EvidenceBundle, EvidenceItem


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


@dataclass
class FakeSession:
    final_text: str
    total_cost_usd: float = 0.01
    success: bool = True


def _bundle():
    return EvidenceBundle(items=[EvidenceItem(name="backend-tests", exit_code=1,
                                              output_tail="cd: backend: No such file")],
                          diff="d", changed_files=["backend/app/x.py"])


def test_build_prompt_includes_rules_and_evidence():
    p = build_prompt("f08", "Build conflicts API", _bundle(), prior_context="")
    assert "harness" in p.lower() or "environmental" in p.lower()
    assert "intent" in p.lower()
    assert "backend-tests" in p


def test_judge_returns_parsed_verdict(tmp_path: Path):
    runner = lambda *a, **k: FakeSession('```json\n{"verdict":"PASS","confidence":0.8}\n```')
    v = judge("f08", "intent", _bundle(), prior_context="", target_path=tmp_path,
              session_runner=runner)
    assert v.verdict == "PASS"


def test_judge_retries_then_fails_safe(tmp_path: Path):
    calls = {"n": 0}

    def runner(*a, **k):
        calls["n"] += 1
        return FakeSession("no json at all")

    v = judge("f08", "intent", _bundle(), prior_context="", target_path=tmp_path,
              session_runner=runner)
    assert calls["n"] == 2          # one retry
    assert v.verdict == "FAIL"      # conservative fail-safe
    assert any("could not" in r.lower() or "parse" in r.lower() for r in v.reasons)


# --- Fix #1: verifier must not mutate the code it judges ---

def test_judge_uses_read_only_tools_and_default_permission(tmp_path: Path):
    """judge() must pass VERIFIER_TOOLS (no Write/Edit) and permission_mode='default'."""
    captured: dict = {}

    def capturing_runner(*a, **k):
        captured.update(k)
        return FakeSession('```json\n{"verdict":"PASS","confidence":0.9}\n```')

    judge("f99", "intent", _bundle(), prior_context="", target_path=tmp_path,
          session_runner=capturing_runner)

    assert "Write" not in captured["tools"]
    assert "Edit" not in captured["tools"]
    assert captured["permission_mode"] == "default"


# --- Fix #2: robust verdict extraction ---

def test_parse_fenced_after_decoy_bare_object():
    """A decoy bare object before a fenced block must not prevent extraction."""
    text = 'noise {"foo": 1} then ```json\n{"verdict":"FAIL","reasons":["x"]}\n```'
    v = parse_verdict(text)
    assert v is not None and v.verdict == "FAIL"


def test_parse_second_bare_object_wins_when_first_invalid():
    """When first bare block is invalid, the second valid one is returned."""
    text = 'prefix {"unrelated": true} {"verdict": "PASS"}'
    v = parse_verdict(text)
    assert v is not None and v.verdict == "PASS"
