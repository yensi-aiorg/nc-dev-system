from __future__ import annotations

from pathlib import Path
from typing import Any

from ncdev.utils import write_json
from ncdev.v2.models import (
    BuildPlanDoc,
    CapabilitySnapshotDoc,
    DesignPackDoc,
    ExecutionLogDoc,
    FeatureMapDoc,
    JobQueueDoc,
    JobRunLogDoc,
    ResearchPackDoc,
    RoutingPlanDoc,
    ScaffoldManifestDocV2,
    ScaffoldPlanDoc,
    SourcePackDoc,
    TaskRequestDoc,
    TargetProjectContractDoc,
    VerificationContractDoc,
    VerificationRunDoc,
    EvidenceIndexDoc,
    V2RunState,
)


def ensure_v2_schema_files(workspace: Path) -> None:
    schema_dir = workspace / ".nc-dev" / "v2" / "schemas"
    schema_dir.mkdir(parents=True, exist_ok=True)
    schema_map: dict[str, dict[str, Any]] = {
        "source-pack.v2.json": SourcePackDoc.model_json_schema(),
        "research-pack.v2.json": ResearchPackDoc.model_json_schema(),
        "feature-map.v2.json": FeatureMapDoc.model_json_schema(),
        "design-pack.v2.json": DesignPackDoc.model_json_schema(),
        "build-plan.v2.json": BuildPlanDoc.model_json_schema(),
        "target-project-contract.v2.json": TargetProjectContractDoc.model_json_schema(),
        "scaffold-plan.v2.json": ScaffoldPlanDoc.model_json_schema(),
        "scaffold-manifest.v2.json": ScaffoldManifestDocV2.model_json_schema(),
        "verification-contract.v2.json": VerificationContractDoc.model_json_schema(),
        "execution-log.v2.json": ExecutionLogDoc.model_json_schema(),
        "job-queue.v2.json": JobQueueDoc.model_json_schema(),
        "job-run-log.v2.json": JobRunLogDoc.model_json_schema(),
        "task-request.v2.json": TaskRequestDoc.model_json_schema(),
        "verification-run.v2.json": VerificationRunDoc.model_json_schema(),
        "evidence-index.v2.json": EvidenceIndexDoc.model_json_schema(),
        "capability-snapshot.v2.json": CapabilitySnapshotDoc.model_json_schema(),
        "routing-plan.v2.json": RoutingPlanDoc.model_json_schema(),
        "run-state.v2.json": V2RunState.model_json_schema(),
    }
    for name, schema in schema_map.items():
        write_json(schema_dir / name, schema)


def init_v2_run_dirs(workspace: Path, run_id: str) -> Path:
    run_dir = workspace / ".nc-dev" / "v2" / "runs" / run_id
    (run_dir / "outputs").mkdir(parents=True, exist_ok=True)
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    return run_dir


def persist_v2_run_state(state: V2RunState) -> Path:
    path = Path(state.run_dir) / "run-state.json"
    write_json(path, state.model_dump(mode="json"))
    return path


def persist_v2_artifact(run_dir: Path, name: str, payload: dict[str, Any]) -> Path:
    path = run_dir / "outputs" / name
    write_json(path, payload)
    return path
