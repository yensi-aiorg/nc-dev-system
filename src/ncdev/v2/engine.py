from __future__ import annotations

import json
from pathlib import Path

from ncdev.adapters.registry import build_provider_registry, probe_registry_capabilities
from ncdev.artifacts.state import (
    ensure_v2_schema_files,
    init_v2_run_dirs,
    persist_v2_artifact,
    persist_v2_run_state,
)
from ncdev.discovery.pipeline import run_discovery_pipeline
from ncdev.utils import make_run_id
from ncdev.v2.config import ensure_default_v2_config
from ncdev.v2.execution import execute_routed_tasks
from ncdev.v2.job_runner import run_job_queue
from ncdev.v2.jobs import materialize_job_queue, materialize_repair_job_queue
from ncdev.v2.models import V2Phase, V2RunState, V2TaskState, V2TaskStatus
from ncdev.v2.prepare import prepare_target_project
from ncdev.v2.routing import resolve_routing_plan
from ncdev.v2.verification import run_v2_verification


def _base_state(run_id: str, workspace: Path, run_dir: Path, command: str) -> V2RunState:
    return V2RunState(
        run_id=run_id,
        command=command,
        workspace=str(workspace),
        run_dir=str(run_dir),
        tasks=[
            V2TaskState(name="capability_probe", status=V2TaskStatus.RUNNING),
            V2TaskState(name="routing"),
            V2TaskState(name="source_ingest"),
            V2TaskState(name="discovery"),
            V2TaskState(name="execution"),
            V2TaskState(name="prepare_target"),
            V2TaskState(name="job_queue"),
            V2TaskState(name="job_execution"),
            V2TaskState(name="verification"),
            V2TaskState(name="repair_queue"),
            V2TaskState(name="repair_execution"),
        ],
    )


def _set_task(state: V2RunState, name: str, status: V2TaskStatus, message: str = "", artifacts: list[str] | None = None) -> None:
    for task in state.tasks:
        if task.name == name:
            task.status = status
            task.message = message
            if artifacts is not None:
                task.artifacts = artifacts
            return
    state.tasks.append(
        V2TaskState(
            name=name,
            status=status,
            message=message,
            artifacts=artifacts or [],
        )
    )


def run_v2_discovery(workspace: Path, source_path: Path, dry_run: bool, command: str = "discover-v2") -> V2RunState:
    config = ensure_default_v2_config(workspace)
    ensure_v2_schema_files(workspace)

    run_id = make_run_id("v2")
    run_dir = init_v2_run_dirs(workspace, run_id)
    state = _base_state(run_id, workspace=workspace, run_dir=run_dir, command=command)
    state.phase = V2Phase.INGEST
    persist_v2_run_state(state)

    registry = build_provider_registry()
    capability_doc = probe_registry_capabilities(registry)
    capability_path = persist_v2_artifact(
        run_dir,
        "capability-snapshot.json",
        capability_doc.model_dump(mode="json"),
    )
    state.provider_snapshots.append(str(capability_path))
    state.artifacts.append(str(capability_path))
    _set_task(
        state,
        "capability_probe",
        V2TaskStatus.PASSED,
        "provider capabilities probed",
        artifacts=[str(capability_path)],
    )

    routing_doc = resolve_routing_plan(config, registry)
    routing_path = persist_v2_artifact(
        run_dir,
        "routing-plan.json",
        routing_doc.model_dump(mode="json"),
    )
    state.artifacts.append(str(routing_path))
    _set_task(
        state,
        "routing",
        V2TaskStatus.PASSED,
        "routing plan resolved",
        artifacts=[str(routing_path)],
    )

    source_pack, research_pack, feature_map, design_pack, build_plan, target_contract, scaffold_plan = run_discovery_pipeline(
        source_path,
        dry_run=dry_run,
    )
    state.phase = V2Phase.DISCOVERY
    output_paths = [
        persist_v2_artifact(run_dir, "source-pack.json", source_pack.model_dump(mode="json")),
        persist_v2_artifact(run_dir, "research-pack.json", research_pack.model_dump(mode="json")),
        persist_v2_artifact(run_dir, "feature-map.json", feature_map.model_dump(mode="json")),
        persist_v2_artifact(run_dir, "design-pack.json", design_pack.model_dump(mode="json")),
        persist_v2_artifact(run_dir, "build-plan.json", build_plan.model_dump(mode="json")),
        persist_v2_artifact(run_dir, "target-project-contract.json", target_contract.model_dump(mode="json")),
        persist_v2_artifact(run_dir, "scaffold-plan.json", scaffold_plan.model_dump(mode="json")),
    ]
    state.artifacts.extend([str(path) for path in output_paths])
    _set_task(
        state,
        "source_ingest",
        V2TaskStatus.PASSED,
        f"source normalized from {Path(str(source_path)).name}",
        artifacts=[str(output_paths[0])],
    )
    _set_task(
        state,
        "discovery",
        V2TaskStatus.PASSED,
        "discovery artifacts generated",
        artifacts=[str(path) for path in output_paths[1:]],
    )
    execution_doc = execute_routed_tasks(routing_doc, registry, run_dir / "outputs", dry_run=dry_run)
    execution_path = persist_v2_artifact(run_dir, "execution-log.json", execution_doc.model_dump(mode="json"))
    state.artifacts.append(str(execution_path))
    _set_task(
        state,
        "execution",
        V2TaskStatus.PASSED,
        f"executed {len(execution_doc.results)} routed discovery tasks",
        artifacts=[str(execution_path)],
    )
    state.phase = V2Phase.COMPLETE
    state.status = V2TaskStatus.PASSED
    state.metadata["dry_run"] = dry_run
    state.metadata["routing_decisions"] = len(routing_doc.decisions)
    state.touch()
    persist_v2_run_state(state)
    return state


def run_v2_prepare(workspace: Path, source_path: Path, dry_run: bool, command: str = "prepare-v2") -> V2RunState:
    state = run_v2_discovery(workspace=workspace, source_path=source_path, dry_run=dry_run, command=command)
    run_dir = Path(state.run_dir)
    outputs_dir = run_dir / "outputs"
    feature_map = json.loads((outputs_dir / "feature-map.json").read_text(encoding="utf-8"))
    target_contract = json.loads((outputs_dir / "target-project-contract.json").read_text(encoding="utf-8"))
    scaffold_plan = json.loads((outputs_dir / "scaffold-plan.json").read_text(encoding="utf-8"))

    from ncdev.v2.models import FeatureMapDoc, ScaffoldPlanDoc, TargetProjectContractDoc

    manifest, verification_contract = prepare_target_project(
        output_root=workspace / ".nc-dev" / "v2" / "generated" / state.run_id,
        feature_map=FeatureMapDoc.model_validate(feature_map),
        target_contract=TargetProjectContractDoc.model_validate(target_contract),
        scaffold_plan=ScaffoldPlanDoc.model_validate(scaffold_plan),
    )
    manifest_path = persist_v2_artifact(run_dir, "scaffold-manifest.json", manifest.model_dump(mode="json"))
    verification_path = persist_v2_artifact(
        run_dir,
        "verification-contract.json",
        verification_contract.model_dump(mode="json"),
    )
    state.artifacts.extend([str(manifest_path), str(verification_path)])
    _set_task(
        state,
        "prepare_target",
        V2TaskStatus.PASSED,
        "target project scaffold prepared",
        artifacts=[str(manifest_path), str(verification_path)],
    )
    state.metadata["target_project_path"] = manifest.target_path
    registry = build_provider_registry()
    job_queue = materialize_job_queue(run_dir, registry)
    job_queue_path = persist_v2_artifact(run_dir, "job-queue.json", job_queue.model_dump(mode="json"))
    state.artifacts.append(str(job_queue_path))
    _set_task(
        state,
        "job_queue",
        V2TaskStatus.PASSED,
        f"materialized {len(job_queue.jobs)} execution jobs",
        artifacts=[str(job_queue_path)],
    )
    state.metadata["job_count"] = len(job_queue.jobs)
    state.touch()
    persist_v2_run_state(state)
    return state


def run_v2_execute(workspace: Path, run_id: str, dry_run: bool, command: str = "execute-v2") -> V2RunState:
    state = load_v2_run_state(workspace, run_id)
    run_dir = Path(state.run_dir)
    state.command = command
    state.phase = V2Phase.COMPLETE

    registry = build_provider_registry()
    job_run_log = run_job_queue(run_dir, registry, dry_run=dry_run)
    job_run_log_path = persist_v2_artifact(run_dir, "job-run-log.json", job_run_log.model_dump(mode="json"))
    state.artifacts.append(str(job_run_log_path))
    passed = sum(1 for record in job_run_log.records if record.status in {"passed", "stubbed", "dry-run"})
    failed = sum(1 for record in job_run_log.records if record.status == "failed")
    blocked = sum(1 for record in job_run_log.records if record.status == "blocked")
    _set_task(
        state,
        "job_execution",
        V2TaskStatus.PASSED if failed == 0 else V2TaskStatus.FAILED,
        f"executed {len(job_run_log.records)} jobs: {passed} passed, {failed} failed, {blocked} blocked",
        artifacts=[str(job_run_log_path)],
    )
    state.metadata["job_run_count"] = len(job_run_log.records)
    state.metadata["job_failed_count"] = failed
    state.status = V2TaskStatus.PASSED if failed == 0 else V2TaskStatus.FAILED
    state.touch()
    persist_v2_run_state(state)
    return state


def run_v2_verify(
    workspace: Path,
    run_id: str,
    *,
    base_url: str,
    dry_run: bool,
    command: str = "verify-v2",
) -> V2RunState:
    state = load_v2_run_state(workspace, run_id)
    run_dir = Path(state.run_dir)
    state.command = command

    verification_run, evidence_index = run_v2_verification(
        run_dir,
        base_url=base_url,
        dry_run=dry_run,
    )
    verification_path = persist_v2_artifact(run_dir, "verification-run.json", verification_run.model_dump(mode="json"))
    evidence_path = persist_v2_artifact(run_dir, "evidence-index.json", evidence_index.model_dump(mode="json"))
    state.artifacts.extend([str(verification_path), str(evidence_path)])
    _set_task(
        state,
        "verification",
        V2TaskStatus.PASSED if verification_run.overall_passed else V2TaskStatus.FAILED,
        f"verification completed with overall_passed={verification_run.overall_passed}",
        artifacts=[str(verification_path), str(evidence_path)],
    )
    state.metadata["verification_passed"] = verification_run.overall_passed
    state.status = V2TaskStatus.PASSED if verification_run.overall_passed else V2TaskStatus.FAILED
    state.touch()
    persist_v2_run_state(state)
    return state


def run_v2_repair(workspace: Path, run_id: str, dry_run: bool, command: str = "repair-v2") -> V2RunState:
    state = load_v2_run_state(workspace, run_id)
    run_dir = Path(state.run_dir)
    state.command = command

    registry = build_provider_registry()
    repair_queue = materialize_repair_job_queue(run_dir, registry)
    repair_queue_path = persist_v2_artifact(run_dir, "repair-queue.json", repair_queue.model_dump(mode="json"))
    state.artifacts.append(str(repair_queue_path))
    _set_task(
        state,
        "repair_queue",
        V2TaskStatus.PASSED,
        f"materialized {len(repair_queue.jobs)} repair jobs",
        artifacts=[str(repair_queue_path)],
    )

    repair_run_log = run_job_queue(run_dir, registry, dry_run=dry_run, queue_name="repair-queue.json")
    repair_run_log_path = persist_v2_artifact(run_dir, "repair-run-log.json", repair_run_log.model_dump(mode="json"))
    state.artifacts.append(str(repair_run_log_path))
    failed = sum(1 for record in repair_run_log.records if record.status == "failed")
    state.metadata["repair_job_count"] = len(repair_run_log.records)
    state.metadata["repair_failed_count"] = failed
    _set_task(
        state,
        "repair_execution",
        V2TaskStatus.PASSED if failed == 0 else V2TaskStatus.FAILED,
        f"executed {len(repair_run_log.records)} repair jobs with {failed} failures",
        artifacts=[str(repair_run_log_path)],
    )
    state.status = V2TaskStatus.PASSED if failed == 0 else V2TaskStatus.FAILED
    state.touch()
    persist_v2_run_state(state)
    return state


def run_v2_full(
    workspace: Path,
    source_path: Path,
    *,
    base_url: str,
    dry_run: bool,
    repair_cycles: int = 1,
    command: str = "full-v2",
) -> V2RunState:
    state = run_v2_prepare(workspace=workspace, source_path=source_path, dry_run=dry_run, command=command)
    state = run_v2_execute(workspace=workspace, run_id=state.run_id, dry_run=dry_run, command=command)
    state = run_v2_verify(workspace=workspace, run_id=state.run_id, base_url=base_url, dry_run=dry_run, command=command)

    cycles_run = 0
    while cycles_run < repair_cycles and state.status != V2TaskStatus.PASSED:
        cycles_run += 1
        state = run_v2_repair(workspace=workspace, run_id=state.run_id, dry_run=dry_run, command=command)
        state = run_v2_verify(workspace=workspace, run_id=state.run_id, base_url=base_url, dry_run=dry_run, command=command)

    state.metadata["repair_cycles_requested"] = repair_cycles
    state.metadata["repair_cycles_run"] = cycles_run
    state.touch()
    persist_v2_run_state(state)
    return state


def load_v2_run_state(workspace: Path, run_id: str) -> V2RunState:
    path = workspace / ".nc-dev" / "v2" / "runs" / run_id / "run-state.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return V2RunState.model_validate(data)


def summarize_v2_status(state: V2RunState) -> str:
    task_summary = ",".join([f"{task.name}:{task.status.value}" for task in state.tasks])
    return (
        f"run_id={state.run_id} phase={state.phase.value} status={state.status.value} "
        f"tasks={task_summary}"
    )
