from __future__ import annotations

import json
from pathlib import Path

from ncdev.v2.models import (
    BatchDeliveryEntry,
    BuildPlanDoc,
    DeliverySummaryDoc,
    FullRunReportDoc,
    TargetProjectContractDoc,
    V2RunState,
    V2TaskStatus,
)


def assemble_delivery_summary(build_plan: BuildPlanDoc, target_contract: TargetProjectContractDoc) -> DeliverySummaryDoc:
    batches = [
        BatchDeliveryEntry(
            id=batch.id,
            title=batch.title,
            summary=batch.summary,
            acceptance_criteria=batch.acceptance_criteria,
        )
        for batch in build_plan.batches
    ]
    return DeliverySummaryDoc(
        generator="ncdev.v2.delivery",
        source_inputs=["build-plan.json", "target-project-contract.json"],
        project_name=build_plan.project_name,
        target_type=target_contract.target_type,
        stack=target_contract.stack,
        batch_count=len(batches),
        batches=batches,
        instructions=_build_execution_steps(target_contract, build_plan),
        ownership_rules=target_contract.ownership_rules,
        required_artifacts=target_contract.required_artifacts,
        risks=build_plan.risks,
    )


def load_delivery_inputs(run_dir: Path) -> tuple[BuildPlanDoc, TargetProjectContractDoc]:
    outputs = run_dir / "outputs"
    build_plan = BuildPlanDoc.model_validate(
        json.loads((outputs / "build-plan.json").read_text(encoding="utf-8"))
    )
    target_contract = TargetProjectContractDoc.model_validate(
        json.loads((outputs / "target-project-contract.json").read_text(encoding="utf-8"))
    )
    return build_plan, target_contract


def assemble_full_run_report(state: V2RunState) -> FullRunReportDoc:
    task_statuses = {task.name: task.status.value for task in state.tasks}
    failed_tasks = [task.name for task in state.tasks if task.status == V2TaskStatus.FAILED]
    next_actions = (
        [
            f"Investigate failed tasks: {', '.join(failed_tasks)}",
            "Run another repair cycle or intervene manually on the target project.",
        ]
        if failed_tasks
        else [
            "Review the delivery summary and verification evidence before release.",
            "Run a human acceptance pass on the generated target project.",
        ]
    )
    return FullRunReportDoc(
        generator="ncdev.v2.delivery",
        source_inputs=["run-state.json"],
        run_id=state.run_id,
        command=state.command,
        project_name=str(state.metadata.get("project_name", "")),
        target_path=str(state.metadata.get("target_project_path", "")),
        final_status=state.status.value,
        verification_passed=bool(state.metadata.get("verification_passed", False)),
        bootstrap_succeeded=bool(state.metadata.get("bootstrap_succeeded", False)),
        teardown_succeeded=bool(state.metadata.get("teardown_succeeded", False)),
        repair_cycles_requested=int(state.metadata.get("repair_cycles_requested", 0)),
        repair_cycles_run=int(state.metadata.get("repair_cycles_run", 0)),
        tasks=task_statuses,
        failed_tasks=failed_tasks,
        next_actions=next_actions,
        metadata=state.metadata,
    )


def _build_execution_steps(contract: TargetProjectContractDoc, plan: BuildPlanDoc) -> list[str]:
    return [
        f"Verify all {len(plan.batches)} build batches are committed to the target project referenced by scaffold-manifest.json.",
        f"Confirm required artifacts are present: {', '.join(contract.required_artifacts)}.",
        f"Validate the declared stack: {', '.join(f'{key}={value}' for key, value in contract.stack.items())}.",
        "Run the full test suite (unit, integration, functional, and E2E) and capture exit codes.",
        "Capture Playwright screenshots for supported user flows and include them in the evidence index.",
        "Review the ownership rules and ensure all generated code remains inside the target project.",
    ]
