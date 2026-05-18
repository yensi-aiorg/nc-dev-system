"""Sentinel Engine — reduced to Sentinel fix mode and state utilities.

The legacy orchestration pipeline has been superseded by the new claude-driven pipeline.
This module retains only: run_sentinel_fix, load_sentinel_run_state, summarize_sentinel_status.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from ncdev.artifacts.state import (
    init_sentinel_run_dirs,
    persist_sentinel_artifact,
    persist_sentinel_run_state,
)
from ncdev.core.config import (
    NCDevConfig,
    SentinelServiceConfig,
    UnknownServiceError,
    load_config,
    resolve_service,
    validate_service_for_deploy,
)
from ncdev.core.models import (
    FixOutcome,
    SentinelFailureReport,
    SentinelFixResult,
    SentinelPhase,
    SentinelRunState,
    SentinelTaskState,
    SentinelTaskStatus,
)
from ncdev.core.sentinel_callback import send_fix_result
from ncdev.core.sentinel_deploy import (
    open_and_merge_to_staging,
    rollback_if_unsafe,
    verify_on_staging,
)
from ncdev.core.sentinel_safety import SentinelSafetyGate
from ncdev.factory import run_factory_with_bundle
from ncdev.sentinel_charter import synthesize_charter_from_sentinel_report
from ncdev.sentinel_reproduce import _run_test_file, reproduce_failure
from ncdev.utils import make_run_id


def _set_task(state: SentinelRunState, name: str, status: SentinelTaskStatus, message: str = "", artifacts: list[str] | None = None) -> None:
    for task in state.tasks:
        if task.name == name:
            task.status = status
            task.message = message
            if artifacts is not None:
                task.artifacts = artifacts
            return
    state.tasks.append(
        SentinelTaskState(
            name=name,
            status=status,
            message=message,
            artifacts=artifacts or [],
        )
    )


def _base_fix_state(run_id: str, workspace: Path, run_dir: Path, command: str) -> SentinelRunState:
    return SentinelRunState(
        run_id=run_id,
        command=command,
        workspace=str(workspace),
        run_dir=str(run_dir),
        tasks=[
            SentinelTaskState(name="load_report", status=SentinelTaskStatus.RUNNING),
            SentinelTaskState(name="checkout_version"),
            SentinelTaskState(name="reproduce"),
            SentinelTaskState(name="fix"),
            SentinelTaskState(name="validate"),
            SentinelTaskState(name="submit"),
        ],
    )


def load_sentinel_run_state(workspace: Path, run_id: str) -> SentinelRunState:
    path = workspace / ".nc-dev" / "runs" / run_id / "run-state.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return SentinelRunState.model_validate(data)


def summarize_sentinel_status(state: SentinelRunState) -> str:
    task_summary = ",".join([f"{task.name}:{task.status.value}" for task in state.tasks])
    return (
        f"run_id={state.run_id} phase={state.phase.value} status={state.status.value} "
        f"tasks={task_summary}"
    )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _persist_progress(
    state: SentinelRunState,
    *,
    phase: SentinelPhase | None = None,
) -> None:
    if phase is not None:
        state.phase = phase
    state.touch()
    persist_sentinel_run_state(state)


def _run_git(
    args: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _git_failure_message(action: str, result: subprocess.CompletedProcess[str]) -> str:
    output = "\n".join(
        part.strip() for part in (result.stdout, result.stderr) if part.strip()
    )
    if not output:
        output = f"git exited with status {result.returncode}"
    return f"{action} failed: {output}"


def _clone_and_checkout(
    *,
    svc: SentinelServiceConfig,
    report: SentinelFailureReport,
    checkout_dir: Path,
    fix_branch: str,
) -> tuple[bool, str]:
    clone_source = svc.repo_clone_url.strip() or svc.repo_path.strip()
    if not clone_source:
        return False, "service has neither repo_clone_url nor repo_path configured"

    checkout_dir.parent.mkdir(parents=True, exist_ok=True)
    clone_result = _run_git(["clone", clone_source, str(checkout_dir)], timeout=600)
    if clone_result.returncode != 0:
        return False, _git_failure_message("git clone", clone_result)

    checkout_result = _run_git(
        ["checkout", report.service.git_sha],
        cwd=checkout_dir,
        timeout=120,
    )
    if checkout_result.returncode != 0:
        return False, _git_failure_message("git checkout", checkout_result)

    branch_result = _run_git(
        ["checkout", "-b", fix_branch],
        cwd=checkout_dir,
        timeout=120,
    )
    if branch_result.returncode != 0:
        return False, _git_failure_message("git checkout -b", branch_result)

    return True, ""


def _git_head(repo_dir: Path) -> str | None:
    result = _run_git(["rev-parse", "HEAD"], cwd=repo_dir, timeout=30)
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def _diff_scope(repo_dir: Path, base_sha: str) -> tuple[int, int, list[str], str]:
    stat_result = _run_git(["diff", "--stat", f"{base_sha}..HEAD"], cwd=repo_dir)
    if stat_result.returncode != 0:
        return 0, 0, [], _git_failure_message("git diff --stat", stat_result)

    numstat_result = _run_git(["diff", "--numstat", f"{base_sha}..HEAD"], cwd=repo_dir)
    if numstat_result.returncode != 0:
        return 0, 0, [], _git_failure_message("git diff --numstat", numstat_result)

    paths: list[str] = []
    lines_changed = 0
    for line in numstat_result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        added, deleted, path = parts[0], parts[1], parts[2]
        paths.append(path)
        if added.isdigit():
            lines_changed += int(added)
        if deleted.isdigit():
            lines_changed += int(deleted)

    return len(paths), lines_changed, paths, stat_result.stdout.strip()


def _rerun_reproduction_test(repo_dir: Path, test_path: str) -> tuple[bool, str]:
    if not test_path:
        return False, "reproduction did not provide a test path"
    return _run_test_file(repo_dir, test_path)


def _build_fix_result(
    *,
    report: SentinelFailureReport,
    run_id: str,
    outcome: FixOutcome,
    outcome_detail: str,
    commit_sha: str | None,
    files_changed: list[str],
    reproduction_test: str | None,
    attempts_used: int,
    max_attempts: int,
    started_at: datetime,
    pr_url: str | None = None,
    fix_branch: str | None = None,
    completed_at: datetime | None = None,
) -> SentinelFixResult:
    completed = completed_at or _utc_now()
    return SentinelFixResult(
        report_id=report.report_id,
        run_id=run_id,
        outcome=outcome,
        outcome_detail=outcome_detail,
        pr_url=pr_url,
        fix_branch=fix_branch,
        commit_sha=commit_sha,
        files_changed=files_changed,
        reproduction_test=reproduction_test,
        attempts_used=attempts_used,
        max_attempts=max_attempts,
        duration_seconds=max(0, int((completed - started_at).total_seconds())),
        started_at=started_at,
        completed_at=completed,
    )


def _persist_fix_result(
    *,
    state: SentinelRunState,
    run_dir: Path,
    result: SentinelFixResult,
) -> Path:
    result_path = persist_sentinel_artifact(
        run_dir,
        "fix-result.json",
        result.model_dump(mode="json"),
    )
    state.artifacts.append(str(result_path))
    state.metadata["fix_result"] = result.model_dump(mode="json")
    return result_path


def run_sentinel_fix(
    workspace: Path,
    report_path: Path,
    target_repo_path: Path,
    dry_run: bool,
    *,
    auto_deploy: bool = False,
    max_attempts: int = 3,
    command: str = "fix",
    run_id: str | None = None,
    safety_gate: SentinelSafetyGate | None = None,
    config: NCDevConfig | None = None,
    callback_url: str = "",
    callback_api_key: str = "",
) -> SentinelRunState:
    run_id = run_id or make_run_id("sentinel-fix")
    run_dir = init_sentinel_run_dirs(workspace, run_id)
    state = _base_fix_state(run_id, workspace=workspace, run_dir=run_dir, command=command)
    state.phase = SentinelPhase.INGEST
    persist_sentinel_run_state(state)

    # --- load_report ---
    if not report_path.exists():
        _set_task(
            state,
            "load_report",
            SentinelTaskStatus.BLOCKED,
            f"report file not found: {report_path}",
        )
        state.phase = SentinelPhase.BLOCKED
        state.status = SentinelTaskStatus.BLOCKED
        state.touch()
        persist_sentinel_run_state(state)
        return state

    try:
        raw = json.loads(report_path.read_text(encoding="utf-8"))
        report = SentinelFailureReport.model_validate(raw)
    except Exception as exc:
        _set_task(
            state,
            "load_report",
            SentinelTaskStatus.BLOCKED,
            f"invalid report: {exc}",
        )
        state.phase = SentinelPhase.BLOCKED
        state.status = SentinelTaskStatus.BLOCKED
        state.touch()
        persist_sentinel_run_state(state)
        return state

    report_artifact_path = persist_sentinel_artifact(
        run_dir,
        "sentinel-report.json",
        report.model_dump(mode="json"),
    )
    state.artifacts.append(str(report_artifact_path))

    triage = report.triage
    fix_branch = f"sentinel/fix/{report.report_id}"
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
        SentinelTaskStatus.PASSED,
        f"loaded report {report.report_id} ({report.source.value}/{report.severity.value})",
        artifacts=[str(report_artifact_path)],
    )

    if dry_run:
        state.metadata["dry_run"] = True
        state.phase = SentinelPhase.COMPLETE
        state.status = SentinelTaskStatus.PASSED
        state.touch()
        persist_sentinel_run_state(state)
        return state

    config = config or load_config(workspace)
    callback_cfg = config.sentinel.callback
    callback_url = callback_url or (callback_cfg.url if callback_cfg.enabled else "")
    callback_api_key = callback_api_key or callback_cfg.api_key
    gate = safety_gate or SentinelSafetyGate()
    started_at = state.started_at
    max_fix_attempts = triage.max_attempts if triage else max_attempts
    checkout_dir = run_dir / "checkout"
    repro_test_path: str | None = None
    files_changed: list[str] = []
    attempts_used = 0

    def finish(
        *,
        outcome: FixOutcome,
        detail: str,
        task_name: str,
        task_status: SentinelTaskStatus,
        phase: SentinelPhase | None = None,
        commit_sha: str | None = None,
        pr_url: str | None = None,
        result_fix_branch: str | None = None,
        record_outcome: bool = True,
    ) -> SentinelRunState:
        _set_task(state, task_name, task_status, detail)
        if task_name == "clone":
            _set_task(state, "checkout_version", task_status, detail)
        if task_name == "verify":
            _set_task(state, "validate", task_status, detail)

        result = _build_fix_result(
            report=report,
            run_id=run_id,
            outcome=outcome,
            outcome_detail=detail,
            commit_sha=commit_sha,
            files_changed=files_changed,
            reproduction_test=repro_test_path,
            attempts_used=attempts_used,
            max_attempts=max_fix_attempts,
            started_at=started_at,
            pr_url=pr_url,
            fix_branch=result_fix_branch,
        )
        result_path = _persist_fix_result(
            state=state,
            run_dir=run_dir,
            result=result,
        )

        if callback_url:
            sent = send_fix_result(
                result=result,
                callback_url=callback_url,
                api_key=callback_api_key,
                retry_count=callback_cfg.retry_count,
                retry_delay_seconds=callback_cfg.retry_delay_seconds,
            )
            callback_status = (
                SentinelTaskStatus.PASSED if sent else SentinelTaskStatus.FAILED
            )
            _set_task(
                state,
                "callback",
                callback_status,
                "callback sent" if sent else "callback failed",
                artifacts=[str(result_path)],
            )
            _set_task(state, "submit", callback_status, "callback sent" if sent else "callback failed")
        else:
            _set_task(
                state,
                "callback",
                SentinelTaskStatus.PASSED,
                "no callback configured",
                artifacts=[str(result_path)],
            )
            _set_task(state, "submit", SentinelTaskStatus.PASSED, "no callback configured")

        if record_outcome:
            gate.record_outcome(report, success=(outcome == FixOutcome.FIXED))

        state.phase = phase or (
            SentinelPhase.BLOCKED
            if outcome in {FixOutcome.BLOCKED, FixOutcome.CHECKOUT_FAILED}
            else SentinelPhase.COMPLETE
        )
        state.status = (
            SentinelTaskStatus.PASSED
            if outcome == FixOutcome.FIXED
            else (
                SentinelTaskStatus.BLOCKED
                if outcome in {FixOutcome.BLOCKED, FixOutcome.CHECKOUT_FAILED}
                else SentinelTaskStatus.FAILED
            )
        )
        state.touch()
        persist_sentinel_run_state(state)
        return state

    _set_task(state, "resolve_service", SentinelTaskStatus.RUNNING)
    _persist_progress(state, phase=SentinelPhase.DISCOVERY)
    try:
        svc = resolve_service(report.service.name, config)
    except UnknownServiceError as exc:
        return finish(
            outcome=FixOutcome.BLOCKED,
            detail=str(exc),
            task_name="resolve_service",
            task_status=SentinelTaskStatus.BLOCKED,
            phase=SentinelPhase.BLOCKED,
        )

    _set_task(state, "resolve_service", SentinelTaskStatus.PASSED, "service resolved")
    _persist_progress(state)

    _set_task(state, "safety_preflight", SentinelTaskStatus.RUNNING)
    _persist_progress(state)
    verdict = gate.preflight(report)
    if not verdict.allowed:
        return finish(
            outcome=FixOutcome.BLOCKED,
            detail=verdict.reason,
            task_name="safety_preflight",
            task_status=SentinelTaskStatus.BLOCKED,
            phase=SentinelPhase.BLOCKED,
        )
    _set_task(state, "safety_preflight", SentinelTaskStatus.PASSED, "safety preflight passed")
    _persist_progress(state)

    _set_task(state, "claim", SentinelTaskStatus.RUNNING)
    gate.claim(report, run_id)
    _set_task(state, "claim", SentinelTaskStatus.PASSED, "run claimed")
    _persist_progress(state)

    try:
        _set_task(state, "clone", SentinelTaskStatus.RUNNING)
        _set_task(state, "checkout_version", SentinelTaskStatus.RUNNING)
        _persist_progress(state)
        cloned, clone_message = _clone_and_checkout(
            svc=svc,
            report=report,
            checkout_dir=checkout_dir,
            fix_branch=fix_branch,
        )
        if not cloned:
            return finish(
                outcome=FixOutcome.CHECKOUT_FAILED,
                detail=clone_message,
                task_name="clone",
                task_status=SentinelTaskStatus.FAILED,
                phase=SentinelPhase.BLOCKED,
            )
        _set_task(
            state,
            "clone",
            SentinelTaskStatus.PASSED,
            f"checked out {report.service.git_sha} on {fix_branch}",
        )
        _set_task(
            state,
            "checkout_version",
            SentinelTaskStatus.PASSED,
            f"checked out {report.service.git_sha} on {fix_branch}",
        )
        _persist_progress(state)

        _set_task(state, "reproduce", SentinelTaskStatus.RUNNING)
        _persist_progress(state)
        repro = reproduce_failure(
            report,
            checkout_dir,
            config=config,
            model=None,
            timeout=1800,
            max_budget_usd=None,
        )
        repro_test_path = repro.test_path or None
        if repro_test_path:
            state.metadata["reproduction_test"] = repro_test_path
        if not repro.reproduced:
            return finish(
                outcome=FixOutcome.CANNOT_REPRODUCE,
                detail=repro.reason or "production failure could not be reproduced",
                task_name="reproduce",
                task_status=SentinelTaskStatus.FAILED,
                commit_sha=_git_head(checkout_dir),
            )
        _set_task(
            state,
            "reproduce",
            SentinelTaskStatus.PASSED,
            repro.reason or "reproduction test fails as required",
            artifacts=[repro_test_path] if repro_test_path else None,
        )
        _persist_progress(state)

        _set_task(state, "fix", SentinelTaskStatus.RUNNING)
        _persist_progress(state)
        try:
            bundle = synthesize_charter_from_sentinel_report(
                report,
                svc,
                checkout_dir,
                reproduction_test_path=repro_test_path,
            )
            factory_state = run_factory_with_bundle(
                workspace=workspace,
                bundle=bundle,
                target_repo_path=checkout_dir,
                source_label=report_path,
                max_cycles=max_fix_attempts,
                builder_model=None,
                builder_timeout=3600,
                max_budget_usd=None,
                config=config,
            )
        except Exception as exc:
            return finish(
                outcome=FixOutcome.FIX_FAILED,
                detail=f"factory fix failed: {exc}",
                task_name="fix",
                task_status=SentinelTaskStatus.FAILED,
                commit_sha=_git_head(checkout_dir),
            )
        attempts_used = factory_state.cycles_run
        state.metadata["attempts"] = attempts_used
        _set_task(
            state,
            "fix",
            SentinelTaskStatus.PASSED,
            f"factory completed {attempts_used} cycle(s)",
        )
        _persist_progress(state)

        _set_task(state, "verify", SentinelTaskStatus.RUNNING)
        _set_task(state, "validate", SentinelTaskStatus.RUNNING)
        _persist_progress(state)
        repro_passed, repro_output = _rerun_reproduction_test(
            checkout_dir,
            repro_test_path or "",
        )
        head_sha = _git_head(checkout_dir)
        files_count, lines_changed, changed_paths, diff_detail = _diff_scope(
            checkout_dir,
            report.service.git_sha,
        )
        files_changed = changed_paths
        state.metadata.update({
            "files_changed": files_count,
            "lines_changed": lines_changed,
            "changed_paths": changed_paths,
        })

        if not repro_passed:
            detail = repro_output or "reproduction test still fails after fix"
            return finish(
                outcome=FixOutcome.FIX_FAILED,
                detail=detail,
                task_name="verify",
                task_status=SentinelTaskStatus.FAILED,
                commit_sha=head_sha,
            )

        if diff_detail.startswith("git diff"):
            return finish(
                outcome=FixOutcome.VALIDATION_FAILED,
                detail=diff_detail,
                task_name="verify",
                task_status=SentinelTaskStatus.FAILED,
                commit_sha=head_sha,
            )

        scope = gate.check_scope(
            files_count,
            lines_changed,
            changed_paths,
            extra_protected=svc.protected_files,
        )
        if not scope.allowed:
            return finish(
                outcome=FixOutcome.VALIDATION_FAILED,
                detail=scope.reason,
                task_name="verify",
                task_status=SentinelTaskStatus.FAILED,
                commit_sha=head_sha,
                result_fix_branch=fix_branch,
            )

        _set_task(
            state,
            "verify",
            SentinelTaskStatus.PASSED,
            "fix verified locally",
        )
        _set_task(
            state,
            "validate",
            SentinelTaskStatus.PASSED,
            "fix verified locally",
        )
        _set_task(state, "deploy", SentinelTaskStatus.RUNNING)
        _persist_progress(state)

        deploy_violations = validate_service_for_deploy(svc)
        if deploy_violations:
            detail = (
                "fix verified locally; staging deploy skipped - incomplete service "
                f"config: {'; '.join(deploy_violations)}"
            )
            return finish(
                outcome=FixOutcome.FIXED,
                detail=detail,
                task_name="deploy",
                task_status=SentinelTaskStatus.PASSED,
                commit_sha=head_sha,
                result_fix_branch=fix_branch,
            )

        deploy_result = open_and_merge_to_staging(
            checkout_dir,
            svc,
            report,
            fix_branch,
            commit_sha=head_sha or "",
        )
        state.metadata["deploy_result"] = asdict(deploy_result)
        if not deploy_result.merged:
            detail = deploy_result.error or "staging PR did not merge"
            return finish(
                outcome=FixOutcome.VALIDATION_FAILED,
                detail=detail,
                task_name="deploy",
                task_status=SentinelTaskStatus.FAILED,
                commit_sha=head_sha,
                pr_url=deploy_result.pr_url or None,
                result_fix_branch=deploy_result.fix_branch or fix_branch,
            )

        deploy_status = (
            SentinelTaskStatus.PASSED
            if deploy_result.deployed
            else SentinelTaskStatus.FAILED
        )
        _set_task(
            state,
            "deploy",
            deploy_status,
            "staging deploy completed"
            if deploy_result.deployed
            else deploy_result.error or "staging deploy failed",
        )
        _set_task(state, "staging_verify", SentinelTaskStatus.RUNNING)
        _persist_progress(state)

        staging = verify_on_staging(
            checkout_dir,
            svc,
            reproduction_test=repro_test_path or "",
        )
        state.metadata["staging_verification"] = asdict(staging)
        _set_task(
            state,
            "staging_verify",
            SentinelTaskStatus.PASSED
            if staging.verified
            else SentinelTaskStatus.FAILED,
            staging.detail,
        )
        _persist_progress(state)

        rollback = rollback_if_unsafe(
            checkout_dir,
            svc,
            deploy_result,
            staging_verified=staging.verified,
        )
        if rollback is not None:
            state.metadata["rollback_result"] = asdict(rollback)
            _set_task(
                state,
                "rollback",
                SentinelTaskStatus.PASSED if rollback.ok else SentinelTaskStatus.FAILED,
                "rollback succeeded" if rollback.ok else rollback.error or "rollback failed",
            )
            _persist_progress(state)

        if deploy_result.deployed and staging.verified:
            return finish(
                outcome=FixOutcome.FIXED,
                detail="fix verified locally and on staging",
                task_name="staging_verify",
                task_status=SentinelTaskStatus.PASSED,
                commit_sha=head_sha,
                pr_url=deploy_result.pr_url or None,
                result_fix_branch=deploy_result.fix_branch or fix_branch,
            )

        failures: list[str] = []
        if not deploy_result.deployed:
            failures.append(
                f"staging deploy failed: {deploy_result.error or 'deploy command failed'}"
            )
        if not staging.verified:
            failures.append(
                f"staging verification failed: {staging.detail or 'verification failed'}"
            )
        if rollback is not None:
            failures.append(f"rollback ok={rollback.ok}")
        return finish(
            outcome=FixOutcome.VALIDATION_FAILED,
            detail="; ".join(failures) or "staging validation failed",
            task_name="staging_verify",
            task_status=SentinelTaskStatus.FAILED,
            commit_sha=head_sha,
            pr_url=deploy_result.pr_url or None,
            result_fix_branch=deploy_result.fix_branch or fix_branch,
        )
    finally:
        gate.release(report)

    return state
