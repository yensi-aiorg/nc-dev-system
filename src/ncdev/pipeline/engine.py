"""Pipeline engine — sequential verified sprint pipeline (Claude-orchestrated).

This is the PRD-scale entry point. Replaces the old 9-artifact discovery
+ per-task-routing + parallel-builder pipeline with a thin outer loop:

    Phase 1 — Preflight                        (this module)
    Phase 2 — Charter generation                (pipeline.charter)
    Phase 3 — Design system                     (pipeline.design_phase)
    Phase 4 — Context ingestion into Citex      (pipeline.context_ingestion — brownfield)
    Phase 5 — Sequential feature execution      (pipeline.claude_executor)
    Phase 6 — Summary + metrics                 (this module)

Each phase is a Claude session (or a no-op for greenfield/skipped cases).
NC Dev itself just:

    * checks preconditions (git, claude, codex, Citex)
    * hands artifacts between phases
    * enforces hard-fail on Phase C for greenfield UI without designs
    * commits on pass, tags [BROKEN] on exhaustion
    * rolls up metrics at the end

The old run_pipeline() interface is preserved so the ``ncdev full`` CLI
command doesn't need to change.
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ncdev.utils import make_run_id
from ncdev.core.config import NCDevConfig, ensure_default_config
from ncdev.pipeline.charter import generate_charter, load_charter
from ncdev.pipeline.claude_executor import execute_feature_claude_driven
from ncdev.pipeline.design_phase import run_design_phase
from ncdev.pipeline.integration_gate import IntegrationResult, run_integration_gate
from ncdev.pipeline.models import (
    ProvenanceRecord,
    StepResult,
    StepStatus,
    PipelineRunState,
)
from ncdev.pipeline.provenance import append_provenance

console = Console()


def run_pipeline(
    workspace: Path,
    source_path: Path,
    base_url: str = "http://localhost:23000",
    dry_run: bool = False,
    target_repo_path: Path | None = None,
    run_id: str | None = None,
    builder_model: str | None = None,
    builder_timeout: int = 3600,
    max_budget_usd: float | None = None,
    config: NCDevConfig | None = None,
    strict_deps: bool = False,
    halt_on_failed: bool = True,
    skip_integration_gate: bool = False,
    skip_charter: bool = False,
    # Retained for CLI signature compat; Claude's systematic-debugging
    # skill handles repair now, so this is a no-op.
    max_repair_attempts: int | None = None,
) -> PipelineRunState:
    """Run the full pipeline on a PRD.

    Entry point for ``ncdev full --source <prd>``.
    """
    # ── Phase 1: Preflight + workspace setup ─────────────────────────────
    run_id = run_id or make_run_id("run")
    run_dir = workspace / ".nc-dev" / "runs" / run_id
    outputs_dir = run_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    # Mode-aware config: single source of truth for which CLI runs each
    # session. Load once, pass through every phase.
    if config is None:
        try:
            config = ensure_default_config(workspace)
        except Exception:  # noqa: BLE001
            config = NCDevConfig()

    # Persist the capability snapshot for this run — telemetry / the
    # spec's snapshot guardrail. Best-effort: never fail a run over it.
    try:
        from ncdev.core.capability_probe import persist_capability_snapshot

        persist_capability_snapshot(workspace)
    except Exception:  # noqa: BLE001
        pass

    state = PipelineRunState(
        run_id=run_id,
        workspace=str(workspace),
        run_dir=str(run_dir),
        target_path=str(target_repo_path) if target_repo_path else "",
        phase="init",
    )

    console.print(Panel(
        f"[bold cyan]NC Dev — {config.mode} mode[/bold cyan]\n"
        f"Run ID: {run_id}\n"
        f"Source: {source_path}\n"
        f"Target: {target_repo_path or '(greenfield)'}",
        border_style="cyan",
    ))

    # ── Phase 2: Charter ─────────────────────────────────────────────────
    state.phase = "charter"
    console.print("\n[bold]Phase 2: Charter (Claude planning session)[/bold]")

    if dry_run:
        console.print("  [dim]Dry run — skipping charter generation[/dim]")
        bundle = None
    elif skip_charter:
        try:
            bundle = load_charter(outputs_dir, strict=False)
        except Exception as exc:  # noqa: BLE001
            console.print(Panel(
                f"[bold red]Pre-built charter load failed[/bold red]\n"
                f"{exc}\n"
                f"Expected charter artifacts under: {outputs_dir}",
                border_style="red",
            ))
            state.phase = "failed"
            state.status = "failed"
            _persist_state(state, run_dir)
            return state
        console.print(
            f"  [green]✓[/green] Loaded pre-built charter: "
            f"{len(bundle.feature_queue.features)} features queued"
        )
    else:
        bundle, charter_session = generate_charter(
            prd_path=source_path,
            output_dir=outputs_dir,
            target_repo=target_repo_path,
            model=builder_model,
            max_budget_usd=max_budget_usd,
            log_path=run_dir / "logs" / "charter.jsonl",
            config=config,
        )
        if bundle is None:
            console.print(Panel(
                f"[bold red]Charter generation failed[/bold red]\n"
                f"Session: {charter_session.summary()}\n"
                f"See: {outputs_dir}/charter-error.json (if present) "
                f"or run log at {run_dir}/logs/charter.jsonl",
                border_style="red",
            ))
            state.phase = "failed"
            state.status = "failed"
            _persist_state(state, run_dir)
            return state
        console.print(f"  [green]✓[/green] Charter: {len(bundle.feature_queue.features)} features queued")

    # Resolve target path now that we have the charter
    target_path = (
        Path(bundle.contract.existing_repo_path).expanduser().resolve()
        if bundle and bundle.contract.existing_repo_path
        else (target_repo_path or (workspace / (bundle.contract.project_name if bundle else "project"))).resolve()
    )
    target_path.mkdir(parents=True, exist_ok=True)
    state.target_path = str(target_path)

    # ── Phase 3: Design system ───────────────────────────────────────────
    state.phase = "design"
    console.print("\n[bold]Phase 3: Design system[/bold]")
    if dry_run or bundle is None:
        console.print("  [dim]Skipped[/dim]")
    else:
        design = run_design_phase(
            contract=bundle.contract,
            target_path=target_path,
            output_dir=outputs_dir,
            model=builder_model,
            max_budget_usd=max_budget_usd,
            log_path=run_dir / "logs" / "design.jsonl",
            config=config,
        )
        if design.skipped:
            console.print("  [dim]Non-UI project — design phase skipped[/dim]")
        elif design.hard_failed:
            console.print(Panel(
                f"[bold red]Design phase HARD FAILED[/bold red]\n"
                f"{design.error}\n"
                f"See: {outputs_dir}/design-phase-error.json",
                border_style="red",
            ))
            state.phase = "failed"
            state.status = "failed"
            _persist_state(state, run_dir)
            return state
        else:
            src = design.design_doc.source if design.design_doc else "?"
            console.print(f"  [green]✓[/green] Design system ready (source={src})")

    # ── Phase 4: Brownfield context ingestion ────────────────────────────
    state.phase = "ingestion"
    if bundle and bundle.contract.is_brownfield and bundle.contract.uses_citex and not dry_run:
        console.print("\n[bold]Phase 4: Ingest existing code into Citex[/bold]")
        try:
            from ncdev.pipeline.citex_client import CitexClient
            from ncdev.pipeline.context_ingestion import ingest_project_context
            project_id = bundle.contract.project_name
            citex = CitexClient(project_id=project_id)
            if citex.health_check():
                report = ingest_project_context(
                    run_dir=run_dir,
                    target_path=target_path,
                    feature_queue=bundle.feature_queue,
                    project_id=project_id,
                )
                console.print(f"  [green]✓[/green] Ingested {report.successful}/{report.total_documents} docs")
            else:
                console.print("  [yellow]Citex unreachable — feature builds will run without RAG grounding[/yellow]")
        except Exception as exc:  # noqa: BLE001
            console.print(f"  [yellow]Citex ingestion failed: {exc} — continuing without RAG[/yellow]")
    else:
        console.print("\n[dim]Phase 4: Context ingestion skipped (greenfield or dry run)[/dim]")

    # ── Phase 5: Sequential feature execution ────────────────────────────
    state.phase = "building"
    completed: list[StepResult] = []

    if dry_run or bundle is None:
        console.print("\n[dim]Phase 5: Feature execution skipped (dry run)[/dim]")
    else:
        features = bundle.feature_queue.features
        state.feature_queue = bundle.feature_queue
        state.total_features = len(features)

        # Brownfield: skip features already implemented
        remaining = _filter_completed_features(target_path, features, completed)
        _sync_progress_state(state, completed)
        _persist_state(state, run_dir)
        console.print(f"\n[bold]Phase 5: Building {len(remaining)} features sequentially[/bold]")

        for feature in remaining:
            state.current_step = feature.feature_id
            _persist_state(state, run_dir)

            # Dependency gate: a feature whose depends_on_features contains
            # any non-PASSED id is skipped rather than built. In strict mode,
            # halt the whole run at the first broken dep.
            unmet = _unmet_dependencies(feature, completed)
            if unmet:
                reason = (
                    f"dependency not satisfied: {', '.join(unmet)} "
                    "(required feature(s) are not in PASSED state)"
                )
                console.print(Panel(
                    f"[red]BLOCKED[/red] {feature.feature_id} — {reason}",
                    border_style="red",
                ))
                completed.append(StepResult(
                    feature_id=feature.feature_id,
                    status=StepStatus.BLOCKED,
                    error_message=reason,
                ))
                _sync_progress_state(state, completed)
                _persist_state(state, run_dir)
                if strict_deps:
                    console.print("[red]--strict-deps set: halting run[/red]")
                    break
                continue

            console.print(Panel(
                f"[cyan]{feature.feature_id}[/cyan] — {feature.title}",
                border_style="blue",
            ))

            result = execute_feature_claude_driven(
                feature=feature,
                target_path=target_path,
                run_dir=run_dir,
                charter_bundle=bundle,
                prior_results=completed,
                project_id=bundle.contract.project_name,
                model=builder_model,
                timeout=builder_timeout,
                max_budget_usd=max_budget_usd,
                config=config,
            )
            completed.append(result)
            # Persist provenance — what this feature session actually
            # touched. Replaces marker-policing as the source of truth
            # for feature→artifact mapping.
            append_provenance(run_dir, ProvenanceRecord(
                feature_id=result.feature_id,
                commit_sha=result.commit_sha,
                files_created=list(result.files_created),
                files_modified=list(result.files_modified),
                duration_seconds=result.build_duration_seconds or 0.0,
            ))
            _sync_progress_state(state, completed)
            _persist_state(state, run_dir)

            status_style = "green" if result.status == StepStatus.PASSED else "red"
            duration_min = (result.build_duration_seconds or 0) / 60
            console.print(
                f"  [{status_style}]{result.status.value}[/{status_style}] "
                f"— commit {result.commit_sha[:8] or '(none)'} "
                f"({duration_min:.1f} min, "
                f"{len(result.files_created) + len(result.files_modified)} files)"
            )

            # Halt on first FAILED. The default behaviour — silently
            # marching past a broken feature into a [BROKEN] commit
            # while subsequent features build on top is exactly the
            # "grossly skips features and moves on" failure mode this
            # change exists to prevent. Pass halt_on_failed=False (CLI:
            # --continue-on-failed) only when explicitly opting in.
            if halt_on_failed and result.status == StepStatus.FAILED:
                console.print(Panel(
                    f"[bold red]HALT — feature {feature.feature_id} FAILED[/bold red]\n"
                    f"Reason(s):\n  - " + "\n  - ".join(
                        result.verification.failure_reasons[:5]
                        if result.verification else ["(no verification details)"]
                    ) + "\nRun aborted. Pass --continue-on-failed to override.",
                    border_style="red",
                ))
                break

    # ── Phase 5b: Integration gate ───────────────────────────────────────
    integration: IntegrationResult | None = None
    if not dry_run and bundle is not None and not skip_integration_gate:
        any_passed = any(r.status == StepStatus.PASSED for r in completed)
        if any_passed:
            state.phase = "integration"
            console.print("\n[bold]Phase 5b: Integration gate[/bold]")
            integration = run_integration_gate(
                bundle=bundle,
                target_path=target_path,
                completed=completed,
            )
            state.metadata["integration"] = integration.__dict__.copy()
            _persist_state(state, run_dir)
            if integration.passed:
                console.print(
                    f"  [green]✓[/green] Integration gate passed in "
                    f"{integration.duration_seconds:.1f}s "
                    f"({integration.routes_probed} routes probed)"
                )
            else:
                console.print(Panel(
                    "[bold red]Integration gate FAILED[/bold red]\n"
                    + "\n".join(f"  - {f}" for f in integration.failures[:10]),
                    border_style="red",
                ))

    # ── Phase 6: Summary ─────────────────────────────────────────────────
    state.phase = "complete"
    passed = [r for r in completed if r.status == StepStatus.PASSED]
    # Both FAILED (tried and broke) and BLOCKED (couldn't try because a dep
    # broke) count as run-level failures. Without this, a --strict-deps halt
    # would report "passed" despite halting because of broken deps.
    unsuccessful = [
        r for r in completed
        if r.status in (StepStatus.FAILED, StepStatus.BLOCKED)
    ]

    # Verification regression: any feature ended BLOCKED while its
    # declared dep was earlier reported PASSED is a verification bug —
    # something that "passed" actually wasn't producing the artifacts a
    # downstream feature relied on. Surface it as a hard error rather
    # than letting it hide in a partial-pass status.
    regressions = _detect_verification_regressions(completed)
    if regressions:
        state.status = "verification_regression"
        state.metadata["verification_regressions"] = regressions
    elif integration is not None and not integration.passed:
        # The whole product must work as a unit. Per-feature PASSED is
        # necessary but not sufficient — if integration fails, the run
        # is integration_failed regardless of feature counts.
        state.status = "integration_failed"
    elif not unsuccessful:
        state.status = "passed"
    elif passed:
        state.status = "partial"
    else:
        state.status = "failed"

    _print_summary_table(completed)

    if regressions:
        console.print(Panel(
            "[bold red]Verification regression detected[/bold red]\n"
            "Features ended BLOCKED whose declared dependencies were "
            "earlier reported PASSED — that means an earlier feature's "
            "verification missed a real defect. Investigate:\n  - "
            + "\n  - ".join(regressions),
            border_style="red",
        ))

    _persist_state(state, run_dir)
    return state


def _detect_verification_regressions(completed: list[StepResult]) -> list[str]:
    """Return human-readable descriptions of dep-was-PASSED-now-BLOCKED cases.

    A feature is BLOCKED when ``_unmet_dependencies`` returns a non-empty
    list at gate time. If any of those deps are present in ``completed``
    with status PASSED, the verifier signed off on something that didn't
    actually deliver — a real bug we shouldn't quietly downgrade to
    "partial".
    """
    by_id = {r.feature_id: r for r in completed}
    regressions: list[str] = []
    for r in completed:
        if r.status != StepStatus.BLOCKED:
            continue
        # Parse the feature_ids out of the BLOCKED error_message — the
        # engine writes them as comma-separated after the colon.
        msg = r.error_message or ""
        if "dependency not satisfied:" not in msg:
            continue
        deps_part = msg.split("dependency not satisfied:", 1)[1]
        deps_part = deps_part.split("(", 1)[0]
        dep_ids = [d.strip() for d in deps_part.split(",") if d.strip()]
        for dep in dep_ids:
            prior = by_id.get(dep)
            if prior is not None and prior.status == StepStatus.PASSED:
                regressions.append(
                    f"{r.feature_id} blocked on {dep!r} which was reported PASSED earlier"
                )
    return regressions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unmet_dependencies(feature, completed: list[StepResult]) -> list[str]:
    """Return the ids in ``feature.depends_on_features`` that are not met.

    A dep is "met" when it appears in ``completed`` with status:
      * PASSED  — built successfully this run
      * SKIPPED — brownfield state-scanner determined it was already
                  implemented in the target repo before this run started
    A dep is "unmet" when it:
      * is missing from the completed list (never attempted), OR
      * has status FAILED (we tried and it broke), OR
      * has status BLOCKED (its own dep was unmet — cascading failure).

    The BLOCKED distinction stops feature-N-blocked from being treated
    as "already done" and letting feature N+1 sail through.
    """
    acceptable = {
        r.feature_id for r in completed
        if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
    }
    return [dep for dep in feature.depends_on_features if dep not in acceptable]


def _filter_completed_features(target_path: Path, features, completed: list[StepResult]):
    """Brownfield skip: drop features already implemented in the target repo."""
    try:
        from ncdev.pipeline.state_scanner import build_skip_results, scan_completed_features
    except ImportError:
        return features
    try:
        done_ids = set(scan_completed_features(target_path, features))
    except Exception:  # noqa: BLE001
        return features
    if not done_ids:
        return features
    skipped = build_skip_results(features, done_ids)
    completed.extend(skipped)
    remaining = [f for f in features if f.feature_id not in done_ids]
    console.print(f"  [dim]Skipping {len(done_ids)} features already implemented[/dim]")
    return remaining


def _print_summary_table(completed: list[StepResult]) -> None:
    if not completed:
        return
    table = Table(title="Build Summary")
    table.add_column("Feature", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Duration", justify="right")
    table.add_column("Files", justify="right")
    table.add_column("Commit", justify="right")
    for r in completed:
        colour = {
            StepStatus.PASSED: "green",
            StepStatus.FAILED: "red",
            StepStatus.BLOCKED: "red",
            StepStatus.SKIPPED: "yellow",
        }.get(r.status, "white")
        table.add_row(
            r.feature_id,
            f"[{colour}]{r.status.value}[/{colour}]",
            f"{r.build_duration_seconds:.0f}s",
            str(len(r.files_created) + len(r.files_modified)),
            r.commit_sha[:8] if r.commit_sha else "",
        )
    console.print(table)


def _persist_state(state: PipelineRunState, run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "state.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")


def _sync_progress_state(state: PipelineRunState, completed: list[StepResult]) -> None:
    """Keep persisted progress counters in sync with the completed list."""
    state.completed_steps = list(completed)
    # Count PASSED + SKIPPED — both are "done from NC Dev's perspective".
    # SKIPPED means the brownfield state scanner found them already present;
    # PASSED means they were built successfully during this run.
    state.completed_features = sum(
        1 for r in completed if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
    )
