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

import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ncdev.utils import make_run_id
from ncdev.core.config import NCDevConfig, ensure_default_config
from ncdev.monitoring import MonitorEventWriter
from ncdev.pipeline.charter import generate_charter, load_charter
from ncdev.pipeline.claude_executor import (
    _ensure_git_identity,
    execute_feature_claude_driven,
)
from ncdev.pipeline.design_phase import run_design_phase
from ncdev.pipeline.grounded_verify.integration import grounded_integration_gate
from ncdev.pipeline.integration_gate import IntegrationResult
from ncdev.pipeline.models import (
    ProvenanceRecord,
    StepResult,
    StepStatus,
    PipelineRunState,
)
from ncdev.pipeline.provenance import append_provenance
from ncdev.pipeline.project_runbook import generate_project_runbook

console = Console()

RECOVERY_DIR = ".ncdev/recovery"


def run_pipeline(
    workspace: Path,
    source_path: Path,
    base_url: str = "http://localhost:23300",
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
    target_feature_ids: list[str] | None = None,
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
    monitor = MonitorEventWriter(run_dir, run_id=run_id)
    monitor.emit(
        "run_started",
        phase="init",
        message=f"NC Dev run started in {config.mode} mode",
        data={
            "source": str(source_path),
            "target": str(target_repo_path or ""),
            "mode": config.mode,
        },
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
    monitor.emit("phase_started", phase="charter", message="Charter generation started")
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
        monitor.emit(
            "charter_ready",
            phase="charter",
            message=f"Charter ready with {len(bundle.feature_queue.features)} features",
            data={"features": [f.feature_id for f in bundle.feature_queue.features]},
        )

    # Surface charter assumptions early — before the build compounds a
    # wrong judgment call. A PRD is ambiguous by nature; silent guessing
    # is the dominant spec-failure mode (v4 Pillar C).
    if bundle is not None and bundle.feature_queue.assumptions:
        console.print(Panel(
            "[bold]Charter assumptions[/bold] — the PRD was ambiguous "
            "here; the charter resolved each by a judgment call. Review "
            "before relying on the build:\n  - "
            + "\n  - ".join(bundle.feature_queue.assumptions),
            border_style="yellow",
            title="PRD ambiguities resolved by assumption",
        ))
        state.metadata["charter_assumptions"] = list(
            bundle.feature_queue.assumptions
        )
        monitor.emit(
            "charter_decision",
            phase="charter",
            message="Charter assumptions recorded",
            data={"assumptions": list(bundle.feature_queue.assumptions)},
        )

    if bundle is not None and not (outputs_dir / "behavior-contract.v1.json").exists():
        try:
            from ncdev.contracts.behavior_contract import (
                build_behavior_contract,
                write_behavior_contract,
            )

            write_behavior_contract(
                build_behavior_contract(
                    bundle,
                    source_path=source_path,
                    output_dir=outputs_dir,
                ),
                outputs_dir,
            )
        except Exception as exc:  # noqa: BLE001
            console.print(
                f"  [yellow]Behavior contract generation failed: {exc}[/yellow]"
            )

    # Resolve target path now that we have the charter
    target_path = (
        Path(bundle.contract.existing_repo_path).expanduser().resolve()
        if bundle and bundle.contract.existing_repo_path
        else (target_repo_path or (workspace / (bundle.contract.project_name if bundle else "project"))).resolve()
    )
    target_path.mkdir(parents=True, exist_ok=True)
    state.target_path = str(target_path)

    recovery_branch = ""
    if not dry_run and bundle is not None:
        recovery_branch = _prepare_recovery_branch(
            target_path=target_path,
            run_id=run_id,
            run_dir=run_dir,
            source_path=source_path,
            project_name=bundle.contract.project_name,
            stage="charter-ready",
            outputs_dir=outputs_dir,
            state=state,
            bundle=bundle,
        )
        if recovery_branch:
            state.metadata["recovery_branch"] = recovery_branch
            _persist_state(state, run_dir)

    # ── Phase 3: Design system ───────────────────────────────────────────
    state.phase = "design"
    monitor.emit("phase_started", phase="design", message="Design phase started")
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
        if recovery_branch:
            _commit_recovery_checkpoint(
                target_path=target_path,
                run_id=run_id,
                run_dir=run_dir,
                source_path=source_path,
                branch=recovery_branch,
                project_name=bundle.contract.project_name,
                stage="design-ready",
                outputs_dir=outputs_dir,
                state=state,
                bundle=bundle,
            )

    # ── Phase 3b: AI process runbook ─────────────────────────────────────
    if dry_run or bundle is None:
        pass
    else:
        console.print("\n[bold]Phase 3b: Process runbook[/bold]")
        try:
            runbook = generate_project_runbook(
                target_path=target_path,
                output_dir=outputs_dir,
                bundle=bundle,
                config=config,
                model=builder_model,
                max_budget_usd=max_budget_usd,
                log_path=run_dir / "logs" / "project-runbook.jsonl",
            )
            state.metadata["project_runbook_source"] = runbook.source
            _persist_state(state, run_dir)
            console.print(
                f"  [green]✓[/green] Project runbook ready "
                f"(source={runbook.source})"
            )
            if recovery_branch:
                _commit_recovery_checkpoint(
                    target_path=target_path,
                    run_id=run_id,
                    run_dir=run_dir,
                    source_path=source_path,
                    branch=recovery_branch,
                    project_name=bundle.contract.project_name,
                    stage="runbook-ready",
                    outputs_dir=outputs_dir,
                    state=state,
                    bundle=bundle,
                )
        except Exception as exc:  # noqa: BLE001
            console.print(
                f"  [yellow]Project runbook generation failed: {exc} — "
                "continuing with verifier heuristics[/yellow]"
            )

    # ── Phase 4: Brownfield context ingestion ────────────────────────────
    state.phase = "ingestion"
    monitor.emit("phase_started", phase="ingestion", message="Context ingestion started")
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
    monitor.emit("phase_started", phase="building", message="Feature execution started")
    completed: list[StepResult] = []

    if dry_run or bundle is None:
        console.print("\n[dim]Phase 5: Feature execution skipped (dry run)[/dim]")
    else:
        features = bundle.feature_queue.features
        state.feature_queue = bundle.feature_queue
        state.total_features = len(features)

        # Brownfield: skip features already implemented
        remaining = _filter_completed_features(target_path, features, completed)
        if target_feature_ids:
            targets = set(target_feature_ids)
            remaining = [f for f in remaining if f.feature_id in targets]
        _sync_progress_state(state, completed)
        _persist_state(state, run_dir)
        monitor.emit(
            "feature_queue_ready",
            phase="building",
            message=f"{len(remaining)} features ready for execution",
            data={
                "remaining": [f.feature_id for f in remaining],
                "total_features": len(features),
            },
        )
        target_note = (
            f" (targeted: {', '.join(target_feature_ids)})"
            if target_feature_ids
            else ""
        )
        console.print(
            f"\n[bold]Phase 5: Building {len(remaining)} features "
            f"sequentially{target_note}[/bold]"
        )

        for feature in remaining:
            state.current_step = feature.feature_id
            _persist_state(state, run_dir)
            monitor.emit(
                "feature_started",
                phase="building",
                feature_id=feature.feature_id,
                message=f"{feature.feature_id} — {feature.title}",
                data={
                    "title": feature.title,
                    "description": feature.description,
                    "acceptance_criteria": list(feature.acceptance_criteria),
                    "required_files": list(feature.acceptance.required_files),
                    "required_tests": list(feature.acceptance.required_tests),
                },
            )

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
                monitor.emit(
                    "feature_blocked",
                    phase="building",
                    feature_id=feature.feature_id,
                    message=reason,
                )
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
            monitor.emit(
                "feature_finished",
                phase="building",
                feature_id=result.feature_id,
                message=f"{result.feature_id} {result.status.value}",
                data={
                    "status": result.status.value,
                    "commit_sha": result.commit_sha,
                    "files_created": list(result.files_created),
                    "files_modified": list(result.files_modified),
                    "cost_usd": result.cost_usd,
                    "error_message": result.error_message,
                },
            )
            if bundle.contract.uses_citex:
                try:
                    from ncdev.pipeline.context_ingestion import ingest_feature_result

                    ingest_feature_result(
                        feature=feature,
                        result=result,
                        target_path=target_path,
                        project_id=bundle.contract.project_name,
                    )
                except Exception as exc:  # noqa: BLE001
                    console.print(
                        f"  [yellow]Citex feature-result ingest skipped: "
                        f"{exc}[/yellow]"
                    )
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
            if recovery_branch:
                _commit_recovery_checkpoint(
                    target_path=target_path,
                    run_id=run_id,
                    run_dir=run_dir,
                    source_path=source_path,
                    branch=recovery_branch,
                    project_name=bundle.contract.project_name,
                    stage=f"{result.feature_id}-{result.status.value}",
                    outputs_dir=outputs_dir,
                    state=state,
                    bundle=bundle,
                )

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
            monitor.emit(
                "phase_started",
                phase="integration",
                message="Integration gate started",
            )
            console.print("\n[bold]Phase 5b: Integration gate[/bold]")
            integration = grounded_integration_gate(
                bundle=bundle,
                target_path=target_path,
                completed=completed,
            )
            state.metadata["integration"] = integration.__dict__.copy()
            _persist_state(state, run_dir)
            if integration.passed:
                monitor.emit(
                    "integration_passed",
                    phase="integration",
                    message="Integration gate passed",
                    data=integration.__dict__.copy(),
                )
                console.print(
                    f"  [green]✓[/green] Integration gate passed in "
                    f"{integration.duration_seconds:.1f}s "
                    f"({integration.routes_probed} routes probed)"
                )
            else:
                monitor.emit(
                    "integration_failed",
                    phase="integration",
                    message="Integration gate failed",
                    data=integration.__dict__.copy(),
                )
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
    monitor.emit(
        "run_completed",
        phase="complete",
        message=f"Run completed with status {state.status}",
        data={"status": state.status},
    )

    # Structured run report — consolidated observability artifact
    # (report.json + report.md): features, gauntlet verdicts, charter
    # assumptions, integration result, and what needs human attention.
    try:
        state.completed_steps = completed
        from ncdev.pipeline.run_report import write_run_report

        report_path = write_run_report(state, run_dir)
        console.print(f"  [dim]Run report: {report_path}[/dim]")
    except Exception as exc:  # noqa: BLE001
        console.print(f"  [dim]Run report generation failed: {exc}[/dim]")

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


def _prepare_recovery_branch(
    *,
    target_path: Path,
    run_id: str,
    run_dir: Path,
    source_path: Path,
    project_name: str,
    stage: str,
    outputs_dir: Path,
    state: PipelineRunState,
    bundle,
) -> str:
    """Create/switch to an NC Dev branch and land an early checkpoint.

    Feature sessions commit their own work, but the operator still needs
    a recoverable branch before the first feature session returns. This
    helper keeps that branch local and commits only compact recovery
    metadata under ``.ncdev/recovery``; the noisy workspace
    ``.nc-dev/runs`` directory remains out of the product repo.
    """
    try:
        _ensure_git_repo(target_path)
        _ensure_git_identity(target_path)
        current = _git_stdout(target_path, ["branch", "--show-current"])
        branch = (
            current
            if current.startswith("ncdev/")
            else _recovery_branch_name(project_name or target_path.name, run_id)
        )
        if current != branch:
            if _branch_exists(target_path, branch):
                switched = _git(target_path, ["switch", branch])
            else:
                switched = _git(target_path, ["switch", "-c", branch])
            if switched.returncode != 0:
                console.print(
                    f"  [yellow]Recovery branch setup skipped: "
                    f"{(switched.stderr or switched.stdout).strip()}[/yellow]"
                )
                return ""
        _commit_recovery_checkpoint(
            target_path=target_path,
            run_id=run_id,
            run_dir=run_dir,
            source_path=source_path,
            branch=branch,
            project_name=project_name,
            stage=stage,
            outputs_dir=outputs_dir,
            state=state,
            bundle=bundle,
        )
        console.print(f"  [green]✓[/green] Recovery branch ready: {branch}")
        return branch
    except Exception as exc:  # noqa: BLE001
        console.print(f"  [yellow]Recovery branch setup skipped: {exc}[/yellow]")
        return ""


def _commit_recovery_checkpoint(
    *,
    target_path: Path,
    run_id: str,
    run_dir: Path,
    source_path: Path,
    branch: str,
    project_name: str,
    stage: str,
    outputs_dir: Path,
    state: PipelineRunState,
    bundle,
) -> None:
    rels = _write_recovery_snapshot(
        target_path=target_path,
        run_id=run_id,
        run_dir=run_dir,
        source_path=source_path,
        branch=branch,
        project_name=project_name,
        stage=stage,
        outputs_dir=outputs_dir,
        state=state,
        bundle=bundle,
    )
    if not rels:
        return
    add = _git(target_path, ["add", "-f", *rels])
    if add.returncode != 0:
        console.print(
            f"  [yellow]Recovery checkpoint add failed: "
            f"{(add.stderr or add.stdout).strip()}[/yellow]"
        )
        return
    changed = _git(target_path, ["diff", "--cached", "--quiet", "--", *rels])
    if changed.returncode == 0:
        return
    commit_args = [
        "commit",
        "--no-verify",
        "-m",
        f"chore(ncdev): checkpoint {run_id}",
        "--",
        *rels,
    ]
    commit = _git(target_path, commit_args)
    if commit.returncode != 0 and "nothing to commit" not in (
        commit.stderr or commit.stdout
    ).lower():
        console.print(
            f"  [yellow]Recovery checkpoint commit failed: "
            f"{(commit.stderr or commit.stdout).strip()}[/yellow]"
        )


def _write_recovery_snapshot(
    *,
    target_path: Path,
    run_id: str,
    run_dir: Path,
    source_path: Path,
    branch: str,
    project_name: str,
    stage: str,
    outputs_dir: Path,
    state: PipelineRunState,
    bundle,
) -> list[str]:
    root = target_path / RECOVERY_DIR / run_id
    root.mkdir(parents=True, exist_ok=True)
    feature_ids = [
        str(getattr(feature, "feature_id", ""))
        for feature in getattr(bundle.feature_queue, "features", []) or []
        if getattr(feature, "feature_id", "")
    ]
    checkpoint = {
        "version": 1,
        "run_id": run_id,
        "branch": branch,
        "project_name": project_name,
        "stage": stage,
        "status": state.status,
        "phase": state.phase,
        "current_step": state.current_step,
        "source_path": str(source_path.resolve()),
        "workspace_run_dir": str(run_dir.resolve()),
        "target_path": str(target_path.resolve()),
        "feature_ids": feature_ids,
        "completed_features": state.completed_features,
        "total_features": state.total_features,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    (root / "checkpoint.json").write_text(
        json.dumps(checkpoint, indent=2) + "\n",
        encoding="utf-8",
    )

    rels = [_rel_to_repo(target_path, root / "checkpoint.json")]
    rels.extend(_copy_recovery_artifacts(run_dir=run_dir, outputs_dir=outputs_dir, root=root))
    rels.extend(_write_bundle_recovery_outputs(target_path=target_path, root=root, bundle=bundle))
    target_runbook = target_path / ".ncdev" / "project-runbook.json"
    if target_runbook.exists():
        rels.append(_rel_to_repo(target_path, target_runbook))
    return rels


def _copy_recovery_artifacts(*, run_dir: Path, outputs_dir: Path, root: Path) -> list[str]:
    rels: list[str] = []
    target_repo = root.parents[2]
    output_names = [
        "target-project-contract.json",
        "verification-contract.json",
        "feature-queue.json",
        "behavior-contract.v1.json",
        "behavior-contract.md",
        "design-system.json",
        "project-runbook.json",
    ]
    for name in output_names:
        src = outputs_dir / name
        if not src.exists() or not src.is_file():
            continue
        dest = root / "outputs" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        rels.append(_rel_to_repo(target_repo, dest))

    for src in [run_dir / "state.json", run_dir / "provenance.jsonl"]:
        if not src.exists() or not src.is_file():
            continue
        dest = root / src.name
        shutil.copyfile(src, dest)
        rels.append(_rel_to_repo(target_repo, dest))

    for src in sorted((run_dir / "steps").glob("*/result.json")):
        dest = root / "steps" / src.parent.name / "result.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        rels.append(_rel_to_repo(target_repo, dest))
    for src in sorted((run_dir / "steps").glob("*/signals.json")):
        dest = root / "steps" / src.parent.name / "signals.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        rels.append(_rel_to_repo(target_repo, dest))
    return rels


def _write_bundle_recovery_outputs(*, target_path: Path, root: Path, bundle) -> list[str]:
    """Ensure core charter files exist in the branch even in mocked runs.

    Real charter generation writes these files under ``.nc-dev/runs`` and
    they are copied above. Tests and some caller-supplied bundle flows may
    only have the in-memory bundle, so write the canonical three-file
    charter directly into the recovery snapshot if needed.
    """
    outputs = root / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    specs = {
        "target-project-contract.json": bundle.contract,
        "verification-contract.json": bundle.verification,
        "feature-queue.json": bundle.feature_queue,
    }
    rels: list[str] = []
    for name, model in specs.items():
        dest = outputs / name
        if not dest.exists():
            dest.write_text(model.model_dump_json(indent=2), encoding="utf-8")
        rels.append(_rel_to_repo(target_path, dest))
    return rels


def _ensure_git_repo(target_path: Path) -> None:
    if _git(target_path, ["rev-parse", "--is-inside-work-tree"]).returncode == 0:
        return
    init = _git(target_path, ["init", "-q"])
    if init.returncode != 0:
        raise RuntimeError((init.stderr or init.stdout).strip() or "git init failed")


def _recovery_branch_name(project_name: str, run_id: str) -> str:
    project = _slug(project_name)[:48] or "project"
    run = _slug(run_id)[:64] or "run"
    return f"ncdev/{project}-{run}"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9._-]+", "-", value.lower()).strip("-._")


def _branch_exists(repo: Path, branch: str) -> bool:
    return _git(repo, ["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"]).returncode == 0


def _git_stdout(repo: Path, args: list[str]) -> str:
    result = _git(repo, args)
    return result.stdout.strip() if result.returncode == 0 else ""


def _git(repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


def _rel_to_repo(repo: Path, path: Path) -> str:
    return path.relative_to(repo).as_posix()


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
