# tests/test_grounded_verify/test_models.py
from ncdev.pipeline.grounded_verify.models import (
    Verdict, EvidenceItem, EvidenceBundle, HardFloorResult,
)


def test_verdict_defaults_and_roundtrip():
    v = Verdict(verdict="PASS")
    assert v.confidence == 0.5
    assert v.reasons == [] and v.repair_guidance == []
    assert Verdict.model_validate_json(v.model_dump_json()).verdict == "PASS"


def test_verdict_rejects_unknown_verdict():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Verdict(verdict="MAYBE")


def test_evidence_bundle_holds_items_and_diff():
    b = EvidenceBundle(
        items=[EvidenceItem(name="backend-tests", command="pytest", exit_code=1,
                            output_tail="KeyError", scope="feature-tests")],
        diff="diff --git a b", changed_files=["backend/app/x.py"],
    )
    assert b.items[0].exit_code == 1
    assert b.changed_files == ["backend/app/x.py"]


def test_hard_floor_result():
    assert HardFloorResult(passed=True).reason == ""
    assert HardFloorResult(passed=False, reason="no work").reason == "no work"
