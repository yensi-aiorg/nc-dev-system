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

