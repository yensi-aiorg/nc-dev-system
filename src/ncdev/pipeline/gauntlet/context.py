"""Shared context and helpers for gauntlet layers.

Every layer is a callable ``(GauntletContext) -> GauntletLayerResult``.
The context carries everything a layer might need; layers read only
what they care about. Keeping it one immutable-ish struct means layers
stay independently testable — construct a context, call the layer,
assert the result.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ncdev.core.config import NCDevConfig
from ncdev.pipeline.models import FeatureStep, VerificationContract


@dataclass
class GauntletContext:
    """Everything the gauntlet layers operate on for one feature."""

    feature: FeatureStep
    contract: VerificationContract
    repo: Path

    # Files the feature's session created or modified. Layers that scan
    # a diff (anti-bypass) or scope checks to touched code use this.
    changed_files: list[str] = field(default_factory=list)

    # Unified diff of the feature's work, for anti-bypass and oracle.
    diff: str = ""

    # Which provider built the feature. The oracle layer requires a
    # *different* provider to review, to decorrelate blind spots.
    builder_provider: str = "claude"

    config: NCDevConfig | None = None

    # When False, command-running layers do not shell out — they report
    # SKIPPED. Lets the executor run a fast, hermetic gauntlet in
    # environments where the app cannot be brought up.
    run_commands: bool = True


def run_shell(cmd: str, *, cwd: Path, timeout: int = 600) -> tuple[bool, int, str]:
    """Run a shell command, return (ok, exit_code, combined_output).

    ``ok`` is True only on exit code 0. Output is stdout+stderr merged.
    A timeout or missing shell is reported as ok=False with a synthetic
    exit code so a layer never crashes on a bad command.
    """
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode == 0, proc.returncode, output
    except subprocess.TimeoutExpired:
        return False, -1, f"command timed out after {timeout}s: {cmd}"
    except (OSError, ValueError) as exc:
        return False, -2, f"command could not run: {exc}"


def tail(text: str, lines: int = 60) -> str:
    """Last ``lines`` lines of ``text`` — output tails beat output heads."""
    rows = text.splitlines()
    if len(rows) <= lines:
        return text.strip()
    return "\n".join(rows[-lines:]).strip()
