from __future__ import annotations

import argparse
import shutil
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
        return 0 if state.status == "passed" else 1

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
