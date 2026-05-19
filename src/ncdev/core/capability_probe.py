"""Probe the installed toolchain — give the capability router eyes.

availability.py answers "is the binary there?"; this module answers
"what does it expose?" Results populate the existing
CapabilitySnapshotDoc schema in core/models.py.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

from ncdev.core.models import (
    CapabilityDescriptor,
    CapabilitySnapshotDoc,
    ProviderCapabilitySnapshot,
)

# Claude CLI accepts these short aliases as --model values. "opus" is the
# default for planning/review/implementation. This is alias-based
# resolution — the CLIs expose no machine-readable model inventory.
CLAUDE_MODEL_ALIASES: tuple[str, ...] = ("opus", "sonnet", "haiku")

# Codex model name used when config requests "auto" and nothing is pinned.
CODEX_DEFAULT_MODEL: str = "gpt-5.5"

_SEMVER = re.compile(r"(\d+\.\d+\.\d+)")
_LONG_FLAG = re.compile(r"--[a-z][a-z0-9-]+")


def detect_cli_version(raw: str) -> str:
    """Extract a semver-ish version token from `<cli> --version` output."""
    match = _SEMVER.search(raw or "")
    return match.group(1) if match else "unknown"


def parse_supported_flags(help_text: str) -> list[str]:
    """Sorted, de-duplicated long flags (`--xyz`) found in CLI help text."""
    return sorted(set(_LONG_FLAG.findall(help_text or "")))


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


def _run_help(binary: str) -> str:
    """Return raw `<binary> --help` stdout, or '' on any failure."""
    try:
        result = subprocess.run(
            [binary, "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return (result.stdout or result.stderr or "").strip()
    except (OSError, subprocess.SubprocessError, TypeError):
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
    snap = ProviderCapabilitySnapshot(
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
    flags = parse_supported_flags(_run_help("claude"))
    if flags:
        snap.notes.append(f"flags: {', '.join(flags)}")
    return snap


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
    snap = ProviderCapabilitySnapshot(
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
    flags = parse_supported_flags(_run_help("codex"))
    if flags:
        snap.notes.append(f"flags: {', '.join(flags)}")
    return snap


def probe_toolchain(workspace: Path | None = None) -> CapabilitySnapshotDoc:
    """Probe every provider into one CapabilitySnapshotDoc.

    Never raises — a failed sub-probe is recorded in that provider's
    snapshot.notes and the snapshot is marked unavailable.
    """
    snapshots = [probe_claude(), probe_codex()]
    skills = scan_installed_skills(workspace)
    for snap in snapshots:
        if snap.provider == "anthropic_claude_code" and snap.available:
            snap.notes.append(f"installed skills: {', '.join(skills) or '(none)'}")
    return CapabilitySnapshotDoc(
        generator="ncdev.core.capability_probe",
        snapshots=snapshots,
    )


def write_snapshot(doc: CapabilitySnapshotDoc, path: Path) -> None:
    """Persist the snapshot atomically.

    Writes to a unique temp file in the same directory, then os.replace()
    onto the target — an atomic rename on POSIX. A concurrent reader sees
    either the old complete file or the new complete file, never a
    partial write. Concurrent writers are last-writer-wins, which is
    safe: every prober inspects the same toolchain.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{path.name}.{os.getpid()}.tmp"
    tmp.write_text(doc.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, path)


def load_snapshot(path: Path) -> CapabilitySnapshotDoc | None:
    """Load a persisted snapshot, or None if missing/corrupt."""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        return CapabilitySnapshotDoc.model_validate_json(raw)
    except ValueError:
        return None
