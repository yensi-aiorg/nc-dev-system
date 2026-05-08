from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from ncdev.pipeline.engine import run_pipeline
from ncdev.pipeline.models import (
    CharterBundle,
    FeatureQueueDoc,
    FeatureStep,
    StepResult,
    StepStatus,
    TargetProjectContract,
    VerificationContract,
)


def _bundle(*features: FeatureStep) -> CharterBundle:
    return CharterBundle(
        contract=TargetProjectContract(project_name="proj", project_type="web"),
        verification=VerificationContract(),
        feature_queue=FeatureQueueDoc(project_name="proj", features=list(features)),
    )


def test_run_pipeline_persists_brownfield_skips_in_progress_state(tmp_path: Path, monkeypatch):
    """State-scanner skips must show up immediately in persisted progress.

    Before this fix, completed_steps/completed_features stayed at zero when
    the scanner skipped features before the build loop ran, so a fully
    brownfield/no-op run reported no completed work in state.json.
    """
    workspace = tmp_path / "ws"
    workspace.mkdir()
    source = workspace / "prd.md"
    source.write_text("# PRD\n")
    target = workspace / "target"
    target.mkdir()

    feature = FeatureStep(
        feature_id="f1",
        title="Already done",
        description="",
        acceptance_criteria=[],
    )
    bundle = _bundle(feature)

    monkeypatch.setattr("ncdev.pipeline.engine.generate_charter", lambda **kwargs: (bundle, SimpleNamespace(summary=lambda: "ok")))
    monkeypatch.setattr("ncdev.pipeline.engine.run_design_phase", lambda **kwargs: SimpleNamespace(skipped=True, hard_failed=False, design_doc=None))
    monkeypatch.setattr("ncdev.pipeline.state_scanner.scan_completed_features", lambda target_path, features: ["f1"])
    monkeypatch.setattr(
        "ncdev.pipeline.state_scanner.build_skip_results",
        lambda features, done_ids: [StepResult(feature_id="f1", status=StepStatus.SKIPPED)],
    )

    state = run_pipeline(
        workspace=workspace,
        source_path=source,
        target_repo_path=target,
        builder_model="claude-opus-4-6",
    )

    assert state.status == "passed"
    assert state.completed_features == 1
    assert len(state.completed_steps) == 1
    assert state.completed_steps[0].status == StepStatus.SKIPPED


def _two_feature_bundle() -> CharterBundle:
    f1 = FeatureStep(
        feature_id="f1",
        title="First",
        description="",
        acceptance_criteria=["x"],
    )
    f2 = FeatureStep(
        feature_id="f2",
        title="Second",
        description="",
        acceptance_criteria=["x"],
        depends_on_features=["f1"],
    )
    return _bundle(f1, f2)


def test_halt_on_failed_default_stops_after_first_failed(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    source = workspace / "prd.md"
    source.write_text("# PRD")
    target = workspace / "target"
    target.mkdir()

    bundle = _two_feature_bundle()
    monkeypatch.setattr(
        "ncdev.pipeline.engine.generate_charter",
        lambda **kwargs: (bundle, SimpleNamespace(summary=lambda: "ok")),
    )
    monkeypatch.setattr(
        "ncdev.pipeline.engine.run_design_phase",
        lambda **kwargs: SimpleNamespace(skipped=True, hard_failed=False, design_doc=None),
    )
    monkeypatch.setattr(
        "ncdev.pipeline.state_scanner.scan_completed_features",
        lambda target_path, features: [],
    )

    call_log: list[str] = []

    def fake_executor(*, feature, **kwargs):  # noqa: ARG001
        call_log.append(feature.feature_id)
        if feature.feature_id == "f1":
            return StepResult(
                feature_id="f1",
                status=StepStatus.FAILED,
                verification=None,
            )
        return StepResult(feature_id=feature.feature_id, status=StepStatus.PASSED)

    monkeypatch.setattr("ncdev.pipeline.engine.execute_feature_claude_driven", fake_executor)

    state = run_pipeline(
        workspace=workspace,
        source_path=source,
        target_repo_path=target,
    )

    assert call_log == ["f1"], "f2 should NOT have been attempted after f1 FAILED"
    assert state.status == "failed"


def test_continue_on_failed_keeps_building(tmp_path: Path, monkeypatch):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    source = workspace / "prd.md"
    source.write_text("# PRD")
    target = workspace / "target"
    target.mkdir()

    bundle = _two_feature_bundle()
    # Make f2 not depend on f1 so it isn't BLOCKED — we want to test
    # that --continue-on-failed actually attempts the next feature.
    bundle.feature_queue.features[1].depends_on_features = []

    monkeypatch.setattr(
        "ncdev.pipeline.engine.generate_charter",
        lambda **kwargs: (bundle, SimpleNamespace(summary=lambda: "ok")),
    )
    monkeypatch.setattr(
        "ncdev.pipeline.engine.run_design_phase",
        lambda **kwargs: SimpleNamespace(skipped=True, hard_failed=False, design_doc=None),
    )
    monkeypatch.setattr(
        "ncdev.pipeline.state_scanner.scan_completed_features",
        lambda target_path, features: [],
    )

    call_log: list[str] = []

    def fake_executor(*, feature, **kwargs):  # noqa: ARG001
        call_log.append(feature.feature_id)
        if feature.feature_id == "f1":
            return StepResult(feature_id="f1", status=StepStatus.FAILED)
        return StepResult(feature_id=feature.feature_id, status=StepStatus.PASSED)

    monkeypatch.setattr("ncdev.pipeline.engine.execute_feature_claude_driven", fake_executor)

    state = run_pipeline(
        workspace=workspace,
        source_path=source,
        target_repo_path=target,
        halt_on_failed=False,
    )

    assert call_log == ["f1", "f2"]
    assert state.status == "partial"  # f1 failed, f2 passed


def test_verification_regression_when_blocked_dep_was_passed(tmp_path: Path, monkeypatch):
    """If f1 was reported PASSED but f2 ends up BLOCKED on f1, the
    verifier signed off on something that didn't deliver — surface as
    verification_regression, not partial."""
    workspace = tmp_path / "ws"
    workspace.mkdir()
    source = workspace / "prd.md"
    source.write_text("# PRD")
    target = workspace / "target"
    target.mkdir()

    bundle = _two_feature_bundle()

    monkeypatch.setattr(
        "ncdev.pipeline.engine.generate_charter",
        lambda **kwargs: (bundle, SimpleNamespace(summary=lambda: "ok")),
    )
    monkeypatch.setattr(
        "ncdev.pipeline.engine.run_design_phase",
        lambda **kwargs: SimpleNamespace(skipped=True, hard_failed=False, design_doc=None),
    )
    monkeypatch.setattr(
        "ncdev.pipeline.state_scanner.scan_completed_features",
        lambda target_path, features: [],
    )

    def fake_executor(*, feature, **kwargs):  # noqa: ARG001
        # f1 PASSED. We then synthesize the BLOCKED case for f2 by
        # passing in a fake _unmet_dependencies that returns ["f1"].
        return StepResult(feature_id="f1", status=StepStatus.PASSED)

    monkeypatch.setattr("ncdev.pipeline.engine.execute_feature_claude_driven", fake_executor)
    # Force f2 to be BLOCKED on f1 even though f1 PASSED — the
    # regression detector should catch this.
    monkeypatch.setattr("ncdev.pipeline.engine._unmet_dependencies",
                        lambda feature, completed: ["f1"] if feature.feature_id == "f2" else [])

    state = run_pipeline(
        workspace=workspace,
        source_path=source,
        target_repo_path=target,
        halt_on_failed=False,
    )

    assert state.status == "verification_regression"
    assert state.metadata.get("verification_regressions")
    assert any(
        "blocked on 'f1'" in r and "PASSED earlier" in r
        for r in state.metadata["verification_regressions"]
    )


def test_detect_verification_regressions_helper_returns_empty_when_none() -> None:
    from ncdev.pipeline.engine import _detect_verification_regressions

    completed = [
        StepResult(feature_id="f1", status=StepStatus.PASSED),
        StepResult(feature_id="f2", status=StepStatus.PASSED),
    ]
    assert _detect_verification_regressions(completed) == []


def test_detect_verification_regressions_helper_ignores_blocked_with_failed_dep() -> None:
    """A BLOCKED feature whose dep FAILED is the expected cascading
    failure, not a verification regression — don't flag it."""
    from ncdev.pipeline.engine import _detect_verification_regressions

    completed = [
        StepResult(feature_id="f1", status=StepStatus.FAILED),
        StepResult(
            feature_id="f2",
            status=StepStatus.BLOCKED,
            error_message="dependency not satisfied: f1 (required feature(s) are not in PASSED state)",
        ),
    ]
    assert _detect_verification_regressions(completed) == []
