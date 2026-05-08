from ncdev.pipeline.metrics import compute_run_metrics
from ncdev.pipeline.models import FeatureQueueDoc, StepResult, StepStatus, PipelineRunState


def _make_result(fid: str, status: StepStatus, repairs: int = 0, build_s: float = 60, verify_s: float = 10) -> StepResult:
    return StepResult(
        feature_id=fid, status=status, build_duration_seconds=build_s,
        verify_duration_seconds=verify_s, repair_attempts=repairs,
        files_created=["a.py", "b.py"], files_modified=["c.py"],
    )


def test_all_pass_first_try():
    state = PipelineRunState(
        run_id="t1", started_at="2026-04-11T10:00:00+00:00", updated_at="2026-04-11T11:00:00+00:00",
        completed_steps=[_make_result("f1", StepStatus.PASSED), _make_result("f2", StepStatus.PASSED), _make_result("f3", StepStatus.PASSED)],
    )
    m = compute_run_metrics(state)
    assert m.first_pass_success_rate == 1.0
    assert m.repair_rate == 0.0
    assert m.passed_features == 3
    assert m.failed_features == 0
    assert all(f.passed_first_try for f in m.features)


def test_mixed_results():
    state = PipelineRunState(
        run_id="t2", started_at="2026-04-11T10:00:00+00:00", updated_at="2026-04-11T11:00:00+00:00",
        feature_queue=FeatureQueueDoc(project_name="test-proj"),
        completed_steps=[
            _make_result("f1", StepStatus.PASSED, 0),
            _make_result("f2", StepStatus.PASSED, 2),
            _make_result("f3", StepStatus.FAILED, 2),
            _make_result("f4", StepStatus.PASSED, 0),
        ],
    )
    m = compute_run_metrics(state)
    assert m.first_pass_success_rate == 0.5
    assert m.repair_rate == 0.5
    assert m.mean_repair_attempts == 2.0
    assert m.passed_features == 3
    assert m.failed_features == 1
    assert m.project_name == "test-proj"
    assert [f.passed_first_try for f in m.features] == [True, False, False, True]


def test_build_efficiency():
    state = PipelineRunState(
        run_id="t3", started_at="2026-04-11T10:00:00+00:00", updated_at="2026-04-11T11:00:00+00:00",
        completed_steps=[
            _make_result("f1", StepStatus.PASSED, 0, build_s=80, verify_s=20),
            _make_result("f2", StepStatus.PASSED, 0, build_s=120, verify_s=30),
        ],
    )
    m = compute_run_metrics(state)
    assert abs(m.build_efficiency - 0.8) < 0.01


def test_feature_metrics_populated():
    state = PipelineRunState(
        run_id="t4", started_at="2026-04-11T10:00:00+00:00", updated_at="2026-04-11T11:00:00+00:00",
        completed_steps=[_make_result("f1", StepStatus.PASSED, 0)],
    )
    m = compute_run_metrics(state)
    assert len(m.features) == 1
    assert m.features[0].feature_id == "f1"
    assert m.features[0].passed_first_try is True
    assert m.features[0].files_created == 2
    assert m.features[0].files_modified == 1


def test_empty_run():
    state = PipelineRunState(run_id="t5", started_at="2026-04-11T10:00:00+00:00")
    m = compute_run_metrics(state)
    assert m.first_pass_success_rate == 0.0
    assert m.total_features == 0
    assert m.features == []


def test_blocked_counted_as_failure_not_skipped():
    """Codex R3: BLOCKED must count against failed_features so metrics
    match the engine's overall-status determination."""
    state = PipelineRunState(
        run_id="rm1",
        started_at="2026-04-11T10:00:00+00:00",
        updated_at="2026-04-11T10:10:00+00:00",
        completed_steps=[
            _make_result("f1", StepStatus.PASSED),
            _make_result("f2", StepStatus.FAILED),
            _make_result("f3", StepStatus.BLOCKED),
            _make_result("f4", StepStatus.SKIPPED),
        ],
    )
    m = compute_run_metrics(state)
    assert m.total_features == 4
    assert m.passed_features == 1
    assert m.failed_features == 2      # FAILED + BLOCKED together
    assert m.blocked_features == 1     # tracked separately for detail
    assert m.skipped_features == 1


def test_ingestion_count_passed_through():
    state = PipelineRunState(
        run_id="t6", started_at="2026-04-11T10:00:00+00:00", updated_at="2026-04-11T10:30:00+00:00",
        completed_steps=[_make_result("f1", StepStatus.PASSED)],
        metadata={"citex_queries_by_codex": 7},
    )
    m = compute_run_metrics(state, ingestion_doc_count=12)
    assert m.citex_documents_ingested == 12
    assert m.citex_queries_by_codex == 7
