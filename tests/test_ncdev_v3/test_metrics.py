from ncdev.v3.metrics import compute_run_metrics, FeatureMetric, RunMetrics
from ncdev.v3.models import StepResult, StepStatus, StepVerification, TestResult, V3RunState


def _make_result(feature_id: str, status: StepStatus, repair_attempts: int = 0, build_s: float = 60, verify_s: float = 10) -> StepResult:
    return StepResult(
        feature_id=feature_id,
        status=status,
        build_duration_seconds=build_s,
        verify_duration_seconds=verify_s,
        repair_attempts=repair_attempts,
        files_created=["a.py", "b.py"],
        files_modified=["c.py"],
    )


def test_first_pass_success_rate_all_pass():
    state = V3RunState(run_id="test-1", total_features=3, completed_features=3)
    state.completed_steps = [
        _make_result("f1", StepStatus.PASSED, 0),
        _make_result("f2", StepStatus.PASSED, 0),
        _make_result("f3", StepStatus.PASSED, 0),
    ]
    metrics = compute_run_metrics(state)
    assert metrics.first_pass_success_rate == 1.0
    assert metrics.repair_rate == 0.0
    assert metrics.passed_features == 3
    assert metrics.failed_features == 0


def test_first_pass_success_rate_mixed():
    state = V3RunState(run_id="test-2", total_features=4, completed_features=4)
    state.completed_steps = [
        _make_result("f1", StepStatus.PASSED, 0),
        _make_result("f2", StepStatus.PASSED, 2),  # passed after repair
        _make_result("f3", StepStatus.FAILED, 2),
        _make_result("f4", StepStatus.PASSED, 0),
    ]
    metrics = compute_run_metrics(state)
    assert metrics.first_pass_success_rate == 0.5  # 2 out of 4 first-pass
    assert metrics.repair_rate == 0.5  # 2 out of 4 needed repair
    assert metrics.mean_repair_attempts == 2.0
    assert metrics.passed_features == 3
    assert metrics.failed_features == 1


def test_build_efficiency():
    state = V3RunState(run_id="test-3", total_features=2, completed_features=2)
    state.completed_steps = [
        _make_result("f1", StepStatus.PASSED, 0, build_s=80, verify_s=20),
        _make_result("f2", StepStatus.PASSED, 0, build_s=120, verify_s=30),
    ]
    metrics = compute_run_metrics(state)
    # build_efficiency = 200 / 250 = 0.8
    assert abs(metrics.build_efficiency - 0.8) < 0.01


def test_feature_metrics_populated():
    state = V3RunState(run_id="test-4", total_features=1, completed_features=1)
    state.completed_steps = [_make_result("f1", StepStatus.PASSED, 0)]
    metrics = compute_run_metrics(state)
    assert len(metrics.features) == 1
    assert metrics.features[0].feature_id == "f1"
    assert metrics.features[0].first_pass is True
    assert metrics.features[0].files_created == 2
    assert metrics.features[0].files_modified == 1


def test_empty_run():
    state = V3RunState(run_id="test-5", total_features=0, completed_features=0)
    metrics = compute_run_metrics(state)
    assert metrics.first_pass_success_rate == 0.0
    assert metrics.total_features == 0
    assert metrics.features == []
