"""Unified AI session runner — dispatches on mode.

``run_ai_session()`` is the single entry point every phase of NC Dev
calls when it needs an AI-driven session. It reads ``NCDevV2Config.mode``
and dispatches to the right concrete runner:

    * ``claude_plan_codex_build`` → Claude session, Codex protocol
      injected so Claude shells to ``codex exec`` for implementation.
    * ``claude_only`` → Claude session, Codex protocol NOT injected;
      Claude does implementation itself.
    * ``codex_only`` → Codex CLI session, no skills / subagents / hooks;
      Codex handles the whole task directly.
    * ``openrouter`` → raises ``NotImplementedError`` (API-only, no CLI
      tooling). Caller should fall back or surface to the user.
    * ``custom`` → falls back to Claude orchestrator as a safe default.

The returned :class:`ClaudeSessionResult` is the common result shape
across runners — ``skills_invoked`` and ``codex_invocations`` are
populated only when they applied.
"""

from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Iterable

_IS_POSIX = sys.platform != "win32"

# Upper bound per stream for run_codex_session capture. A chatty codex
# run can produce a lot — we keep the tail (recent output is more
# useful than the head) and note truncation.
_CODEX_CAPTURE_MAX_BYTES = 4 * 1024 * 1024   # 4 MB per stream

from ncdev.claude_session import (
    DEFAULT_BUILD_TOOLS,
    ClaudeSessionResult,
    NCDEV_HOOKS_DIR,
    NCDEV_HOOKS_SETTINGS,
    run_claude_session,
)
from ncdev.v2.config import NCDevV2Config, load_v2_config

logger = logging.getLogger(__name__)


# Mode → which provider runs the main orchestrator session.
# "custom" is intentionally absent — it's handled by consulting the
# user's hand-tuned routing via provider_dispatch instead.
MODE_ORCHESTRATOR: dict[str, str] = {
    "claude_plan_codex_build": "claude",
    "claude_only": "claude",
    "codex_only": "codex",
    "openrouter": "openrouter",
}

# Mode → who actually writes code. Used by the Claude runner to decide
# whether to inject the Codex-via-Bash protocol (i.e. "delegate impl
# to Codex") vs do the work itself.
MODE_IMPLEMENTER: dict[str, str] = {
    "claude_plan_codex_build": "codex",
    "claude_only": "claude",
    "codex_only": "codex",
    "openrouter": "openrouter",
}


def _resolve_custom_providers(cfg: NCDevV2Config) -> tuple[str, str]:
    """For ``mode=custom``, read orchestrator + implementer from routing.

    Honours the contract stated in v2/config.py: ``custom`` preserves
    the user's hand-tuned ``routing:`` block. We use routing.review to
    pick the orchestrator (review is the "who reasons about code" task)
    and routing.implementation to pick the implementer.

    Both are mapped through :func:`provider_dispatch.resolve_provider_name`
    so long names like ``anthropic_claude_code`` become short
    registry keys (``claude``, ``codex``, ``openrouter``).
    """
    from ncdev.provider_dispatch import resolve_provider_name

    review_chain = cfg.routing.review or ["anthropic_claude_code"]
    impl_chain = cfg.routing.implementation or ["openai_codex"]
    orch = resolve_provider_name(review_chain[0])
    impl = resolve_provider_name(impl_chain[0])
    return orch, impl


def _resolve_config(
    config: NCDevV2Config | None,
    workspace: Path | None,
) -> NCDevV2Config:
    if config is not None:
        return config
    if workspace is not None:
        try:
            return load_v2_config(workspace)
        except Exception:  # noqa: BLE001
            pass
    return NCDevV2Config()


def run_ai_session(
    prompt: str,
    *,
    cwd: Path,
    config: NCDevV2Config | None = None,
    workspace: Path | None = None,
    tools: Iterable[str] = DEFAULT_BUILD_TOOLS,
    model: str | None = None,
    timeout: int = 1800,
    permission_mode: str = "acceptEdits",
    append_system_prompt: str | None = None,
    include_codex_protocol: bool | None = None,
    max_budget_usd: float | None = None,
    log_path: Path | None = None,
    on_event: Callable[[dict], None] | None = None,
    extra_args: list[str] | None = None,
    settings_path: Path | None = None,
    enable_ncdev_hooks: bool = True,
) -> ClaudeSessionResult:
    """Run an AI session, dispatching on the active mode.

    ``include_codex_protocol`` defaults to ``True`` when the mode's
    implementer is Codex (i.e. Claude should delegate), ``False`` when
    implementer is Claude. Explicit values win.
    """
    cfg = _resolve_config(config, workspace)

    if cfg.mode == "custom":
        # Honour the hand-tuned routing block — this is exactly what
        # "custom" means per the config contract.
        orch, impl = _resolve_custom_providers(cfg)
    else:
        orch = MODE_ORCHESTRATOR.get(cfg.mode, "claude")
        impl = MODE_IMPLEMENTER.get(cfg.mode, "codex")

    logger.info("run_ai_session mode=%s orch=%s impl=%s cwd=%s", cfg.mode, orch, impl, cwd)

    if orch == "openrouter":
        raise NotImplementedError(
            "openrouter mode is API-only and cannot spawn a file-editing "
            "session. Install and configure the Claude or Codex CLI and "
            "pick a CLI mode (claude_plan_codex_build, claude_only, or "
            "codex_only)."
        )

    if orch == "codex":
        return run_codex_session(
            prompt,
            cwd=cwd,
            timeout=timeout,
            model=model,
            log_path=log_path,
            extra_args=extra_args,
        )

    # orch == "claude"
    if include_codex_protocol is None:
        include_codex_protocol = (impl == "codex")

    effective_model = model or "claude-opus-4-6"
    return run_claude_session(
        prompt,
        cwd=cwd,
        tools=tools,
        model=effective_model,
        timeout=timeout,
        permission_mode=permission_mode,
        append_system_prompt=append_system_prompt,
        include_codex_protocol=include_codex_protocol,
        max_budget_usd=max_budget_usd,
        log_path=log_path,
        on_event=on_event,
        extra_args=extra_args,
        settings_path=settings_path,
        enable_ncdev_hooks=enable_ncdev_hooks,
    )


# ---------------------------------------------------------------------------
# Codex runner — used by codex_only mode
# ---------------------------------------------------------------------------


def run_codex_session(
    prompt: str,
    *,
    cwd: Path,
    timeout: int = 1800,
    model: str | None = None,
    log_path: Path | None = None,
    extra_args: list[str] | None = None,
    max_bytes_per_stream: int = _CODEX_CAPTURE_MAX_BYTES,
) -> ClaudeSessionResult:
    """Run a Codex session. No skills, no subagents, no NC Dev hooks.

    Uses the same safety primitives as :func:`run_claude_session`:
    thread-per-pipe readers so backpressure can't deadlock the child,
    watchdog that kills the process group on wall-clock timeout, and
    a tail-bounded byte buffer per stream so a chatty Codex run
    doesn't blow RAM. Returns the same :class:`ClaudeSessionResult`
    shape (common result type across runners).
    """
    if shutil.which("codex") is None:
        return ClaudeSessionResult(
            success=False, final_text="", exit_code=-1,
            error="codex CLI not found on PATH",
        )

    # Codex prompt must be scoped — no Claude skill references.
    codex_prompt = (
        prompt
        + "\n\n---\n\n"
        + "You are running in codex_only mode (no Claude orchestrator). "
        "Produce a plan, implement, write tests, and commit with "
        "Conventional Commits. Leave the working tree clean when done."
    )

    cmd: list[str] = [
        "codex", "exec",
        "--full-auto",
        "--sandbox", "danger-full-access",
    ]
    if model:
        cmd += ["--model", model]
    if extra_args:
        cmd += list(extra_args)
    cmd.append(codex_prompt)

    popen_kwargs: dict = dict(
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    if _IS_POSIX:
        popen_kwargs["start_new_session"] = True

    start = time.time()
    try:
        proc = subprocess.Popen(cmd, **popen_kwargs)
    except (FileNotFoundError, OSError) as exc:
        return ClaudeSessionResult(
            success=False, final_text="", exit_code=-1,
            error=f"failed to spawn codex: {exc}",
        )

    stdout_buf = _TailBuffer(max_bytes_per_stream)
    stderr_buf = _TailBuffer(max_bytes_per_stream)

    def _drain(stream, buf: "_TailBuffer") -> None:
        try:
            for line in stream:
                buf.append(line)
        except Exception:  # noqa: BLE001
            pass

    stdout_thread = threading.Thread(
        target=_drain, args=(proc.stdout, stdout_buf), daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_drain, args=(proc.stderr, stderr_buf), daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()

    timeout_fired = threading.Event()

    def _watchdog() -> None:
        if timeout <= 0:
            return
        if proc.poll() is None:
            time.sleep(timeout)
        if proc.poll() is None:
            timeout_fired.set()
            _kill_process_tree(proc)

    threading.Thread(target=_watchdog, daemon=True).start()

    try:
        proc.wait(timeout=timeout + 30)
    except subprocess.TimeoutExpired:
        _kill_process_tree(proc)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass

    # Drain final bytes
    stdout_thread.join(timeout=2.0)
    stderr_thread.join(timeout=2.0)

    duration = time.time() - start
    final_text = stdout_buf.text()
    stderr_text = stderr_buf.text()
    exit_code = proc.returncode if proc.returncode is not None else -1

    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        truncation_note = ""
        if stdout_buf.truncated or stderr_buf.truncated:
            truncation_note = (
                f"\n(NOTE: output tail-truncated to {max_bytes_per_stream} "
                "bytes per stream)\n"
            )
        log_path.write_text(
            f"RUNNER: codex\nEXIT: {exit_code}\nDURATION: {duration:.1f}s"
            f"{truncation_note}\n\n"
            f"STDOUT:\n{final_text}\n\nSTDERR:\n{stderr_text}\n",
            encoding="utf-8",
        )

    if timeout_fired.is_set():
        return ClaudeSessionResult(
            success=False,
            final_text=final_text,
            exit_code=exit_code,
            duration_seconds=duration,
            stderr=stderr_text,
            error=f"codex session timed out after {timeout}s",
        )

    return ClaudeSessionResult(
        success=exit_code == 0,
        final_text=final_text,
        exit_code=exit_code,
        duration_seconds=duration,
        stderr=stderr_text,
        error=None if exit_code == 0 else f"codex exited with code {exit_code}",
    )


# ---------------------------------------------------------------------------
# Helpers (shared)
# ---------------------------------------------------------------------------


class _TailBuffer:
    """Accumulate text but keep only the tail of ``max_bytes``.

    Recent output is more useful than the head when debugging a builder
    that went off the rails. ``truncated`` flips True once we start
    dropping bytes so callers can surface that to users / logs.
    """

    __slots__ = ("_chunks", "_size", "_max", "truncated")

    def __init__(self, max_bytes: int) -> None:
        self._chunks: list[str] = []
        self._size = 0
        self._max = max_bytes
        self.truncated = False

    def append(self, chunk: str) -> None:
        if not chunk:
            return
        enc = len(chunk.encode("utf-8", errors="ignore"))
        self._chunks.append(chunk)
        self._size += enc
        while self._size > self._max and self._chunks:
            head = self._chunks.pop(0)
            self._size -= len(head.encode("utf-8", errors="ignore"))
            self.truncated = True

    def text(self) -> str:
        return "".join(self._chunks)


def _kill_process_tree(proc: subprocess.Popen) -> None:
    """Kill a process and its children. Mirror of claude_session's helper."""
    if proc.poll() is not None:
        return
    try:
        if _IS_POSIX:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    proc.kill()
        else:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
    except Exception:  # noqa: BLE001
        pass
