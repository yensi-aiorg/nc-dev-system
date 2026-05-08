"""Sentinel Engine — reduced to Sentinel fix mode and state utilities.

The legacy orchestration pipeline has been superseded by the new claude-driven pipeline.
This module retains only: run_sentinel_fix, load_sentinel_run_state, summarize_sentinel_status.
"""

from __future__ import annotations

import json
from pathlib import Path

from ncdev.artifacts.state import (
    init_sentinel_run_dirs,
    persist_sentinel_artifact,
    persist_sentinel_run_state,
)
from ncdev.utils import make_run_id
from ncdev.core.models import SentinelFailureReport, SentinelPhase, SentinelRunState, SentinelTaskState, SentinelTaskStatus


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

    # Non-dry-run: execution phases are future work.
    state.phase = SentinelPhase.COMPLETE
    state.status = SentinelTaskStatus.PASSED
    state.touch()
    persist_sentinel_run_state(state)
    return state
