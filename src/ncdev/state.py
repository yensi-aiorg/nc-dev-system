from __future__ import annotations

from pathlib import Path
from typing import Any

from ncdev.models import (
    ArchitectureDoc,
    BuildResultDoc,
    ChangePlanDoc,
    ConsensusDoc,
    DeliveryReportDoc,
    FeaturesDoc,
    HardenReportDoc,
    HumanQuestionsDoc,
    ModelAssessment,
    RepoInventoryDoc,
    RiskMapDoc,
    RunState,
    ScaffoldingManifestDoc,
    TestPlanDoc,
    TestResultDoc,
)
from ncdev.utils import write_json, write_text


def ensure_schema_files(workspace: Path) -> None:
    schema_dir = workspace / ".nc-dev" / "schemas"
    schema_dir.mkdir(parents=True, exist_ok=True)

    schema_map: dict[str, dict[str, Any]] = {
        "features.v1.json": FeaturesDoc.model_json_schema(),
        "architecture.v1.json": ArchitectureDoc.model_json_schema(),
        "test-plan.v1.json": TestPlanDoc.model_json_schema(),
        "repo-inventory.v1.json": RepoInventoryDoc.model_json_schema(),
        "risk-map.v1.json": RiskMapDoc.model_json_schema(),
        "change-plan.v1.json": ChangePlanDoc.model_json_schema(),
        "model-assessment.v1.json": ModelAssessment.model_json_schema(),
        "consensus.v1.json": ConsensusDoc.model_json_schema(),
        "run-state.v1.json": RunState.model_json_schema(),
        "human-questions.v1.json": HumanQuestionsDoc.model_json_schema(),
        "scaffolding-manifest.v1.json": ScaffoldingManifestDoc.model_json_schema(),
        "build-result.v1.json": BuildResultDoc.model_json_schema(),
        "test-result.v1.json": TestResultDoc.model_json_schema(),
        "harden-report.v1.json": HardenReportDoc.model_json_schema(),
        "delivery-report.v1.json": DeliveryReportDoc.model_json_schema(),
    }

    for name, schema in schema_map.items():
        write_json(schema_dir / name, schema)


def init_run_dirs(workspace: Path, run_id: str) -> Path:
    run_dir = workspace / ".nc-dev" / "runs" / run_id
    (run_dir / "assessments").mkdir(parents=True, exist_ok=True)
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    (run_dir / "outputs").mkdir(parents=True, exist_ok=True)
    return run_dir


def persist_run_state(state: RunState) -> None:
    write_json(Path(state.run_dir) / "run-state.json", state.model_dump(mode="json"))


def persist_model_assessment(run_dir: Path, assessment: ModelAssessment) -> Path:
    model_dir = run_dir / "assessments" / assessment.task_id
    model_dir.mkdir(parents=True, exist_ok=True)
    path = model_dir / f"{assessment.model}.json"
    write_json(path, assessment.model_dump(mode="json"))
    return path


def persist_consensus(run_dir: Path, consensus: ConsensusDoc) -> Path:
    path = run_dir / "outputs" / "consensus.json"
    write_json(path, consensus.model_dump(mode="json"))
    return path


def persist_output_doc(run_dir: Path, name: str, payload: dict[str, Any]) -> Path:
    path = run_dir / "outputs" / name
    write_json(path, payload)
    return path


def append_log(run_dir: Path, line: str) -> None:
    log_path = run_dir / "logs" / "events.log"
    existing = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    write_text(log_path, existing + line + "\n")
