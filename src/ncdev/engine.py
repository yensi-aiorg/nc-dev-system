from __future__ import annotations

import json
import re
from pathlib import Path

from ncdev.analysis.adjudicator import build_human_questions
from ncdev.analysis.consensus import adjudicate
from ncdev.analysis.discovery import build_change_plan, build_risk_map, discover_repo
from ncdev.analysis.parser import parse_requirements
from ncdev.analysis.runner import run_model_assessments
from ncdev.builder.supervisor import execute_change_plan
from ncdev.config import ensure_default_config
from ncdev.hardener.audit import run_hardening_checks
from ncdev.models import (
    ChangeBatch,
    ChangePlanDoc,
    Phase,
    RunState,
    TaskState,
    TaskStatus,
)
from ncdev.reporter.generate import generate_delivery_report
from ncdev.scaffolder.renderer import scaffold_greenfield_project
from ncdev.preflight import required_commands, run_preflight
from ncdev.state import (
    append_log,
    ensure_schema_files,
    init_run_dirs,
    persist_consensus,
    persist_model_assessment,
    persist_output_doc,
    persist_run_state,
)
from ncdev.tester.pipeline import run_test_pipeline
from ncdev.utils import make_run_id


def _slug(value: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return clean or "project"


def _make_tasks(mode: str) -> list[TaskState]:
    tasks = [TaskState(name="analysis", status=TaskStatus.RUNNING)]
    if mode == "greenfield":
        tasks.append(TaskState(name="scaffold"))
    tasks.extend([TaskState(name="build"), TaskState(name="test"), TaskState(name="harden"), TaskState(name="deliver")])
    return tasks


def _task(state: RunState, name: str) -> TaskState:
    for t in state.tasks:
        if t.name == name:
            return t
    t = TaskState(name=name)
    state.tasks.append(t)
    return t


def _set_task(state: RunState, name: str, status: TaskStatus, msg: str = "") -> None:
    t = _task(state, name)
    t.status = status
    t.message = msg


def _base_state(run_id: str, command: str, mode: str, workspace: Path, run_dir: Path) -> RunState:
    return RunState(
        run_id=run_id,
        command=command,
        mode=mode,
        workspace=str(workspace),
        run_dir=str(run_dir),
        tasks=_make_tasks(mode),
    )


def _build_prompt(mode: str, summary_payload: str) -> str:
    return (
        f"NC Dev System dual-model analysis. Mode: {mode}. "
        "Return concise engineering assessment, risks, and immediate next actions.\n\n"
        f"Input:\n{summary_payload}"
    )


def _gate_consensus(state: RunState, run_dir: Path, prompt: str, dry_run: bool) -> bool:
    config = ensure_default_config(Path(state.workspace))
    assessments = run_model_assessments(prompt, config, Path(state.workspace), dry_run=dry_run)

    for item in assessments:
        path = persist_model_assessment(run_dir, item)
        state.model_outputs.append(str(path))

    consensus = adjudicate(
        assessments,
        config.analysis.consensus.min_agreement_score,
        config.analysis.consensus.min_model_confidence,
    )
    cpath = persist_consensus(run_dir, consensus)
    state.model_outputs.append(str(cpath))

    if consensus.decision != "approved":
        questions = build_human_questions(assessments, consensus)
        qpath = persist_output_doc(run_dir, "human-questions.json", questions.model_dump(mode="json"))
        state.model_outputs.append(str(qpath))
        _set_task(state, "analysis", TaskStatus.BLOCKED, "; ".join(consensus.conflicts) or "consensus gate failed")
        state.phase = Phase.BLOCKED
        state.status = TaskStatus.BLOCKED
        append_log(run_dir, f"consensus blocked: {_task(state, 'analysis').message}")
        persist_run_state(state)
        return False

    _set_task(state, "analysis", TaskStatus.PASSED, "consensus approved")
    append_log(run_dir, "consensus approved")
    persist_run_state(state)
    return True


def _preflight_or_block(state: RunState, run_dir: Path, mode: str, full: bool, dry_run: bool) -> bool:
    if dry_run:
        return True
    req = required_commands(mode=mode, full=full)
    preflight = run_preflight(req)
    persist_output_doc(
        run_dir,
        "preflight.json",
        {"ok": preflight.ok, "required": preflight.required, "missing": preflight.missing},
    )
    if preflight.ok:
        return True
    state.phase = Phase.BLOCKED
    state.status = TaskStatus.BLOCKED
    _set_task(state, "analysis", TaskStatus.BLOCKED, f"missing commands: {', '.join(preflight.missing)}")
    persist_run_state(state)
    return False


def _greenfield_batches_from_features(features: dict) -> ChangePlanDoc:
    batches: list[ChangeBatch] = []
    for idx, feature in enumerate(features.get("features", []), start=1):
        name = feature.get("name", f"feature-{idx}")
        batches.append(
            ChangeBatch(
                id=f"batch-{idx:03d}",
                title=f"Implement {name}",
                changes=[f"Implement {name} across frontend/backend as required."],
                validations=[f"Feature tests for {name} pass."],
                rollback=[f"Revert commits for {name}."],
            )
        )
    if not batches:
        batches.append(
            ChangeBatch(
                id="batch-001",
                title="Implement baseline feature set",
                changes=["Implement baseline product workflow from requirements."],
                validations=["Core smoke tests pass."],
                rollback=["Revert baseline batch commits."],
            )
        )
    return ChangePlanDoc(batches=batches)


def _fix_retest_loop(
    project_path: Path,
    mode: str,
    test_failures: list[str],
    max_retries: int,
    dry_run: bool,
) -> tuple[bool, list[str]]:
    if max_retries <= 0:
        return False, test_failures

    attempts = 0
    failures = test_failures
    while attempts < max_retries and failures:
        attempts += 1
        fix_plan = ChangePlanDoc(
            batches=[
                ChangeBatch(
                    id=f"fix-{attempts:03d}",
                    title="Fix test failures",
                    changes=[f"Address test failures: {', '.join(failures[:3])}"],
                    validations=["Re-run test suite and verify all failures closed."],
                    rollback=["Revert fix commit if regressions occur."],
                )
            ]
        )
        execute_change_plan(
            project_path=project_path,
            mode=mode,
            plan=fix_plan,
            max_retries=max_retries,
            dry_run=dry_run,
        )
        retest = run_test_pipeline(project_path=project_path, dry_run=dry_run)
        failures = retest.failures
        if retest.passed:
            return True, []

    return False, failures


def run_greenfield(
    workspace: Path,
    requirements_path: Path,
    dry_run: bool,
    full: bool,
    command: str = "build",
) -> RunState:
    config = ensure_default_config(workspace)
    ensure_schema_files(workspace)

    run_id = make_run_id("greenfield")
    run_dir = init_run_dirs(workspace, run_id)
    state = _base_state(run_id, command=command, mode="greenfield", workspace=workspace, run_dir=run_dir)
    state.phase = Phase.ANALYZE
    persist_run_state(state)
    if not _preflight_or_block(state, run_dir, mode="greenfield", full=full, dry_run=dry_run):
        return state

    features, architecture, test_plan = parse_requirements(requirements_path)
    features_path = persist_output_doc(run_dir, "features.json", features.model_dump(mode="json"))
    arch_path = persist_output_doc(run_dir, "architecture.json", architecture.model_dump(mode="json"))
    test_plan_path = persist_output_doc(run_dir, "test-plan.json", test_plan.model_dump(mode="json"))
    state.model_outputs.extend([str(features_path), str(arch_path), str(test_plan_path)])

    payload_summary = (
        f"features={len(features.features)}; architecture_components={len(architecture.components)}; "
        f"test_scenarios={len(test_plan.e2e_scenarios)}"
    )
    if not _gate_consensus(state, run_dir, _build_prompt("greenfield", payload_summary), dry_run=dry_run):
        return state

    if not full:
        state.phase = Phase.COMPLETE
        state.status = TaskStatus.PASSED
        state.touch()
        persist_run_state(state)
        return state

    state.phase = Phase.BUILD

    project_name = requirements_path.stem or "generated-project"
    project_path = workspace / ".nc-dev" / "generated" / run_id / _slug(project_name)
    manifest = scaffold_greenfield_project(
        templates_root=workspace / "templates",
        output_dir=project_path,
        project_name=project_name,
        features=features,
        architecture=architecture,
    )
    persist_output_doc(run_dir, "scaffolding-manifest.json", manifest.model_dump(mode="json"))
    _set_task(state, "scaffold", TaskStatus.PASSED, f"scaffolded at {project_path}")

    change_plan = _greenfield_batches_from_features(features.model_dump(mode="json"))
    persist_output_doc(run_dir, "change-plan.json", change_plan.model_dump(mode="json"))

    build_result = execute_change_plan(
        project_path=project_path,
        mode="greenfield",
        plan=change_plan,
        max_retries=config.safety.max_retries,
        dry_run=dry_run,
    )
    persist_output_doc(run_dir, "build-result.json", build_result.model_dump(mode="json"))
    if any(r.status != "passed" for r in build_result.results):
        _set_task(state, "build", TaskStatus.FAILED, "one or more batches failed")
        state.phase = Phase.BLOCKED
        state.status = TaskStatus.FAILED
        state.touch()
        persist_run_state(state)
        return state
    _set_task(state, "build", TaskStatus.PASSED, f"{len(build_result.results)} batches passed")

    state.phase = Phase.TEST
    test_result = run_test_pipeline(project_path=project_path, dry_run=dry_run)
    persist_output_doc(run_dir, "test-result.json", test_result.model_dump(mode="json"))
    if not test_result.passed:
        fixed, remaining = _fix_retest_loop(
            project_path=project_path,
            mode="greenfield",
            test_failures=test_result.failures,
            max_retries=config.safety.max_retries,
            dry_run=dry_run,
        )
        if not fixed:
            _set_task(state, "test", TaskStatus.FAILED, f"test failures remain: {remaining[:2]}")
            state.phase = Phase.BLOCKED
            state.status = TaskStatus.FAILED
            state.touch()
            persist_run_state(state)
            return state
    _set_task(state, "test", TaskStatus.PASSED, "test pipeline passed")

    harden_report = run_hardening_checks(project_path=project_path)
    persist_output_doc(run_dir, "harden-report.json", harden_report.model_dump(mode="json"))
    _set_task(state, "harden", TaskStatus.PASSED, "hardening report generated")

    state.phase = Phase.DELIVER
    delivery = generate_delivery_report(
        run_id=run_id,
        mode="greenfield",
        project_path=project_path,
        output_dir=run_dir / "outputs",
        test_result=test_result,
        harden_report=harden_report,
    )
    persist_output_doc(run_dir, "delivery-report.json", delivery.model_dump(mode="json"))
    _set_task(state, "deliver", TaskStatus.PASSED, "delivery artifacts generated")

    state.phase = Phase.COMPLETE
    state.status = TaskStatus.PASSED
    state.touch()
    persist_run_state(state)
    return state


def run_brownfield(
    workspace: Path,
    repo_path: Path,
    include_paths: list[str],
    exclude_paths: list[str],
    dry_run: bool,
    full: bool,
    command: str = "analyze",
) -> RunState:
    config = ensure_default_config(workspace)
    ensure_schema_files(workspace)

    run_id = make_run_id("brownfield")
    run_dir = init_run_dirs(workspace, run_id)
    state = _base_state(run_id, command=command, mode="brownfield", workspace=workspace, run_dir=run_dir)
    state.phase = Phase.ANALYZE
    persist_run_state(state)
    if not _preflight_or_block(state, run_dir, mode="brownfield", full=full, dry_run=dry_run):
        return state

    inventory = discover_repo(repo_path, include_paths=include_paths, exclude_paths=exclude_paths)
    risk_map = build_risk_map(inventory)
    change_plan = build_change_plan(inventory, risk_map)

    inv_path = persist_output_doc(run_dir, "repo-inventory.json", inventory.model_dump(mode="json"))
    risk_path = persist_output_doc(run_dir, "risk-map.json", risk_map.model_dump(mode="json"))
    cp_path = persist_output_doc(run_dir, "change-plan.json", change_plan.model_dump(mode="json"))
    state.model_outputs.extend([str(inv_path), str(risk_path), str(cp_path)])

    payload_summary = (
        f"languages={inventory.detected_languages}; package_managers={inventory.package_managers}; "
        f"risks={len(risk_map.risks)}; batches={len(change_plan.batches)}"
    )
    if not _gate_consensus(state, run_dir, _build_prompt("brownfield", payload_summary), dry_run=dry_run):
        return state

    if not full:
        state.phase = Phase.COMPLETE
        state.status = TaskStatus.PASSED
        state.touch()
        persist_run_state(state)
        return state

    state.phase = Phase.BUILD
    build_result = execute_change_plan(
        project_path=repo_path,
        mode="brownfield",
        plan=change_plan,
        max_retries=config.safety.max_retries,
        dry_run=dry_run,
    )
    persist_output_doc(run_dir, "build-result.json", build_result.model_dump(mode="json"))
    if any(r.status != "passed" for r in build_result.results):
        _set_task(state, "build", TaskStatus.FAILED, "one or more batches failed")
        state.phase = Phase.BLOCKED
        state.status = TaskStatus.FAILED
        state.touch()
        persist_run_state(state)
        return state
    _set_task(state, "build", TaskStatus.PASSED, f"{len(build_result.results)} batches passed")

    state.phase = Phase.TEST
    test_result = run_test_pipeline(project_path=repo_path, dry_run=dry_run)
    persist_output_doc(run_dir, "test-result.json", test_result.model_dump(mode="json"))
    if not test_result.passed:
        fixed, remaining = _fix_retest_loop(
            project_path=repo_path,
            mode="brownfield",
            test_failures=test_result.failures,
            max_retries=config.safety.max_retries,
            dry_run=dry_run,
        )
        if not fixed:
            _set_task(state, "test", TaskStatus.FAILED, f"test failures remain: {remaining[:2]}")
            state.phase = Phase.BLOCKED
            state.status = TaskStatus.FAILED
            state.touch()
            persist_run_state(state)
            return state
    _set_task(state, "test", TaskStatus.PASSED, "test pipeline passed")

    harden_report = run_hardening_checks(project_path=repo_path)
    persist_output_doc(run_dir, "harden-report.json", harden_report.model_dump(mode="json"))
    _set_task(state, "harden", TaskStatus.PASSED, "hardening report generated")

    state.phase = Phase.DELIVER
    delivery = generate_delivery_report(
        run_id=run_id,
        mode="brownfield",
        project_path=repo_path,
        output_dir=run_dir / "outputs",
        test_result=test_result,
        harden_report=harden_report,
    )
    persist_output_doc(run_dir, "delivery-report.json", delivery.model_dump(mode="json"))
    _set_task(state, "deliver", TaskStatus.PASSED, "delivery artifacts generated")

    state.phase = Phase.COMPLETE
    state.status = TaskStatus.PASSED
    state.touch()
    persist_run_state(state)
    return state


def load_run_state(workspace: Path, run_id: str) -> RunState:
    path = workspace / ".nc-dev" / "runs" / run_id / "run-state.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return RunState.model_validate(data)


def summarize_status(state: RunState) -> str:
    task_summary = ",".join([f"{t.name}:{t.status.value}" for t in state.tasks])
    return (
        f"run_id={state.run_id} phase={state.phase.value} status={state.status.value} "
        f"mode={state.mode} tasks={task_summary}"
    )


def deliver_for_run(workspace: Path, run_id: str) -> Path:
    run_state = load_run_state(workspace, run_id)
    run_dir = Path(run_state.run_dir)
    report = run_dir / "outputs" / "delivery-report.json"
    if report.exists():
        return report

    summary = {
        "run_id": run_id,
        "mode": run_state.mode,
        "summary": "No delivery report exists yet for this run.",
    }
    return persist_output_doc(run_dir, "delivery-report.json", summary)
