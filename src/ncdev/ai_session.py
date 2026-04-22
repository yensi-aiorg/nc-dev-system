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
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable, Iterable

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
MODE_ORCHESTRATOR: dict[str, str] = {
    "claude_plan_codex_build": "claude",
    "claude_only": "claude",
    "codex_only": "codex",
    "openrouter": "openrouter",
    "custom": "claude",   # safe default — custom may still want Claude orchestration
}

# Mode → who actually writes code. Used by the Claude runner to decide
# whether to inject the Codex-via-Bash protocol (i.e. "delegate impl
# to Codex") vs do the work itself.
MODE_IMPLEMENTER: dict[str, str] = {
    "claude_plan_codex_build": "codex",
    "claude_only": "claude",
    "codex_only": "codex",
    "openrouter": "openrouter",
    "custom": "codex",
}


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
) -> ClaudeSessionResult:
    """Run a Codex session. No skills, no subagents, no NC Dev hooks.

    Codex handles planning + implementation + testing + committing in
    one shot per invocation. This is the "lean mode" — you lose skill
    machinery and cross-feature reasoning quality in exchange for speed
    and lower cost.
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

    start = time.time()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        duration = time.time() - start
        stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
        return ClaudeSessionResult(
            success=False,
            final_text=(exc.stdout or "") if isinstance(exc.stdout, str) else "",
            exit_code=-1,
            duration_seconds=duration,
            stderr=stderr,
            error=f"codex session timed out after {timeout}s",
        )
    except FileNotFoundError:
        return ClaudeSessionResult(
            success=False, final_text="", exit_code=-1,
            error="codex CLI disappeared mid-invocation",
        )

    duration = time.time() - start
    final_text = proc.stdout or ""

    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            f"RUNNER: codex\nEXIT: {proc.returncode}\nDURATION: {duration:.1f}s\n\n"
            f"STDOUT:\n{final_text}\n\nSTDERR:\n{proc.stderr or ''}\n",
            encoding="utf-8",
        )

    return ClaudeSessionResult(
        success=proc.returncode == 0,
        final_text=final_text,
        exit_code=proc.returncode,
        duration_seconds=duration,
        stderr=proc.stderr or "",
        error=None if proc.returncode == 0 else f"codex exited with code {proc.returncode}",
    )
