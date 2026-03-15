"""Minimal HTTP API for receiving Sentinel failure reports.

Start: ncdev serve --port 16650
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ncdev.v2.models import SentinelFailureReport, _utc_now


def create_app(
    *,
    workspace: Path,
    api_key: str = "",
) -> FastAPI:
    app = FastAPI(title="NC Dev System — Sentinel Intake API")
    run_registry: dict[str, dict[str, Any]] = {}
    lock = threading.Lock()

    def _check_auth(request: Request) -> None:
        if not api_key:
            return
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {api_key}":
            raise HTTPException(status_code=401, detail="Unauthorized")

    @app.get("/api/v1/health")
    def health() -> dict[str, Any]:
        with lock:
            active = sum(1 for r in run_registry.values() if r.get("status") == "running")
            queued = sum(1 for r in run_registry.values() if r.get("status") == "queued")
        return {
            "status": "healthy",
            "active_runs": active,
            "queued": queued,
        }

    @app.post("/api/v1/reports", status_code=202)
    def post_report(request: Request, body: dict[str, Any]) -> JSONResponse:
        _check_auth(request)
        try:
            report = SentinelFailureReport.model_validate(body)
        except ValidationError as exc:
            return JSONResponse(
                status_code=400,
                content={
                    "accepted": False,
                    "error": "Invalid report schema",
                    "details": [str(e["msg"]) for e in exc.errors()],
                },
            )

        run_id = f"fix-{report.report_id}-{_utc_now().strftime('%Y%m%d-%H%M%S')}"
        with lock:
            run_registry[run_id] = {
                "run_id": run_id,
                "report_id": report.report_id,
                "status": "queued",
                "queued_at": _utc_now().isoformat(),
            }

        return JSONResponse(
            status_code=202,
            content={
                "accepted": True,
                "run_id": run_id,
                "status": "queued",
                "status_url": f"/api/v1/runs/{run_id}",
            },
        )

    @app.get("/api/v1/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        with lock:
            entry = run_registry.get(run_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return entry

    @app.get("/api/v1/runs/{run_id}/result")
    def get_run_result(run_id: str) -> dict[str, Any]:
        with lock:
            entry = run_registry.get(run_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="Run not found")
        if entry.get("status") != "complete":
            raise HTTPException(status_code=404, detail="Run not complete")
        return entry.get("result", {})

    return app
