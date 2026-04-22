"""Claude Code session runner — the single way NC Dev spawns Claude.

This is the primitive every higher-level orchestrator (discovery, feature
executor, dev loop) builds on. It spawns Claude Code in non-interactive
``--print --output-format stream-json`` mode, streams events as they
arrive, writes a full event log, and returns a structured result.

Skills, subagents, and MCP servers are controlled per call via the
``tools`` and ``append_system_prompt`` arguments. Claude's cost ceiling
is enforced by ``--max-budget-usd`` when ``max_budget_usd`` is provided —
this is the primitive the token-budget-driven mode switch hooks into.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable


PROTOCOLS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts" / "protocols"
CODEX_PROTOCOL_PATH = PROTOCOLS_DIR / "codex-via-bash.md"


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class ToolCallRecord:
    """One tool invocation observed in the stream."""
    tool: str
    input_summary: str  # truncated string form of the input
    raw: dict


@dataclass
class ClaudeSessionResult:
    """Structured outcome of a Claude session."""
    success: bool
    final_text: str
    exit_code: int
    events: list[dict] = field(default_factory=list)
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    skills_invoked: list[str] = field(default_factory=list)
    codex_invocations: list[str] = field(default_factory=list)
    subagents_dispatched: list[str] = field(default_factory=list)
    files_touched: list[str] = field(default_factory=list)
    total_cost_usd: float | None = None
    duration_seconds: float = 0.0
    stderr: str = ""
    error: str | None = None

    def summary(self) -> str:
        parts = [
            f"success={self.success}",
            f"exit={self.exit_code}",
            f"dur={self.duration_seconds:.1f}s",
        ]
        if self.total_cost_usd is not None:
            parts.append(f"cost=${self.total_cost_usd:.3f}")
        if self.tool_calls:
            parts.append(f"tools={len(self.tool_calls)}")
        if self.skills_invoked:
            parts.append(f"skills={','.join(self.skills_invoked)}")
        if self.codex_invocations:
            parts.append(f"codex={len(self.codex_invocations)}")
        return " ".join(parts)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


# Default tool allowlist for Claude sessions that orchestrate builds.
# Caller can override completely. Tools that enable the Codex-as-peer
# architecture: Bash (to shell out to codex exec), Skill (to invoke skills
# like test-driven-development), Task (to dispatch subagents).
DEFAULT_BUILD_TOOLS: tuple[str, ...] = (
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
    "Bash",
    "Skill",
    "Task",
)

# Minimal tool set for planning-only sessions that must not edit code.
DEFAULT_PLAN_TOOLS: tuple[str, ...] = (
    "Read",
    "Glob",
    "Grep",
    "Write",       # may write charter / feature-queue artifacts
    "Skill",
)


def run_claude_session(
    prompt: str,
    *,
    cwd: Path,
    tools: Iterable[str] = DEFAULT_BUILD_TOOLS,
    model: str = "claude-opus-4-6",
    timeout: int = 1800,
    permission_mode: str = "acceptEdits",
    append_system_prompt: str | None = None,
    include_codex_protocol: bool = True,
    max_budget_usd: float | None = None,
    log_path: Path | None = None,
    on_event: Callable[[dict], None] | None = None,
    extra_args: list[str] | None = None,
) -> ClaudeSessionResult:
    """Spawn a Claude session and stream its events.

    Parameters
    ----------
    prompt:
        The user-facing prompt. Pass a task statement, not a huge context
        blob — put big context in files and ask Claude to read them.
    cwd:
        Working directory for the session (the target repo, typically).
    tools:
        Tool allowlist. Use :data:`DEFAULT_BUILD_TOOLS` for feature builds
        (includes Bash for Codex shell-out, Skill for skill invocation,
        Task for subagents). Use :data:`DEFAULT_PLAN_TOOLS` for read-only
        planning sessions.
    model:
        Model label for Claude. Default: ``claude-opus-4-6``.
    timeout:
        Kill-switch in seconds. Separate from ``max_budget_usd`` — both
        can terminate the session.
    permission_mode:
        Passed to ``--permission-mode``. Default ``acceptEdits`` lets the
        model edit files without interactive prompts. Use
        ``bypassPermissions`` for fully trusted runs.
    append_system_prompt:
        Text appended to Claude's default system prompt. Use this to
        inject the Codex protocol, project charter reference, etc.
    include_codex_protocol:
        When True (default), the Codex-via-Bash protocol is prepended to
        ``append_system_prompt`` so every session knows how to delegate
        to Codex. Set False for sessions that must not invoke Codex.
    max_budget_usd:
        Hard cost ceiling for this session. Claude aborts if exceeded.
        This is the hook for budget-driven mode switching.
    log_path:
        If provided, every stream event is appended as a JSONL line.
    on_event:
        Optional callback fired per event in real time. Use for live
        progress UI. Exceptions in the callback are caught and logged.
    extra_args:
        Additional raw flags passed to ``claude``. Escape hatch.
    """
    if shutil.which("claude") is None:
        return ClaudeSessionResult(
            success=False, final_text="", exit_code=-1,
            error="claude CLI not found on PATH",
        )

    # Compose the system prompt append block
    system_prompt_parts: list[str] = []
    if include_codex_protocol and CODEX_PROTOCOL_PATH.exists():
        system_prompt_parts.append(CODEX_PROTOCOL_PATH.read_text(encoding="utf-8"))
    if append_system_prompt:
        system_prompt_parts.append(append_system_prompt)
    system_prompt = "\n\n---\n\n".join(system_prompt_parts) if system_prompt_parts else None

    tools_list = list(tools)

    cmd: list[str] = [
        "claude",
        "-p", prompt,
        "--output-format", "stream-json",
        "--include-partial-messages",
        "--include-hook-events",
        "--model", model,
        "--permission-mode", permission_mode,
        "--allowedTools", ",".join(tools_list),
    ]
    if system_prompt:
        cmd += ["--append-system-prompt", system_prompt]
    if max_budget_usd is not None:
        cmd += ["--max-budget-usd", f"{max_budget_usd:.4f}"]
    if extra_args:
        cmd += list(extra_args)

    start = time.time()
    events: list[dict] = []
    log_fh = None
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_fh = log_path.open("w", encoding="utf-8")

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except (FileNotFoundError, OSError) as exc:
        if log_fh:
            log_fh.close()
        return ClaudeSessionResult(
            success=False, final_text="", exit_code=-1,
            error=f"failed to spawn claude: {exc}",
        )

    final_text = ""
    skills: list[str] = []
    tool_calls: list[ToolCallRecord] = []
    codex_calls: list[str] = []
    subagents: list[str] = []
    files_touched: set[str] = set()
    total_cost: float | None = None

    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                # Tolerate non-JSON noise — log raw, skip parse
                if log_fh:
                    log_fh.write(json.dumps({"_raw": line}) + "\n")
                continue

            events.append(event)
            if log_fh:
                log_fh.write(json.dumps(event) + "\n")
                log_fh.flush()

            _extract_event_signals(
                event,
                skills=skills,
                tool_calls=tool_calls,
                codex_calls=codex_calls,
                subagents=subagents,
                files_touched=files_touched,
            )

            if event.get("type") == "result":
                final_text = event.get("result") or event.get("text") or final_text
                total_cost = event.get("total_cost_usd", total_cost)

            if on_event is not None:
                try:
                    on_event(event)
                except Exception:  # noqa: BLE001
                    # Never let a caller callback crash the session reader
                    pass

        proc.wait(timeout=timeout)
        stderr_text = proc.stderr.read() if proc.stderr else ""
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
        stderr_text = proc.stderr.read() if proc.stderr else ""
        if log_fh:
            log_fh.close()
        return ClaudeSessionResult(
            success=False, final_text=final_text, exit_code=-1,
            events=events, tool_calls=tool_calls,
            skills_invoked=skills, codex_invocations=codex_calls,
            subagents_dispatched=subagents,
            files_touched=sorted(files_touched),
            total_cost_usd=total_cost,
            duration_seconds=time.time() - start,
            stderr=stderr_text,
            error=f"claude session timed out after {timeout}s",
        )
    finally:
        if log_fh:
            log_fh.close()

    exit_code = proc.returncode
    duration = time.time() - start

    # Fall back to final event text if result event didn't land
    if not final_text:
        for ev in reversed(events):
            if ev.get("type") in ("assistant", "result"):
                text = _extract_text(ev)
                if text:
                    final_text = text
                    break

    return ClaudeSessionResult(
        success=exit_code == 0,
        final_text=final_text,
        exit_code=exit_code,
        events=events,
        tool_calls=tool_calls,
        skills_invoked=skills,
        codex_invocations=codex_calls,
        subagents_dispatched=subagents,
        files_touched=sorted(files_touched),
        total_cost_usd=total_cost,
        duration_seconds=duration,
        stderr=stderr_text,
        error=None if exit_code == 0 else f"claude exited with code {exit_code}",
    )


# ---------------------------------------------------------------------------
# Event parsing helpers
# ---------------------------------------------------------------------------


def _extract_event_signals(
    event: dict,
    *,
    skills: list[str],
    tool_calls: list[ToolCallRecord],
    codex_calls: list[str],
    subagents: list[str],
    files_touched: set[str],
) -> None:
    """Pull structured signals out of a stream event.

    Stream-json schema has evolved across Claude Code versions — we keep
    this tolerant: inspect common shapes, ignore unknowns.
    """
    ev_type = event.get("type")

    # Tool use appears inside assistant messages as content items with
    # type=tool_use. Extract recursively.
    if ev_type == "assistant":
        message = event.get("message") or {}
        content = message.get("content") or []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "tool_use":
                tool_name = item.get("name", "?")
                input_data = item.get("input") or {}
                summary = _summarize_input(tool_name, input_data)
                tool_calls.append(ToolCallRecord(
                    tool=tool_name,
                    input_summary=summary,
                    raw=item,
                ))
                if tool_name == "Skill":
                    skill_name = input_data.get("skill") or input_data.get("name")
                    if skill_name and skill_name not in skills:
                        skills.append(skill_name)
                elif tool_name == "Task":
                    agent = input_data.get("subagent_type") or input_data.get("agent")
                    if agent:
                        subagents.append(agent)
                elif tool_name == "Bash":
                    cmd = input_data.get("command", "")
                    if "codex exec" in cmd or cmd.strip().startswith("codex "):
                        codex_calls.append(cmd[:500])
                elif tool_name in ("Write", "Edit"):
                    path = input_data.get("file_path")
                    if path:
                        files_touched.add(path)


def _summarize_input(tool: str, data: dict) -> str:
    if tool == "Bash":
        cmd = str(data.get("command", ""))
        return cmd[:200]
    if tool in ("Write", "Edit"):
        return str(data.get("file_path", ""))[:200]
    if tool == "Read":
        return str(data.get("file_path", ""))[:200]
    if tool == "Skill":
        return str(data.get("skill") or data.get("name") or "")[:200]
    if tool == "Task":
        desc = data.get("description", "")
        sub = data.get("subagent_type", "")
        return f"{sub}: {desc}"[:200]
    return str(data)[:200]


def _extract_text(event: dict) -> str:
    """Best-effort pull of readable text from an event."""
    if not isinstance(event, dict):
        return ""
    if "result" in event:
        return str(event["result"])
    if "text" in event:
        return str(event["text"])
    message = event.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    texts.append(str(item.get("text", "")))
            if texts:
                return "\n".join(texts)
    return ""
