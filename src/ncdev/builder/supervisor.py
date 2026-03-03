from __future__ import annotations

import subprocess
from pathlib import Path

from ncdev.models import BuildBatchResult, BuildResultDoc, ChangePlanDoc


def _run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, check=False)
    out = (proc.stdout or "").strip() or (proc.stderr or "").strip()
    return proc.returncode, out


def _build_codex_prompt(batch_id: str, title: str) -> str:
    return (
        f"Implement batch {batch_id}: {title}. "
        "Follow repository conventions, add tests, and produce clean commits."
    )


def execute_change_plan(
    project_path: Path,
    mode: str,
    plan: ChangePlanDoc,
    max_retries: int,
    dry_run: bool,
) -> BuildResultDoc:
    results: list[BuildBatchResult] = []

    for batch in plan.batches:
        branch = f"nc-dev/{batch.id}"
        worktree = project_path / ".worktrees" / batch.id
        if dry_run:
            results.append(
                BuildBatchResult(
                    batch_id=batch.id,
                    status="passed",
                    branch=branch,
                    worktree_path=str(worktree),
                    attempts=1,
                    builder_used="codex(dry-run)",
                    notes=f"Simulated build for {batch.title}",
                )
            )
            continue

        project_path.joinpath(".worktrees").mkdir(parents=True, exist_ok=True)
        rc, out = _run(["git", "worktree", "add", str(worktree), "-b", branch], project_path)
        if rc != 0:
            results.append(
                BuildBatchResult(
                    batch_id=batch.id,
                    status="failed",
                    branch=branch,
                    worktree_path=str(worktree),
                    attempts=0,
                    builder_used="codex",
                    notes=f"worktree create failed: {out}",
                )
            )
            continue

        attempts = 0
        passed = False
        notes = ""
        builder_used = "codex"
        prompt = _build_codex_prompt(batch.id, batch.title)

        while attempts < max_retries and not passed:
            attempts += 1
            rc, out = _run(["codex", "exec", "--skip-git-repo-check", prompt], worktree)
            if rc == 0:
                passed = True
                notes = out[:500]
            else:
                notes = out[:500]

        if not passed:
            builder_used = "claude-fallback"
            rc, out = _run(["claude", "--print", prompt], worktree)
            passed = rc == 0
            notes = out[:500]

        results.append(
            BuildBatchResult(
                batch_id=batch.id,
                status="passed" if passed else "failed",
                branch=branch,
                worktree_path=str(worktree),
                attempts=attempts,
                builder_used=builder_used,
                notes=notes,
            )
        )

    return BuildResultDoc(mode=mode, project_path=str(project_path), results=results)
