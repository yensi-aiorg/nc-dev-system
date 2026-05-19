"""
AI Provider Adapter for NC Dev System.

Routes all AI CLI calls through a pluggable provider interface.
Supports Codex CLI (default) and Claude CLI (fallback).
Config-driven -- switch providers without code changes.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
import shutil
import sys
import tempfile
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4)

IS_WINDOWS = sys.platform == "win32"


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------


class AIProvider(ABC):
    """Base class for AI provider adapters."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this provider's CLI is installed and reachable."""
        ...

    @abstractmethod
    async def complete(
        self,
        prompt: str,
        timeout: int = 300,
        cwd: str | None = None,
        tools: list[str] | None = None,
    ) -> Optional[str]:
        """Send *prompt* to the provider and return the text response.

        Parameters
        ----------
        prompt:
            The full prompt text.
        timeout:
            Maximum seconds to wait for a response.
        cwd:
            Working directory for the subprocess (target project).
        tools:
            List of allowed tool names (e.g. ``["Edit", "Write", "Bash"]``).
            Interpretation is provider-specific.
        """
        ...

    def build_argv(
        self,
        prompt: str,
        *,
        model: str | None = None,
        tools: list[str] | None = None,
        codex_options: list[str] | None = None,
    ) -> list[str]:
        """Build argv for direct ``subprocess.run(...)`` invocation.

        Callers that need fine-grained control over subprocess lifecycle
        (logging, custom timeouts, Popen session groups, etc.) can use
        the returned argv instead of :meth:`complete`. API-based providers
        (e.g. OpenRouter) raise :class:`NotImplementedError`.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not expose a CLI argv. Use .complete() instead."
        )

    @property
    def short_name(self) -> str:
        """Short registry key for this provider (e.g. 'codex', 'claude')."""
        return getattr(self, "_cmd_name", type(self).__name__.lower())


# ---------------------------------------------------------------------------
# CLI-based provider mixin
# ---------------------------------------------------------------------------


class _CLIProviderMixin:
    """Shared subprocess logic for CLI-based providers."""

    _cmd_name: str = ""
    _available: Optional[bool] = None

    def _get_command(self) -> str:
        if IS_WINDOWS:
            cmd = (
                shutil.which(f"{self._cmd_name}.cmd")
                or shutil.which(f"{self._cmd_name}.exe")
                or shutil.which(self._cmd_name)
            )
            return cmd if cmd else self._cmd_name
        return self._cmd_name

    # ---- availability ------------------------------------------------------

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available

        cmd = self._get_command()
        try:
            if IS_WINDOWS:
                result = subprocess.run(
                    f"{cmd} --version", capture_output=True, timeout=5, shell=True,
                )
            else:
                result = subprocess.run(
                    [cmd, "--version"], capture_output=True, timeout=5,
                )
            self._available = result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            self._available = False

        if not self._available:
            logger.debug("%s CLI is not available", self._cmd_name)
        else:
            logger.info("%s CLI is available", self._cmd_name)
        return self._available

    # ---- shell command building (override per provider) --------------------

    def _build_shell_cmd(
        self,
        prompt_file: str,
        tools: list[str] | None = None,
    ) -> str:
        raise NotImplementedError

    # ---- subprocess call ---------------------------------------------------

    def _call_sync(
        self,
        prompt: str,
        timeout: int = 300,
        cwd: str | None = None,
        tools: list[str] | None = None,
    ) -> Optional[str]:
        temp_file = None
        try:
            temp_file = tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, encoding="utf-8",
            )
            temp_file.write(prompt)
            temp_file.close()

            logger.debug(
                "Wrote prompt to temp file: %s (%d chars)",
                temp_file.name, len(prompt),
            )

            shell_cmd = self._build_shell_cmd(temp_file.name, tools=tools)

            popen_kwargs: dict = dict(
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            if cwd:
                popen_kwargs["cwd"] = cwd
            if not IS_WINDOWS:
                popen_kwargs["start_new_session"] = True

            proc = subprocess.Popen(shell_cmd, **popen_kwargs)
            try:
                stdout, stderr = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                if not IS_WINDOWS:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                else:
                    proc.kill()
                proc.wait(timeout=5)
                logger.error("%s CLI timed out after %ds", self._cmd_name, timeout)
                return None

            response = stdout.decode().strip() if stdout else ""
            error_output = stderr.decode().strip() if stderr else ""

            logger.info(
                "%s CLI finished: returncode=%d, stdout=%d chars, stderr=%d chars",
                self._cmd_name, proc.returncode, len(response), len(error_output),
            )

            if proc.returncode != 0:
                logger.error(
                    "%s CLI exit code %d. stderr: %s",
                    self._cmd_name, proc.returncode, error_output[:500],
                )
                if response:
                    logger.info(
                        "Non-zero exit but got stdout -- using response anyway (%d chars)",
                        len(response),
                    )
                    return response
                return None

            if not response:
                logger.warning("%s CLI returned empty response", self._cmd_name)
                if error_output:
                    logger.warning("Stderr: %s", error_output[:500])
            return response
        except Exception as exc:
            logger.exception("Error calling %s CLI: %s", self._cmd_name, exc)
            return None
        finally:
            if temp_file and os.path.exists(temp_file.name):
                try:
                    os.unlink(temp_file.name)
                except Exception:
                    pass

    # ---- async wrapper -----------------------------------------------------

    async def complete(
        self,
        prompt: str,
        timeout: int = 300,
        cwd: str | None = None,
        tools: list[str] | None = None,
    ) -> Optional[str]:
        if not self.is_available():
            logger.error("%s CLI is not available", self._cmd_name)
            return None

        loop = asyncio.get_running_loop()
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(
                    _executor, self._call_sync, prompt, timeout, cwd, tools,
                ),
                timeout=timeout + 10,
            )
        except asyncio.TimeoutError:
            logger.error("%s CLI timed out after %ds", self._cmd_name, timeout)
            return None
        except Exception as exc:
            logger.exception("Error calling %s CLI: %s", self._cmd_name, exc)
            return None


# ---------------------------------------------------------------------------
# Concrete providers
# ---------------------------------------------------------------------------


def _resolve_claude_model(model: str | None) -> str:
    """Resolve an auto/None model request to a concrete Claude model."""
    from ncdev.core.capability_policy import resolve_model
    from ncdev.core.capability_probe import probe_claude
    from ncdev.core.capability_ledger import read_entries

    return resolve_model(
        "anthropic_claude_code", model, probe_claude(),
        ledger_entries=read_entries(),
    )


class CodexCLIProvider(_CLIProviderMixin, AIProvider):
    """AI provider backed by the Codex CLI.

    Command shape: ``cat <prompt> | codex exec --full-auto --skip-git-repo-check -``
    ``--full-auto`` already grants all tool permissions; the ``tools`` parameter
    is ignored.
    """

    _cmd_name = "codex"

    def _build_shell_cmd(
        self,
        prompt_file: str,
        tools: list[str] | None = None,
    ) -> str:
        cmd_exe = self._get_command()
        cat_cmd = "type" if IS_WINDOWS else "cat"
        return f'{cat_cmd} "{prompt_file}" | {cmd_exe} exec --full-auto --skip-git-repo-check -'

    def build_argv(
        self,
        prompt: str,
        *,
        model: str | None = None,
        tools: list[str] | None = None,
        codex_options: list[str] | None = None,
    ) -> list[str]:
        from ncdev.core.capability_policy import resolve_model
        from ncdev.core.capability_probe import probe_codex

        argv = [
            self._cmd_name,
            "exec",
            "--full-auto",
            "--sandbox",
            "danger-full-access",
        ]
        argv += ["--model", resolve_model("openai_codex", model, probe_codex())]
        if codex_options:
            argv += list(codex_options)
        argv.append(prompt)
        return argv


class ClaudeCLIProvider(_CLIProviderMixin, AIProvider):
    """AI provider backed by the Claude Code CLI.

    Command shape: ``cat <prompt> | claude -p - --output-format text [--allowedTools ...]``
    """

    _cmd_name = "claude"

    def _build_shell_cmd(
        self,
        prompt_file: str,
        tools: list[str] | None = None,
    ) -> str:
        cmd_exe = self._get_command()
        cat_cmd = "type" if IS_WINDOWS else "cat"
        cmd = f'{cat_cmd} "{prompt_file}" | {cmd_exe} -p - --output-format text'
        if tools:
            allowed = ",".join(tools)
            cmd += f' --allowedTools "{allowed}"'
        return cmd

    def build_argv(
        self,
        prompt: str,
        *,
        model: str | None = None,
        tools: list[str] | None = None,
    ) -> list[str]:
        argv = [
            self._cmd_name,
            "-p",
            prompt,
            "--output-format",
            "text",
            "--model",
            _resolve_claude_model(model),
        ]
        if tools:
            argv += ["--allowedTools", ",".join(tools)]
        return argv


class OpenRouterProvider(AIProvider):
    """API-based provider that routes to models via OpenRouter (openrouter.ai).

    Requires ``OPENROUTER_API_KEY`` in the environment. The model is taken from
    ``OPENROUTER_MODEL`` (default ``anthropic/claude-opus-4-6``). This provider
    has no CLI — callers must use :meth:`complete` (API call), not
    :meth:`build_argv` which raises :class:`NotImplementedError`.
    """

    _cmd_name = "openrouter"
    _BASE_URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self) -> None:
        self._api_key = os.environ.get("OPENROUTER_API_KEY", "")
        self._model = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-opus-4-6")

    @property
    def short_name(self) -> str:
        return "openrouter"

    def is_available(self) -> bool:
        return bool(self._api_key)

    async def complete(
        self,
        prompt: str,
        timeout: int = 300,
        cwd: str | None = None,
        tools: list[str] | None = None,
    ) -> Optional[str]:
        if not self._api_key:
            logger.error("OPENROUTER_API_KEY is not set; OpenRouter provider is unavailable")
            return None
        try:
            import httpx  # type: ignore
        except ImportError:
            logger.error("httpx is not installed; OpenRouter provider requires httpx")
            return None
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    self._BASE_URL,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self._model,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"]
        except Exception as exc:
            logger.exception("OpenRouter request failed: %s", exc)
            return None


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_PROVIDER_CLASSES: dict[str, type[AIProvider]] = {
    "codex": CodexCLIProvider,
    "claude": ClaudeCLIProvider,
    "openrouter": OpenRouterProvider,
}

_provider_instances: dict[str, AIProvider] = {}


def get_provider(name: str = "codex") -> AIProvider:
    """Return a singleton provider instance by name.

    Raises :class:`ValueError` for unknown provider names.
    """
    if name not in _PROVIDER_CLASSES:
        raise ValueError(
            f"Unknown AI provider '{name}'. "
            f"Available: {', '.join(sorted(_PROVIDER_CLASSES))}"
        )
    if name not in _provider_instances:
        _provider_instances[name] = _PROVIDER_CLASSES[name]()
    return _provider_instances[name]


def get_provider_with_fallback(
    primary: str = "codex",
    fallback: str = "claude",
) -> AIProvider:
    """Return *primary* provider if available, otherwise *fallback*.

    Raises :class:`ValueError` if neither name is valid.
    """
    prov = get_provider(primary)
    if prov.is_available():
        return prov
    logger.info(
        "%s provider unavailable, falling back to %s", primary, fallback,
    )
    return get_provider(fallback)


def reset_registry() -> None:
    """Clear cached provider instances (useful for tests)."""
    _provider_instances.clear()
    # Reset availability cache on all known classes
    for cls in _PROVIDER_CLASSES.values():
        if hasattr(cls, "_available"):
            cls._available = None  # type: ignore[attr-defined]


def register_provider(name: str, provider_cls: type[AIProvider]) -> None:
    """Register or replace a provider class. Useful for tests that inject fakes."""
    _PROVIDER_CLASSES[name] = provider_cls
    _provider_instances.pop(name, None)
