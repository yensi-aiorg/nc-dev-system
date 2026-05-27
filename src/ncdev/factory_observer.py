"""Operator-facing factory run summaries and status rendering."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


SUMMARY_JSON = "factory-summary.json"
SUMMARY_MD = "factory-summary.md"
SPEND_LEDGER = "spend-ledger.jsonl"


@dataclass
class ResumePreflight:
    ok: bool
    run_dir: Path
    target_repo: Path
    stop_reason: str = "unknown"
    last_pipeline_status: str = "unknown"
    cycles_run: int = 0
    failed_feature_ids: list[str] = field(default_factory=list)
    dirty_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    resume_command: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "run_dir": str(self.run_dir),
            "target_repo": str(self.target_repo),
            "stop_reason": self.stop_reason,
            "last_pipeline_status": self.last_pipeline_status,
            "cycles_run": self.cycles_run,
            "failed_feature_ids": self.failed_feature_ids,
            "dirty_files": self.dirty_files,
            "warnings": self.warnings,
            "blockers": self.blockers,
            "resume_command": self.resume_command,
        }


def render_resume_preflight(preflight: ResumePreflight) -> str:
    lines = [
        "# Factory Resume Preflight",
        "",
        f"- Result: {'ok' if preflight.ok else 'blocked'}",
        f"- Run: {preflight.run_dir}",
        f"- Target: {preflight.target_repo}",
        f"- Previous stop reason: {preflight.stop_reason}",
        f"- Previous pipeline status: {preflight.last_pipeline_status}",
        f"- Previous cycles: {preflight.cycles_run}",
        f"- Failed feature ids: {', '.join(preflight.failed_feature_ids) or '(none found)'}",
    ]
    if preflight.dirty_files:
        lines.extend(["", "## Dirty Target Files", ""])
        lines.extend(f"- `{line}`" for line in preflight.dirty_files[:20])
    if preflight.blockers:
        lines.extend(["", "## Blockers", ""])
        lines.extend(f"- {blocker}" for blocker in preflight.blockers)
    if preflight.warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- {warning}" for warning in preflight.warnings)
    if preflight.ok:
        lines.extend(["", "## Resume Command", "", f"`{preflight.resume_command}`"])
    lines.append("")
    return "\n".join(lines)


def find_latest_run_dir(workspace: Path) -> Path | None:
    runs_dir = workspace / ".nc-dev" / "runs"
    if not runs_dir.exists():
        return None
    candidates = [p for p in runs_dir.iterdir() if p.is_dir()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def find_latest_run_for_target(
    workspace: Path,
    target_repo: Path,
) -> Path | None:
    """Return the most recent run dir whose state.json points at ``target_repo``.

    Used by factory auto-resume to find a usable prior charter when the
    user relaunches the factory against the same project (typical after
    fixing an nc-dev-system bug and restarting). Returns None if no
    prior run targets this repo OR if none have a loadable charter.
    """
    runs_dir = workspace / ".nc-dev" / "runs"
    if not runs_dir.exists():
        return None
    target_resolved = str(target_repo.resolve())
    matches: list[Path] = []
    for candidate in runs_dir.iterdir():
        if not candidate.is_dir():
            continue
        state_path = candidate / "state.json"
        if not state_path.exists():
            continue
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if state.get("target_path") != target_resolved:
            continue
        # Must have a full charter on disk to be resumable; an empty
        # or partial outputs/ directory is no better than a fresh
        # charter.
        outputs = candidate / "outputs"
        required = (
            "feature-queue.json",
            "target-project-contract.json",
            "verification-contract.json",
        )
        if not all((outputs / name).exists() for name in required):
            continue
        matches.append(candidate)
    if not matches:
        return None
    return max(matches, key=lambda p: p.stat().st_mtime)


def _git_status_short(repo: Path) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ["<git status unavailable>"]
    if result.returncode != 0:
        return ["<not a git repository or status failed>"]
    return [line for line in result.stdout.splitlines() if line.strip()]


def _state_failed_feature_ids(run_dir: Path) -> list[str]:
    state_path = run_dir / "state.json"
    if not state_path.exists():
        return []
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    failed: list[str] = []
    for step in state.get("completed_steps", []) or []:
        status = str(step.get("status", "")).lower()
        if status in {"failed", "blocked", "repairing", "building", "verifying"}:
            feature_id = str(step.get("feature_id", "")).strip()
            if feature_id:
                failed.append(feature_id)
    return failed


def resume_preflight(
    *,
    run_dir: Path,
    target_repo: Path,
    source_path: Path,
    force: bool = False,
) -> ResumePreflight:
    summary = load_factory_status(run_dir)
    stop_reason = str(summary.get("stop_reason") or "unknown")
    dirty_files = _git_status_short(target_repo)
    failed_feature_ids = _state_failed_feature_ids(run_dir)
    blockers: list[str] = []
    warnings: list[str] = []
    summary_target = str(summary.get("target_path") or "")
    target_repo_str = str(target_repo.resolve())

    if dirty_files:
        blockers.append(
            "target repository has uncommitted changes; commit/stash them "
            "or rerun with --force-resume"
        )
    if summary_target and Path(summary_target).resolve() != target_repo.resolve():
        blockers.append(
            "resume target does not match the previous factory target "
            f"({summary_target})"
        )
    if stop_reason == "steward_continue_at_end":
        blockers.append("previous run already completed successfully")
    if stop_reason == "unmetered_spend_blocked":
        blockers.append(
            "previous run did not start because unmetered spend was blocked"
        )
    if stop_reason in {"too_many_failures", "steward_unrecoverable"}:
        blockers.append(
            "previous stop reason requires human inspection before resume"
        )
    if stop_reason == "test_craftr_unavailable":
        warnings.append("verify TestCraftr is healthy before resuming")
    if stop_reason == "budget_exhausted":
        warnings.append("increase max cycles or spend cap before resuming")
    if stop_reason == "wall_time_exhausted":
        warnings.append("increase --max-wall-time-minutes before resuming")
    if not failed_feature_ids and stop_reason not in {
        "budget_exhausted",
        "wall_time_exhausted",
        "test_craftr_unavailable",
    }:
        warnings.append("no failed feature ids were found in state.json")

    if force and blockers:
        warnings.extend(f"forced past blocker: {blocker}" for blocker in blockers)
        blockers = []

    resume_command = (
        "ncdev factory "
        f"--source {source_path.resolve()} "
        f"--target-repo {target_repo_str} "
        f"--resume-charter {run_dir.resolve()}"
    )
    return ResumePreflight(
        ok=not blockers,
        run_dir=run_dir,
        target_repo=target_repo,
        stop_reason=stop_reason,
        last_pipeline_status=str(summary.get("last_pipeline_status") or "unknown"),
        cycles_run=int(summary.get("cycles_run") or 0),
        failed_feature_ids=failed_feature_ids,
        dirty_files=dirty_files,
        warnings=warnings,
        blockers=blockers,
        resume_command=resume_command,
    )


def read_spend_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            rows.append({"status": "unreadable", "raw": line})
    return rows


def spend_summary(run_dir: Path) -> dict[str, Any]:
    rows = read_spend_ledger(run_dir / SPEND_LEDGER)
    metered_cost = 0.0
    unmetered_events = 0
    blocked_events = 0
    for row in rows:
        cost = row.get("cost_usd")
        if isinstance(cost, int | float):
            metered_cost += float(cost)
        if row.get("metered") is False:
            unmetered_events += 1
        if row.get("status") == "blocked":
            blocked_events += 1
    return {
        "event_count": len(rows),
        "metered_cost_usd": round(metered_cost, 4),
        "unmetered_events": unmetered_events,
        "blocked_events": blocked_events,
        "ledger_path": str(run_dir / SPEND_LEDGER) if rows else "",
    }


def stop_diagnostics(
    *,
    stop_reason: str | None,
    run_dir: Path | None,
    source_path: str,
    target_path: str,
) -> dict[str, Any]:
    reason = stop_reason or "unknown"
    resume = ""
    if run_dir and source_path and target_path:
        resume = (
            "ncdev factory "
            f"--source {source_path} "
            f"--target-repo {target_path} "
            f"--resume-charter {run_dir}"
        )

    table: dict[str, tuple[str, list[str]]] = {
        "steward_continue_at_end": (
            "The Steward accepted the product at the end of the queue.",
            ["No recovery needed. Inspect the run report and verification evidence."],
        ),
        "steward_unrecoverable": (
            "The Steward or charter mutation marked the run unrecoverable.",
            [
                "Open the latest steward response under <run>/steward/.",
                "Tighten the PRD or charter, then resume against the run charter.",
            ],
        ),
        "test_craftr_unavailable": (
            "Required TestCraftr verification could not produce usable evidence.",
            [
                "Check the local TestCraftr runner path and the target app URL.",
                "Rerun with --require-test-craftr after the verifier is healthy.",
            ],
        ),
        "budget_exhausted": (
            "The run exhausted its cycle or metered spend budget.",
            [
                "Inspect spend-ledger.jsonl and failed feature reports.",
                "Resume with a larger cap only after scoping the remaining failures.",
            ],
        ),
        "wall_time_exhausted": (
            "The factory-level wall-clock cap stopped the run.",
            [
                "Inspect the latest cycle before extending the time cap.",
                "Resume with --resume-charter and a larger --max-wall-time-minutes.",
            ],
        ),
        "too_many_failures": (
            "The consecutive-failure breaker stopped a repeated repair loop.",
            [
                "Inspect the latest Steward reasoning and failed step logs.",
                "Fix the blocking cause or rewrite the charter before resuming.",
            ],
        ),
        "unmetered_spend_blocked": (
            "A budgeted run would use an agent path without reliable cost telemetry.",
            [
                "Rerun with --allow-unmetered if that risk is intentional.",
                "Alternatively switch the config mode to claude_only for metered sessions.",
            ],
        ),
    }
    headline, actions = table.get(
        reason,
        (
            "The run stopped for a reason this version does not classify.",
            ["Inspect factory-summary.json, state.json, and spend-ledger.jsonl."],
        ),
    )
    if resume and reason not in {
        "steward_continue_at_end",
        "unmetered_spend_blocked",
    }:
        actions.append(f"Resume command: {resume}")
    return {
        "headline": headline,
        "next_actions": actions,
        "resume_command": resume,
    }


def write_factory_summary(run_dir: Path, payload: dict[str, Any]) -> dict[str, Path]:
    run_dir.mkdir(parents=True, exist_ok=True)
    json_path = run_dir / SUMMARY_JSON
    md_path = run_dir / SUMMARY_MD
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    md_path.write_text(render_factory_status(payload), encoding="utf-8")
    return {"json": json_path, "markdown": md_path}


def load_factory_status(run_dir: Path) -> dict[str, Any]:
    summary_path = run_dir / SUMMARY_JSON
    if summary_path.exists():
        return json.loads(summary_path.read_text(encoding="utf-8"))

    state_path = run_dir / "state.json"
    state: dict[str, Any] = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            state = {"status": "unreadable"}
    spend = spend_summary(run_dir)
    return {
        "run_dir": str(run_dir),
        "stop_reason": state.get("status", "unknown"),
        "last_pipeline_status": state.get("status", "unknown"),
        "cycles_run": 0,
        "recorded_cost_usd": spend["metered_cost_usd"],
        "spend": spend,
        "diagnosis": stop_diagnostics(
            stop_reason=state.get("status"),
            run_dir=run_dir,
            source_path="",
            target_path=state.get("target_path", ""),
        ),
        "fallback": "factory-summary.json was missing; rendered from raw artifacts",
    }


def render_factory_status(summary: dict[str, Any]) -> str:
    diagnosis = summary.get("diagnosis") or {}
    spend = summary.get("spend") or {}
    lines = [
        f"# Factory status - {Path(summary.get('run_dir', '')).name or 'unknown'}",
        "",
        f"- Stop reason: {summary.get('stop_reason', 'unknown')}",
        f"- Diagnosis: {diagnosis.get('headline', 'unknown')}",
        f"- Cycles: {summary.get('cycles_run', 0)}",
        f"- Last pipeline status: {summary.get('last_pipeline_status', '')}",
        f"- Consecutive failures: {summary.get('consecutive_failures', 0)}",
        f"- Metered cost: ${summary.get('recorded_cost_usd', 0.0):.4f}",
        f"- Spend events: {spend.get('event_count', 0)}",
        f"- Unmetered events: {spend.get('unmetered_events', 0)}",
        "",
        "## Next Actions",
        "",
    ]
    actions = diagnosis.get("next_actions") or []
    lines.extend(f"- {action}" for action in actions)
    decisions = summary.get("decisions") or []
    if decisions:
        lines.extend(["", "## Steward Decisions", ""])
        for decision in decisions[-5:]:
            lines.append(
                f"- {decision.get('disposition', 'unknown')}: "
                f"{decision.get('reasoning', '')[:240]}"
            )
    reports = summary.get("verification_reports") or []
    if reports:
        lines.extend(["", "## Verification Reports", ""])
        lines.extend(f"- {report}" for report in reports[-5:])
    lines.append("")
    return "\n".join(lines)
