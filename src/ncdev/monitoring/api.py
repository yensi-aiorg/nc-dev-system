"""HTTP API and static dashboard for live NC Dev run monitoring."""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response, StreamingResponse

from ncdev.factory_observer import find_latest_run_dir
from ncdev.monitoring.events import EVENTS_JSONL


def create_monitor_app(*, workspace: Path, run_dir: Path | None = None) -> FastAPI:
    workspace = Path(workspace).resolve()
    fixed_run_dir = Path(run_dir).resolve() if run_dir is not None else None
    app = FastAPI(title="NC Dev Live Monitor")

    def _resolve_run_dir(run_id: str | None = None) -> Path:
        if run_id and run_id != "latest":
            candidate = workspace / ".nc-dev" / "runs" / run_id
            if not candidate.exists():
                raise HTTPException(status_code=404, detail="Run not found")
            return candidate
        if fixed_run_dir is not None:
            return fixed_run_dir
        latest = find_latest_run_dir(workspace)
        if latest is None:
            raise HTTPException(status_code=404, detail="No NC Dev runs found")
        return latest

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return DASHBOARD_HTML

    @app.get("/favicon.ico")
    def favicon() -> Response:
        return Response(status_code=204)

    @app.get("/api/v1/monitor/runs")
    def list_runs() -> dict[str, Any]:
        root = workspace / ".nc-dev" / "runs"
        if not root.exists():
            return {"runs": []}
        runs = []
        for candidate in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            if not candidate.is_dir():
                continue
            state = _read_json(candidate / "state.json")
            runs.append({
                "run_id": candidate.name,
                "run_dir": str(candidate),
                "status": state.get("status", "unknown"),
                "phase": state.get("phase", ""),
                "current_step": state.get("current_step", ""),
                "updated_at": state.get("updated_at", ""),
            })
        return {"runs": runs}

    @app.get("/api/v1/monitor/runs/latest")
    def latest_run() -> dict[str, Any]:
        return build_snapshot(_resolve_run_dir())

    @app.get("/api/v1/monitor/runs/{run_id}/state")
    def run_state(run_id: str) -> dict[str, Any]:
        return build_snapshot(_resolve_run_dir(run_id))

    @app.get("/api/v1/monitor/runs/{run_id}/events")
    def run_events(run_id: str, limit: int = 250) -> dict[str, Any]:
        run = _resolve_run_dir(run_id)
        return {"run_id": run.name, "events": read_events(run, limit=max(1, min(limit, 1000)))}

    @app.get("/api/v1/monitor/runs/{run_id}/stream")
    async def event_stream(run_id: str) -> StreamingResponse:
        async def generate():
            last_seen = ""
            first = True
            while True:
                run = _resolve_run_dir(run_id)
                snapshot = build_snapshot(run, event_limit=80)
                events = snapshot.get("events") or []
                newest = events[-1].get("id", "") if events else ""
                if first or newest != last_seen:
                    first = False
                    last_seen = newest
                    yield f"data: {json.dumps(snapshot)}\n\n"
                await asyncio.sleep(1.0)

        return StreamingResponse(generate(), media_type="text/event-stream")

    return app


def build_snapshot(run_dir: Path, *, event_limit: int = 250) -> dict[str, Any]:
    run_dir = Path(run_dir)
    state = _read_json(run_dir / "state.json")
    outputs = run_dir / "outputs"
    feature_queue = _read_json(outputs / "feature-queue.json")
    behavior = _read_json(outputs / "behavior-contract.v1.json")
    current_step = str(state.get("current_step") or "")
    target_path = Path(state.get("target_path") or "") if state.get("target_path") else None
    features = feature_queue.get("features") or []
    current_feature = next(
        (feature for feature in features if feature.get("feature_id") == current_step),
        {},
    )
    events = read_events(run_dir, limit=event_limit)
    file_changes = _git_status(target_path) if target_path else []
    active = _active_agent_count(state, events)
    test_files = [
        item for item in file_changes
        if _looks_like_test_path(item.get("path", ""))
    ]

    return {
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "state": state,
        "summary": {
            "phase": state.get("phase", ""),
            "status": state.get("status", "unknown"),
            "current_step": current_step,
            "completed_features": state.get("completed_features", 0),
            "total_features": state.get("total_features", len(features)),
            "active_agents": active,
        },
        "features": features,
        "current_feature": current_feature,
        "behavior_targets": _behavior_targets(behavior, current_step),
        "file_changes": file_changes,
        "test_files": test_files,
        "events": events,
        "codex_logs": _codex_log_tail(run_dir),
    }


def read_events(run_dir: Path, *, limit: int = 250) -> list[dict[str, Any]]:
    path = Path(run_dir) / EVENTS_JSONL
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    events: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            events.append({"id": "", "type": "unreadable", "message": line[:500]})
    return events


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def _git_status(target_path: Path | None) -> list[dict[str, str]]:
    if target_path is None or not target_path.exists():
        return []
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=str(target_path),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception:  # noqa: BLE001
        return []
    if result.returncode != 0:
        return []
    rows: list[dict[str, str]] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        status = line[:2].strip() or "?"
        path = line[3:].strip() if len(line) > 3 else line.strip()
        rows.append({"status": status, "path": path})
    return rows


def _active_agent_count(state: dict[str, Any], events: list[dict[str, Any]]) -> int:
    if state.get("status") not in {"running", "partial", "failed", "passed"}:
        return 0
    phase = str(state.get("phase") or "")
    if phase in {"complete", "failed"}:
        return 0
    count = 1 if state.get("current_step") or phase in {"charter", "design", "ingestion", "building", "integration"} else 0
    recent_types = {str(event.get("type")) for event in events[-25:]}
    if "codex_invocation" in recent_types or "codex_log" in recent_types:
        count += 1
    if "subagent_started" in recent_types:
        count += 1
    return count


def _looks_like_test_path(path: str) -> bool:
    lowered = path.lower()
    return (
        "/test" in lowered
        or "tests/" in lowered
        or lowered.startswith("test_")
        or lowered.endswith((".spec.ts", ".spec.tsx", ".test.ts", ".test.tsx", "_test.py"))
    )


def _behavior_targets(behavior: dict[str, Any], feature_id: str) -> list[dict[str, Any]]:
    if not feature_id:
        return []
    scenarios = behavior.get("scenarios") or []
    matched: list[dict[str, Any]] = []
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            continue
        encoded = json.dumps(scenario, sort_keys=True)
        if feature_id in encoded:
            matched.append(scenario)
    return matched[:12]


def _codex_log_tail(run_dir: Path, *, max_chars: int = 12000) -> list[dict[str, str]]:
    logs: list[dict[str, str]] = []
    steps = Path(run_dir) / "steps"
    if not steps.exists():
        return logs
    for session_path in sorted(steps.glob("*/session.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]:
        try:
            text = session_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if "RUNNER: codex" not in text:
            continue
        logs.append({
            "feature_id": session_path.parent.name,
            "path": str(session_path),
            "tail": text[-max_chars:],
        })
    return logs


DASHBOARD_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>NC Dev Monitor</title>
  <style>
    :root {
      --canvas: #010102;
      --surface-1: #0f1011;
      --surface-2: #141516;
      --surface-3: #18191a;
      --hairline: #23252a;
      --hairline-strong: #34343a;
      --ink: #f7f8f8;
      --ink-muted: #d0d6e0;
      --ink-subtle: #8a8f98;
      --ink-tertiary: #62666d;
      --accent: #5e6ad2;
      --accent-hover: #828fff;
      --success: #27a644;
      --danger: #ff5f57;
      --warning: #d6a243;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif;
      color: var(--ink);
      background: var(--canvas);
    }
    * { box-sizing: border-box; }
    body { margin: 0; height: 100vh; overflow: hidden; background: var(--canvas); }
    button, input { font: inherit; }
    .app { height: 100vh; min-height: 100vh; overflow: hidden; display: grid; grid-template-columns: 260px minmax(0, 1fr) 370px; }
    .sidebar, .right { border-color: var(--hairline); background: #070708; }
    .sidebar { border-right: 1px solid var(--hairline); padding: 16px; overflow: auto; min-height: 0; }
    .right { border-left: 1px solid var(--hairline); display: grid; grid-template-rows: auto minmax(0, 1fr) auto; min-width: 0; min-height: 0; }
    .main { min-width: 0; min-height: 0; padding: 16px; display: grid; grid-template-rows: auto auto minmax(0, 1fr); gap: 12px; }
    .brand { display: flex; align-items: center; gap: 10px; margin-bottom: 18px; }
    .mark { width: 24px; height: 24px; border-radius: 7px; background: var(--accent); display: grid; place-items: center; color: white; font-size: 13px; font-weight: 700; }
    h1, h2, h3, p { margin: 0; }
    h1 { font-size: 15px; line-height: 1.2; font-weight: 650; }
    h2 { font-size: 12px; line-height: 1.2; color: var(--ink-subtle); font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; }
    h3 { font-size: 13px; line-height: 1.3; font-weight: 600; }
    .muted { color: var(--ink-subtle); }
    .tiny { font-size: 11px; color: var(--ink-tertiary); }
    .mono { font-family: "SF Mono", ui-monospace, Menlo, Consolas, monospace; }
    .toolbar, .panel, .metric, .run-row { background: var(--surface-1); border: 1px solid var(--hairline); border-radius: 8px; }
    .toolbar { min-height: 54px; display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 12px; }
    .toolbar-title { min-width: 0; }
    .toolbar-title h1 { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .status-dot { width: 7px; height: 7px; border-radius: 99px; background: var(--success); box-shadow: 0 0 0 3px rgba(39, 166, 68, 0.12); }
    .conn { display: flex; align-items: center; gap: 8px; color: var(--ink-muted); font-size: 12px; white-space: nowrap; }
    .metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
    .metric { padding: 12px; min-height: 74px; }
    .metric .value { font-size: 24px; font-weight: 650; line-height: 1.1; margin-top: 10px; }
    .grid { display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(340px, 0.9fr); gap: 12px; min-height: 0; }
    .panel { min-height: 0; overflow: hidden; display: flex; flex-direction: column; }
    .panel-head { padding: 12px; border-bottom: 1px solid var(--hairline); display: flex; align-items: center; justify-content: space-between; gap: 8px; }
    .panel-body { padding: 10px 12px; overflow: auto; min-height: 0; }
    .run-list { display: grid; gap: 8px; }
    .run-row { width: 100%; max-width: 100%; min-width: 0; overflow: hidden; color: inherit; text-align: left; padding: 10px; cursor: pointer; }
    .run-row h3, .row h3, .row p { overflow-wrap: anywhere; }
    .run-row:hover { border-color: var(--hairline-strong); background: var(--surface-2); }
    .run-row.active { border-color: var(--accent); }
    .row { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: 9px; align-items: start; padding: 9px 0; border-bottom: 1px solid rgba(35, 37, 42, 0.72); }
    .row:last-child { border-bottom: 0; }
    .pill { border: 1px solid var(--hairline); background: var(--surface-2); color: var(--ink-muted); border-radius: 999px; padding: 3px 8px; font-size: 11px; white-space: nowrap; }
    .pill.pass { color: #91e59f; border-color: rgba(39, 166, 68, 0.45); }
    .pill.fail { color: #ffaaa5; border-color: rgba(255, 95, 87, 0.45); }
    .pill.active { color: #c9cdff; border-color: rgba(94, 106, 210, 0.68); }
    .timeline-dot { width: 9px; height: 9px; margin-top: 4px; border-radius: 99px; background: var(--ink-tertiary); }
    .timeline-dot.active { background: var(--accent); box-shadow: 0 0 0 4px rgba(94, 106, 210, 0.12); }
    .timeline-dot.pass { background: var(--success); }
    .timeline-dot.fail { background: var(--danger); }
    .pre { white-space: pre-wrap; word-break: break-word; font-size: 11.5px; line-height: 1.45; color: var(--ink-muted); }
    .event { padding: 9px 12px; border-bottom: 1px solid rgba(35, 37, 42, 0.72); }
    .event-type { color: var(--accent-hover); font-size: 11px; margin-bottom: 4px; }
    .empty { padding: 16px 0; color: var(--ink-tertiary); font-size: 12px; }
    .split { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 12px; }
    .list { display: grid; gap: 8px; }
    .code-row { border: 1px solid var(--hairline); border-radius: 6px; padding: 8px; background: #0a0b0c; }
    @media (max-width: 1300px) {
      body { overflow: auto; }
      .app { height: auto; min-height: 100vh; overflow: visible; }
      .app { grid-template-columns: 240px minmax(0, 1fr); }
      .right { grid-column: 1 / -1; border-left: 0; border-top: 1px solid var(--hairline); min-height: 360px; }
      .metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    @media (max-width: 760px) {
      .app { grid-template-columns: 1fr; }
      .sidebar { border-right: 0; border-bottom: 1px solid var(--hairline); max-height: 260px; }
      .grid, .split { grid-template-columns: 1fr; }
      .metrics { grid-template-columns: 1fr 1fr; }
    }
  </style>
</head>
<body>
  <div class="app">
    <aside class="sidebar">
      <div class="brand"><div class="mark">N</div><div><h1>NC Dev Monitor</h1><p class="tiny">Live run telemetry</p></div></div>
      <div class="panel-head" style="padding-left:0;padding-right:0;border-bottom:0"><h2>Runs</h2><span class="tiny" id="run-count"></span></div>
      <div class="run-list" id="runs"></div>
    </aside>
    <main class="main">
      <section class="toolbar">
        <div class="toolbar-title"><h1 id="title">Waiting for run</h1><p class="tiny mono" id="run-dir"></p></div>
        <div class="conn"><span class="status-dot"></span><span id="connection">connected</span></div>
      </section>
      <section class="metrics">
        <div class="metric"><h2>Phase</h2><div class="value" id="phase">-</div></div>
        <div class="metric"><h2>Feature</h2><div class="value" id="feature">-</div></div>
        <div class="metric"><h2>Agents</h2><div class="value" id="agents">0</div></div>
        <div class="metric"><h2>Progress</h2><div class="value" id="progress">0/0</div></div>
      </section>
      <section class="grid">
        <div class="panel">
          <div class="panel-head"><h2>Feature Queue</h2><span class="pill" id="status-pill">unknown</span></div>
          <div class="panel-body" id="features"></div>
        </div>
        <div class="panel">
          <div class="panel-head"><h2>Current Work</h2><span class="pill active" id="current-step">none</span></div>
          <div class="panel-body">
            <div class="list">
              <div><h3 id="current-title">No active feature</h3><p class="muted" id="current-desc"></p></div>
              <div class="split">
                <div><h2>Behavior</h2><div id="behavior" class="list"></div></div>
                <div><h2>Tests</h2><div id="tests" class="list"></div></div>
              </div>
              <div><h2>Files Changing</h2><div id="files" class="list"></div></div>
            </div>
          </div>
        </div>
      </section>
    </main>
    <aside class="right">
      <div class="panel-head"><h2>Live Events</h2><span class="tiny mono" id="event-count"></span></div>
      <div id="events" style="overflow:auto"></div>
      <div class="panel" style="margin:12px; max-height:260px">
        <div class="panel-head"><h2>Codex Log Tail</h2></div>
        <div class="panel-body"><div id="codex" class="pre muted">No Codex log captured yet.</div></div>
      </div>
    </aside>
  </div>
  <script>
    let selectedRun = "latest";
    let source = null;
    const $ = (id) => document.getElementById(id);
    const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

    async function loadRuns() {
      const res = await fetch("/api/v1/monitor/runs");
      const body = await res.json();
      $("run-count").textContent = `${body.runs.length}`;
      $("runs").innerHTML = body.runs.slice(0, 60).map(run => `
        <button class="run-row ${run.run_id === selectedRun ? "active" : ""}" data-run="${esc(run.run_id)}">
          <div style="display:flex;justify-content:space-between;gap:8px"><h3 class="mono">${esc(run.run_id)}</h3><span class="pill">${esc(run.status)}</span></div>
          <p class="tiny">${esc(run.phase || "unknown")} ${run.current_step ? " / " + esc(run.current_step) : ""}</p>
        </button>
      `).join("") || `<div class="empty">No runs found.</div>`;
      document.querySelectorAll(".run-row").forEach(btn => btn.onclick = () => { selectedRun = btn.dataset.run; connect(); loadRuns(); });
    }

    function connect() {
      if (source) source.close();
      source = new EventSource(`/api/v1/monitor/runs/${selectedRun}/stream`);
      source.onmessage = (event) => render(JSON.parse(event.data));
      source.onerror = () => { $("connection").textContent = "reconnecting"; };
    }

    function render(data) {
      $("connection").textContent = "connected";
      const s = data.summary || {};
      $("title").textContent = data.run_id || "Waiting for run";
      $("run-dir").textContent = data.run_dir || "";
      $("phase").textContent = s.phase || "-";
      $("feature").textContent = s.current_step || "-";
      $("agents").textContent = s.active_agents ?? 0;
      $("progress").textContent = `${s.completed_features ?? 0}/${s.total_features ?? 0}`;
      $("status-pill").textContent = s.status || "unknown";
      $("current-step").textContent = s.current_step || "none";

      const completed = new Map((data.state?.completed_steps || []).map(step => [step.feature_id, step.status]));
      $("features").innerHTML = (data.features || []).map(feature => {
        const status = completed.get(feature.feature_id) || (feature.feature_id === s.current_step ? "building" : "pending");
        const tone = status === "passed" || status === "skipped" ? "pass" : (status === "failed" || status === "blocked" ? "fail" : (feature.feature_id === s.current_step ? "active" : ""));
        return `<div class="row"><span class="timeline-dot ${tone}"></span><div><h3>${esc(feature.feature_id)} - ${esc(feature.title)}</h3><p class="tiny">${esc(feature.description || "")}</p></div><span class="pill ${tone}">${esc(status)}</span></div>`;
      }).join("") || `<div class="empty">No feature queue loaded.</div>`;

      const cur = data.current_feature || {};
      $("current-title").textContent = cur.title ? `${cur.feature_id} - ${cur.title}` : "No active feature";
      $("current-desc").textContent = cur.description || "";
      const criteria = (cur.acceptance_criteria || []).map(c => ({label: c}));
      const behavior = (data.behavior_targets || []).map(b => ({label: b.title || b.name || b.id || JSON.stringify(b).slice(0, 180)}));
      $("behavior").innerHTML = [...criteria, ...behavior].map(item => `<div class="code-row tiny">${esc(item.label)}</div>`).join("") || `<div class="empty">No behavior target for current feature.</div>`;
      $("tests").innerHTML = (data.test_files || []).map(file => `<div class="code-row"><span class="pill">${esc(file.status)}</span> <span class="mono tiny">${esc(file.path)}</span></div>`).join("") || `<div class="empty">No test files changing right now.</div>`;
      $("files").innerHTML = (data.file_changes || []).map(file => `<div class="code-row"><span class="pill">${esc(file.status)}</span> <span class="mono tiny">${esc(file.path)}</span></div>`).join("") || `<div class="empty">Working tree is clean or unavailable.</div>`;

      const events = data.events || [];
      $("event-count").textContent = `${events.length}`;
      $("events").innerHTML = events.slice().reverse().map(ev => `<div class="event"><div class="event-type mono">${esc(ev.type)} ${ev.feature_id ? "/ " + esc(ev.feature_id) : ""}</div><div class="pre">${esc(ev.message || JSON.stringify(ev.data || {}))}</div><div class="tiny mono">${esc(ev.ts || "")}</div></div>`).join("") || `<div class="empty" style="padding:16px">No live events yet.</div>`;
      const codex = data.codex_logs || [];
      $("codex").textContent = codex.length ? codex.map(log => `${log.feature_id}\n${log.tail}`).join("\n\n---\n\n") : "No Codex log captured yet.";
    }

    loadRuns().then(connect);
    setInterval(loadRuns, 5000);
  </script>
</body>
</html>"""
