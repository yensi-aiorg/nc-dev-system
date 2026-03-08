import json
from pathlib import Path

from ncdev.v2.ui import build_run_snapshot, render_run_dashboard


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_build_run_snapshot_collects_state_and_logs(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "v2-test"
    _write_json(
        run_dir / "run-state.json",
        {
            "run_id": "v2-test",
            "command": "full-v2",
            "phase": "discovery",
            "status": "running",
            "tasks": [{"name": "discovery", "status": "passed", "message": "ok"}],
        },
    )
    _write_json(
        run_dir / "logs" / "job-status.json",
        {
            "job_id": "job-1",
            "title": "Implement auth",
            "provider": "openai_codex",
            "model": "gpt-5.3",
            "status": "running",
        },
    )
    _write_json(
        run_dir / "outputs" / "job-queue.json",
        {
            "jobs": [
                {"provider": "openai_codex", "model": "gpt-5.3"},
                {"provider": "anthropic_claude_code", "model": "opus-4.6"},
            ]
        },
    )
    _write_json(
        run_dir / "outputs" / "job-run-log.json",
        {
            "records": [
                {"job_id": "job-0", "provider": "openai_codex", "status": "passed"}
            ]
        },
    )
    _write_json(
        run_dir / "outputs" / "evidence-index.json",
        {
            "screenshots": ["one.png", "two.png"],
            "reports": ["report.html"],
            "videos": ["video.webm"],
            "traces": [],
        },
    )
    live_log = run_dir / "logs" / "jobs" / "job-1-codex-stdout.log"
    live_log.parent.mkdir(parents=True, exist_ok=True)
    live_log.write_text("line one\nline two\n", encoding="utf-8")

    snapshot = build_run_snapshot(run_dir)

    assert snapshot.run_id == "v2-test"
    assert snapshot.active_job["job_id"] == "job-1"
    assert snapshot.provider_counts["openai_codex:gpt-5.3"] == 1
    assert snapshot.evidence_counts["screenshots"] == 2
    assert snapshot.latest_log_lines[-1] == "line two"


def test_render_run_dashboard_returns_renderable(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "v2-test"
    _write_json(
        run_dir / "run-state.json",
        {
            "run_id": "v2-test",
            "command": "execute-v2",
            "phase": "complete",
            "status": "passed",
            "tasks": [],
        },
    )
    renderable = render_run_dashboard(build_run_snapshot(run_dir))
    assert renderable is not None
