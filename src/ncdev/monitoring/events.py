"""Best-effort JSONL event emission for live run monitoring."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EVENTS_JSONL = "events.jsonl"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_short(value: Any, limit: int = 600) -> str:
    text = str(value or "")
    return text if len(text) <= limit else text[: limit - 3] + "..."


class MonitorEventWriter:
    """Append normalized monitor events without affecting run behavior.

    This writer deliberately swallows all IO and serialization errors.
    Observability must never change whether a build passes, fails, halts,
    or commits.
    """

    def __init__(self, run_dir: Path, *, run_id: str | None = None) -> None:
        self.run_dir = Path(run_dir)
        self.run_id = run_id or self.run_dir.name

    @property
    def path(self) -> Path:
        return self.run_dir / EVENTS_JSONL

    def emit(
        self,
        event_type: str,
        *,
        phase: str = "",
        feature_id: str = "",
        message: str = "",
        data: dict[str, Any] | None = None,
    ) -> None:
        payload = {
            "id": f"{time.time_ns()}",
            "ts": _utc_now(),
            "run_id": self.run_id,
            "type": event_type,
            "phase": phase,
            "feature_id": feature_id,
            "message": _safe_short(message, 1000),
            "data": data or {},
        }
        try:
            self.run_dir.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, sort_keys=False) + "\n")
        except Exception:  # noqa: BLE001
            return

    def emit_ai_event(
        self,
        event: dict[str, Any],
        *,
        phase: str = "",
        feature_id: str = "",
    ) -> None:
        """Normalize useful Claude/Codex stream events for the dashboard."""
        for payload in normalize_ai_event(event):
            self.emit(
                payload["type"],
                phase=phase,
                feature_id=feature_id,
                message=payload.get("message", ""),
                data=payload.get("data", {}),
            )


def normalize_ai_event(event: dict[str, Any]) -> list[dict[str, Any]]:
    """Return monitor events extracted from a raw AI stream event."""
    if not isinstance(event, dict):
        return []

    ev_type = event.get("type")
    normalized: list[dict[str, Any]] = []

    if ev_type in {"codex_stdout", "codex_stderr"}:
        stream = "stdout" if ev_type == "codex_stdout" else "stderr"
        text = _safe_short(event.get("text"), 1200)
        normalized.append({
            "type": "codex_log",
            "message": text,
            "data": {"stream": stream, "text": text},
        })
        return normalized

    if ev_type == "result":
        result = _safe_short(event.get("result") or event.get("text"), 1200)
        normalized.append({
            "type": "session_result",
            "message": result or "AI session completed",
            "data": {
                "subtype": event.get("subtype"),
                "total_cost_usd": event.get("total_cost_usd"),
                "duration_ms": event.get("duration_ms"),
            },
        })
        return normalized

    if ev_type != "assistant":
        text = _extract_text(event)
        if text:
            normalized.append({
                "type": "agent_message",
                "message": _safe_short(text, 1200),
                "data": {"raw_type": ev_type},
            })
        return normalized

    message = event.get("message") or {}
    content = message.get("content") or []
    if isinstance(content, str):
        normalized.append({
            "type": "agent_message",
            "message": _safe_short(content, 1200),
            "data": {},
        })
        return normalized

    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "text":
            text = _safe_short(item.get("text"), 1200)
            if text:
                normalized.append({
                    "type": "agent_message",
                    "message": text,
                    "data": {},
                })
            continue
        if item.get("type") != "tool_use":
            continue

        tool = str(item.get("name") or "?")
        input_data = item.get("input") or {}
        event_type = "tool_call"
        summary = _summarize_tool(tool, input_data)
        data = {"tool": tool, "input": _redact_input(input_data), "summary": summary}

        if tool in {"Write", "Edit"}:
            event_type = "file_edit"
            data["path"] = input_data.get("file_path", "")
        elif tool == "Read":
            event_type = "file_read"
            data["path"] = input_data.get("file_path", "")
        elif tool == "Skill":
            event_type = "skill_invoked"
            data["skill"] = input_data.get("skill") or input_data.get("name") or ""
        elif tool == "Task":
            event_type = "subagent_started"
            data["subagent"] = input_data.get("subagent_type") or input_data.get("agent") or ""
        elif tool == "Bash":
            command = str(input_data.get("command") or "")
            data["command"] = _safe_short(command, 1200)
            lower = command.lower()
            if "codex exec" in lower or lower.strip().startswith("codex "):
                event_type = "codex_invocation"
            elif any(token in lower for token in ("pytest", "npm test", "pnpm test", "vitest", "playwright", "ruff", "mypy")):
                event_type = "test_command"

        normalized.append({
            "type": event_type,
            "message": summary,
            "data": data,
        })
    return normalized


def _extract_text(event: dict[str, Any]) -> str:
    if "result" in event:
        return str(event["result"])
    if "text" in event:
        return str(event["text"])
    message = event.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(item.get("text", ""))
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        )
    return ""


def _summarize_tool(tool: str, data: dict[str, Any]) -> str:
    if tool == "Bash":
        return _safe_short(data.get("command"), 240)
    if tool in {"Write", "Edit", "Read"}:
        return _safe_short(data.get("file_path"), 240)
    if tool == "Skill":
        return _safe_short(data.get("skill") or data.get("name"), 240)
    if tool == "Task":
        sub = data.get("subagent_type") or data.get("agent") or "subagent"
        desc = data.get("description") or ""
        return _safe_short(f"{sub}: {desc}", 240)
    return _safe_short(data, 240)


def _redact_input(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(secret in lowered for secret in ("token", "secret", "password", "api_key", "authorization")):
                redacted[key] = "<redacted>"
            elif key in {"content", "new_string", "old_string"}:
                redacted[key] = _safe_short(item, 500)
            else:
                redacted[key] = _redact_input(item)
        return redacted
    if isinstance(value, list):
        return [_redact_input(item) for item in value[:20]]
    return value
