"""Build metrics — tracks feature effectiveness and first-pass success rate."""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from ncdev.v3.models import StepStatus, V3RunState


class FeatureMetric(BaseModel):
    feature_id: str
    title: str = ""
    status: str
    first_pass: bool
    repair_attempts: int
    build_duration_seconds: float
    verify_duration_seconds: float
    total_duration_seconds: float
    files_created: int
    files_modified: int


class RunMetrics(BaseModel):
    run_id: str
    project_name: str = ""
    started_at: str = ""
    completed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    total_duration_seconds: float = 0.0
    total_features: int = 0
    passed_features: int = 0
    failed_features: int = 0
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
    """Compute metrics from completed step results."""
    steps = state.completed_steps
    total = len(steps)

    if total == 0:
        return RunMetrics(run_id=state.run_id, started_at=state.started_at)

    passed = [s for s in steps if s.status == StepStatus.PASSED]
    failed = [s for s in steps if s.status == StepStatus.FAILED]
    first_pass = [s for s in steps if s.status == StepStatus.PASSED and s.repair_attempts == 0]
    repaired = [s for s in steps if s.repair_attempts > 0]

    total_build = sum(s.build_duration_seconds for s in steps)
    total_verify = sum(s.verify_duration_seconds for s in steps)
    total_time = total_build + total_verify

    feature_metrics = [
        FeatureMetric(
            feature_id=s.feature_id,
            status=s.status.value,
            first_pass=(s.status == StepStatus.PASSED and s.repair_attempts == 0),
            repair_attempts=s.repair_attempts,
            build_duration_seconds=s.build_duration_seconds,
            verify_duration_seconds=s.verify_duration_seconds,
            total_duration_seconds=s.build_duration_seconds + s.verify_duration_seconds,
            files_created=len(s.files_created),
            files_modified=len(s.files_modified),
        )
        for s in steps
    ]

    hours = total_time / 3600 if total_time > 0 else 1

    return RunMetrics(
        run_id=state.run_id,
        started_at=state.started_at,
        total_duration_seconds=total_time,
        total_features=total,
        passed_features=len(passed),
        failed_features=len(failed),
        first_pass_success_rate=len(first_pass) / total,
        repair_rate=len(repaired) / total,
        mean_repair_attempts=(
            sum(s.repair_attempts for s in repaired) / len(repaired)
            if repaired else 0.0
        ),
        build_efficiency=total_build / total_time if total_time > 0 else 0.0,
        feature_throughput_per_hour=total / hours,
        features=feature_metrics,
        citex_documents_ingested=ingestion_doc_count,
    )
