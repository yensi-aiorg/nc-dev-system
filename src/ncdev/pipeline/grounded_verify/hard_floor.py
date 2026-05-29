# src/ncdev/pipeline/grounded_verify/hard_floor.py
"""Pre-LLM hard floor. The only checks the agent cannot override."""
from __future__ import annotations

import py_compile
from pathlib import Path

from ncdev.pipeline.claude_executor import (
    _git_head, _git_working_tree_dirty,
)
from ncdev.pipeline.grounded_verify.models import HardFloorResult


def check_hard_floor(
    target_path: Path,
    *,
    pre_commit: str,
    changed_files: list[str],
    timeout: int = 300,
) -> HardFloorResult:
    """Auto-fail only if there is no work to judge, or a changed .py has a syntax error."""
    made_commit = _git_head(target_path) != pre_commit
    dirty = _git_working_tree_dirty(target_path)
    if not made_commit and not dirty:
        return HardFloorResult(passed=False, reason="no work produced (no commit, clean tree)")

    for path in changed_files:
        if not path.endswith(".py"):
            continue
        fp = target_path / path
        if not fp.exists():
            continue
        try:
            py_compile.compile(str(fp), doraise=True)
        except py_compile.PyCompileError as e:
            msg = e.msg if hasattr(e, "msg") else str(e)
            return HardFloorResult(
                passed=False,
                reason=f"does not compile: {path}: {msg}",
            )

    return HardFloorResult(passed=True)
