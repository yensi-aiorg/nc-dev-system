from __future__ import annotations

from pathlib import Path

from ncdev.adapters.base import ProviderAdapter
from ncdev.v2.models import ExecutionLogDoc, RoutingPlanDoc, TaskExecutionRecord, TaskType


DISCOVERY_TASK_ARTIFACTS: dict[TaskType, str] = {
    TaskType.SOURCE_INGEST: "source-pack.json",
    TaskType.REPO_ANALYSIS: "source-pack.json",
    TaskType.MARKET_RESEARCH: "research-pack.json",
    TaskType.FEATURE_EXTRACTION: "feature-map.json",
    TaskType.DESIGN_BRIEF: "design-pack.json",
}


def execute_routed_tasks(
    routing_plan: RoutingPlanDoc,
    registry: dict[str, ProviderAdapter],
    outputs_dir: Path,
) -> ExecutionLogDoc:
    results: list[TaskExecutionRecord] = []
    for decision in routing_plan.decisions:
        artifact_name = DISCOVERY_TASK_ARTIFACTS.get(decision.task_type)
        if not artifact_name:
            continue
        artifact_path = outputs_dir / artifact_name
        if decision.provider == "unassigned" or decision.provider not in registry or not artifact_path.exists():
            results.append(
                TaskExecutionRecord(
                    provider=decision.provider,
                    model=decision.model,
                    task_type=decision.task_type,
                    status="skipped",
                    summary=f"Skipped {decision.task_type.value}; provider or artifact was unavailable.",
                    input_artifact=str(artifact_path),
                )
            )
            continue

        adapter = registry[decision.provider]
        result = adapter.run_task(
            task_type=decision.task_type,
            artifact_path=artifact_path,
            model=decision.model,
            options={"fallback_providers": decision.fallback_providers},
        )
        results.append(TaskExecutionRecord.model_validate(result.model_dump(mode="json")))

    return ExecutionLogDoc(
        generator="ncdev.v2.execution",
        source_inputs=[str(outputs_dir)],
        results=results,
    )
