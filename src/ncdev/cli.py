from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console

from ncdev.engine import (
    deliver_for_run,
    load_run_state,
    run_brownfield,
    run_greenfield,
    summarize_status,
)
from ncdev.v2.engine import load_v2_run_state, run_v2_discovery, summarize_v2_status

console = Console()


def _workspace(path: str | None) -> Path:
    return Path(path).resolve() if path else Path.cwd()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ncdev", description="NC Dev System runtime")
    sub = parser.add_subparsers(dest="command", required=True)

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
    discover_v2.add_argument("--workspace", default=None)
    discover_v2.add_argument("--dry-run", action="store_true", help="Use local heuristic discovery only")

    status_v2 = sub.add_parser("status-v2", help="Print V2 run status")
    status_v2.add_argument("--run-id", required=True)
    status_v2.add_argument("--workspace", default=None)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

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
        state = run_v2_discovery(
            workspace=workspace,
            source_path=Path(args.source).resolve(),
            dry_run=bool(args.dry_run),
            command="discover-v2",
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

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
