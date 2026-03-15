import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ncdev.intake_api import create_app

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "sentinel_reports"


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    app = create_app(workspace=tmp_path, api_key="test-key")
    return TestClient(app)


def test_health_endpoint(client: TestClient) -> None:
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["active_runs"] == 0
    assert data["queued"] == 0


def test_post_report_requires_auth(client: TestClient) -> None:
    raw = json.loads((FIXTURES_DIR / "backend_error.json").read_text())
    resp = client.post("/api/v1/reports", json=raw)
    assert resp.status_code == 401


def test_post_report_accepts_valid_report(client: TestClient) -> None:
    raw = json.loads((FIXTURES_DIR / "backend_error.json").read_text())
    resp = client.post(
        "/api/v1/reports",
        json=raw,
        headers={"Authorization": "Bearer test-key"},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["accepted"] is True
    assert "run_id" in data
    assert data["status"] == "queued"
    assert "status_url" in data


def test_post_report_rejects_invalid_schema(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/reports",
        json={"not": "valid"},
        headers={"Authorization": "Bearer test-key"},
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data["accepted"] is False


def test_get_run_status_after_post(client: TestClient) -> None:
    raw = json.loads((FIXTURES_DIR / "backend_error.json").read_text())
    post_resp = client.post(
        "/api/v1/reports",
        json=raw,
        headers={"Authorization": "Bearer test-key"},
    )
    run_id = post_resp.json()["run_id"]
    get_resp = client.get(f"/api/v1/runs/{run_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == "queued"


def test_get_run_status_not_found(client: TestClient) -> None:
    resp = client.get("/api/v1/runs/nonexistent")
    assert resp.status_code == 404


def test_get_run_result_not_found(client: TestClient) -> None:
    resp = client.get("/api/v1/runs/nonexistent/result")
    assert resp.status_code == 404


def test_no_auth_when_no_key(tmp_path: Path) -> None:
    app = create_app(workspace=tmp_path, api_key="")
    client = TestClient(app)
    raw = json.loads((FIXTURES_DIR / "backend_error.json").read_text())
    resp = client.post("/api/v1/reports", json=raw)
    assert resp.status_code == 202
