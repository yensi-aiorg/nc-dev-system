import json
from pathlib import Path

import pytest

from ncdev.pipeline.grounded_verify.judge import build_prompt, judge
from ncdev.pipeline.grounded_verify.models import EvidenceBundle, EvidenceItem

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
    ("f05_venv_bandit.json", "PASS"),    # dep-only bandit finding, clean changed files
    ("genuine_keyerror.json", "FAIL"),   # real failing integration test (assertions ran)
])
def test_real_judge_rulings(tmp_path, fixture, expected):
    # Sound with an empty target_path: f05's evidence is a clean diff-scoped scan;
    # genuine's is a real assertion failure. Neither hinges on the judge finding
    # code on disk.
    v = judge("f08", "feature intent", _bundle(fixture),
              prior_context="", target_path=tmp_path)
    assert v.verdict == expected, v.reasons


@pytest.mark.llm
def test_real_judge_passes_harness_noise_when_work_is_real(tmp_path):
    """The original incident: the test command hit a shell `cd` error (harness
    noise) while the real implementation WAS on disk. The verifier must
    investigate the working tree, find the working code, and PASS — not
    rubber-stamp the exit code (old Gauntlet bug) and not blind-FAIL.

    Unlike the thin fixture (empty repo), this materializes real work in
    target_path so the judge's grounding tools have something true to find.
    """
    api = tmp_path / "backend" / "app" / "api"
    api.mkdir(parents=True)
    (tmp_path / "backend" / "app" / "__init__.py").write_text("")
    (api / "__init__.py").write_text("")
    (api / "tracker.py").write_text(
        "def ingest(items):\n"
        '    """Ingest tracker entries for conflicts/obligations."""\n'
        "    if not isinstance(items, list):\n"
        "        raise ValueError('items must be a list')\n"
        "    return {'ingested': len(items), 'items': items}\n"
    )
    tests = tmp_path / "backend" / "tests"
    tests.mkdir(parents=True)
    (tests / "test_tracker.py").write_text(
        "from app.api.tracker import ingest\n\n"
        "def test_ingest_returns_items():\n"
        "    assert ingest([{'id': 1}]) == {'ingested': 1, 'items': [{'id': 1}]}\n"
    )
    diff = (
        "diff --git a/backend/app/api/tracker.py b/backend/app/api/tracker.py\n"
        "new file mode 100644\n"
        "+def ingest(items):\n"
        "+    if not isinstance(items, list):\n"
        "+        raise ValueError('items must be a list')\n"
        "+    return {'ingested': len(items), 'items': items}\n"
    )
    bundle = EvidenceBundle(
        items=[EvidenceItem(
            name="backend-tests", command="cd backend && pytest",
            exit_code=1,
            output_tail="/usr/bin/cd: line 4: cd: backend: No such file or directory",
            scope="feature-tests",
        )],
        diff=diff,
        changed_files=["backend/app/api/tracker.py", "backend/tests/test_tracker.py"],
        screenshots=[],
    )
    v = judge("f08", "Build a tracker ingest API for conflicts/obligations",
              bundle, prior_context="", target_path=tmp_path)
    assert v.verdict == "PASS", v.reasons
