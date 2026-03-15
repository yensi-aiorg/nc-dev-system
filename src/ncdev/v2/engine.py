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
from ncdev.discovery.pipeline import run_discovery_pipeline_with_target
from ncdev.utils import make_run_id, write_text
from ncdev.v2.config import ensure_default_v2_config
from ncdev.v2.execution import execute_routed_tasks
from ncdev.v2.job_runner import run_job_queue
from ncdev.v2.jobs import materialize_job_queue, materialize_repair_job_queue
from ncdev.v2.delivery import assemble_delivery_summary, load_delivery_inputs
from ncdev.v2.models import FullRunReportDoc, SentinelFailureReport, V2Phase, V2RunState, V2TaskState, V2TaskStatus
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
            V2TaskState(name="delivery_summary"),
            V2TaskState(name="release_gate"),
            V2TaskState(name="final_report"),
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


def run_v2_discovery(
    workspace: Path,
    source_path: Path,
    dry_run: bool,
    command: str = "discover-v2",
    *,
    target_repo_path: Path | None = None,
    run_id: str | None = None,
) -> V2RunState:
    config = ensure_default_v2_config(workspace)
    ensure_v2_schema_files(workspace)

    run_id = run_id or make_run_id("v2")
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

    source_pack, research_pack, feature_map, design_pack, design_brief, build_plan, phase_plan, target_contract, scaffold_plan = run_discovery_pipeline_with_target(
        source_path,
        dry_run=dry_run,
        target_repo_path=target_repo_path,
    )
    state.phase = V2Phase.DISCOVERY
    output_paths = [
        persist_v2_artifact(run_dir, "source-pack.json", source_pack.model_dump(mode="json")),
        persist_v2_artifact(run_dir, "research-pack.json", research_pack.model_dump(mode="json")),
        persist_v2_artifact(run_dir, "feature-map.json", feature_map.model_dump(mode="json")),
        persist_v2_artifact(run_dir, "design-pack.json", design_pack.model_dump(mode="json")),
        persist_v2_artifact(run_dir, "design-brief.json", design_brief.model_dump(mode="json")),
        persist_v2_artifact(run_dir, "build-plan.json", build_plan.model_dump(mode="json")),
        persist_v2_artifact(run_dir, "phase-plan.json", phase_plan.model_dump(mode="json")),
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
    execution_doc = execute_routed_tasks(
        routing_doc, registry, run_dir / "outputs",
        dry_run=dry_run,
        target_repo_path=str(Path(str(target_repo_path)).resolve()) if target_repo_path else "",
    )
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
    state.metadata["project_name"] = feature_map.project_name
    state.metadata["routing_decisions"] = len(routing_doc.decisions)
    if target_repo_path is not None:
        state.metadata["target_repo_path"] = str(target_repo_path)
    state.touch()
    persist_v2_run_state(state)
    return state


def run_v2_prepare(
    workspace: Path,
    source_path: Path,
    dry_run: bool,
    command: str = "prepare-v2",
    *,
    target_repo_path: Path | None = None,
    run_id: str | None = None,
) -> V2RunState:
    state = run_v2_discovery(
        workspace=workspace,
        source_path=source_path,
        dry_run=dry_run,
        command=command,
        target_repo_path=target_repo_path,
        run_id=run_id,
    )
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
        target_root=target_repo_path,
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
        "existing target repository prepared" if manifest.existing_repo else "target project scaffold prepared",
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
    failure_kinds: dict[str, int] = {}
    for record in job_run_log.records:
        failure_kind = str(record.metadata.get("failure_kind", "")).strip()
        if failure_kind:
            failure_kinds[failure_kind] = failure_kinds.get(failure_kind, 0) + 1
    _set_task(
        state,
        "job_execution",
        V2TaskStatus.PASSED if failed == 0 else V2TaskStatus.FAILED,
        f"executed {len(job_run_log.records)} jobs: {passed} passed, {failed} failed, {blocked} blocked",
        artifacts=[str(job_run_log_path)],
    )
    state.metadata["job_run_count"] = len(job_run_log.records)
    state.metadata["job_failed_count"] = failed
    state.metadata["job_failure_kinds"] = failure_kinds
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

    verification_run, evidence_index, bootstrap_run, issue_bundle = run_v2_verification(
        run_dir,
        base_url=base_url,
        dry_run=dry_run,
    )
    bootstrap_path = persist_v2_artifact(run_dir, "bootstrap-run.json", bootstrap_run.model_dump(mode="json"))
    verification_path = persist_v2_artifact(run_dir, "verification-run.json", verification_run.model_dump(mode="json"))
    evidence_path = persist_v2_artifact(run_dir, "evidence-index.json", evidence_index.model_dump(mode="json"))
    issues_path = persist_v2_artifact(run_dir, "verification-issues.json", issue_bundle.model_dump(mode="json"))
    state.artifacts.extend([str(bootstrap_path), str(verification_path), str(evidence_path), str(issues_path)])
    _set_task(
        state,
        "verification",
        V2TaskStatus.PASSED if verification_run.overall_passed else V2TaskStatus.FAILED,
        f"verification completed with overall_passed={verification_run.overall_passed}",
        artifacts=[str(bootstrap_path), str(verification_path), str(evidence_path), str(issues_path)],
    )
    state.metadata["bootstrap_succeeded"] = bootstrap_run.bootstrap_succeeded
    state.metadata["teardown_succeeded"] = bootstrap_run.teardown_succeeded
    state.metadata["verification_issue_count"] = issue_bundle.issue_count
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
    failure_kinds: dict[str, int] = {}
    for record in repair_run_log.records:
        failure_kind = str(record.metadata.get("failure_kind", "")).strip()
        if failure_kind:
            failure_kinds[failure_kind] = failure_kinds.get(failure_kind, 0) + 1
    state.metadata["repair_job_count"] = len(repair_run_log.records)
    state.metadata["repair_failed_count"] = failed
    state.metadata["repair_failure_kinds"] = failure_kinds
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


def run_v2_deliver(workspace: Path, run_id: str, command: str = "deliver-v2") -> V2RunState:
    state = load_v2_run_state(workspace, run_id)
    run_dir = Path(state.run_dir)
    state.command = command

    build_plan, target_contract = load_delivery_inputs(run_dir)
    delivery_summary = assemble_delivery_summary(build_plan, target_contract)
    delivery_path = persist_v2_artifact(run_dir, "delivery-summary.json", delivery_summary.model_dump(mode="json"))
    state.artifacts.append(str(delivery_path))
    _set_task(
        state,
        "delivery_summary",
        V2TaskStatus.PASSED,
        f"delivery summary assembled: {delivery_summary.batch_count} batches, {len(delivery_summary.execution_steps)} steps",
        artifacts=[str(delivery_path)],
    )
    state.metadata["project_name"] = delivery_summary.project_name
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
    target_repo_path: Path | None = None,
    run_id: str | None = None,
) -> V2RunState:
    state = run_v2_prepare(
        workspace=workspace,
        source_path=source_path,
        dry_run=dry_run,
        command=command,
        target_repo_path=target_repo_path,
        run_id=run_id,
    )
    state = run_v2_execute(workspace=workspace, run_id=state.run_id, dry_run=dry_run, command=command)
    state = run_v2_verify(workspace=workspace, run_id=state.run_id, base_url=base_url, dry_run=dry_run, command=command)

    cycles_run = 0
    while cycles_run < repair_cycles and state.status != V2TaskStatus.PASSED:
        cycles_run += 1
        state = run_v2_repair(workspace=workspace, run_id=state.run_id, dry_run=dry_run, command=command)
        state = run_v2_verify(workspace=workspace, run_id=state.run_id, base_url=base_url, dry_run=dry_run, command=command)

    state = run_v2_deliver(workspace=workspace, run_id=state.run_id, command=command)
    state.metadata["repair_cycles_requested"] = repair_cycles
    state.metadata["repair_cycles_run"] = cycles_run

    report = _build_full_run_report(state)
    _set_task(
        state,
        "release_gate",
        V2TaskStatus.PASSED if report.readiness_decision != "blocked" else V2TaskStatus.FAILED,
        f"release gate decision: {report.readiness_decision}",
    )
    if report.readiness_decision == "blocked":
        state.status = V2TaskStatus.FAILED
    report_path = persist_v2_artifact(Path(state.run_dir), "full-run-report.json", report.model_dump(mode="json"))
    summary_path = Path(state.run_dir) / "outputs" / "full-run-summary.md"
    write_text(summary_path, _render_full_run_summary(report))
    state.artifacts.extend([str(report_path), str(summary_path)])
    _set_task(
        state,
        "final_report",
        V2TaskStatus.PASSED,
        "full run summary generated",
        artifacts=[str(report_path), str(summary_path)],
    )
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


def _build_full_run_report(state: V2RunState) -> FullRunReportDoc:
    run_dir = Path(state.run_dir)
    outputs_dir = run_dir / "outputs"
    scaffold_manifest_path = outputs_dir / "scaffold-manifest.json"
    verification_run_path = outputs_dir / "verification-run.json"
    evidence_index_path = outputs_dir / "evidence-index.json"
    verification_contract_path = outputs_dir / "verification-contract.json"
    verification_issues_path = outputs_dir / "verification-issues.json"

    project_name = ""
    target_path = ""
    if scaffold_manifest_path.exists():
        scaffold_manifest = json.loads(scaffold_manifest_path.read_text(encoding="utf-8"))
        project_name = str(scaffold_manifest.get("project_name", ""))
        target_path = str(scaffold_manifest.get("target_path", ""))

    verification_passed = bool(state.metadata.get("verification_passed", False))
    bootstrap_succeeded = bool(state.metadata.get("bootstrap_succeeded", False))
    teardown_succeeded = bool(state.metadata.get("teardown_succeeded", False))
    verification_summary: dict[str, object] = {}
    verification_issue_count = int(state.metadata.get("verification_issue_count", 0))
    issue_categories: list[str] = []
    evidence_complete = False
    if verification_run_path.exists():
        verification_payload = json.loads(verification_run_path.read_text(encoding="utf-8"))
        verification_passed = bool(verification_payload.get("overall_passed", verification_passed))
        verification_summary = dict(verification_payload.get("summary", {}))
    if verification_issues_path.exists():
        issues_payload = json.loads(verification_issues_path.read_text(encoding="utf-8"))
        verification_issue_count = int(issues_payload.get("issue_count", verification_issue_count))
        issue_categories = sorted({str(issue.get("category", "")) for issue in issues_payload.get("issues", []) if issue.get("category")})
        evidence_complete = all(str(issue.get("category", "")) != "evidence" for issue in issues_payload.get("issues", []))
    if not evidence_complete and evidence_index_path.exists() and verification_contract_path.exists():
        evidence_payload = json.loads(evidence_index_path.read_text(encoding="utf-8"))
        verification_contract = json.loads(verification_contract_path.read_text(encoding="utf-8"))
        target_root = Path(target_path) if target_path else None
        if target_root:
            evidence_complete = all((target_root / rel_path).exists() for rel_path in verification_contract.get("evidence_paths", []))
        else:
            evidence_complete = bool(
                evidence_payload.get("screenshots")
                or evidence_payload.get("reports")
                or evidence_payload.get("videos")
                or evidence_payload.get("traces")
            )

    tasks = {task.name: task.status.value for task in state.tasks}
    failed_tasks = [task.name for task in state.tasks if task.status in {V2TaskStatus.FAILED, V2TaskStatus.BLOCKED}]
    blockers: list[str] = []
    warnings: list[str] = []
    provider_failure_kinds: dict[str, int] = {}
    for bucket_name in ("job_failure_kinds", "repair_failure_kinds"):
        bucket = dict(state.metadata.get(bucket_name, {}))
        for kind, count in bucket.items():
            provider_failure_kinds[kind] = provider_failure_kinds.get(kind, 0) + int(count)
    if not verification_passed:
        blockers.append("Verification did not pass.")
    if not bootstrap_succeeded:
        blockers.append("Target application did not bootstrap successfully.")
    if not evidence_complete:
        blockers.append("Required verification evidence is incomplete.")
    if int(state.metadata.get("job_failed_count", 0)) > 0:
        blockers.append("One or more execution jobs failed.")
    if int(state.metadata.get("repair_failed_count", 0)) > 0:
        blockers.append("One or more repair jobs failed.")
    if verification_issue_count > 0:
        blockers.append(f"Verification reported {verification_issue_count} issue(s).")
    if failed_tasks:
        blockers.append(f"Run contains failed tasks: {', '.join(failed_tasks)}.")
    if verification_summary.get("runner_error"):
        blockers.append("Verification runner reported an exception.")
    if provider_failure_kinds:
        blockers.append(
            "Provider execution failures were detected: "
            + ", ".join(f"{kind}={count}" for kind, count in sorted(provider_failure_kinds.items()))
            + "."
        )
    if not teardown_succeeded and bootstrap_succeeded:
        warnings.append("Verification teardown did not fully succeed.")

    dry_run = bool(state.metadata.get("dry_run", False))
    readiness_score = 100
    readiness_score -= min(50, verification_issue_count * 10)
    readiness_score -= min(20, int(state.metadata.get("job_failed_count", 0)) * 10)
    readiness_score -= min(20, int(state.metadata.get("repair_failed_count", 0)) * 10)
    if not verification_passed:
        readiness_score -= 30
    if not evidence_complete:
        readiness_score -= 20
    if not bootstrap_succeeded:
        readiness_score -= 20
    if not teardown_succeeded and bootstrap_succeeded:
        readiness_score -= 5
    readiness_score = max(0, min(100, readiness_score))

    next_actions: list[str] = []
    if dry_run:
        readiness_decision = "simulation_only"
        release_recommendation = "do_not_release"
        next_actions.append("Run the flow again without --dry-run before making any release decision.")
        next_actions.append("Review generated artifacts and verification contracts for realism.")
    elif not blockers:
        readiness_decision = "ready_for_human_review"
        release_recommendation = "human_approval_required"
        next_actions.append("Review the delivery pack and verification evidence before release.")
        next_actions.append("Run a human acceptance pass on the generated target project.")
        if warnings:
            next_actions.extend(warnings)
    else:
        readiness_decision = "blocked"
        release_recommendation = "hold"
        next_actions.append("Inspect verification-run.json and repair-run-log.json for unresolved failures.")
        if not bootstrap_succeeded:
            next_actions.append("Confirm the target project's local startup commands and base URL are correct.")
        if verification_summary.get("runner_error"):
            next_actions.append("Stabilize the verification harness before another repair cycle.")
        if provider_failure_kinds:
            next_actions.append("Investigate provider CLI failures, timeouts, or missing task outputs before retrying.")
        if state.metadata.get("repair_cycles_run", 0) >= state.metadata.get("repair_cycles_requested", 0):
            next_actions.append("Increase repair cycles or intervene manually on the failed target project.")
        if warnings:
            next_actions.extend(warnings)

    return FullRunReportDoc(
        generator="ncdev.v2.engine",
        source_inputs=[str(run_dir)],
        run_id=state.run_id,
        command=state.command,
        project_name=project_name,
        target_path=target_path,
        final_status=state.status.value,
        readiness_decision=readiness_decision,
        release_recommendation=release_recommendation,
        readiness_score=readiness_score,
        verification_passed=verification_passed,
        bootstrap_succeeded=bootstrap_succeeded,
        teardown_succeeded=teardown_succeeded,
        evidence_complete=evidence_complete,
        human_approval_required=True,
        repair_cycles_requested=int(state.metadata.get("repair_cycles_requested", 0)),
        repair_cycles_run=int(state.metadata.get("repair_cycles_run", 0)),
        tasks=tasks,
        failed_tasks=failed_tasks,
        blockers=blockers,
        next_actions=next_actions,
        metadata={
            "verification_summary": verification_summary,
            "job_failed_count": state.metadata.get("job_failed_count", 0),
            "repair_failed_count": state.metadata.get("repair_failed_count", 0),
            "verification_issue_count": verification_issue_count,
            "issue_categories": issue_categories,
            "provider_failure_kinds": provider_failure_kinds,
            "warnings": warnings,
        },
    )


def _render_full_run_summary(report: FullRunReportDoc) -> str:
    failed = ", ".join(report.failed_tasks) if report.failed_tasks else "none"
    actions = "\n".join(f"- {action}" for action in report.next_actions) or "- none"
    return "\n".join(
        [
            "# Full Run Summary",
            "",
            f"- Run ID: `{report.run_id}`",
            f"- Command: `{report.command}`",
            f"- Project: `{report.project_name}`",
            f"- Target Path: `{report.target_path}`",
            f"- Final Status: `{report.final_status}`",
            f"- Readiness Decision: `{report.readiness_decision}`",
            f"- Release Recommendation: `{report.release_recommendation}`",
            f"- Readiness Score: `{report.readiness_score}`",
            f"- Verification Passed: `{report.verification_passed}`",
            f"- Bootstrap Succeeded: `{report.bootstrap_succeeded}`",
            f"- Teardown Succeeded: `{report.teardown_succeeded}`",
            f"- Evidence Complete: `{report.evidence_complete}`",
            f"- Repair Cycles: `{report.repair_cycles_run}` / `{report.repair_cycles_requested}`",
            f"- Failed Tasks: {failed}",
            f"- Blockers: {', '.join(report.blockers) if report.blockers else 'none'}",
            "",
            "## Next Actions",
            actions,
            "",
        ]
    )


def _base_fix_state(run_id: str, workspace: Path, run_dir: Path, command: str) -> V2RunState:
    return V2RunState(
        run_id=run_id,
        command=command,
        workspace=str(workspace),
        run_dir=str(run_dir),
        tasks=[
            V2TaskState(name="load_report", status=V2TaskStatus.RUNNING),
            V2TaskState(name="checkout_version"),
            V2TaskState(name="reproduce"),
            V2TaskState(name="fix"),
            V2TaskState(name="validate"),
            V2TaskState(name="submit"),
        ],
    )


def run_v2_fix(
    workspace: Path,
    report_path: Path,
    target_repo_path: Path,
    dry_run: bool,
    *,
    auto_deploy: bool = False,
    max_attempts: int = 3,
    command: str = "fix",
    run_id: str | None = None,
) -> V2RunState:
    run_id = run_id or make_run_id("v2-fix")
    run_dir = init_v2_run_dirs(workspace, run_id)
    state = _base_fix_state(run_id, workspace=workspace, run_dir=run_dir, command=command)
    state.phase = V2Phase.INGEST
    persist_v2_run_state(state)

    # --- load_report ---
    if not report_path.exists():
        _set_task(
            state,
            "load_report",
            V2TaskStatus.BLOCKED,
            f"report file not found: {report_path}",
        )
        state.phase = V2Phase.BLOCKED
        state.status = V2TaskStatus.BLOCKED
        state.touch()
        persist_v2_run_state(state)
        return state

    try:
        raw = json.loads(report_path.read_text(encoding="utf-8"))
        report = SentinelFailureReport.model_validate(raw)
    except Exception as exc:
        _set_task(
            state,
            "load_report",
            V2TaskStatus.BLOCKED,
            f"invalid report: {exc}",
        )
        state.phase = V2Phase.BLOCKED
        state.status = V2TaskStatus.BLOCKED
        state.touch()
        persist_v2_run_state(state)
        return state

    report_artifact_path = persist_v2_artifact(
        run_dir,
        "sentinel-report.json",
        report.model_dump(mode="json"),
    )
    state.artifacts.append(str(report_artifact_path))

    triage = report.triage
    fix_branch = f"nc-dev/sentinel-fix-{report.report_id}"
    state.metadata.update({
        "mode": "sentinel-fix",
        "report_id": report.report_id,
        "service_name": report.service.name,
        "git_sha": report.service.git_sha,
        "error_code": report.error.error_code,
        "severity": report.severity.value,
        "source": report.source.value,
        "attempts": 0,
        "max_attempts": triage.max_attempts if triage else max_attempts,
        "auto_deploy": triage.auto_deploy if triage else auto_deploy,
        "fix_branch": fix_branch,
    })

    _set_task(
        state,
        "load_report",
        V2TaskStatus.PASSED,
        f"loaded report {report.report_id} ({report.source.value}/{report.severity.value})",
        artifacts=[str(report_artifact_path)],
    )

    if dry_run:
        state.metadata["dry_run"] = True
        state.phase = V2Phase.COMPLETE
        state.status = V2TaskStatus.PASSED
        state.touch()
        persist_v2_run_state(state)
        return state

    # Non-dry-run: execution phases are future work.
    # Return after load for now.
    state.phase = V2Phase.COMPLETE
    state.status = V2TaskStatus.PASSED
    state.touch()
    persist_v2_run_state(state)
    return state
