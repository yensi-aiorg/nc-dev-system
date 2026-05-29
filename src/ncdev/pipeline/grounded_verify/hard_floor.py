# src/ncdev/pipeline/grounded_verify/hard_floor.py
"""Pre-LLM hard floor. The only checks the agent cannot override."""
from __future__ import annotations

from pathlib import Path

from ncdev.pipeline.claude_executor import (
    _git_head, _git_working_tree_dirty, _run_shell,
)
from ncdev.pipeline.grounded_verify.models import HardFloorResult


def check_hard_floor(
    target_path: Path,
    *,
    pre_commit: str,
    compile_cmd: str | None,
    timeout: int = 300,
) -> HardFloorResult:
    """Auto-fail only if there is no work to judge, or it won't compile."""
    made_commit = _git_head(target_path) != pre_commit
    dirty = _git_working_tree_dirty(target_path)
    if not made_commit and not dirty:
        return HardFloorResult(passed=False, reason="no work produced (no commit, clean tree)")
    if compile_cmd:
        ok, out = _run_shell(compile_cmd, cwd=target_path, timeout=timeout)
        if not ok:
            return HardFloorResult(
                passed=False,
                reason=f"does not compile: {out.strip().splitlines()[-1] if out.strip() else compile_cmd}",
            )
    return HardFloorResult(passed=True)
