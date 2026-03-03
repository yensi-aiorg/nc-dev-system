from __future__ import annotations

import shutil
from dataclasses import dataclass


@dataclass
class PreflightResult:
    ok: bool
    required: list[str]
    missing: list[str]


def run_preflight(required: list[str]) -> PreflightResult:
    missing = [cmd for cmd in required if shutil.which(cmd) is None]
    return PreflightResult(ok=len(missing) == 0, required=required, missing=missing)


def required_commands(mode: str, full: bool) -> list[str]:
    base = ["git", "claude", "codex"]
    if full:
        base.extend(["pytest", "python3"])
        if mode == "greenfield":
            base.extend(["npm", "npx"])
    return sorted(set(base))
