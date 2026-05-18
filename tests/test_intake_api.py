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


def _fix_result_dict(run_id: str) -> dict[str, object]:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    return {
        "report_id": "rep-xyz",
        "run_id": run_id,
        "schema_version": "1.0",
        "outcome": "fixed",
        "outcome_detail": "verified locally",
        "pr_url": None,
        "fix_branch": None,
        "commit_sha": "deadbeef",
        "files_changed": ["app.py"],
        "reproduction_test": "tests/test_repro.py",
        "agent_reasoning": None,
        "fix_description": "null guard",
        "attempts_used": 1,
        "max_attempts": 3,
        "duration_seconds": 12,
        "started_at": now,
        "completed_at": now,
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


def test_status_endpoint_returns_clean_shape(tmp_path):
    def fake_runner(**kw):
        from ncdev.core.models import SentinelRunState

        st = SentinelRunState(
            run_id=kw["run_id"],
            workspace=str(tmp_path),
            run_dir=str(tmp_path),
            command="fix",
        )
        st.metadata["fix_result"] = _fix_result_dict(kw["run_id"])
        return st

    app = create_app(workspace=tmp_path, fix_runner=fake_runner)
    client = TestClient(app)
    run_id = client.post("/api/v1/reports", json=_valid_report_body()).json()["run_id"]
    _wait_status(client, run_id, "complete")

    body = client.get(f"/api/v1/runs/{run_id}").json()

    assert body["status"] == "complete"
    assert body["outcome"] == "fixed"
    assert body["error"] is None
    assert "run_state" not in body


def test_result_409_while_running(tmp_path):
    import threading

    release = threading.Event()

    def fake_runner(**kw):
        release.wait(timeout=2)
        from ncdev.core.models import SentinelRunState

        st = SentinelRunState(
            run_id=kw["run_id"],
            workspace=str(tmp_path),
            run_dir=str(tmp_path),
            command="fix",
        )
        st.metadata["fix_result"] = _fix_result_dict(kw["run_id"])
        return st

    app = create_app(workspace=tmp_path, fix_runner=fake_runner)
    client = TestClient(app)
    run_id = client.post("/api/v1/reports", json=_valid_report_body()).json()["run_id"]
    _wait_status(client, run_id, "running")

    try:
        response = client.get(f"/api/v1/runs/{run_id}/result")
        assert response.status_code == 409
        assert response.json() == {"status": "running", "detail": "run not complete"}
    finally:
        release.set()


def test_result_returns_full_fix_result_when_complete(tmp_path):
    def fake_runner(**kw):
        from ncdev.core.models import SentinelRunState

        st = SentinelRunState(
            run_id=kw["run_id"],
            workspace=str(tmp_path),
            run_dir=str(tmp_path),
            command="fix",
        )
        st.metadata["fix_result"] = _fix_result_dict(kw["run_id"])
        return st

    app = create_app(workspace=tmp_path, fix_runner=fake_runner)
    client = TestClient(app)
    run_id = client.post("/api/v1/reports", json=_valid_report_body()).json()["run_id"]
    _wait_status(client, run_id, "complete")

    response = client.get(f"/api/v1/runs/{run_id}/result")
    body = response.json()

    assert response.status_code == 200
    assert body["status"] == "complete"
    assert body["outcome"] == "fixed"
    assert body["commit_sha"] == "deadbeef"
    assert body["reproduction_test"] == "tests/test_repro.py"


def test_result_failed_run_returns_error(tmp_path):
    def fake_runner(**kw):
        raise RuntimeError("explode")

    app = create_app(workspace=tmp_path, fix_runner=fake_runner)
    client = TestClient(app)
    run_id = client.post("/api/v1/reports", json=_valid_report_body()).json()["run_id"]
    _wait_status(client, run_id, "failed")

    response = client.get(f"/api/v1/runs/{run_id}/result")

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert "explode" in response.json()["error"]
    assert response.json()["result"] is None


def test_list_runs_endpoint(tmp_path):
    def fake_runner(**kw):
        from ncdev.core.models import SentinelRunState

        st = SentinelRunState(
            run_id=kw["run_id"],
            workspace=str(tmp_path),
            run_dir=str(tmp_path),
            command="fix",
        )
        st.metadata["fix_result"] = _fix_result_dict(kw["run_id"])
        return st

    app = create_app(workspace=tmp_path, fix_runner=fake_runner)
    client = TestClient(app)
    body1 = _valid_report_body()
    body2 = dict(body1, report_id="rep-2")

    client.post("/api/v1/reports", json=body1)
    client.post("/api/v1/reports", json=body2)

    runs = client.get("/api/v1/runs").json()["runs"]

    assert len(runs) == 2
    assert all("status" in run for run in runs)
    assert all("run_state" not in run for run in runs)


def test_unknown_run_404(tmp_path):
    app = create_app(workspace=tmp_path, fix_runner=lambda **kw: None)
    client = TestClient(app)

    assert client.get("/api/v1/runs/nope").status_code == 404
    assert client.get("/api/v1/runs/nope/result").status_code == 404


def test_get_endpoints_require_auth_when_configured(tmp_path):
    app = create_app(workspace=tmp_path, api_key="secret", fix_runner=lambda **kw: None)
    client = TestClient(app)

    assert client.get("/api/v1/runs").status_code == 401
    assert client.get("/api/v1/runs/nope").status_code == 401
    assert client.get("/api/v1/runs/nope/result").status_code == 401


def test_invalid_report_rejected(tmp_path):
    app = create_app(workspace=tmp_path, fix_runner=lambda **kw: None)
    client = TestClient(app)

    response = client.post("/api/v1/reports", json={"bad": "shape"})

    assert response.status_code == 400
