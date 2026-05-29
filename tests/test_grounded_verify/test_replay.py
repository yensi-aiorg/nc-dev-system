import json
from pathlib import Path

import pytest

from ncdev.pipeline.grounded_verify.judge import build_prompt, judge
from ncdev.pipeline.grounded_verify.models import EvidenceBundle

FIX = Path(__file__).parent / "fixtures"


def _bundle(name: str) -> EvidenceBundle:
    return EvidenceBundle.model_validate_json((FIX / name).read_text())


def test_cd_error_signal_present_in_prompt():
    # The harness/env-noise signal must reach the agent so it CAN exonerate.
    p = build_prompt("f08", "Build tracker ingest API", _bundle("f08_cd_error.json"),
                     prior_context="")
    assert "No such file or directory" in p
    assert "harness" in p.lower() or "environmental" in p.lower()


def test_genuine_failure_signal_present_in_prompt():
    p = build_prompt("f08", "Resolve stale tracker entries",
                     _bundle("genuine_keyerror.json"), prior_context="")
    assert "KeyError: 'items'" in p


@pytest.mark.llm
@pytest.mark.parametrize("fixture,expected", [
    ("f08_cd_error.json", "PASS"),       # cd error = harness noise, work is fine
    ("f05_venv_bandit.json", "PASS"),    # dep-only finding, clean changed files
    ("genuine_keyerror.json", "FAIL"),   # real failing integration test
])
def test_real_judge_rulings(tmp_path, fixture, expected):
    v = judge("f08", "feature intent", _bundle(fixture),
              prior_context="", target_path=tmp_path)
    assert v.verdict == expected
