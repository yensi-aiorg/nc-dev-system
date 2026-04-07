from __future__ import annotations

import argparse
import shutil
import threading
from pathlib import Path

from rich.console import Console

from ncdev.engine import (
    deliver_for_run,
    load_run_state,
    run_brownfield,
    run_greenfield,
    summarize_status,
)
from ncdev.preflight import run_preflight
from ncdev.utils import make_run_id
from ncdev.v2.engine import (
    load_v2_run_state,
    run_v2_deliver,
    run_v2_discovery,
    run_v2_execute,
    run_v2_fix,
    run_v2_full,
    run_v2_prepare,
    run_v2_repair,
    run_v2_verify,
    summarize_v2_status,
)
from ncdev.v2.ui import watch_run_dashboard
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

Website SaaS mode:
- run from the target repo when possible
- point --source at a README.md, requirements.md, or docs folder
- if the current folder is a git repo, it is inferred as the target repo

Recommended flow:

1. Discovery dry run
   ncdev discover-v2 --source ./docs/README.md --dry-run

2. Prepare the target repo
   ncdev prepare-v2 --source ./docs/README.md

3. Run the full loop
   ncdev full-v2 --source ./docs/README.md --base-url http://localhost:23000

Optional live UI:
- headed terminal dashboard:
  ncdev full-v2 --source ./docs/README.md --base-url http://localhost:23000 --ui headed

Useful variants:
- explicit target repo:
  ncdev full-v2 --source /path/to/docs --target-repo /path/to/repo --base-url http://localhost:23000
- status:
  ncdev status-v2 --run-id <run-id>
- verify again:
  ncdev verify-v2 --run-id <run-id> --base-url http://localhost:23000
"""


def _run_with_ui(run_dir: Path, callback):
    stop_event = threading.Event()
    result: dict[str, object] = {}
    error: dict[str, BaseException] = {}

    def _worker() -> None:
        try:
            result["value"] = callback()
        except BaseException as exc:  # pragma: no cover - re-raised in caller
            error["value"] = exc
        finally:
            stop_event.set()

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    try:
        watch_run_dashboard(run_dir, stop_event, console=console)
    finally:
        stop_event.set()
        thread.join()
    if "value" in error:
        raise error["value"]
    return result["value"]


def _run_v2_command(ui_mode: str, run_dir: Path, callback):
    if ui_mode == "headed":
        return _run_with_ui(run_dir, callback)
    return callback()


def _doctor_report(workspace: Path) -> tuple[bool, str]:
    required = ["git", "python3", "pytest", "claude", "codex", "node", "npm", "npx"]
    optional = ["docker"]
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
    lines.append("Optional:")
    lines.append(f"- docker: {'ok' if docker_path else 'missing'}")
    lines.append("")
    if core.ok:
        lines.append("Result: ready for website SaaS mode")
        lines.append("Next step: run `ncdev quickstart` or `ncdev discover-v2 --source <entry-doc> --dry-run`")
    else:
        lines.append(f"Result: missing core tools: {', '.join(core.missing)}")
        lines.append("Fix the missing tools above before running a full V2 loop.")
    return core.ok, "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ncdev", description="NC Dev System runtime")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("quickstart", help="Print the recommended website SaaS workflow")
    sub.add_parser("doctor", help="Check prerequisites for the current website SaaS mode")

    build = sub.add_parser("build", help="Run greenfield build kickoff (analysis phase)")
    build.add_argument("--requirements", required=True, help="Path to requirements markdown")
    build.add_argument("--mode", default="greenfield", choices=["greenfield"])
    build.add_argument("--workspace", default=None)
    build.add_argument("--dry-run", action="store_true", help="Use simulated model outputs")
    build.add_argument("--analysis-only", action="store_true", help="Stop after analysis phase")

    analyze = sub.add_parser("analyze", help="Analyze a brownfield repository")
    analyze.add_argument("--repo", required=True, help="Path to existing repository")
    analyze.add_argument("--mode", default="brownfield", choices=["brownfield"])
    analyze.add_argument("--include-path", action="append", default=[])
    analyze.add_argument("--exclude-path", action="append", default=[])
    analyze.add_argument("--workspace", default=None)
    analyze.add_argument("--dry-run", action="store_true", help="Use simulated model outputs")
    analyze.add_argument("--analysis-only", action="store_true", help="Stop after analysis phase")

    status = sub.add_parser("status", help="Print run status")
    status.add_argument("--run-id", required=True)
    status.add_argument("--workspace", default=None)

    deliver = sub.add_parser("deliver", help="Generate delivery summary artifact")
    deliver.add_argument("--run-id", required=True)
    deliver.add_argument("--workspace", default=None)

    discover_v2 = sub.add_parser("discover-v2", help="Run V2 source-ingest and discovery pipeline")
    discover_v2.add_argument("--source", required=True, help="Path to source requirements or discovery input")
    discover_v2.add_argument("--target-repo", default=None, help="Existing target repository to inspect and operate on")
    discover_v2.add_argument("--workspace", default=None)
    discover_v2.add_argument("--dry-run", action="store_true", help="Use local heuristic discovery only")
    discover_v2.add_argument("--ui", choices=["headless", "headed"], default="headless")

    status_v2 = sub.add_parser("status-v2", help="Print V2 run status")
    status_v2.add_argument("--run-id", required=True)
    status_v2.add_argument("--workspace", default=None)

    prepare_v2 = sub.add_parser("prepare-v2", help="Run V2 discovery and scaffold a target project")
    prepare_v2.add_argument("--source", required=True, help="Path to source requirements or discovery input")
    prepare_v2.add_argument("--target-repo", default=None, help="Existing target repository to prepare instead of scaffolding a hidden one")
    prepare_v2.add_argument("--workspace", default=None)
    prepare_v2.add_argument("--dry-run", action="store_true", help="Use local heuristic discovery only")
    prepare_v2.add_argument("--ui", choices=["headless", "headed"], default="headless")

    execute_v2 = sub.add_parser("execute-v2", help="Run queued V2 jobs for a prepared target project")
    execute_v2.add_argument("--run-id", required=True)
    execute_v2.add_argument("--workspace", default=None)
    execute_v2.add_argument("--dry-run", action="store_true", help="Do not invoke provider CLIs")
    execute_v2.add_argument("--ui", choices=["headless", "headed"], default="headless")

    verify_v2 = sub.add_parser("verify-v2", help="Run V2 verification against the prepared target project")
    verify_v2.add_argument("--run-id", required=True)
    verify_v2.add_argument("--workspace", default=None)
    verify_v2.add_argument("--base-url", default="http://localhost:23000")
    verify_v2.add_argument("--dry-run", action="store_true", help="Do not invoke project test or browser commands")
    verify_v2.add_argument("--ui", choices=["headless", "headed"], default="headless")

    repair_v2 = sub.add_parser("repair-v2", help="Run V2 repair jobs for failed execution or verification")
    repair_v2.add_argument("--run-id", required=True)
    repair_v2.add_argument("--workspace", default=None)
    repair_v2.add_argument("--dry-run", action="store_true", help="Do not invoke provider CLIs")
    repair_v2.add_argument("--ui", choices=["headless", "headed"], default="headless")

    deliver_v2 = sub.add_parser("deliver-v2", help="Assemble the V2 delivery summary artifact")
    deliver_v2.add_argument("--run-id", required=True)
    deliver_v2.add_argument("--workspace", default=None)

    full_v2 = sub.add_parser("full-v2", help="Run the full V2 flow: prepare, execute, verify, and repair if needed")
    full_v2.add_argument("--source", required=True, help="Path to source requirements or discovery input")
    full_v2.add_argument("--target-repo", default=None, help="Existing target repository to inspect, modify, and verify")
    full_v2.add_argument("--workspace", default=None)
    full_v2.add_argument("--base-url", default="http://localhost:23000")
    full_v2.add_argument("--dry-run", action="store_true", help="Do not invoke provider CLIs or test/browser commands")
    full_v2.add_argument("--repair-cycles", type=int, default=1)
    full_v2.add_argument("--ui", choices=["headless", "headed"], default="headless")

    # --- V3: Sequential Verified Sprint Engine ---
    full_v3 = sub.add_parser("full-v3", help="Run the V3 sequential verified sprint pipeline")
    full_v3.add_argument("--source", required=True, help="Path to source requirements or spec")
    full_v3.add_argument("--target-repo", default=None, help="Existing target repository")
    full_v3.add_argument("--workspace", default=None)
    full_v3.add_argument("--base-url", default="http://localhost:23000")
    full_v3.add_argument("--dry-run", action="store_true", help="Do not invoke builders")
    full_v3.add_argument("--model", default="sonnet", choices=["opus", "sonnet", "haiku"], help="Builder model")
    full_v3.add_argument("--timeout", type=int, default=600, help="Builder timeout per feature (seconds)")
    full_v3.add_argument("--max-repairs", type=int, default=2, help="Max repair attempts per feature")

    # --- Dev Mode: The Autonomous Senior Engineer ---
    dev_parser = sub.add_parser("dev", help="Autonomous development — Claude + Codex + Citex + Playwright")
    dev_parser.add_argument("--project", required=True, help="Path to the project directory")
    dev_parser.add_argument("--task", required=True, help="What to build, fix, or enhance")
    dev_parser.add_argument("--mode", default="auto", choices=["auto", "greenfield", "enhance", "bugfix"], help="Development mode")

    # --- Report: generate video report for an already-built project ---
    report_parser = sub.add_parser("report", help="Generate video report for a completed project (separate from build)")
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
    fix_parser.add_argument("--ui", choices=["headless", "headed"], default="headless")

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

    if args.command == "build":
        workspace = _workspace(args.workspace)
        state = run_greenfield(
            workspace=workspace,
            requirements_path=Path(args.requirements).resolve(),
            dry_run=bool(args.dry_run),
            full=not bool(args.analysis_only),
            command="build",
        )
        console.print(summarize_status(state))
        console.print(f"run_dir={state.run_dir}")
        return 0

    if args.command == "analyze":
        workspace = _workspace(args.workspace)
        state = run_brownfield(
            workspace=workspace,
            repo_path=Path(args.repo).resolve(),
            include_paths=args.include_path,
            exclude_paths=args.exclude_path,
            dry_run=bool(args.dry_run),
            full=not bool(args.analysis_only),
            command="analyze",
        )
        console.print(summarize_status(state))
        console.print(f"run_dir={state.run_dir}")
        return 0

    if args.command == "status":
        workspace = _workspace(args.workspace)
        state = load_run_state(workspace, args.run_id)
        console.print(summarize_status(state))
        console.print(f"run_dir={state.run_dir}")
        return 0

    if args.command == "deliver":
        workspace = _workspace(args.workspace)
        artifact = deliver_for_run(workspace, args.run_id)
        console.print(f"delivery_artifact={artifact}")
        return 0

    if args.command == "discover-v2":
        workspace = _workspace(args.workspace)
        target_repo = _resolve_target_repo(args.target_repo, workspace)
        run_id = make_run_id("v2")
        run_dir = workspace / ".nc-dev" / "v2" / "runs" / run_id
        state = _run_v2_command(
            args.ui,
            run_dir,
            lambda: run_v2_discovery(
                workspace=workspace,
                source_path=Path(args.source).resolve(),
                dry_run=bool(args.dry_run),
                command="discover-v2",
                target_repo_path=target_repo,
                run_id=run_id,
            ),
        )
        console.print(summarize_v2_status(state))
        console.print(f"run_dir={state.run_dir}")
        return 0

    if args.command == "status-v2":
        workspace = _workspace(args.workspace)
        state = load_v2_run_state(workspace, args.run_id)
        console.print(summarize_v2_status(state))
        console.print(f"run_dir={state.run_dir}")
        return 0

    if args.command == "prepare-v2":
        workspace = _workspace(args.workspace)
        target_repo = _resolve_target_repo(args.target_repo, workspace)
        run_id = make_run_id("v2")
        run_dir = workspace / ".nc-dev" / "v2" / "runs" / run_id
        state = _run_v2_command(
            args.ui,
            run_dir,
            lambda: run_v2_prepare(
                workspace=workspace,
                source_path=Path(args.source).resolve(),
                dry_run=bool(args.dry_run),
                command="prepare-v2",
                target_repo_path=target_repo,
                run_id=run_id,
            ),
        )
        console.print(summarize_v2_status(state))
        console.print(f"run_dir={state.run_dir}")
        return 0

    if args.command == "execute-v2":
        workspace = _workspace(args.workspace)
        run_dir = workspace / ".nc-dev" / "v2" / "runs" / args.run_id
        state = _run_v2_command(
            args.ui,
            run_dir,
            lambda: run_v2_execute(
                workspace=workspace,
                run_id=args.run_id,
                dry_run=bool(args.dry_run),
                command="execute-v2",
            ),
        )
        console.print(summarize_v2_status(state))
        console.print(f"run_dir={state.run_dir}")
        return 0

    if args.command == "verify-v2":
        workspace = _workspace(args.workspace)
        run_dir = workspace / ".nc-dev" / "v2" / "runs" / args.run_id
        state = _run_v2_command(
            args.ui,
            run_dir,
            lambda: run_v2_verify(
                workspace=workspace,
                run_id=args.run_id,
                base_url=args.base_url,
                dry_run=bool(args.dry_run),
                command="verify-v2",
            ),
        )
        console.print(summarize_v2_status(state))
        console.print(f"run_dir={state.run_dir}")
        return 0

    if args.command == "repair-v2":
        workspace = _workspace(args.workspace)
        run_dir = workspace / ".nc-dev" / "v2" / "runs" / args.run_id
        state = _run_v2_command(
            args.ui,
            run_dir,
            lambda: run_v2_repair(
                workspace=workspace,
                run_id=args.run_id,
                dry_run=bool(args.dry_run),
                command="repair-v2",
            ),
        )
        console.print(summarize_v2_status(state))
        console.print(f"run_dir={state.run_dir}")
        return 0

    if args.command == "deliver-v2":
        workspace = _workspace(args.workspace)
        state = run_v2_deliver(
            workspace=workspace,
            run_id=args.run_id,
            command="deliver-v2",
        )
        console.print(summarize_v2_status(state))
        console.print(f"run_dir={state.run_dir}")
        return 0

    if args.command == "full-v2":
        workspace = _workspace(args.workspace)
        target_repo = _resolve_target_repo(args.target_repo, workspace)
        run_id = make_run_id("v2")
        run_dir = workspace / ".nc-dev" / "v2" / "runs" / run_id
        state = _run_v2_command(
            args.ui,
            run_dir,
            lambda: run_v2_full(
                workspace=workspace,
                source_path=Path(args.source).resolve(),
                base_url=args.base_url,
                dry_run=bool(args.dry_run),
                repair_cycles=int(args.repair_cycles),
                command="full-v2",
                target_repo_path=target_repo,
                run_id=run_id,
            ),
        )
        console.print(summarize_v2_status(state))
        console.print(f"run_dir={state.run_dir}")
        return 0

    if args.command == "full-v3":
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
