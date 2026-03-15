from __future__ import annotations

import subprocess
from pathlib import Path

from ncdev.models import BuildBatchResult, BuildResultDoc, ChangePlanDoc


def _run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, check=False)
    out = (proc.stdout or "").strip() or (proc.stderr or "").strip()
    return proc.returncode, out


def _is_git_repo(path: Path) -> bool:
    rc, _ = _run(["git", "rev-parse", "--is-inside-work-tree"], path)
    return rc == 0


def _merge_batch(project_path: Path, branch: str) -> tuple[bool, str]:
    rc, out = _run(["git", "merge", "--no-ff", branch, "-m", f"merge: {branch}"], project_path)
    if rc != 0:
        _run(["git", "merge", "--abort"], project_path)
        return False, out
    return True, out


def _current_head_sha(project_path: Path) -> str:
    rc, out = _run(["git", "rev-parse", "HEAD"], project_path)
    return out.strip() if rc == 0 else ""


def _create_checkpoint(project_path: Path, checkpoint_name: str, sha: str) -> tuple[bool, str]:
    if not sha:
        return False, "no head sha available"
    rc, out = _run(["git", "branch", "-f", checkpoint_name, sha], project_path)
    return rc == 0, out


def _cleanup_worktree(project_path: Path, worktree: Path) -> None:
    _run(["git", "worktree", "remove", str(worktree), "--force"], project_path)


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
    repo_mode = _is_git_repo(project_path)

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
                    notes=f"Simulated build+merge governance for {batch.title}",
                )
            )
            continue

        if not repo_mode:
            results.append(
                BuildBatchResult(
                    batch_id=batch.id,
                    status="failed",
                    branch=branch,
                    worktree_path=str(worktree),
                    attempts=0,
                    builder_used="codex",
                    notes="project path is not a git repository",
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
            rc, out = _run(["codex", "exec", "--skip-git-repo-check", "--sandbox", "danger-full-access", prompt], worktree)
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
        checkpoint_name = f"nc-dev/checkpoint/{batch.id}"
        checkpoint_sha = _current_head_sha(project_path)
        checkpoint_ok, checkpoint_out = _create_checkpoint(project_path, checkpoint_name, checkpoint_sha)
        if passed:
            merged, merge_notes = _merge_batch(project_path, branch)
            results[-1].status = "passed" if merged else "failed"
            results[-1].notes = (
                f"{results[-1].notes}\ncheckpoint: {checkpoint_name}@{checkpoint_sha or 'unknown'} "
                f"({ 'ok' if checkpoint_ok else checkpoint_out[:100] })\nmerge: {merge_notes[:300]}"
            )
        _cleanup_worktree(project_path, worktree)

    return BuildResultDoc(mode=mode, project_path=str(project_path), results=results)
