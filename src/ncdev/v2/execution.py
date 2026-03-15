from __future__ import annotations

from pathlib import Path
from typing import Any

from ncdev.adapters.base import ProviderAdapter
from ncdev.utils import write_json
from ncdev.v2.models import (
    ExecutionLogDoc,
    RoutingPlanDoc,
    TaskExecutionRecord,
    TaskRequestDoc,
    TaskType,
)


TASK_INPUT_ARTIFACTS: dict[TaskType, list[str]] = {
    TaskType.SOURCE_INGEST: ["source-pack.json"],
    TaskType.REPO_ANALYSIS: ["source-pack.json"],
    TaskType.MARKET_RESEARCH: ["research-pack.json"],
    TaskType.FEATURE_EXTRACTION: ["feature-map.json"],
    TaskType.DESIGN_BRIEF: ["design-pack.json"],
    TaskType.BUILD_BATCH: ["build-plan.json", "target-project-contract.json", "scaffold-plan.json"],
    TaskType.TEST_AUTHORING: ["build-plan.json", "scaffold-plan.json"],
    TaskType.QA_SWEEP: ["target-project-contract.json", "scaffold-plan.json"],
    TaskType.DELIVERY_PACK: ["build-plan.json", "target-project-contract.json"],
}


def _resolve_input_paths(outputs_dir: Path, task_type: TaskType) -> tuple[list[Path], list[str]]:
    artifact_names = TASK_INPUT_ARTIFACTS.get(task_type, [])
    paths = [outputs_dir / artifact_name for artifact_name in artifact_names]
    missing = [str(path) for path in paths if not path.exists()]
    return paths, missing


def _task_request_path(outputs_dir: Path, task_type: TaskType) -> Path:
    return outputs_dir / "task-requests" / f"{task_type.value}.json"


def _persist_task_request(path: Path, request: TaskRequestDoc) -> str:
    write_json(path, request.model_dump(mode="json"))
    return str(path)


def execute_routed_tasks(
    routing_plan: RoutingPlanDoc,
    registry: dict[str, ProviderAdapter],
    outputs_dir: Path,
    *,
    dry_run: bool,
    target_repo_path: str = "",
) -> ExecutionLogDoc:
    results: list[TaskExecutionRecord] = []
    for decision in routing_plan.decisions:
        artifact_paths, missing_artifacts = _resolve_input_paths(outputs_dir, decision.task_type)
        if not artifact_paths:
            continue

        resolved_inputs = [str(path) for path in artifact_paths]
        if decision.provider == "unassigned" or decision.provider not in registry:
            results.append(
                TaskExecutionRecord(
                    provider=decision.provider,
                    model=decision.model,
                    task_type=decision.task_type,
                    status="skipped",
                    summary=f"Skipped {decision.task_type.value}; provider was unavailable.",
                    input_artifact=resolved_inputs[0] if resolved_inputs else "",
                    input_artifacts=resolved_inputs,
                    metadata={"missing_artifacts": missing_artifacts},
                )
            )
            continue

        if missing_artifacts:
            results.append(
                TaskExecutionRecord(
                    provider=decision.provider,
                    model=decision.model,
                    task_type=decision.task_type,
                    status="skipped",
                    summary=f"Skipped {decision.task_type.value}; required artifacts were missing.",
                    input_artifact=resolved_inputs[0] if resolved_inputs else "",
                    input_artifacts=resolved_inputs,
                    metadata={"missing_artifacts": missing_artifacts},
                )
            )
            continue

        adapter = registry[decision.provider]
        task_request = adapter.build_task_request(
            task_type=decision.task_type,
            artifact_paths=artifact_paths,
            model=decision.model,
            options={"fallback_providers": decision.fallback_providers},
        )
        task_request_path = _persist_task_request(
            _task_request_path(outputs_dir, decision.task_type),
            task_request,
        )
        task_options: dict[str, Any] = {
            "dry_run": dry_run,
            "fallback_providers": decision.fallback_providers,
            "task_request_path": task_request_path,
            "task_request": task_request.model_dump(mode="json"),
        }
        # Pass target_path for tasks that need to write to the target repo
        if target_repo_path and decision.task_type in (
            TaskType.BUILD_BATCH,
            TaskType.TEST_AUTHORING,
            TaskType.QA_SWEEP,
        ):
            task_options["target_path"] = target_repo_path

        result = adapter.run_task(
            task_type=decision.task_type,
            artifact_paths=artifact_paths,
            model=decision.model,
            options=task_options,
        )
        record = TaskExecutionRecord.model_validate(result.model_dump(mode="json"))
        record.input_artifacts = resolved_inputs
        if not record.input_artifact and resolved_inputs:
            record.input_artifact = resolved_inputs[0]
        if task_request_path not in record.artifact_paths:
            record.artifact_paths.append(task_request_path)
        results.append(record)

    return ExecutionLogDoc(
        generator="ncdev.v2.execution",
        source_inputs=[str(outputs_dir), str(outputs_dir / "task-requests")],
        results=results,
    )
