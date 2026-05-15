"""NC Dev Factory — closed-loop autonomous build + judge + replan.

Replaces "ncdev full → maybe quality_gate" with:

    cycle 1: build → judge → continue | repair | replan | stop
    cycle 2: same, with the previous cycle's state carried forward
    ...

The judge is a Product Steward Claude session (see
``ncdev.pipeline.product_steward``). The build is the existing
``run_pipeline``. The factory itself is thin — its only job is to
sequence cycles and act on Steward dispositions until the product
is done or the budget runs out.

Mid-cycle mutations (insert_features / rewrite_acceptance /
rerun_charter) are NOT YET applied in this slice — they are logged
and downgraded to STOP_AS_UNRECOVERABLE for now. The next slice
will wire them up. CONTINUE / REPAIR / STOP work today.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from ncdev.core.config import NCDevConfig
from ncdev.pipeline.charter import load_charter
from ncdev.pipeline.engine import run_pipeline
from ncdev.pipeline.models import CharterBundle
from ncdev.pipeline.product_steward import (
    Disposition,
    StewardDecision,
    run_product_steward,
)

logger = logging.getLogger(__name__)
console = Console()


class FactoryStopReason(str, Enum):
    STEWARD_CONTINUE_AT_END = "steward_continue_at_end"
    STEWARD_UNRECOVERABLE = "steward_unrecoverable"
    BUDGET_EXHAUSTED = "budget_exhausted"
    NOT_YET_IMPLEMENTED = "disposition_not_yet_implemented"


@dataclass
class FactoryRunState:
    workspace: Path
    source_path: Path
    cycles_run: int = 0
    stop_reason: FactoryStopReason | None = None
    last_pipeline_status: str = ""
    decisions: list[StewardDecision] = field(default_factory=list)
    run_dirs: list[str] = field(default_factory=list)


def load_charter_bundle_from_run(run_dir: Path) -> CharterBundle:
    """Indirection point so tests can stub charter loading."""
    return load_charter(run_dir / "outputs", strict=False)


def run_factory(
    *,
    workspace: Path,
    source_path: Path,
    target_repo_path: Path | None = None,
    max_cycles: int = 5,
    builder_model: str | None = None,
    builder_timeout: int = 3600,
    max_budget_usd: float | None = None,
    config: NCDevConfig | None = None,
) -> FactoryRunState:
    """Run the build→judge→repeat loop.

    Returns when the Steward signals CONTINUE at end-of-queue, signals
    STOP_AS_UNRECOVERABLE, returns a not-yet-implemented disposition,
    or ``max_cycles`` has been spent.
    """
    state = FactoryRunState(
        workspace=workspace.resolve(),
        source_path=source_path.resolve(),
    )

    for cycle in range(1, max_cycles + 1):
        console.print(Panel(
            f"[bold cyan]Factory cycle {cycle}/{max_cycles}[/bold cyan]",
            border_style="cyan",
        ))

        # Phase A — build (or re-build)
        pipeline_state = run_pipeline(
            workspace=workspace,
            source_path=source_path,
            target_repo_path=target_repo_path,
            builder_model=builder_model,
            builder_timeout=builder_timeout,
            max_budget_usd=max_budget_usd,
            config=config,
            # Factory owns halting via Steward — engine should always
            # surface FAILED features instead of returning early.
            halt_on_failed=False,
        )
        state.cycles_run = cycle
        state.last_pipeline_status = pipeline_state.status
        state.run_dirs.append(pipeline_state.run_dir)

        # Phase B — judge (Steward)
        run_dir = Path(pipeline_state.run_dir)
        try:
            bundle = load_charter_bundle_from_run(run_dir)
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]Charter unreadable after build: {exc}[/red]")
            state.stop_reason = FactoryStopReason.STEWARD_UNRECOVERABLE
            return state

        decision = run_product_steward(
            prd_path=source_path,
            bundle=bundle,
            completed=list(pipeline_state.completed_steps),
            target_path=Path(pipeline_state.target_path),
            run_dir=run_dir / "steward" / f"cycle-{cycle}",
            config=config,
            model=builder_model,
            max_budget_usd=max_budget_usd,
        )
        state.decisions.append(decision)
        console.print(
            f"  [cyan]Steward[/cyan]: {decision.disposition.value} — "
            f"{decision.reasoning[:200]}"
        )

        # Phase C — act
        if decision.disposition == Disposition.CONTINUE:
            # CONTINUE at end-of-run = product is done.
            state.stop_reason = FactoryStopReason.STEWARD_CONTINUE_AT_END
            return state
        if decision.disposition == Disposition.STOP_AS_UNRECOVERABLE:
            state.stop_reason = FactoryStopReason.STEWARD_UNRECOVERABLE
            return state
        if decision.disposition == Disposition.REPAIR_CURRENT_SLICE:
            # Repair = next cycle re-runs the affected features. The
            # state scanner will see the FAILED status from this cycle
            # and not skip them. (The next slice will tighten this to
            # only re-run target_feature_ids; for now we re-enter the
            # whole pipeline.)
            continue
        if decision.disposition in {
            Disposition.INSERT_FEATURES,
            Disposition.REWRITE_ACCEPTANCE,
            Disposition.RERUN_CHARTER,
        }:
            console.print(
                f"[yellow]Disposition {decision.disposition.value} "
                "is not yet implemented in this slice — stopping. "
                "Decision persisted for the next slice to act on.[/yellow]"
            )
            state.stop_reason = FactoryStopReason.NOT_YET_IMPLEMENTED
            return state

    state.stop_reason = FactoryStopReason.BUDGET_EXHAUSTED
    return state
