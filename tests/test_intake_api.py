import json
import time
from pathlib import Path

from fastapi.testclient import TestClient

from ncdev.intake_api import create_app


def _valid_report_body() -> dict[str, object]:
    """Minimal valid SentinelFailureReport as a dict."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    return {
        "report_id": "rep-xyz",
        "service": {
            "name": "svc",
            "version": "1",
            "git_sha": "abc",
            "git_repo": "git@github.com:o/svc.git",
        },
        "source": "backend",
        "severity": "high",
        "error": {"error_type": "ERR", "error_code": "E1", "message": "boom"},
        "frequency": {"last_hour": 1, "last_24h": 1, "first_seen": now},
        "context": {},
        "detected_at": now,
    }


def _wait_status(client: TestClient, run_id: str, target: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/api/v1/runs/{run_id}")
        body = response.json()
        if body.get("status") == target:
            return body
        time.sleep(0.05)
    raise AssertionError(f"run {run_id} never reached {target}")


def test_post_report_persists_report_file(tmp_path):
    captured = {}

    def fake_runner(**kw):
        captured["report_path"] = kw["report_path"]
        from ncdev.core.models import SentinelRunState

        state = SentinelRunState(
            run_id=kw["run_id"],
            workspace=str(tmp_path),
            run_dir=str(tmp_path),
            command="fix",
        )
        state.metadata["fix_result"] = {"outcome": "fixed"}
        return state

    app = create_app(workspace=tmp_path, fix_runner=fake_runner)
    client = TestClient(app)

    response = client.post("/api/v1/reports", json=_valid_report_body())
    assert response.status_code == 202
    run_id = response.json()["run_id"]
    _wait_status(client, run_id, "complete")

    report_path = Path(captured["report_path"])
    assert report_path.exists()
    assert json.loads(report_path.read_text(encoding="utf-8"))["report_id"] == "rep-xyz"


def test_run_transitions_queued_running_complete(tmp_path):
    import threading

    release = threading.Event()

    def fake_runner(**kw):
        release.wait(timeout=2)
        from ncdev.core.models import SentinelRunState

        state = SentinelRunState(
            run_id=kw["run_id"],
            workspace=str(tmp_path),
            run_dir=str(tmp_path),
            command="fix",
        )
        state.metadata["fix_result"] = {"outcome": "fixed"}
        return state

    app = create_app(workspace=tmp_path, fix_runner=fake_runner)
    client = TestClient(app)
    run_id = client.post("/api/v1/reports", json=_valid_report_body()).json()["run_id"]

    _wait_status(client, run_id, "running")
    release.set()
    final = _wait_status(client, run_id, "complete")

    assert final["status"] == "complete"


def test_failed_runner_marks_run_failed(tmp_path):
    def fake_runner(**kw):
        raise RuntimeError("kaboom")

    app = create_app(workspace=tmp_path, fix_runner=fake_runner)
    client = TestClient(app)
    run_id = client.post("/api/v1/reports", json=_valid_report_body()).json()["run_id"]

    entry = _wait_status(client, run_id, "failed")

    assert "kaboom" in entry.get("error", "")


def test_invalid_report_rejected(tmp_path):
    app = create_app(workspace=tmp_path, fix_runner=lambda **kw: None)
    client = TestClient(app)

    response = client.post("/api/v1/reports", json={"bad": "shape"})

    assert response.status_code == 400
