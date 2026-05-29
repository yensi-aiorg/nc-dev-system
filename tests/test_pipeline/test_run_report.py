"""Tests for the structured run report (Phase 5 observability)."""
from __future__ import annotations

import json
from pathlib import Path

from ncdev.pipeline.models import PipelineRunState, StepResult, StepStatus
from ncdev.pipeline.run_report import build_run_report, write_run_report


def _state(**kw) -> PipelineRunState:
    base = dict(
        run_id="run-001", command="factory", status="passed",
        target_path="/tmp/app",
    )
    base.update(kw)
    return PipelineRunState(**base)


def _verdict_json(run_dir: Path, fid: str, *, verdict: str, reasons: list[str]):
    step = run_dir / "steps" / fid
    step.mkdir(parents=True, exist_ok=True)
    (step / "verdict.json").write_text(
        json.dumps({"verdict": verdict, "confidence": 0.9, "reasons": reasons}),
        encoding="utf-8",
    )


def test_report_counts_passed_and_failed(tmp_path: Path) -> None:
    state = _state()
    state.completed_steps = [
        StepResult(feature_id="f01", status=StepStatus.PASSED),
        StepResult(feature_id="f02", status=StepStatus.FAILED, error_message="boom"),
    ]
    report = build_run_report(state, tmp_path)
    assert report.passed_count == 1
    assert report.failed_count == 1


def test_report_surfaces_charter_assumptions(tmp_path: Path) -> None:
    state = _state()
    state.metadata["charter_assumptions"] = ["assumed single-tenant"]
    report = build_run_report(state, tmp_path)
    assert report.assumptions == ["assumed single-tenant"]
    assert "assumed single-tenant" in report.to_markdown()


def test_report_reads_verifier_blocking_failures(tmp_path: Path) -> None:
    state = _state()
    state.completed_steps = [
        StepResult(feature_id="f01", status=StepStatus.FAILED),
    ]
    _verdict_json(
        tmp_path, "f01", verdict="FAIL",
        reasons=["stubbed integration in production code"],
    )
    report = build_run_report(state, tmp_path)
    fr = report.features[0]
    assert fr.gauntlet_ran is True
    assert fr.gauntlet_passed is False
    assert any("stubbed integration" in b for b in fr.gauntlet_blocking)


def test_report_marks_verifier_not_run_when_absent(tmp_path: Path) -> None:
    state = _state()
    state.completed_steps = [StepResult(feature_id="f01", status=StepStatus.PASSED)]
    report = build_run_report(state, tmp_path)
    assert report.features[0].gauntlet_ran is False


def test_attention_items_lists_failures(tmp_path: Path) -> None:
    state = _state(status="partial")
    state.completed_steps = [
        StepResult(feature_id="f01", status=StepStatus.PASSED),
        StepResult(feature_id="f02", status=StepStatus.FAILED, error_message="oops"),
    ]
    report = build_run_report(state, tmp_path)
    attention = report.attention_items
    assert len(attention) == 1
    assert "f02" in attention[0] and "oops" in attention[0]


def test_report_reflects_integration_result(tmp_path: Path) -> None:
    state = _state()
    state.metadata["integration"] = {"passed": False, "failures": ["route /x 500"]}
    report = build_run_report(state, tmp_path)
    assert report.integration_passed is False
    assert report.integration_failures == ["route /x 500"]


def test_report_sums_feature_costs(tmp_path: Path) -> None:
    state = _state()
    s1 = StepResult(feature_id="f01", status=StepStatus.PASSED, cost_usd=2.5)
    s2 = StepResult(feature_id="f02", status=StepStatus.PASSED, cost_usd=1.5)
    state.completed_steps = [s1, s2]
    report = build_run_report(state, tmp_path)
    assert report.total_cost_usd == 4.0
    assert "$4.00" in report.to_markdown()
    assert report.to_dict()["total_cost_usd"] == 4.0


def test_write_run_report_persists_both_files(tmp_path: Path) -> None:
    state = _state()
    state.completed_steps = [StepResult(feature_id="f01", status=StepStatus.PASSED)]
    md_path = write_run_report(state, tmp_path)
    assert md_path.name == "report.md"
    assert md_path.exists()
    json_path = tmp_path / "report.json"
    assert json_path.exists()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["run_id"] == "run-001"
    assert data["passed"] == 1
