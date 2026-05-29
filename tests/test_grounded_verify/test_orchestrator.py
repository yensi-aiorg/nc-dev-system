# tests/test_grounded_verify/test_orchestrator.py
from pathlib import Path

from ncdev.pipeline.grounded_verify import grounded_verify
from ncdev.pipeline.grounded_verify.models import HardFloorResult, Verdict, EvidenceBundle


def test_hard_floor_fail_skips_agent(monkeypatch, tmp_path: Path):
    import ncdev.pipeline.grounded_verify as gv
    monkeypatch.setattr(gv, "check_hard_floor",
                        lambda *a, **k: HardFloorResult(passed=False, reason="no work produced"))
    called = {"judge": False}
    monkeypatch.setattr(gv, "judge",
                        lambda *a, **k: called.__setitem__("judge", True) or Verdict(verdict="PASS"))
    ver = grounded_verify(tmp_path, feature_id="f01", intent="x", pre_commit="OLD",
                          backend_test_cmd=None, frontend_test_cmd=None,
                          build_command=None, changed_files=[], diff="")
    assert ver.overall_passed is False
    assert ver.failure_reasons == ["no work produced"]
    assert called["judge"] is False        # invariant: agent never called below floor


def test_pass_verdict_maps_to_overall_passed(monkeypatch, tmp_path: Path):
    import ncdev.pipeline.grounded_verify as gv
    monkeypatch.setattr(gv, "check_hard_floor", lambda *a, **k: HardFloorResult(passed=True))
    monkeypatch.setattr(gv, "gather_evidence", lambda *a, **k: EvidenceBundle())
    monkeypatch.setattr(gv, "judge",
                        lambda *a, **k: Verdict(verdict="PASS", confidence=0.9))
    ver = grounded_verify(tmp_path, feature_id="f01", intent="x", pre_commit="OLD",
                          backend_test_cmd=None, frontend_test_cmd=None,
                          build_command=None, changed_files=[], diff="")
    assert ver.overall_passed is True
    assert ver.failure_reasons == []
