"""Run-level build metrics for the V3 pipeline."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from ncdev.v3.models import StepStatus, V3RunState


class FeatureMetric(BaseModel):
    """Per-feature effectiveness metrics."""

    feature_id: str
    status: str
    passed_first_try: bool
    repair_attempts: int = 0
    build_duration_seconds: float = 0.0
    verify_duration_seconds: float = 0.0
    files_created: int = 0
    files_modified: int = 0


class RunMetrics(BaseModel):
    """Aggregate metrics for one V3 run."""

    run_id: str
    project_name: str = ""
    started_at: str = ""
    completed_at: str = ""
    total_duration_seconds: float = 0.0
    total_features: int = 0
    passed_features: int = 0          # built successfully this run
    failed_features: int = 0          # tried and broke OR dep-blocked
    skipped_features: int = 0         # brownfield — already implemented
    blocked_features: int = 0         # broken dep cascaded here
    first_pass_success_rate: float = 0.0
    repair_rate: float = 0.0
    mean_repair_attempts: float = 0.0
    build_efficiency: float = 0.0
    feature_throughput_per_hour: float = 0.0
    features: list[FeatureMetric] = Field(default_factory=list)
    builder_primary: str = "codex"
    builder_model: str = "gpt-5.4"
    citex_documents_ingested: int = 0
    citex_queries_by_codex: int = 0


def compute_run_metrics(
    state: V3RunState,
    ingestion_doc_count: int = 0,
) -> RunMetrics:
    """Compute aggregate run metrics from the current V3 run state."""
    steps = state.completed_steps
    total = len(steps)

    if total == 0:
        return RunMetrics(run_id=state.run_id, started_at=state.started_at)

    passed = [s for s in steps if s.status == StepStatus.PASSED]
    # Both FAILED (tried and broke) and BLOCKED (upstream dep broke)
    # are failures at the run-metric level — they count against
    # failed_features so the number matches the engine's "unsuccessful"
    # run status. blocked_features is tracked separately for detail.
    failed_direct = [s for s in steps if s.status == StepStatus.FAILED]
    blocked = [s for s in steps if s.status == StepStatus.BLOCKED]
    failed = failed_direct + blocked
    skipped = [s for s in steps if s.status == StepStatus.SKIPPED]
    first_pass = [s for s in passed if s.repair_attempts == 0]
    repaired = [s for s in steps if s.repair_attempts > 0]

    build_sum = sum(s.build_duration_seconds for s in steps)
    verify_sum = sum(s.verify_duration_seconds for s in steps)
    total_active_time = build_sum + verify_sum

    started = _parse_iso(state.started_at)
    completed_at = state.updated_at or state.started_at
    completed = _parse_iso(completed_at)
    total_duration_seconds = max((completed - started).total_seconds(), 0.0)

    feature_metrics = [
        FeatureMetric(
            feature_id=s.feature_id,
            status=s.status.value,
            passed_first_try=(s.status == StepStatus.PASSED and s.repair_attempts == 0),
            repair_attempts=s.repair_attempts,
            build_duration_seconds=s.build_duration_seconds,
            verify_duration_seconds=s.verify_duration_seconds,
            files_created=len(s.files_created),
            files_modified=len(s.files_modified),
        )
        for s in steps
    ]

    return RunMetrics(
        run_id=state.run_id,
        project_name=_resolve_project_name(state),
        started_at=state.started_at,
        completed_at=completed_at,
        total_duration_seconds=total_duration_seconds,
        total_features=total,
        passed_features=len(passed),
        failed_features=len(failed),
        skipped_features=len(skipped),
        blocked_features=len(blocked),
        first_pass_success_rate=len(first_pass) / total,
        repair_rate=len(repaired) / total,
        mean_repair_attempts=(
            sum(s.repair_attempts for s in repaired) / len(repaired)
            if repaired else 0.0
        ),
        build_efficiency=build_sum / total_active_time if total_active_time > 0 else 0.0,
        feature_throughput_per_hour=(
            len(passed) / (total_duration_seconds / 3600.0) if total_duration_seconds > 0 else 0.0
        ),
        features=feature_metrics,
        citex_documents_ingested=ingestion_doc_count,
        citex_queries_by_codex=int(state.metadata.get("citex_queries_by_codex", 0)),
    )


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _resolve_project_name(state: V3RunState) -> str:
    if state.feature_queue and state.feature_queue.project_name:
        return state.feature_queue.project_name
    return str(state.metadata.get("project_id", "")) or "unknown"
