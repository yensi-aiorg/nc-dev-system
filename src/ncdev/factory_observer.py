"""Operator-facing factory run summaries and status rendering."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SUMMARY_JSON = "factory-summary.json"
SUMMARY_MD = "factory-summary.md"
SPEND_LEDGER = "spend-ledger.jsonl"


def find_latest_run_dir(workspace: Path) -> Path | None:
    runs_dir = workspace / ".nc-dev" / "runs"
    if not runs_dir.exists():
        return None
    candidates = [p for p in runs_dir.iterdir() if p.is_dir()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


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
