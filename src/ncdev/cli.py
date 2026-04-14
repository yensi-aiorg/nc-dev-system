from __future__ import annotations

import argparse
import json
import subprocess
import shutil
import tempfile
from pathlib import Path

from rich.console import Console

from ncdev.preflight import run_preflight
from ncdev.v2.engine import (
    load_v2_run_state,
    run_v2_fix,
    summarize_v2_status,
)
from ncdev.v3.engine import run_v3_full

console = Console()


def _workspace(path: str | None) -> Path:
    return Path(path).resolve() if path else Path.cwd()


def _resolve_target_repo(explicit_target_repo: str | None, workspace: Path) -> Path | None:
    if explicit_target_repo:
        return Path(explicit_target_repo).resolve()
    if (workspace / ".git").exists():
        return workspace
    return None


def _quickstart_text() -> str:
    return """NC Dev System Quickstart

Recommended flow:

1. Dry-run discovery
   ncdev full --source ./docs/README.md --dry-run

2. Full build (sequential verified sprints)
   ncdev full --source ./docs/README.md --base-url http://localhost:23000

3. Full build with explicit target repo
   ncdev full --source /path/to/docs --target-repo /path/to/repo --base-url http://localhost:23000

4. Autonomous dev mode
   ncdev dev --project /path/to/project --task "Build feature X"

5. Generate video report
   ncdev report --project /path/to/project

Other commands:
   ncdev fix --report report.json --target /path/to/repo
   ncdev serve --port 16650
   ncdev doctor
"""


def _check_app_boots(target_path: Path) -> bool:
    """Check whether the backend app still imports cleanly after a fix."""
    backend_path = target_path / "backend"
    if not backend_path.exists():
        return True

    try:
        result = subprocess.run(
            ["python", "-c", "from app.main import app; print('BOOT_OK')"],
            cwd=str(backend_path),
            capture_output=True,
            text=True,
            timeout=30,
        )
        return "BOOT_OK" in result.stdout
    except Exception:
        return False


async def _run_quality_gate_fixes(manifest) -> int:
    """Apply quality gate fixes using Claude Code CLI."""
    from ncdev.quality_gate.models import FixManifest

    manifest = FixManifest.model_validate(manifest)
    target = Path(manifest.target_path).resolve()
    fixed = 0

    # Process all issues, not just P0/P1. Already sorted by priority.
    all_issues = manifest.issues
    timeout_by_priority = {"P0": 300, "P1": 300, "P2": 180, "P3": 120}
    console.print(
        f"[yellow]Fixing {len(all_issues)} issues "
        f"(P0/P1: {sum(1 for i in all_issues if i.priority in ('P0', 'P1'))}, "
        f"P2: {sum(1 for i in all_issues if i.priority == 'P2')}, "
        f"P3: {sum(1 for i in all_issues if i.priority == 'P3')})[/yellow]"
    )

    if not all_issues:
        return 0

    with tempfile.TemporaryDirectory(prefix="ncdev-qg-fixes-") as temp_dir:
        manifest_path = Path(temp_dir) / "fix-manifest.json"
        manifest_path.write_text(
            json.dumps(manifest.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )

        for issue in all_issues:
            timeout = timeout_by_priority.get(issue.priority, 120)
            console.print(f"  Fixing [{issue.priority}] {issue.title} (timeout {timeout}s)...")

            # Checkpoint before fix attempt — snapshot working tree
            snapshot = subprocess.run(
                ["git", "stash", "create"],
                cwd=str(target),
                capture_output=True,
                text=True,
            )
            stash_sha = snapshot.stdout.strip()

            reproduction = "\n".join(
                f"  {index + 1}. {step}" for index, step in enumerate(issue.reproduction)
            ) or "  1. Reproduction steps were not provided."
            affected_files = (
                ", ".join(path for path in issue.affected_files_hint if path)
                or "unknown"
            )

            prompt = f"""Fix this bug in the application.

Manifest file: {manifest_path}
Issue ID: {issue.id}
Title: {issue.title}
Priority: {issue.priority}
Category: {issue.category}
Flow: {issue.flow}

What should happen: {issue.expected}
What actually happens: {issue.actual}

Root cause hint: {issue.root_cause_hint or "None provided"}

Reproduction steps:
{reproduction}

Likely affected files: {affected_files}

Requirements:
- Make the minimal change necessary to fix this issue.
- Do not refactor unrelated code.
- Run the most relevant tests for this issue.
- Leave the repository with your code changes unstaged and uncommitted.
- Print a short summary of what you changed and which tests you ran.
"""

            try:
                result = subprocess.run(
                    [
                        "claude",
                        "-p",
                        prompt,
                        "--output-format",
                        "text",
                        "--allowedTools",
                        "Edit,Write,Bash,Read,Glob,Grep",
                    ],
                    cwd=str(target),
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired:
                console.print(f"    [red]Timed out after {timeout}s — reverting[/red]")
                subprocess.run(["git", "checkout", "."], cwd=str(target), capture_output=True)
                if stash_sha:
                    subprocess.run(["git", "stash", "apply", stash_sha], cwd=str(target), capture_output=True)
                continue
            except FileNotFoundError:
                console.print("    [red]Claude CLI not found[/red]")
                break

            if result.returncode != 0:
                error = (result.stderr or result.stdout or "").strip()
                console.print(f"    [red]Failed: {error[:200]} — reverting[/red]")
                subprocess.run(["git", "checkout", "."], cwd=str(target), capture_output=True)
                if stash_sha:
                    subprocess.run(["git", "stash", "apply", stash_sha], cwd=str(target), capture_output=True)
                continue

            if not _check_app_boots(target):
                console.print("    [red]Fix broke app — reverting[/red]")
                subprocess.run(["git", "checkout", "."], cwd=str(target), capture_output=True)
                if stash_sha:
                    subprocess.run(["git", "stash", "apply", stash_sha], cwd=str(target), capture_output=True)
                continue

            # Success — commit the fix
            subprocess.run(["git", "add", "-A"], cwd=str(target), capture_output=True)
            subprocess.run(
                ["git", "commit", "-m", f"fix: {issue.title} [{issue.id}]"],
                cwd=str(target),
                capture_output=True,
            )
            fixed += 1
            console.print("    [green]Fixed[/green]")

    tone = "green" if fixed == len(all_issues) else "yellow"
    console.print(
        f"[{tone}]Fixed {fixed}/{len(all_issues)} issues[/{tone}]"
    )
    return fixed


def _doctor_report(workspace: Path) -> tuple[bool, str]:
    required = ["git", "python3", "pytest", "claude", "codex", "node", "npm", "npx"]
    core = run_preflight(required)
    docker_path = shutil.which("docker")

    lines = ["NC Dev System Doctor", "", f"Workspace: {workspace}"]
    if (workspace / ".git").exists():
        lines.append("Target repo inference: current folder is a git repository")
    else:
        lines.append("Target repo inference: current folder is not a git repository")
    lines.append("")
    lines.append("Core requirements:")
    for cmd in required:
        status = "ok" if cmd not in core.missing else "missing"
        lines.append(f"- {cmd}: {status}")
    lines.append("")
    from ncdev.preflight import check_citex
    citex_ok = check_citex()
    lines.append("Optional:")
    lines.append(f"- docker: {'ok' if docker_path else 'missing'}")
    lines.append(f"- citex (localhost:20161): {'ok' if citex_ok else 'not running'}")
    lines.append("")
    if core.ok:
        lines.append("Result: ready")
        lines.append("Next step: run `ncdev quickstart` or `ncdev full --source <entry-doc> --dry-run`")
    else:
        lines.append(f"Result: missing core tools: {', '.join(core.missing)}")
        lines.append("Fix the missing tools above before running a full build.")
    return core.ok, "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ncdev", description="NC Dev System — autonomous builder")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("quickstart", help="Print the recommended workflow")
    sub.add_parser("doctor", help="Check prerequisites")

    # --- Full: Sequential Verified Sprint Engine ---
    full = sub.add_parser("full", help="Run the full sequential verified sprint pipeline")
    full.add_argument("--source", required=True, help="Path to source requirements or spec")
    full.add_argument("--target-repo", default=None, help="Existing target repository")
    full.add_argument("--workspace", default=None)
    full.add_argument("--base-url", default="http://localhost:23000")
    full.add_argument("--dry-run", action="store_true", help="Do not invoke builders")
    full.add_argument("--model", default="opus", choices=["opus", "sonnet", "haiku"], help="Claude model for fallback/repair")
    full.add_argument("--timeout", type=int, default=600, help="Builder timeout per feature (seconds)")
    full.add_argument("--max-repairs", type=int, default=2, help="Max repair attempts per feature")
    full.add_argument("--quality-gate", action="store_true", default=False, help="Run quality gate loop after build completes")

    # --- Dev Mode: The Autonomous Senior Engineer ---
    dev_parser = sub.add_parser("dev", help="Autonomous development — Claude + Codex + Citex + Playwright")
    dev_parser.add_argument("--project", required=True, help="Path to the project directory")
    dev_parser.add_argument("--task", required=True, help="What to build, fix, or enhance")
    dev_parser.add_argument("--mode", default="auto", choices=["auto", "greenfield", "enhance", "bugfix"], help="Development mode")

    # --- Report: generate video report for an already-built project ---
    report_parser = sub.add_parser("report", help="Generate video report for a completed project")
    report_parser.add_argument("--project", required=True, help="Path to the project directory")
    report_parser.add_argument("--task", default="", help="Description of what was built (for narration)")

    # --- Sentinel Fix Mode ---
    fix_parser = sub.add_parser("fix", help="Fix a production error from a Sentinel report")
    fix_parser.add_argument("--report", help="Path to SentinelFailureReport JSON file")
    fix_parser.add_argument("--report-dir", help="Path to directory of report JSON files (batch mode)")
    fix_parser.add_argument("--target", required=True, help="Path to the target repository to fix")
    fix_parser.add_argument("--dry-run", action="store_true", default=False)
    fix_parser.add_argument("--auto-deploy", action="store_true", default=False, help="Auto-create PR if fix passes")
    fix_parser.add_argument("--max-attempts", type=int, default=3, help="Max fix attempts")
    fix_parser.add_argument("--batch", action="store_true", default=False, help="Process multiple reports")
    fix_parser.add_argument("--run-id", default=None, help="Resume a previous fix run")
    fix_parser.add_argument("--workspace", default=None)

    # --- Sentinel HTTP Intake ---
    serve_parser = sub.add_parser("serve", help="Start HTTP intake API for Sentinel reports")
    serve_parser.add_argument("--port", type=int, default=16650)
    serve_parser.add_argument("--workers", type=int, default=1)
    serve_parser.add_argument("--api-key", default=None, help="API key for authentication")
    serve_parser.add_argument("--workspace", default=None)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "quickstart":
        console.print(_quickstart_text())
        return 0

    if args.command == "doctor":
        workspace = Path.cwd()
        ok, report = _doctor_report(workspace)
        console.print(report)
        return 0 if ok else 1

    if args.command == "full":
        workspace = _workspace(args.workspace)
        target_repo = _resolve_target_repo(args.target_repo, workspace)
        state = run_v3_full(
            workspace=workspace,
            source_path=Path(args.source).resolve(),
            base_url=args.base_url,
            dry_run=bool(args.dry_run),
            target_repo_path=target_repo,
            builder_model=args.model,
            builder_timeout=args.timeout,
            max_repair_attempts=args.max_repairs,
        )
        console.print(f"run_id={state.run_id} status={state.status}")
        console.print(f"features: {state.completed_features}/{state.total_features} passed")
        console.print(f"run_dir={state.run_dir}")
        if state.status != "passed":
            return 1

        if args.quality_gate and not args.dry_run:
            import asyncio
            from ncdev.quality_gate.config import QualityGateConfig
            from ncdev.quality_gate.orchestrator import QualityGateOrchestrator

            qg_config = QualityGateConfig(enabled=True, max_cycles=3)
            orchestrator = QualityGateOrchestrator(qg_config)
            prd_content = Path(args.source).resolve().read_text()
            console.print("[cyan]Starting quality gate loop...[/cyan]")
            qg_state = asyncio.run(
                orchestrator.run(
                    project_name=workspace.name,
                    target_url=args.base_url,
                    target_path=str(target_repo or workspace),
                    prd_content=prd_content,
                    fix_callback=_run_quality_gate_fixes,
                )
            )
            console.print(f"quality_gate phase={qg_state.phase} cycles={qg_state.current_cycle}")
            if qg_state.final_scores:
                s = qg_state.final_scores
                console.print(f"scores: core_flow={s.core_flow} resilience={s.resilience} polish={s.polish}")
            return 0 if qg_state.phase == "passed" else 1

        return 0

    if args.command == "dev":
        from ncdev.dev import run_dev
        project_path = Path(args.project).resolve()
        result = run_dev(
            project_path=project_path,
            task=args.task,
            mode=args.mode,
        )
        return 0 if result.get("status") == "passed" else 1

    if args.command == "report":
        from ncdev.dev import generate_video_report
        project_path = Path(args.project).resolve()
        task = args.task or "Project build"
        console.print(f"[cyan]Generating video report for {project_path.name}...[/cyan]")
        video_path = generate_video_report(project_path, task, "")
        if video_path:
            console.print(f"[green]Video: {video_path}[/green]")
            return 0
        console.print("[yellow]No video generated — check screenshots in .ncdev/evidence/[/yellow]")
        return 0  # Non-fatal

    if args.command == "fix":
        workspace = _workspace(args.workspace)
        report_path = Path(args.report) if args.report else None
        target = Path(args.target)

        if report_path is None and args.report_dir is None:
            print("Error: --report or --report-dir is required")
            return 1

        if report_path:
            state = run_v2_fix(
                workspace=workspace,
                report_path=report_path,
                target_repo_path=target,
                dry_run=args.dry_run,
                auto_deploy=args.auto_deploy,
                max_attempts=args.max_attempts,
                run_id=args.run_id,
            )
            print(summarize_v2_status(state))
        return 0

    if args.command == "serve":
        from ncdev.intake_api import create_app
        import uvicorn
        workspace = _workspace(args.workspace)
        app = create_app(workspace=workspace, api_key=args.api_key or "")
        console.print(f"[cyan]Starting NC Dev intake API on port {args.port}...[/cyan]")
        uvicorn.run(app, host="0.0.0.0", port=args.port, workers=args.workers)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
