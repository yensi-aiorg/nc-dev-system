from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from ncdev.monitoring.api import build_snapshot, create_monitor_app
from ncdev.monitoring.events import MonitorEventWriter, normalize_ai_event


def test_monitor_event_writer_is_best_effort_jsonl(tmp_path: Path):
    writer = MonitorEventWriter(tmp_path / "run-1", run_id="run-1")

    writer.emit("phase_started", phase="charter", message="Charter started")

    events_path = tmp_path / "run-1" / "events.jsonl"
    row = json.loads(events_path.read_text(encoding="utf-8").splitlines()[0])
    assert row["run_id"] == "run-1"
    assert row["type"] == "phase_started"
    assert row["phase"] == "charter"
    assert row["message"] == "Charter started"


def test_normalize_ai_event_extracts_files_codex_and_tests():
    raw = {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "tool_use", "name": "Edit", "input": {"file_path": "src/app.py"}},
                {
                    "type": "tool_use",
                    "name": "Bash",
                    "input": {"command": "codex exec --full-auto 'build tests'"},
                },
                {
                    "type": "tool_use",
                    "name": "Bash",
                    "input": {"command": "pytest tests/test_app.py"},
                },
            ],
        },
    }

    types = [event["type"] for event in normalize_ai_event(raw)]

    assert types == ["file_edit", "codex_invocation", "test_command"]


def test_build_snapshot_includes_current_feature_behavior_and_test_files(tmp_path: Path):
    workspace = tmp_path / "ws"
    run_dir = workspace / ".nc-dev" / "runs" / "run-1"
    outputs = run_dir / "outputs"
    outputs.mkdir(parents=True)
    target = tmp_path / "target"
    target.mkdir()
    (target / ".git").mkdir()
    (run_dir / "state.json").write_text(
        json.dumps({
            "run_id": "run-1",
            "status": "running",
            "phase": "building",
            "target_path": str(target),
            "current_step": "f1",
            "completed_features": 0,
            "total_features": 1,
        }),
        encoding="utf-8",
    )
    (outputs / "feature-queue.json").write_text(
        json.dumps({
            "features": [{
                "feature_id": "f1",
                "title": "Login",
                "description": "Build login",
                "acceptance_criteria": ["Reject bad credentials"],
            }],
        }),
        encoding="utf-8",
    )
    (outputs / "behavior-contract.v1.json").write_text(
        json.dumps({"scenarios": [{"id": "s1", "feature_id": "f1", "title": "Bad login fails"}]}),
        encoding="utf-8",
    )
    MonitorEventWriter(run_dir).emit("feature_started", feature_id="f1", message="f1")

    snapshot = build_snapshot(run_dir)

    assert snapshot["summary"]["current_step"] == "f1"
    assert snapshot["current_feature"]["title"] == "Login"
    assert snapshot["behavior_targets"][0]["title"] == "Bad login fails"
    assert snapshot["events"][0]["type"] == "feature_started"


def test_monitor_app_serves_latest_snapshot(tmp_path: Path):
    run_dir = tmp_path / ".nc-dev" / "runs" / "run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "state.json").write_text(
        json.dumps({"run_id": "run-1", "status": "running", "phase": "charter"}),
        encoding="utf-8",
    )

    app = create_monitor_app(workspace=tmp_path)
    client = TestClient(app)

    assert client.get("/").status_code == 200
    body = client.get("/api/v1/monitor/runs/latest").json()
    assert body["run_id"] == "run-1"
    assert body["summary"]["phase"] == "charter"
