#!/usr/bin/env python3
"""NC Dev System — thin orchestrator for autonomous development.

This module is deliberately small. It spawns a single Claude session per
task and lets Claude drive everything via skills + Codex delegation. The
old 5-step plan/build/verify/fix ladder is gone — Claude's
:skill:`test-driven-development`, :skill:`verification-before-completion`,
and :skill:`systematic-debugging` skills handle that loop internally.

NC Dev's only responsibilities in this file:

1. Preflight (git repo, Citex reachable, claude + codex CLIs on PATH).
2. Ensure the target project is a git repo (and has a remote for greenfield).
3. Compose a short task prompt referencing the project + Citex.
4. Run one Claude session with full tool access (Bash so Claude can shell
   to Codex, Skill so it can invoke skills, Task so it can dispatch subagents).
5. Commit any dirty leftovers with ``[BROKEN]`` if Claude exited without
   committing (recoverability guarantee).
6. Store a short run summary in Citex.

For PRD-scale work, use :mod:`ncdev.v3.engine` (full pipeline) or the
``ncdev full`` command. This ``dev`` command is the freeform
``--task "whatever"`` entry point.
"""

from __future__ import annotations

import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel

from ncdev.ai_session import run_ai_session
from ncdev.claude_session import DEFAULT_BUILD_TOOLS
from ncdev.preflight import require_citex
from ncdev.v2.config import NCDevV2Config, load_v2_config

console = Console()

# ── Citex Integration ───────────────────────────────────────────────────
CITEX_API = "http://localhost:20161"


def citex_store(project_id: str, content: str, metadata: dict) -> bool:
    """Store a short run summary in Citex."""
    try:
        import httpx
        resp = httpx.post(
            f"{CITEX_API}/api/v1/documents/ingest",
            json={"project_id": project_id, "content": content, "metadata": metadata},
            timeout=30,
        )
        return resp.status_code < 400
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Failed to store context in Citex at {CITEX_API}") from exc


def citex_query(project_id: str, query: str, limit: int = 10) -> str:
    """Query Citex for relevant project context."""
    try:
        import httpx
        resp = httpx.post(
            f"{CITEX_API}/api/v1/retrieval/query",
            json={"project_id": project_id, "query": query, "limit": limit},
            timeout=30,
        )
        if resp.status_code < 400:
            results = resp.json()
            parts = []
            for r in results.get("results", results.get("documents", [])):
                content = r.get("content", r.get("text", ""))
                if content:
                    parts.append(content[:2000])
            return "\n\n---\n\n".join(parts) if parts else ""
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Failed to query Citex at {CITEX_API}") from exc
    return ""


# ── Git / GitHub setup ──────────────────────────────────────────────────


def _ensure_git_repo(project_path: Path, mode: str) -> None:
    """Ensure the project is a git repo (and has a remote for greenfield)."""
    git_dir = project_path / ".git"
    if not git_dir.exists():
        subprocess.run(["git", "init"], cwd=str(project_path),
                       capture_output=True, timeout=10)
        subprocess.run(["git", "add", "-A"], cwd=str(project_path),
                       capture_output=True, timeout=10)
        subprocess.run(
            ["git", "commit", "-q", "-m", "chore: initial commit"],
            cwd=str(project_path), capture_output=True, timeout=10,
        )
    subprocess.run(["git", "config", "pull.rebase", "true"],
                   cwd=str(project_path), capture_output=True, timeout=5)

    if mode in ("greenfield", "auto"):
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=str(project_path), capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            project_name = project_path.name
            console.print(f"  [yellow]Creating GitHub repo: yensi-solutions/{project_name}...[/yellow]")
            gh_result = subprocess.run(
                ["gh", "repo", "create", f"yensi-solutions/{project_name}",
                 "--private", "--source", str(project_path), "--push"],
                cwd=str(project_path), capture_output=True, text=True, timeout=30,
            )
            if gh_result.returncode == 0:
                console.print(f"  [green]✓[/green] GitHub repo created: yensi-solutions/{project_name}")
            else:
                subprocess.run(
                    ["git", "remote", "add", "origin",
                     f"git@github.com:yensi-solutions/{project_name}.git"],
                    cwd=str(project_path), capture_output=True, timeout=5,
                )


def _git_head(project_path: Path) -> str:
    r = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(project_path), capture_output=True, text=True, timeout=5,
    )
    return r.stdout.strip() if r.returncode == 0 else ""


def _git_working_tree_dirty(project_path: Path) -> bool:
    r = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(project_path), capture_output=True, text=True, timeout=5,
    )
    return r.returncode == 0 and bool(r.stdout.strip())


def _commit_broken_leftovers(project_path: Path, task: str) -> str:
    """Commit leftover dirty tree with [BROKEN] tag for recoverability.

    Only used when the session itself failed (non-zero exit, crash, timeout).
    For successful sessions that simply forgot to commit, use
    :func:`_commit_session_leftovers` instead.
    """
    subprocess.run(["git", "add", "-A"],
                   cwd=str(project_path), capture_output=True, timeout=10)
    r = subprocess.run(
        ["git", "commit", "-m",
         f"[BROKEN] ncdev dev: {task[:80]}\n\n"
         "Claude session exited without a clean working tree. "
         "Committed for recoverability."],
        cwd=str(project_path), capture_output=True, timeout=10,
    )
    if r.returncode != 0:
        return ""
    return _git_head(project_path)


def _mode_expects_codex_implementer(cfg: NCDevV2Config) -> bool:
    """Return True iff the effective mode's implementer is Codex.

    Resolution mirrors :func:`ai_session._resolve_custom_providers`:

    - preset ``claude_plan_codex_build`` → Codex
    - preset ``codex_only`` → Codex is the orchestrator AND implementer, but
      there is no Claude-to-Codex delegation to detect — the session IS
      Codex — so we do NOT warn on zero Claude→Codex calls. Return False.
    - ``custom`` → take ``routing.implementation[0]`` and map it through
      :func:`provider_dispatch.resolve_provider_name`; the long name
      ``openai_codex`` and the short alias ``codex`` both resolve to
      ``codex``.
    - any other preset → False.
    """
    if cfg.mode == "claude_plan_codex_build":
        return True
    if cfg.mode != "custom":
        return False

    from ncdev.provider_dispatch import resolve_provider_name

    impl_chain = getattr(cfg.routing, "implementation", None) or []
    if not impl_chain:
        return False
    try:
        return resolve_provider_name(impl_chain[0]) == "codex"
    except (KeyError, ValueError):
        return False


def _commit_session_leftovers(project_path: Path, task: str) -> str:
    """Auto-commit leftover dirty tree from a SUCCESSFUL session.

    When Claude's session exits with success=True but forgets to commit, we
    preserve the work with a neutral ``chore(ncdev):`` Conventional Commit
    rather than tagging it ``[BROKEN]``. The human reviewer is expected to
    amend with a more specific prefix (``feat:``, ``fix:``, ``docs:``, ...)
    if they want before pushing. Returns the new commit SHA or an empty
    string if nothing was committed.
    """
    subprocess.run(["git", "add", "-A"],
                   cwd=str(project_path), capture_output=True, timeout=10)
    short_task = task.replace("\n", " ").strip()[:72] or "uncommitted session work"
    r = subprocess.run(
        ["git", "commit", "-m",
         f"chore(ncdev): {short_task}\n\n"
         "Auto-committed by ncdev dev after a successful session that left "
         "an uncommitted working tree. Review the diff and amend the "
         "commit message with a more specific Conventional Commit prefix "
         "(feat / fix / docs / refactor / ...) before pushing."],
        cwd=str(project_path), capture_output=True, timeout=10,
    )
    if r.returncode != 0:
        return ""
    return _git_head(project_path)


# ── Prompt composition (short, contract-driven) ─────────────────────────


def _build_task_prompt(task: str, project_path: Path, project_id: str, mode: str) -> str:
    """Compose the short prompt for a freeform dev task.

    Deliberately terse — the Codex protocol is injected via
    ``--append-system-prompt`` by :func:`run_claude_session`, and Claude
    can read the repo itself with the Read tool. We do not pre-gather
    file trees or README content here; Claude is better at deciding
    what to look at.
    """
    return f"""# Task for this ncdev dev session

Mode: {mode}
Project: {project_path}
Citex project ID: {project_id}
Citex URL: {CITEX_API}

## What the user wants

{task}

## Your workflow

You are the engineer. Drive the full cycle yourself using the skill
machinery available to you. Codex is your implementation peer — see
the Codex protocol in your system prompt.

1. Explore the project using Read/Glob/Grep. Query Citex (via HTTP
   or any CLI it exposes) for prior context.
2. If this is non-trivial, use the `writing-plans` skill.
3. Use `test-driven-development` for any behavioural change.
4. **MANDATORY: Delegate bulk implementation and test writing to
   Codex via Bash.** This mode is `claude_plan_codex_build` — you
   plan, read, and review; Codex implements. For any new file, any
   new test file, any multi-file edit of similar shape (routers,
   components, models), and any change larger than roughly 30 lines,
   you MUST shell out with:
   ```
   codex exec --full-auto --sandbox danger-full-access "<scoped task>"
   ```
   Do not write bulk implementation yourself with Write/Edit just
   because it feels faster — that defeats the whole point of the
   split mode. Claude may still use Edit for small precision tweaks
   (1–10 lines), state-machine design, review fixes, and config
   adjustments. If you end a session in this mode with zero Codex
   calls while touching multiple files, the harness will surface a
   warning saying the mode contract was violated — that warning is
   not cosmetic, it means you picked the wrong tool.
5. Use `verification-before-completion` — run the project's tests,
   boot the app, check a health endpoint if one exists. No claiming
   done without evidence.
6. On failure, use `systematic-debugging` — root-cause first, don't
   loop blindly.
7. **MANDATORY: Before ending your session, stage all changes and
   create a git commit using Conventional Commits** (`feat:`, `fix:`,
   `docs:`, `refactor:`, `test:`, `chore:`, etc.). The working tree
   MUST be clean when you finish. If you leave uncommitted changes,
   the harness will auto-commit them with a neutral `chore(ncdev):`
   message — which is worse than a descriptive one from you. Do not
   end the session until `git status` shows a clean working tree.

## What success looks like

- Tests exist and pass for any behavioural change.
- Working tree is clean, all changes committed.
- One-paragraph summary in your final response.

Begin.
"""


# ── Main Entry Point ────────────────────────────────────────────────────


def run_dev(
    project_path: Path,
    task: str,
    mode: str = "auto",
    *,
    model: str | None = None,
    timeout: int = 3600,
    max_budget_usd: float | None = None,
    config: NCDevV2Config | None = None,
) -> dict[str, Any]:
    """Run a single ncdev dev session.

    This is thin glue. Claude does the actual work; NC Dev handles:
    preflight, git repo setup, session orchestration, broken-tag
    fallback on failure, Citex ingestion of the run summary.
    """
    start = time.time()
    project_id = project_path.name
    run_id = f"dev-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"

    require_citex(CITEX_API)

    console.print(Panel(
        f"[bold cyan]NC Dev System — thin orchestrator[/bold cyan]\n"
        f"Project: {project_path}\n"
        f"Task:    {task}\n"
        f"Mode:    {mode}\n"
        f"Run:     {run_id}",
        border_style="cyan",
    ))

    _ensure_git_repo(project_path, mode)

    pre_head = _git_head(project_path)

    # Load mode-aware config so the session dispatcher knows which CLI to run.
    effective_config = config
    if effective_config is None:
        try:
            effective_config = load_v2_config(project_path)
        except Exception:  # noqa: BLE001
            effective_config = NCDevV2Config()
    console.print(f"\n[bold]Running session (mode={effective_config.mode})...[/bold]")
    log_path = project_path / ".ncdev" / "runs" / run_id / "session.jsonl"
    prompt = _build_task_prompt(task, project_path, project_id, mode)
    session = run_ai_session(
        prompt,
        cwd=project_path,
        config=effective_config,
        tools=DEFAULT_BUILD_TOOLS,
        model=model,
        timeout=timeout,
        permission_mode="acceptEdits",
        max_budget_usd=max_budget_usd,
        log_path=log_path,
    )
    console.print(f"  Session: {session.summary()}")

    post_head = _git_head(project_path)
    dirty = _git_working_tree_dirty(project_path)

    # Decide status based on session outcome AND evidence of work:
    #
    #   session.success=False                       → failed; [BROKEN] commit
    #                                                 leftovers if any
    #   session.success=True  + dirty tree          → passed; auto-commit with
    #                                                 neutral chore(ncdev):
    #   session.success=True  + commit made + clean → passed
    #   session.success=True  + no commit  + clean  → failed (session claims
    #                                                 success but produced no
    #                                                 evidence of work)
    made_commit = bool(post_head and post_head != pre_head)

    if not session.success:
        status = "failed"
        if dirty:
            broken_sha = _commit_broken_leftovers(project_path, task)
            if broken_sha:
                console.print(
                    f"  [yellow]Session failed; committed leftovers with "
                    f"[BROKEN] tag: {broken_sha[:8]}[/yellow]"
                )
                post_head = broken_sha
                made_commit = True
    elif dirty:
        auto_sha = _commit_session_leftovers(project_path, task)
        if auto_sha:
            console.print(
                f"  [cyan]Session succeeded with dirty tree; "
                f"auto-committed as {auto_sha[:8]} (chore(ncdev): ...). "
                f"Amend the message before pushing if you want a more "
                f"specific Conventional Commit prefix.[/cyan]"
            )
            post_head = auto_sha
            made_commit = True
            status = "passed"
        else:
            # Auto-commit silently failed (e.g. nothing staged because
            # everything was gitignored, or git identity missing). Do NOT
            # mark this run as passed — that would hide exactly the kind of
            # false-positive-success we are trying to prevent.
            status = "failed"
            console.print(
                "  [yellow]Session reported success but auto-commit "
                "produced no SHA; working tree still dirty. Marking "
                "failed.[/yellow]"
            )
    elif made_commit:
        status = "passed"
    else:
        # Session claimed success but nothing changed — no files touched, no
        # commit made, no dirty tree. Treat as a false-positive success.
        status = "failed"
        console.print(
            "  [yellow]Session reported success but produced no commit "
            "and no working-tree changes. Marking failed — there is no "
            "evidence of work.[/yellow]"
        )

    # Mode-vs-behavior check: if the active mode expects Codex to implement
    # but the session touched files without calling Codex even once, Claude
    # implemented directly. Not a failure — just a divergence worth
    # surfacing.
    expected_codex = _mode_expects_codex_implementer(effective_config)
    codex_calls_made = len(session.codex_invocations)
    files_touched_count = len(session.files_touched)
    if (
        status == "passed"
        and expected_codex
        and codex_calls_made == 0
        and files_touched_count > 0
    ):
        console.print(
            f"  [yellow]Mode is {effective_config.mode!r} but the session "
            f"made 0 Codex calls while touching {files_touched_count} file(s). "
            f"Claude implemented directly instead of delegating. Outcome is "
            f"accepted, but consider tightening the task prompt or switching "
            f"to codex_only if delegation is required.[/yellow]"
        )

    duration = time.time() - start

    # Ingest short run summary to Citex (best-effort; do not fail the run)
    try:
        citex_store(
            project_id,
            content=(
                f"ncdev dev run {run_id}\n"
                f"Task: {task}\n"
                f"Status: {status}\n"
                f"Commit: {post_head[:12] if post_head else ''}\n"
                f"Session: {session.summary()}\n"
                f"Final response:\n{(session.final_text or '')[:2000]}"
            ),
            metadata={
                "run_id": run_id,
                "task": task[:500],
                "mode": mode,
                "status": status,
                "commit_sha": post_head,
                "skills_invoked": session.skills_invoked,
                "codex_invocations": len(session.codex_invocations),
                "total_cost_usd": session.total_cost_usd,
                "duration_seconds": duration,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
    except Exception as exc:  # noqa: BLE001
        console.print(f"  [yellow]Citex ingestion of run summary failed: {exc}[/yellow]")

    console.print(Panel(
        f"[bold]Status:[/bold] {status}\n"
        f"[bold]Commit:[/bold] {post_head[:12] if post_head else '(none)'}\n"
        f"[bold]Skills:[/bold] {', '.join(session.skills_invoked) or '(none)'}\n"
        f"[bold]Codex calls:[/bold] {codex_calls_made}\n"
        f"[bold]Files touched:[/bold] {files_touched_count}\n"
        f"[bold]Duration:[/bold] {duration:.1f}s"
        + (f"\n[bold]Cost:[/bold] ${session.total_cost_usd:.3f}"
           if session.total_cost_usd is not None else ""),
        title="Run complete",
        border_style="green" if status == "passed" else "yellow",
    ))

    return {
        "run_id": run_id,
        "status": status,
        "commit_sha": post_head,
        "session_summary": session.summary(),
        "skills_invoked": session.skills_invoked,
        "codex_invocations": session.codex_invocations,
        "total_cost_usd": session.total_cost_usd,
        "duration_seconds": duration,
        "final_text": session.final_text,
    }
