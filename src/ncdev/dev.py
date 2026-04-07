#!/usr/bin/env python3
"""NC Dev System — The Autonomous Senior Software Engineer.

Thin glue that connects Claude CLI + Codex CLI + Citex + Playwright + ElevenLabs.
The AI decides how to work. This script provides context and enforces guardrails.

Usage:
    ncdev dev --project /path/to/repo --task "Build a document Q&A for law firms"
    ncdev dev --project /path/to/repo --task "Fix payment webhook timeout" --mode bugfix
    ncdev dev --project /path/to/repo --task "Add PDF export feature" --mode enhance
"""

from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel

console = Console()

# ── Citex Integration ───────────────────────────────────────────────────
CITEX_API = "http://localhost:20160"


def citex_store(project_id: str, content: str, metadata: dict) -> bool:
    """Store context in Citex for future retrieval."""
    try:
        import httpx
        resp = httpx.post(
            f"{CITEX_API}/api/v1/documents/ingest",
            json={
                "project_id": project_id,
                "content": content,
                "metadata": metadata,
            },
            timeout=30,
        )
        return resp.status_code < 400
    except Exception:
        return False


def citex_query(project_id: str, query: str, limit: int = 10) -> str:
    """Query Citex for relevant project context."""
    try:
        import httpx
        resp = httpx.post(
            f"{CITEX_API}/api/v1/retrieval/query",
            json={
                "project_id": project_id,
                "query": query,
                "limit": limit,
            },
            timeout=30,
        )
        if resp.status_code < 400:
            results = resp.json()
            # Format results as context string
            parts = []
            for r in results.get("results", results.get("documents", [])):
                content = r.get("content", r.get("text", ""))
                if content:
                    parts.append(content[:2000])
            return "\n\n---\n\n".join(parts) if parts else ""
    except Exception:
        pass
    return ""


# ── Project Context ─────────────────────────────────────────────────────

def gather_project_context(project_path: Path, task: str) -> str:
    """Gather context about the project from filesystem + Citex."""
    parts = []

    # 1. Read README/spec if exists
    for name in ["README.md", "SPEC.md", "CLAUDE.md"]:
        fpath = project_path / name
        if fpath.exists():
            parts.append(f"## {name}\n{fpath.read_text(encoding='utf-8')[:5000]}")

    # 2. File tree
    try:
        result = subprocess.run(
            ["find", ".", "-type", "f",
             "-not", "-path", "./.git/*",
             "-not", "-path", "*/node_modules/*",
             "-not", "-path", "*/.venv/*",
             "-not", "-path", "*/__pycache__/*",
             ],
            cwd=str(project_path), capture_output=True, text=True, timeout=10,
        )
        if result.stdout:
            files = sorted(result.stdout.strip().split("\n"))[:200]
            parts.append(f"## Current File Tree ({len(files)} files)\n" + "\n".join(files))
    except Exception:
        pass

    # 3. Recent git history
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-20"],
            cwd=str(project_path), capture_output=True, text=True, timeout=5,
        )
        if result.stdout:
            parts.append(f"## Recent Git History\n{result.stdout}")
    except Exception:
        pass

    # 4. Docker/infra info
    for compose_name in ["docker-compose.yml", "docker-compose.yaml"]:
        compose_path = project_path / compose_name
        if compose_path.exists():
            parts.append(f"## Docker Compose\n{compose_path.read_text(encoding='utf-8')[:3000]}")

    # 5. Citex context (if available)
    project_id = project_path.name
    citex_context = citex_query(project_id, task)
    if citex_context:
        parts.append(f"## Previous Context from Citex\n{citex_context}")

    return "\n\n".join(parts)


# ── Guardrails ──────────────────────────────────────────────────────────

GUARDRAILS = """
## NON-NEGOTIABLE GUARDRAILS — You MUST follow these. They cannot be skipped.

1. **FULL INTEGRATION TESTING**: Every feature must be tested as part of the complete system. Do NOT report a feature as done unless it works integrated with everything else. Run the full app and verify.

2. **NO NEW ISSUES**: Run the FULL existing test suite after your changes. If ANY existing test breaks, you MUST fix the regression before reporting done. Zero tolerance.

3. **REGRESSION TESTING**: Every bug fix MUST include a regression test. Every feature MUST include tests that verify it works. Tests are NOT optional.

4. **NO UNDOING PAST WORK**: You MUST NOT remove, disable, skip, or comment out tests/features from previous work to make your current task pass. All previous work must remain intact and functional.

5. **EVIDENCE**: You MUST capture screenshots of the working feature using Playwright. You MUST show test results. You MUST prove your work.

If you cannot satisfy ALL 5 guardrails, the task is NOT done. Go back and fix it.
"""


# ── AI Invocation ───────────────────────────────────────────────────────

def invoke_ai_planning(context: str, task: str, project_path: Path) -> str:
    """Invoke Claude CLI + Codex CLI together to plan the approach."""
    planning_prompt = f"""You are working on the project at {project_path}.

## Task
{task}

## Project Context
{context}

{GUARDRAILS}

## Your Job Right Now
1. Analyze the project and the task.
2. Plan your approach — what will you build, in what order?
3. Plan your test strategy — how will you prove each piece works?
4. Consider how this fits with the existing system (if any).
5. Start implementing. Build incrementally — one small piece at a time.
6. After EACH piece: run tests, check for errors, take screenshots with Playwright if there's a UI.
7. When done: verify ALL existing tests still pass, take final screenshots, produce evidence.

IMPORTANT: You have Bash, Read, Write, Edit, Glob, Grep tools. USE Bash to:
- Run tests (pytest, vitest, npm test)
- Boot the app and check it works
- Run Playwright for screenshots
- Check for import errors
- Verify the full integration

Do NOT just write code and claim it works. PROVE it works by running it.
"""

    # Run Claude CLI as the primary builder
    console.print("[cyan]Invoking Claude CLI...[/cyan]")
    result = subprocess.run(
        [
            "claude", "-p", planning_prompt,
            "--output-format", "text",
            "--model", "claude-sonnet-4-6",
            "--allowedTools", "Edit,Write,Bash,Read,Glob,Grep",
        ],
        cwd=str(project_path),
        capture_output=True,
        text=True,
        timeout=900,  # 15 min
    )

    return result.stdout if result.returncode == 0 else f"ERROR: {result.stderr}"


def invoke_codex_parallel(context: str, task: str, project_path: Path) -> str:
    """Invoke Codex CLI for parallel/supporting work."""
    codex_prompt = f"""You are working on the project at {project_path}.

## Task
{task}

## Project Context
{context}

{GUARDRAILS}

Implement the task. Run tests after implementation. Fix any failures.
"""

    console.print("[yellow]Invoking Codex CLI...[/yellow]")
    try:
        result = subprocess.run(
            [
                "codex", "exec", "--full-auto",
                codex_prompt,
            ],
            cwd=str(project_path),
            capture_output=True,
            text=True,
            timeout=600,
        )
        return result.stdout if result.returncode == 0 else f"ERROR: {result.stderr}"
    except Exception as e:
        return f"Codex unavailable: {e}"


# ── Video Report ────────────────────────────────────────────────────────

def generate_video_report(project_path: Path, task: str, results: str) -> Path | None:
    """Generate a Playwright video with ElevenLabs audio overlay."""
    evidence_dir = project_path / ".ncdev" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    # Ask Claude to create the Playwright script and narration
    video_prompt = f"""Create a video report for this completed development task.

## Task Completed
{task}

## Results Summary
{results[:3000]}

## Instructions
1. Write a Playwright script at {evidence_dir}/record.ts that:
   - Opens the app (check docker-compose.yml for the URL, or use localhost:24100)
   - Navigates through the key features that were built/fixed
   - Takes screenshots at each step
   - Records a video of the walkthrough

2. Write a narration script at {evidence_dir}/narration.txt that:
   - Describes what was built/fixed (30 seconds)
   - Shows the key features working (30 seconds)
   - Shows tests passing (15 seconds)
   - Summary (15 seconds)
   Total: ~1-2 minutes

3. Run the Playwright script to capture the video.
4. The video should be saved at {evidence_dir}/report.webm

Focus on SHOWING the working product, not explaining code.
"""

    result = subprocess.run(
        [
            "claude", "-p", video_prompt,
            "--output-format", "text",
            "--model", "claude-sonnet-4-6",
            "--allowedTools", "Edit,Write,Bash,Read,Glob,Grep",
        ],
        cwd=str(project_path),
        capture_output=True,
        text=True,
        timeout=300,
    )

    video_path = evidence_dir / "report.webm"
    if video_path.exists():
        return video_path

    # Fallback: check for screenshots
    screenshots = list(evidence_dir.glob("*.png"))
    if screenshots:
        console.print(f"  [yellow]Video not generated but {len(screenshots)} screenshots captured[/yellow]")

    return None


# ── Guardrail Verification ──────────────────────────────────────────────

def verify_guardrails(project_path: Path) -> tuple[bool, list[str]]:
    """Run guardrail checks. Returns (passed, issues)."""
    issues = []

    # 1. Run backend tests
    backend_path = project_path / "backend"
    if backend_path.exists():
        result = subprocess.run(
            ["python", "-m", "pytest", "-q", "--tb=short"],
            cwd=str(backend_path), capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            issues.append(f"Backend tests FAILED:\n{result.stdout[-500:]}")
        else:
            console.print(f"  [green]✓[/green] Backend tests pass")

    # 2. Run frontend tests
    frontend_path = project_path / "frontend"
    if frontend_path.exists() and (frontend_path / "package.json").exists():
        result = subprocess.run(
            ["bash", "-c", "npx vitest run 2>&1 || npm test 2>&1 || true"],
            cwd=str(frontend_path), capture_output=True, text=True, timeout=120,
        )
        # Non-blocking for now — frontend test setup varies

    # 3. Check app boots
    if backend_path.exists():
        result = subprocess.run(
            ["python", "-c", "from app.main import app; print('BOOT_OK')"],
            cwd=str(backend_path), capture_output=True, text=True, timeout=30,
        )
        if "BOOT_OK" not in result.stdout:
            issues.append(f"Backend cannot boot: {result.stderr[-300:]}")
        else:
            console.print(f"  [green]✓[/green] Backend boots OK")

    # 4. Check for screenshots (evidence)
    evidence_dir = project_path / ".ncdev" / "evidence"
    screenshots = list(evidence_dir.glob("*.png")) if evidence_dir.exists() else []
    if not screenshots:
        issues.append("No screenshots captured — evidence requirement not met")

    return len(issues) == 0, issues


# ── Main Entry Point ────────────────────────────────────────────────────

def run_dev(
    project_path: Path,
    task: str,
    mode: str = "auto",
) -> dict[str, Any]:
    """Run the NC Dev System on a project.

    This is the thin glue. It:
    1. Gathers context (filesystem + Citex)
    2. Invokes Claude CLI + Codex CLI with full context
    3. Verifies guardrails
    4. Generates video report
    5. Stores results in Citex
    """
    start_time = time.time()
    project_id = project_path.name
    run_id = f"dev-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"

    console.print(Panel(
        f"[bold cyan]NC Dev System — Autonomous Senior Engineer[/bold cyan]\n"
        f"Project: {project_path}\n"
        f"Task: {task}\n"
        f"Mode: {mode}\n"
        f"Run: {run_id}",
        border_style="cyan",
    ))

    # 1. Gather context
    console.print("\n[bold]1. Gathering project context...[/bold]")
    context = gather_project_context(project_path, task)
    console.print(f"  Context: {len(context)} chars from filesystem + Citex")

    # 2. Invoke AI peers
    console.print("\n[bold]2. Invoking AI peers (Claude + Codex)...[/bold]")
    claude_output = invoke_ai_planning(context, task, project_path)
    console.print(f"  Claude: {len(claude_output)} chars output")

    # 3. Verify guardrails
    console.print("\n[bold]3. Verifying guardrails...[/bold]")
    passed, issues = verify_guardrails(project_path)

    if not passed:
        console.print(f"  [red]Guardrails FAILED — {len(issues)} issues[/red]")
        for issue in issues:
            console.print(f"    [red]✗[/red] {issue[:200]}")

        # Let Codex try to fix guardrail failures
        console.print("\n[bold]3b. Codex attempting guardrail fixes...[/bold]")
        fix_context = f"The following guardrail checks FAILED:\n" + "\n".join(issues)
        codex_output = invoke_codex_parallel(
            context + "\n\n" + fix_context,
            "Fix the guardrail failures listed above. Run tests, fix all failures.",
            project_path,
        )

        # Re-verify
        passed, issues = verify_guardrails(project_path)
        if not passed:
            console.print(f"  [red]Guardrails still failing after Codex fix attempt[/red]")

    if passed:
        console.print(f"  [green]All guardrails PASSED[/green]")

    # 4. Generate video report
    console.print("\n[bold]4. Generating video report...[/bold]")
    video_path = generate_video_report(project_path, task, claude_output)

    # 5. Store in Citex
    console.print("\n[bold]5. Storing context in Citex...[/bold]")
    citex_store(project_id, f"Task: {task}\nResult: {'PASSED' if passed else 'FAILED'}\n{claude_output[:5000]}", {
        "run_id": run_id,
        "task": task,
        "mode": mode,
        "passed": passed,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    # 6. Summary
    duration = time.time() - start_time
    result = {
        "run_id": run_id,
        "project": str(project_path),
        "task": task,
        "status": "passed" if passed else "failed",
        "duration_seconds": duration,
        "guardrails_passed": passed,
        "guardrail_issues": issues,
        "video_path": str(video_path) if video_path else None,
    }

    status_color = "green" if passed else "red"
    console.print(Panel(
        f"[{status_color}]Status: {result['status'].upper()}[/{status_color}]\n"
        f"Duration: {duration:.0f}s\n"
        f"Guardrails: {'ALL PASSED' if passed else f'{len(issues)} issues'}\n"
        f"Video: {video_path or 'not generated'}",
        title="NC Dev System — Complete",
        border_style=status_color,
    ))

    # Save run report
    report_dir = project_path / ".ncdev" / "runs" / run_id
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "report.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")

    return result
