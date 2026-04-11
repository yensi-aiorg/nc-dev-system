"""V3 Engine — Sequential Verified Sprint Pipeline.

Reuses V2 discovery, replaces V2 execution with sequential feature steps.
Each feature is built on top of verified working code.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ncdev.utils import make_run_id, write_json
from ncdev.v3.feature_queue import materialize_feature_queue
from ncdev.v3.models import StepResult, StepStatus, V3RunState
from ncdev.v3.step_executor import execute_feature_step

console = Console()


def run_v3_full(
    workspace: Path,
    source_path: Path,
    base_url: str,
    dry_run: bool = False,
    target_repo_path: Path | None = None,
    run_id: str | None = None,
    builder_model: str = "opus",
    builder_timeout: int = 600,
    max_repair_attempts: int = 2,
) -> V3RunState:
    """Run the full V3 pipeline: discover → queue → build features sequentially.

    This is the main entry point for V3. It reuses V2's discovery phase
    and replaces the execution phase with sequential verified steps.
    """
    from ncdev.adapters.registry import build_provider_registry, probe_registry_capabilities
    from ncdev.artifacts.state import ensure_v2_schema_files, init_v2_run_dirs, persist_v2_artifact
    from ncdev.discovery.pipeline import run_discovery_pipeline_with_target
    from ncdev.v2.config import ensure_default_v2_config
    from ncdev.v2.execution import execute_routed_tasks
    from ncdev.v2.prepare import prepare_target_project
    from ncdev.v2.routing import resolve_routing_plan

    run_id = run_id or make_run_id("v3")
    run_dir = init_v2_run_dirs(workspace, run_id)

    state = V3RunState(
        run_id=run_id,
        workspace=str(workspace),
        run_dir=str(run_dir),
        target_path=str(target_repo_path) if target_repo_path else "",
    )

    console.print(Panel(
        f"[bold cyan]NC Dev System V3 — Sequential Verified Sprint Engine[/bold cyan]\n"
        f"Run ID: {run_id}\n"
        f"Source: {source_path}\n"
        f"Target: {target_repo_path or 'auto'}",
        border_style="cyan",
    ))

    # ── Phase 1: Discovery (reuse V2) ──────────────────────────
    state.phase = "discovery"
    console.print("\n[bold]Phase 1: Discovery[/bold]")

    config = ensure_default_v2_config(workspace)
    ensure_v2_schema_files(workspace)

    registry = build_provider_registry()
    capability_doc = probe_registry_capabilities(registry)
    persist_v2_artifact(run_dir, "capability-snapshot.json", capability_doc.model_dump(mode="json"))

    routing_doc = resolve_routing_plan(config, registry)
    persist_v2_artifact(run_dir, "routing-plan.json", routing_doc.model_dump(mode="json"))

    source_pack, research_pack, feature_map, design_pack, design_brief, build_plan, phase_plan, target_contract, scaffold_plan = run_discovery_pipeline_with_target(
        source_path,
        dry_run=dry_run,
        target_repo_path=target_repo_path,
    )

    for name, doc in [
        ("source-pack.json", source_pack),
        ("research-pack.json", research_pack),
        ("feature-map.json", feature_map),
        ("design-pack.json", design_pack),
        ("design-brief.json", design_brief),
        ("build-plan.json", build_plan),
        ("phase-plan.json", phase_plan),
        ("target-project-contract.json", target_contract),
        ("scaffold-plan.json", scaffold_plan),
    ]:
        persist_v2_artifact(run_dir, name, doc.model_dump(mode="json"))

    console.print("  [green]✓[/green] Discovery complete")

    # ── Phase 2: Execution (reuse V2 for planning tasks) ──────
    state.phase = "execution"
    console.print("\n[bold]Phase 2: Planning Tasks[/bold]")

    if not dry_run:
        execution_doc = execute_routed_tasks(
            routing_doc, registry, run_dir / "outputs",
            dry_run=dry_run,
            target_repo_path=str(Path(str(target_repo_path)).resolve()) if target_repo_path else "",
        )
        persist_v2_artifact(run_dir, "execution-log.json", execution_doc.model_dump(mode="json"))
    console.print("  [green]✓[/green] Planning tasks complete")

    # ── Phase 3: Prepare Target ──────────────────────────────
    state.phase = "prepare"
    console.print("\n[bold]Phase 3: Prepare Target[/bold]")

    if not dry_run:
        scaffold_manifest, verification_contract = prepare_target_project(
            output_root=run_dir / "outputs",
            feature_map=feature_map,
            target_contract=target_contract,
            scaffold_plan=scaffold_plan,
            target_root=target_repo_path,
        )
        persist_v2_artifact(run_dir, "scaffold-manifest.json", scaffold_manifest.model_dump(mode="json"))
        persist_v2_artifact(run_dir, "verification-contract.json", verification_contract.model_dump(mode="json"))
        target_path = Path(scaffold_manifest.target_path)
    else:
        target_path = target_repo_path or workspace
    state.target_path = str(target_path)
    console.print(f"  [green]✓[/green] Target prepared at {target_path}")

    # ── Phase 4: Feature Queue ────────────────────────────────
    state.phase = "queue"
    console.print("\n[bold]Phase 4: Feature Queue[/bold]")

    feature_queue = materialize_feature_queue(
        run_dir=run_dir,
        project_name=build_plan.project_name,
    )
    write_json(run_dir / "outputs" / "feature-queue.json", feature_queue.model_dump(mode="json"))
    state.feature_queue = feature_queue
    state.total_features = len(feature_queue.features)

    console.print(f"  [green]✓[/green] {len(feature_queue.features)} features queued:")
    for f in feature_queue.features:
        console.print(f"    {f.feature_id}: {f.title}")

    # ── Phase 5: Sequential Feature Execution ─────────────────
    state.phase = "building"
    console.print("\n[bold]Phase 5: Building Features Sequentially[/bold]")

    # Load spec content for prompts
    spec_content = ""
    source_pack_path = run_dir / "outputs" / "source-pack.json"
    if source_pack_path.exists():
        sp = json.loads(source_pack_path.read_text(encoding="utf-8"))
        spec_content = sp.get("raw_content") or sp.get("content") or ""
    if not spec_content:
        spec_content = source_path.read_text(encoding="utf-8") if source_path.exists() else ""

    stack = target_contract.stack if hasattr(target_contract, "stack") else {}
    design_brief_dict = design_brief.model_dump(mode="json") if hasattr(design_brief, "model_dump") else {}

    completed: list[StepResult] = []

    if dry_run:
        console.print("  [dim]Dry run — skipping execution[/dim]")
    else:
        for feature in feature_queue.features:
            state.current_step = feature.feature_id
            _persist_state(state, run_dir)

            result = execute_feature_step(
                feature=feature,
                target_path=target_path,
                run_dir=run_dir,
                prior_results=completed,
                spec_content=spec_content,
                stack=stack if isinstance(stack, dict) else {},
                design_brief=design_brief_dict,
                max_repair_attempts=max_repair_attempts,
                builder_timeout=builder_timeout,
                builder_model=builder_model,
            )

            completed.append(result)
            state.completed_steps = completed
            state.completed_features = len([r for r in completed if r.status == StepStatus.PASSED])
            _persist_state(state, run_dir)

    # ── Phase 6: Summary ──────────────────────────────────────
    state.phase = "complete"
    passed = [r for r in completed if r.status == StepStatus.PASSED]
    failed = [r for r in completed if r.status == StepStatus.FAILED]
    state.status = "passed" if len(failed) == 0 else ("partial" if len(passed) > 0 else "failed")

    # Print summary table
    table = Table(title="V3 Build Summary")
    table.add_column("Feature", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Duration", justify="right")
    table.add_column("Files", justify="right")
    table.add_column("Repairs", justify="right")

    for r in completed:
        status_color = "green" if r.status == StepStatus.PASSED else "red"
        table.add_row(
            r.feature_id,
            f"[{status_color}]{r.status.value}[/{status_color}]",
            f"{r.build_duration_seconds:.0f}s",
            str(len(r.files_created) + len(r.files_modified)),
            str(r.repair_attempts),
        )

    console.print(table)
    console.print(Panel(
        f"[bold]Result:[/bold] {len(passed)}/{len(completed)} features passed\n"
        f"[bold]Status:[/bold] {state.status}",
        title="V3 Complete",
        border_style="green" if state.status == "passed" else "yellow",
    ))

    _persist_state(state, run_dir)
    return state


def _persist_state(state: V3RunState, run_dir: Path) -> None:
    """Save current state to disk."""
    state.updated_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    write_json(run_dir / "run-state.json", state.model_dump(mode="json"))
