from __future__ import annotations

import json
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


@dataclass
class RunSnapshot:
    run_id: str
    command: str = ""
    phase: str = "init"
    status: str = "running"
    tasks: list[dict[str, str]] = field(default_factory=list)
    active_job: dict[str, str] = field(default_factory=dict)
    job_records: list[dict[str, Any]] = field(default_factory=list)
    repair_records: list[dict[str, Any]] = field(default_factory=list)
    provider_counts: dict[str, int] = field(default_factory=dict)
    verification_summary: dict[str, Any] = field(default_factory=dict)
    evidence_counts: dict[str, int] = field(default_factory=dict)
    latest_log_path: str = ""
    latest_log_lines: list[str] = field(default_factory=list)


def _safe_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _tail_lines(path: Path, limit: int = 16) -> list[str]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return lines[-limit:]


def _latest_log_file(run_dir: Path) -> Path | None:
    logs_dir = run_dir / "logs"
    if not logs_dir.exists():
        return None
    candidates = [path for path in logs_dir.rglob("*") if path.is_file()]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def build_run_snapshot(run_dir: Path) -> RunSnapshot:
    run_state = _safe_json(run_dir / "run-state.json")
    outputs_dir = run_dir / "outputs"
    live_job_state = _safe_json(run_dir / "logs" / "job-status.json")
    job_run_log = _safe_json(outputs_dir / "job-run-log.json")
    repair_run_log = _safe_json(outputs_dir / "repair-run-log.json")
    verification_run = _safe_json(outputs_dir / "verification-run.json")
    evidence_index = _safe_json(outputs_dir / "evidence-index.json")

    provider_counter: Counter[str] = Counter()
    for queue_name in ("job-queue.json", "repair-queue.json"):
        queue_doc = _safe_json(outputs_dir / queue_name)
        for job in queue_doc.get("jobs", []):
            provider = str(job.get("provider", "unknown")).strip() or "unknown"
            model = str(job.get("model", "unknown")).strip() or "unknown"
            provider_counter[f"{provider}:{model}"] += 1

    latest_log = _latest_log_file(run_dir)
    return RunSnapshot(
        run_id=str(run_state.get("run_id", run_dir.name)),
        command=str(run_state.get("command", "")),
        phase=str(run_state.get("phase", "init")),
        status=str(run_state.get("status", "running")),
        tasks=[
            {
                "name": str(task.get("name", "")),
                "status": str(task.get("status", "")),
                "message": str(task.get("message", "")),
            }
            for task in run_state.get("tasks", [])
        ],
        active_job={
            "job_id": str(live_job_state.get("job_id", "")),
            "title": str(live_job_state.get("title", "")),
            "provider": str(live_job_state.get("provider", "")),
            "model": str(live_job_state.get("model", "")),
            "queue_name": str(live_job_state.get("queue_name", "")),
            "status": str(live_job_state.get("status", "")),
        },
        job_records=list(job_run_log.get("records", [])),
        repair_records=list(repair_run_log.get("records", [])),
        provider_counts=dict(provider_counter),
        verification_summary=dict(verification_run.get("summary", {})),
        evidence_counts={
            "screenshots": len(evidence_index.get("screenshots", [])),
            "reports": len(evidence_index.get("reports", [])),
            "videos": len(evidence_index.get("videos", [])),
            "traces": len(evidence_index.get("traces", [])),
        },
        latest_log_path=str(latest_log) if latest_log else "",
        latest_log_lines=_tail_lines(latest_log) if latest_log else [],
    )


def _status_style(value: str) -> str:
    lowered = value.lower()
    if lowered in {"passed", "ready_for_human_review"}:
        return "green"
    if lowered in {"failed", "blocked", "hold"}:
        return "red"
    if lowered in {"running", "simulation_only"}:
        return "yellow"
    return "cyan"


def render_run_dashboard(snapshot: RunSnapshot) -> RenderableType:
    summary = Table.grid(expand=True)
    summary.add_column(ratio=1)
    summary.add_column(ratio=1)
    summary.add_column(ratio=1)
    summary.add_row(
        f"[bold]Run[/bold]\n{snapshot.run_id}",
        f"[bold]Command[/bold]\n{snapshot.command or '-'}",
        f"[bold]Phase[/bold]\n[{_status_style(snapshot.phase)}]{snapshot.phase}[/{_status_style(snapshot.phase)}]",
    )
    summary.add_row(
        f"[bold]Status[/bold]\n[{_status_style(snapshot.status)}]{snapshot.status}[/{_status_style(snapshot.status)}]",
        f"[bold]Jobs[/bold]\n{len(snapshot.job_records)} done / {len(snapshot.job_records) + len(snapshot.repair_records)} total recorded",
        f"[bold]Artifacts[/bold]\nshots {snapshot.evidence_counts.get('screenshots', 0)}  reports {snapshot.evidence_counts.get('reports', 0)}",
    )

    task_table = Table(expand=True)
    task_table.add_column("Task", style="bold")
    task_table.add_column("Status", width=10)
    task_table.add_column("Message")
    for task in snapshot.tasks[-8:]:
        task_table.add_row(
            task["name"],
            f"[{_status_style(task['status'])}]{task['status']}[/{_status_style(task['status'])}]",
            task["message"] or "-",
        )
    if not snapshot.tasks:
        task_table.add_row("waiting", "pending", "run state not written yet")

    agent_table = Table(expand=True)
    agent_table.add_column("Agent Pool", style="bold")
    agent_table.add_column("Count", justify="right")
    if snapshot.provider_counts:
        for provider, count in sorted(snapshot.provider_counts.items()):
            agent_table.add_row(provider, str(count))
    else:
        agent_table.add_row("pending", "0")
    if snapshot.active_job.get("job_id"):
        agent_table.add_row(
            "active",
            f"{snapshot.active_job.get('job_id')} ({snapshot.active_job.get('provider')})",
        )

    records_table = Table(expand=True)
    records_table.add_column("Job", style="bold")
    records_table.add_column("Provider")
    records_table.add_column("Status", width=10)
    recent_records = (snapshot.job_records + snapshot.repair_records)[-6:]
    if recent_records:
        for record in recent_records:
            status = str(record.get("status", ""))
            records_table.add_row(
                str(record.get("job_id", "")),
                str(record.get("provider", "")),
                f"[{_status_style(status)}]{status}[/{_status_style(status)}]",
            )
    elif snapshot.active_job.get("job_id"):
        records_table.add_row(
            snapshot.active_job.get("job_id", ""),
            snapshot.active_job.get("provider", ""),
            f"[yellow]{snapshot.active_job.get('status') or 'running'}[/yellow]",
        )
    else:
        records_table.add_row("waiting", "-", "pending")

    log_text = Text()
    if snapshot.latest_log_lines:
        for line in snapshot.latest_log_lines:
            log_text.append(line.rstrip() + "\n")
    else:
        log_text.append("No live logs yet.\n")

    log_title = snapshot.latest_log_path or "log tail"
    if snapshot.active_job.get("title"):
        log_title = f"{snapshot.active_job.get('title')} | {log_title}"

    return Group(
        Panel(summary, title="NC Dev Live Run", border_style="cyan"),
        Panel(task_table, title="Pipeline Tasks", border_style="blue"),
        Panel(agent_table, title="Agents / Queues", border_style="magenta"),
        Panel(records_table, title="Recent Jobs", border_style="green"),
        Panel(log_text, title=log_title, border_style="yellow"),
    )


def watch_run_dashboard(
    run_dir: Path,
    stop_event: threading.Event,
    *,
    console: Console | None = None,
    refresh_per_second: int = 4,
) -> None:
    local_console = console or Console()
    with Live(console=local_console, refresh_per_second=refresh_per_second, transient=False) as live:
        while not stop_event.is_set():
            live.update(render_run_dashboard(build_run_snapshot(run_dir)))
            time.sleep(1 / max(1, refresh_per_second))
        live.update(render_run_dashboard(build_run_snapshot(run_dir)))
