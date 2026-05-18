"""Minimal HTTP API for receiving Sentinel failure reports.

Start: ncdev serve --port 16650
"""
from __future__ import annotations

import json
import threading
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ncdev.core.config import NCDevConfig, load_config
from ncdev.core.engine import run_sentinel_fix
from ncdev.core.models import SentinelFailureReport, _utc_now
from ncdev.core.sentinel_safety import SentinelSafetyGate


def create_app(
    *,
    workspace: Path,
    api_key: str = "",
    fix_runner: Callable[..., Any] = run_sentinel_fix,
) -> FastAPI:
    workspace = Path(workspace)
    run_registry: dict[str, dict[str, Any]] = {}
    lock = threading.Lock()
    try:
        config = load_config(workspace)
    except Exception:  # noqa: BLE001
        config = NCDevConfig()
    max_concurrent = max(1, int(config.sentinel.intake.max_concurrent_runs))
    executor = ThreadPoolExecutor(max_workers=max_concurrent)
    shared_gate = SentinelSafetyGate()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:  # noqa: ARG001
        try:
            yield
        finally:
            executor.shutdown(wait=False)

    app = FastAPI(title="NC Dev System — Sentinel Intake API", lifespan=lifespan)

    def _check_auth(request: Request) -> None:
        if not api_key:
            return
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {api_key}":
            raise HTTPException(status_code=401, detail="Unauthorized")

    def _execute(run_id: str, report_path: Path) -> None:
        with lock:
            run_registry[run_id]["status"] = "running"
            run_registry[run_id]["started_at"] = _utc_now().isoformat()
        try:
            state = fix_runner(
                workspace=workspace,
                report_path=report_path,
                target_repo_path=workspace,
                dry_run=False,
                run_id=run_id,
                safety_gate=shared_gate,
                config=config,
            )
            with lock:
                entry = run_registry[run_id]
                entry["status"] = "complete"
                entry["completed_at"] = _utc_now().isoformat()
                entry["result"] = state.metadata.get("fix_result", {})
                entry["run_state"] = state.model_dump(mode="json")
        except Exception as exc:  # noqa: BLE001
            with lock:
                entry = run_registry[run_id]
                entry["status"] = "failed"
                entry["completed_at"] = _utc_now().isoformat()
                entry["error"] = str(exc)

    @app.get("/api/v1/health")
    def health() -> dict[str, Any]:
        with lock:
            active = sum(1 for r in run_registry.values() if r.get("status") == "running")
            queued = sum(1 for r in run_registry.values() if r.get("status") == "queued")
        return {
            "status": "healthy",
            "active_runs": active,
            "queued": queued,
            "max_concurrent": max_concurrent,
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
        report_path = workspace / ".nc-dev" / "intake" / run_id / "report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        with lock:
            run_registry[run_id] = {
                "run_id": run_id,
                "report_id": report.report_id,
                "status": "queued",
                "queued_at": _utc_now().isoformat(),
                "report_path": str(report_path),
            }
        executor.submit(_execute, run_id, report_path)

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
            if entry is not None:
                entry = dict(entry)
        if entry is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return entry

    @app.get("/api/v1/runs/{run_id}/result")
    def get_run_result(run_id: str) -> dict[str, Any]:
        with lock:
            entry = run_registry.get(run_id)
            if entry is not None:
                entry = dict(entry)
        if entry is None:
            raise HTTPException(status_code=404, detail="Run not found")
        if entry.get("status") != "complete":
            raise HTTPException(status_code=404, detail="Run not complete")
        return entry.get("result", {})

    return app
