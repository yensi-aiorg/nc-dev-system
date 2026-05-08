from __future__ import annotations

from pathlib import Path
from typing import Any

from ncdev.utils import write_json
from ncdev.core.models import (
    BootstrapRunDoc,
    BuildPlanDoc,
    CapabilitySnapshotDoc,
    DeliverySummaryDoc,
    DesignBriefDoc,
    DesignPackDoc,
    ExecutionLogDoc,
    FeatureMapDoc,
    PhasePlanDoc,
    FullRunReportDoc,
    JobQueueDoc,
    JobRunLogDoc,
    ResearchPackDoc,
    RoutingPlanDoc,
    ScaffoldManifestDoc,
    ScaffoldPlanDoc,
    SourcePackDoc,
    TaskRequestDoc,
    TargetProjectContractDoc,
    VerificationContractDoc,
    VerificationIssueBundleDoc,
    VerificationRunDoc,
    EvidenceIndexDoc,
    SentinelRunState,
)


def ensure_schema_files(workspace: Path) -> None:
    schema_dir = workspace / ".nc-dev" / "schemas"
    schema_dir.mkdir(parents=True, exist_ok=True)
    schema_map: dict[str, dict[str, Any]] = {
        "source-pack.json": SourcePackDoc.model_json_schema(),
        "research-pack.json": ResearchPackDoc.model_json_schema(),
        "feature-map.json": FeatureMapDoc.model_json_schema(),
        "design-pack.json": DesignPackDoc.model_json_schema(),
        "design-brief.json": DesignBriefDoc.model_json_schema(),
        "build-plan.json": BuildPlanDoc.model_json_schema(),
        "phase-plan.json": PhasePlanDoc.model_json_schema(),
        "target-project-contract.json": TargetProjectContractDoc.model_json_schema(),
        "scaffold-plan.json": ScaffoldPlanDoc.model_json_schema(),
        "scaffold-manifest.json": ScaffoldManifestDoc.model_json_schema(),
        "verification-contract.json": VerificationContractDoc.model_json_schema(),
        "execution-log.json": ExecutionLogDoc.model_json_schema(),
        "job-queue.json": JobQueueDoc.model_json_schema(),
        "job-run-log.json": JobRunLogDoc.model_json_schema(),
        "task-request.json": TaskRequestDoc.model_json_schema(),
        "bootstrap-run.json": BootstrapRunDoc.model_json_schema(),
        "verification-run.json": VerificationRunDoc.model_json_schema(),
        "evidence-index.json": EvidenceIndexDoc.model_json_schema(),
        "verification-issues.json": VerificationIssueBundleDoc.model_json_schema(),
        "delivery-summary.json": DeliverySummaryDoc.model_json_schema(),
        "full-run-report.json": FullRunReportDoc.model_json_schema(),
        "capability-snapshot.json": CapabilitySnapshotDoc.model_json_schema(),
        "routing-plan.json": RoutingPlanDoc.model_json_schema(),
        "run-state.json": SentinelRunState.model_json_schema(),
    }
    for name, schema in schema_map.items():
        write_json(schema_dir / name, schema)


def init_sentinel_run_dirs(workspace: Path, run_id: str) -> Path:
    run_dir = workspace / ".nc-dev" / "runs" / run_id
    (run_dir / "outputs").mkdir(parents=True, exist_ok=True)
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    return run_dir


def persist_sentinel_run_state(state: SentinelRunState) -> Path:
    path = Path(state.run_dir) / "run-state.json"
    write_json(path, state.model_dump(mode="json"))
    return path


def persist_sentinel_artifact(run_dir: Path, name: str, payload: dict[str, Any]) -> Path:
    path = run_dir / "outputs" / name
    write_json(path, payload)
    return path
