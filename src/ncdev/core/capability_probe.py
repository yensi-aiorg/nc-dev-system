"""Probe the installed toolchain — give the capability router eyes.

availability.py answers "is the binary there?"; this module answers
"what does it expose?" Results populate the existing
CapabilitySnapshotDoc schema in core/models.py.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from ncdev.core.models import (
    CapabilityDescriptor,
    ProviderCapabilitySnapshot,
)

# Claude CLI accepts these short aliases as --model values. "opus" is the
# default for planning/review/implementation. This is alias-based
# resolution — the CLIs expose no machine-readable model inventory.
CLAUDE_MODEL_ALIASES: tuple[str, ...] = ("opus", "sonnet", "haiku")

# Codex model name used when config requests "auto" and nothing is pinned.
CODEX_DEFAULT_MODEL: str = "gpt-5.5"

_SEMVER = re.compile(r"(\d+\.\d+\.\d+)")


def detect_cli_version(raw: str) -> str:
    """Extract a semver-ish version token from `<cli> --version` output."""
    match = _SEMVER.search(raw or "")
    return match.group(1) if match else "unknown"


def _run_version(binary: str) -> str:
    """Return raw `<binary> --version` stdout, or '' on any failure."""
    try:
        result = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return (result.stdout or result.stderr or "").strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def scan_installed_skills(workspace: Path | None = None) -> list[str]:
    """Return sorted, de-duplicated names of installed Claude skills.

    Scans ~/.claude/skills, ~/.claude/plugins, and <workspace>/.claude/skills.
    Each immediate subdirectory is treated as one skill. Missing
    directories are skipped silently — a missing scan source is normal,
    never an error.
    """
    roots: list[Path] = [
        Path.home() / ".claude" / "skills",
        Path.home() / ".claude" / "plugins",
    ]
    if workspace is not None:
        roots.append(workspace / ".claude" / "skills")

    found: set[str] = set()
    for root in roots:
        try:
            if not root.is_dir():
                continue
            for child in root.iterdir():
                if child.is_dir() and not child.name.startswith("."):
                    found.add(child.name)
        except OSError:
            continue
    return sorted(found)


def probe_claude() -> ProviderCapabilitySnapshot:
    """Inspect the installed `claude` CLI."""
    if shutil.which("claude") is None:
        return ProviderCapabilitySnapshot(
            provider="anthropic_claude_code",
            model=CLAUDE_MODEL_ALIASES[0],
            available=False,
            notes=["claude CLI not found on PATH"],
        )
    version = detect_cli_version(_run_version("claude"))
    return ProviderCapabilitySnapshot(
        provider="anthropic_claude_code",
        model=CLAUDE_MODEL_ALIASES[0],
        available=True,
        version=version,
        capabilities=CapabilityDescriptor(
            planning=True,
            implementation=True,
            code_review=True,
            mcp=True,
            subagents=True,
            hooks=True,
        ),
        notes=[f"accepted model aliases: {', '.join(CLAUDE_MODEL_ALIASES)}"],
    )


def probe_codex() -> ProviderCapabilitySnapshot:
    """Inspect the installed `codex` CLI."""
    if shutil.which("codex") is None:
        return ProviderCapabilitySnapshot(
            provider="openai_codex",
            model=CODEX_DEFAULT_MODEL,
            available=False,
            notes=["codex CLI not found on PATH"],
        )
    version = detect_cli_version(_run_version("codex"))
    return ProviderCapabilitySnapshot(
        provider="openai_codex",
        model=CODEX_DEFAULT_MODEL,
        available=True,
        version=version,
        capabilities=CapabilityDescriptor(
            implementation=True,
            test_implementation=True,
            shell_execution=True,
            reasoning_effort_levels=["low", "medium", "high"],
        ),
        notes=["reasoning via config key model_reasoning_effort"],
    )
