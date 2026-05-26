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
rerun_charter) rewrite the charter artifacts on disk and then re-enter
the build pipeline. CONTINUE / REPAIR / STOP keep their direct loop
semantics.
"""
from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel

from ncdev.contracts.verification_report import (
    VerificationIssue,
    VerificationReport,
    load_verification_report,
    summarize_verification_report,
)
from ncdev.core.config import NCDevConfig
from ncdev.pipeline.charter import generate_charter, load_charter, write_charter
from ncdev.pipeline.charter_mutation import (
    apply_amendments,
    archive_and_clear_charter,
    insert_features,
)
from ncdev.pipeline.engine import run_pipeline
from ncdev.pipeline.issue_charter import synthesize_charter_from_report
from ncdev.pipeline.models import CharterBundle
from ncdev.pipeline.product_debt import ProductDebt, classify_issues_to_debt
from ncdev.pipeline.product_steward import (
    Disposition,
    StewardDecision,
    run_product_steward,
)
from ncdev.quality_gate.config import QualityGateConfig
from ncdev.quality_gate.orchestrator import QualityGateOrchestrator
from ncdev.utils import make_run_id

logger = logging.getLogger(__name__)
console = Console()


class FactoryStopReason(str, Enum):
    STEWARD_CONTINUE_AT_END = "steward_continue_at_end"
    STEWARD_UNRECOVERABLE = "steward_unrecoverable"
    TEST_CRAFTR_UNAVAILABLE = "test_craftr_unavailable"
    BUDGET_EXHAUSTED = "budget_exhausted"


@dataclass
class FactoryRunState:
    workspace: Path
    source_path: Path
    cycles_run: int = 0
    stop_reason: FactoryStopReason | None = None
    last_pipeline_status: str = ""
    decisions: list[StewardDecision] = field(default_factory=list)
    run_dirs: list[str] = field(default_factory=list)
    test_craftr_runs: list[str] = field(default_factory=list)
    verification_reports: list[str] = field(default_factory=list)
    baseline_run_id: str | None = None
    baseline_per_feature: dict[str, str] = field(default_factory=dict)
    last_product_debt: list[ProductDebt] = field(default_factory=list)
    changed_files_per_cycle: list[list[str]] = field(default_factory=list)


def surface_skill_candidates() -> None:
    """Print recurring skill candidates from the ledger. Silent when none."""
    from ncdev.core.capability_ledger import read_entries
    from ncdev.core.skill_candidate import detect_skill_candidates

    candidates = detect_skill_candidates(read_entries())
    if not candidates:
        return
    console.print(
        "[bold]Skill candidates detected[/bold] — recurring patterns in the "
        "capability ledger:"
    )
    for c in candidates:
        console.print(f"  - {c.pattern}  [dim](x{c.occurrences})[/dim]")
    console.print(
        "  Consider authoring a skill: "
        "[cyan]ncdev skill-author --name <name> --pattern \"<pattern>\"[/cyan]"
    )


def load_charter_bundle_from_run(run_dir: Path) -> CharterBundle:
    """Indirection point so tests can stub charter loading."""
    return load_charter(run_dir / "outputs", strict=False)


def _files_changed_in_cycle(
    target_repo: Path,
    pre_cycle_sha: str | None,
    post_cycle_sha: str | None,
) -> list[str]:
    """Return repo-relative paths changed between pre_cycle_sha and post_cycle_sha.

    Returns [] when either SHA is missing/empty (first cycle of a brand-new repo)
    or when git fails.
    """
    if not pre_cycle_sha or not post_cycle_sha or pre_cycle_sha == post_cycle_sha:
        return []
    import subprocess

    try:
        r = subprocess.run(
            ["git", "diff", "--name-only", f"{pre_cycle_sha}..{post_cycle_sha}"],
            cwd=str(target_repo),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode != 0:
            return []
        return [line.strip() for line in r.stdout.splitlines() if line.strip()]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


def _git_head(target_repo: Path) -> str | None:
    """Return current HEAD SHA, or None on failure."""
    import subprocess

    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(target_repo),
            capture_output=True,
            text=True,
            timeout=5,
        )
        return r.stdout.strip() if r.returncode == 0 else None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None


def _run_async(coro):
    """Run a coroutine to completion, even from inside a running loop.

    ``asyncio.run()`` raises ``RuntimeError`` when an event loop is
    already running on the current thread (v4 defect #5). When that is
    the case we offload the coroutine to a fresh loop on a worker
    thread so a synchronous factory caller never crashes.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro)).result()


async def _probe_test_craftr_async(
    *,
    target_url: str,
    source_path: Path,
    cycle: int,
    project_id: str,
    test_craftr_url: str,
    baseline_run_id: str | None = None,
    baseline_per_feature: dict[str, str] | None = None,
    changed_files: list[str] | None = None,
) -> tuple[str | None, list[dict[str, Any]], dict[str, Any]]:
    config = QualityGateConfig(test_craftr_url=test_craftr_url)
    orchestrator = QualityGateOrchestrator(config)
    prd_content = source_path.read_text(encoding="utf-8")
    run_id = await orchestrator.trigger_test_run(
        target_url=target_url,
        prd_content=prd_content,
        cycle=cycle,
        project_id=project_id,
        baseline_run_id=baseline_run_id,
        baseline_per_feature=baseline_per_feature,
        changed_files=changed_files,
    )
    result_data = await orchestrator.wait_for_results(run_id)
    issues = await orchestrator.fetch_issues(run_id)
    return run_id, issues, result_data.get("scores", {})


def _probe_test_craftr(
    *,
    target_url: str,
    source_path: Path,
    cycle: int,
    project_id: str,
    test_craftr_url: str,
    baseline_run_id: str | None = None,
    baseline_per_feature: dict[str, str] | None = None,
    changed_files: list[str] | None = None,
) -> tuple[str | None, list[dict[str, Any]], dict[str, Any]]:
    """Run one TestCraftr probe without making the factory depend on it."""
    try:
        return _run_async(
            _probe_test_craftr_async(
                target_url=target_url,
                source_path=source_path,
                cycle=cycle,
                project_id=project_id,
                test_craftr_url=test_craftr_url,
                baseline_run_id=baseline_run_id,
                baseline_per_feature=baseline_per_feature,
                changed_files=changed_files,
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("TestCraftr probe failed: %s", exc)
        return None, [], {}


def _resolve_test_craftr_core_path(
    *,
    explicit_path: str | Path | None,
    workspace: Path,
    target_repo_path: Path | None,
) -> Path | None:
    """Find the lightweight TestCraftr CLI package."""

    candidates: list[Path] = []
    if explicit_path:
        candidates.append(Path(explicit_path))
    env_path = os.getenv("TEST_CRAFTR_CORE_PATH")
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(workspace.resolve().parent / "test-craftr" / "tc-core")
    if target_repo_path:
        candidates.append(
            target_repo_path.resolve().parent / "test-craftr" / "tc-core"
        )
    try:
        candidates.append(
            Path(__file__).resolve().parents[3] / "test-craftr" / "tc-core"
        )
    except IndexError:
        pass

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.expanduser().resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if (resolved / "tc_core" / "cli" / "__main__.py").exists():
            return resolved
    return None


def _verification_issue_to_debt_input(
    issue: VerificationIssue,
    *,
    report: VerificationReport,
) -> dict[str, Any]:
    return {
        "id": issue.issue_id,
        "title": issue.title,
        "type": issue.issue_type or "functionality",
        "category": issue.issue_type or "functionality",
        "feature_id": issue.feature_id,
        "context": {
            "url": report.target_url,
            "scenario_id": issue.scenario_id,
            "expected": issue.expected,
            "actual": issue.actual,
        },
        "evidence": list(issue.evidence_refs),
    }


def _verification_report_to_debt_inputs(
    report: VerificationReport,
) -> list[dict[str, Any]]:
    return [
        _verification_issue_to_debt_input(issue, report=report)
        for issue in report.issues
    ]


def _local_test_craftr_scores(
    report: VerificationReport,
    *,
    report_path: Path,
) -> dict[str, Any]:
    summary = summarize_verification_report(report)
    return {
        **summary,
        "report_path": str(report_path),
    }


def _run_local_test_craftr(
    *,
    contract_path: Path,
    target_url: str,
    out_dir: Path,
    workspace: Path,
    target_repo_path: Path | None,
    test_craftr_core_path: str | Path | None = None,
    timeout_seconds: float = 10.0,
    allow_unexecuted: bool = False,
    browser_smoke: bool = False,
) -> tuple[str | None, list[dict[str, Any]], dict[str, Any], str | None, bool]:
    """Run TestCraftr's local contract runner and load its report."""

    core_path = _resolve_test_craftr_core_path(
        explicit_path=test_craftr_core_path,
        workspace=workspace,
        target_repo_path=target_repo_path,
    )
    if core_path is None:
        logger.warning("Local TestCraftr runner not found")
        return None, [], {}, None, False
    if not contract_path.exists():
        logger.warning("Behavior contract not found: %s", contract_path)
        return None, [], {}, None, False

    cmd = [
        sys.executable,
        "-m",
        "tc_core.cli",
        "run",
        "--contract",
        str(contract_path),
        "--url",
        target_url,
        "--out",
        str(out_dir),
        "--timeout",
        str(timeout_seconds),
    ]
    if target_repo_path:
        cmd.extend(["--project-path", str(target_repo_path)])
    if allow_unexecuted:
        cmd.append("--allow-unexecuted")
    if browser_smoke:
        cmd.append("--browser-smoke")

    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        str(core_path)
        if not existing_pythonpath
        else f"{core_path}{os.pathsep}{existing_pythonpath}"
    )
    try:
        subprocess.run(
            cmd,
            cwd=str(core_path),
            env=env,
            capture_output=True,
            text=True,
            timeout=max(timeout_seconds + 5.0, 15.0),
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logger.warning("Local TestCraftr runner failed: %s", exc)
        return None, [], {}, None, False

    report_path = out_dir / "verification-report.v1.json"
    if not report_path.exists():
        logger.warning("Local TestCraftr produced no report at %s", report_path)
        return None, [], {}, None, False

    try:
        report = load_verification_report(report_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Local TestCraftr report unreadable: %s", exc)
        return None, [], {}, str(report_path), False

    return (
        report.run_id,
        _verification_report_to_debt_inputs(report),
        _local_test_craftr_scores(report, report_path=report_path),
        str(report_path),
        report.is_infrastructure_failure,
    )


def _post_baseline_pin(test_craftr_url: str, payload: dict[str, Any]) -> bool:
    import httpx

    async def _pin() -> None:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{test_craftr_url}/api/baselines/pin",
                json=payload,
                timeout=30.0,
            )
            resp.raise_for_status()

    _run_async(_pin())
    return True


def _pin_test_craftr_baseline(
    *,
    target_url: str,
    source_path: Path,
    project_id: str,
    test_craftr_url: str,
) -> str | None:
    """Capture and pin the current app state as the project baseline.

    Failure is logged and returned as ``None`` so TestCraftr availability
    never crashes the factory.
    """
    run_id, _, _ = _probe_test_craftr(
        target_url=target_url,
        source_path=source_path,
        cycle=0,
        project_id=project_id,
        test_craftr_url=test_craftr_url,
    )
    if run_id is None:
        logger.warning("Baseline capture failed: TestCraftr probe returned no run_id")
        return None

    try:
        if _post_baseline_pin(
            test_craftr_url,
            {"project_id": project_id, "run_id": run_id},
        ):
            return run_id
        logger.warning("Baseline pin failed: TestCraftr returned unsuccessful status")
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Baseline pin failed: %s", exc)
        return None


def _pin_test_craftr_baseline_per_feature(
    *,
    target_url: str,
    source_path: Path,
    project_id: str,
    feature_ids: list[str],
    test_craftr_url: str,
    baseline_run_id: str | None = None,
) -> dict[str, str]:
    """Run one probe, then pin its run_id once per feature_id.

    Returns ``{feature_id: baseline_run_id}`` for features successfully
    pinned. Missing entries mean that pin failed (logged warning). A single
    probe is reused unless ``baseline_run_id`` is provided by the caller.
    """
    run_id = baseline_run_id
    if run_id is None:
        run_id, _, _ = _probe_test_craftr(
            target_url=target_url,
            source_path=source_path,
            cycle=0,
            project_id=project_id,
            test_craftr_url=test_craftr_url,
        )
    if run_id is None:
        logger.warning("Feature baseline capture failed: TestCraftr returned no run_id")
        return {}

    pinned: dict[str, str] = {}
    for feature_id in feature_ids:
        try:
            payload = {
                "project_id": project_id,
                "feature_id": feature_id,
                "run_id": run_id,
                "reason": "factory baseline",
            }
            if _post_baseline_pin(test_craftr_url, payload):
                pinned[feature_id] = run_id
            else:
                logger.warning("Feature baseline pin failed for %s", feature_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Feature baseline pin failed for %s: %s", feature_id, exc)
    return pinned


def _pin_existing_test_craftr_project_baseline(
    *,
    test_craftr_url: str,
    project_id: str,
    run_id: str,
) -> bool:
    try:
        return _post_baseline_pin(
            test_craftr_url,
            {"project_id": project_id, "run_id": run_id},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Project baseline pin failed: %s", exc)
        return False


def _feature_ids_from_bundle(bundle: CharterBundle) -> list[str]:
    return [
        str(feature.feature_id)
        for feature in getattr(bundle.feature_queue, "features", [])
        if getattr(feature, "feature_id", None)
    ]


def _known_routes_from_bundle(bundle: CharterBundle) -> list[str]:
    routes: list[str] = []
    for feature in getattr(bundle.feature_queue, "features", []):
        acceptance = getattr(feature, "acceptance", None)
        required_routes = getattr(acceptance, "required_routes", []) or []
        routes.extend(str(route) for route in required_routes if route)
    return routes


def _factory_test_craftr_project_id(
    workspace: Path,
    target_repo_path: Path | None,
) -> str:
    project_path = target_repo_path or workspace
    return project_path.resolve().name


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
    probe_test_craftr: bool = False,
    require_test_craftr: bool = False,
    capture_baseline: bool = False,
    test_craftr_mode: str = "http",
    test_craftr_core_path: str | Path | None = None,
    allow_unexecuted_contract: bool = False,
    browser_smoke_contract: bool = False,
    test_craftr_url: str = "http://localhost:16630",
    target_url: str = "http://localhost:23000",
) -> FactoryRunState:
    """Run the build→judge→repeat loop.

    Returns when the Steward signals CONTINUE at end-of-queue, signals
    STOP_AS_UNRECOVERABLE, a charter mutation is rejected, or
    ``max_cycles`` has been spent.
    """
    state = FactoryRunState(
        workspace=workspace.resolve(),
        source_path=source_path.resolve(),
    )
    project_id = _factory_test_craftr_project_id(workspace, target_repo_path)

    if capture_baseline and not probe_test_craftr:
        logger.warning(
            "Ignoring TestCraftr baseline capture because probe_test_craftr is false"
        )

    if probe_test_craftr and capture_baseline:
        state.baseline_run_id, _, _ = _probe_test_craftr(
            target_url=target_url,
            source_path=source_path,
            cycle=0,
            project_id=project_id,
            test_craftr_url=test_craftr_url,
        )

    state = _run_factory_cycle_loop(
        state=state,
        workspace=workspace,
        source_path=source_path,
        target_repo_path=target_repo_path,
        max_cycles=max_cycles,
        builder_model=builder_model,
        builder_timeout=builder_timeout,
        max_budget_usd=max_budget_usd,
        config=config,
        probe_test_craftr=probe_test_craftr,
        require_test_craftr=require_test_craftr,
        capture_baseline=capture_baseline,
        test_craftr_mode=test_craftr_mode,
        test_craftr_core_path=test_craftr_core_path,
        allow_unexecuted_contract=allow_unexecuted_contract,
        browser_smoke_contract=browser_smoke_contract,
        test_craftr_url=test_craftr_url,
        target_url=target_url,
        project_id=project_id,
    )
    surface_skill_candidates()
    return state


def run_factory_from_issues(
    *,
    workspace: Path,
    report_path: Path,
    target_repo_path: Path,
    max_cycles: int = 5,
    builder_model: str | None = None,
    builder_timeout: int = 3600,
    max_budget_usd: float | None = None,
    config: NCDevConfig | None = None,
    probe_test_craftr: bool = False,
    require_test_craftr: bool = False,
    test_craftr_mode: str = "http",
    test_craftr_core_path: str | Path | None = None,
    allow_unexecuted_contract: bool = False,
    browser_smoke_contract: bool = False,
    test_craftr_url: str = "http://localhost:16630",
    target_url: str = "http://localhost:23000",
) -> FactoryRunState:
    """Bug-fix mode entrypoint.

    Synthesizes a charter from the TC report, writes it to a fresh run_dir,
    then runs the standard factory loop against that pre-built charter.
    """
    workspace = workspace.resolve()
    report_path = report_path.resolve()
    target_repo_path = target_repo_path.resolve()
    run_id = make_run_id("factory-issues")
    run_dir = workspace / ".nc-dev" / "runs" / run_id
    outputs_dir = run_dir / "outputs"

    bundle = synthesize_charter_from_report(report_path, target_repo_path)
    write_charter(bundle, outputs_dir)

    state = FactoryRunState(
        workspace=workspace,
        source_path=report_path,
    )
    return _run_factory_cycle_loop(
        state=state,
        workspace=workspace,
        source_path=report_path,
        target_repo_path=target_repo_path,
        max_cycles=max_cycles,
        builder_model=builder_model,
        builder_timeout=builder_timeout,
        max_budget_usd=max_budget_usd,
        config=config,
        probe_test_craftr=probe_test_craftr,
        require_test_craftr=require_test_craftr,
        capture_baseline=False,
        test_craftr_mode=test_craftr_mode,
        test_craftr_core_path=test_craftr_core_path,
        allow_unexecuted_contract=allow_unexecuted_contract,
        browser_smoke_contract=browser_smoke_contract,
        test_craftr_url=test_craftr_url,
        target_url=target_url,
        project_id=_factory_test_craftr_project_id(workspace, target_repo_path),
        pipeline_run_id=run_id,
        skip_charter=True,
    )


def run_factory_with_bundle(
    *,
    workspace: Path,
    bundle: CharterBundle,
    target_repo_path: Path,
    source_label: Path,
    max_cycles: int = 3,
    builder_model: str | None = None,
    builder_timeout: int = 3600,
    max_budget_usd: float | None = None,
    config: NCDevConfig | None = None,
) -> FactoryRunState:
    """Run the factory loop against a caller-supplied charter bundle.

    The bundle is persisted to a fresh run directory before entering the
    standard cycle loop. ``source_label`` is audit metadata only; it does
    not need to point at a PRD.
    """
    workspace = workspace.resolve()
    target_repo_path = target_repo_path.resolve()
    source_label = source_label.resolve()
    run_id = make_run_id("factory-bundle")
    run_dir = workspace / ".nc-dev" / "runs" / run_id
    outputs_dir = run_dir / "outputs"

    write_charter(bundle, outputs_dir)

    state = FactoryRunState(
        workspace=workspace,
        source_path=source_label,
    )
    return _run_factory_cycle_loop(
        state=state,
        workspace=workspace,
        source_path=source_label,
        target_repo_path=target_repo_path,
        max_cycles=max_cycles,
        builder_model=builder_model,
        builder_timeout=builder_timeout,
        max_budget_usd=max_budget_usd,
        config=config,
        probe_test_craftr=False,
        require_test_craftr=False,
        capture_baseline=False,
        test_craftr_mode="http",
        test_craftr_core_path=None,
        allow_unexecuted_contract=False,
        browser_smoke_contract=False,
        test_craftr_url="http://localhost:16630",
        target_url="http://localhost:23000",
        project_id=_factory_test_craftr_project_id(workspace, target_repo_path),
        pipeline_run_id=run_id,
        skip_charter=True,
    )


def _run_factory_cycle_loop(
    *,
    state: FactoryRunState,
    workspace: Path,
    source_path: Path,
    target_repo_path: Path | None,
    max_cycles: int,
    builder_model: str | None,
    builder_timeout: int,
    max_budget_usd: float | None,
    config: NCDevConfig | None,
    probe_test_craftr: bool,
    require_test_craftr: bool,
    capture_baseline: bool,
    test_craftr_mode: str,
    test_craftr_core_path: str | Path | None,
    allow_unexecuted_contract: bool,
    browser_smoke_contract: bool,
    test_craftr_url: str,
    target_url: str,
    project_id: str,
    pipeline_run_id: str | None = None,
    skip_charter: bool = False,
) -> FactoryRunState:
    for cycle in range(1, max_cycles + 1):
        console.print(Panel(
            f"[bold cyan]Factory cycle {cycle}/{max_cycles}[/bold cyan]",
            border_style="cyan",
        ))
        pre_cycle_sha = _git_head(target_repo_path) if target_repo_path else None

        # Phase A — build (or re-build)
        pipeline_state = run_pipeline(
            workspace=workspace,
            source_path=source_path,
            target_repo_path=target_repo_path,
            builder_model=builder_model,
            builder_timeout=builder_timeout,
            max_budget_usd=max_budget_usd,
            config=config,
            run_id=pipeline_run_id,
            skip_charter=skip_charter,
            # Factory owns halting via Steward — engine should always
            # surface FAILED features instead of returning early.
            halt_on_failed=False,
        )
        state.cycles_run = cycle
        state.last_pipeline_status = pipeline_state.status
        state.run_dirs.append(pipeline_state.run_dir)
        target_path = Path(pipeline_state.target_path)
        post_cycle_sha = _git_head(target_path)
        changed_files = _files_changed_in_cycle(
            target_path,
            pre_cycle_sha,
            post_cycle_sha,
        )
        state.changed_files_per_cycle.append(changed_files)

        # Phase B — judge (Steward)
        run_dir = Path(pipeline_state.run_dir)

        # Pin the run_dir and reuse its charter for every subsequent
        # cycle. Without this, each repair cycle calls run_pipeline with
        # run_id=None + skip_charter=False, which spins up a fresh
        # run_dir and regenerates the charter from scratch. Charter
        # generation is non-deterministic, so feature IDs drift between
        # cycles and the state-scanner can no longer recognise
        # already-built features — turning a "repair one feature" cycle
        # into a near-full rebuild. RERUN_CHARTER still regenerates, but
        # it does so in-place in this pinned run_dir's outputs/.
        if pipeline_run_id is None:
            pipeline_run_id = run_dir.name
            skip_charter = True

        try:
            bundle = load_charter_bundle_from_run(run_dir)
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]Charter unreadable after build: {exc}[/red]")
            state.stop_reason = FactoryStopReason.STEWARD_UNRECOVERABLE
            return state

        if capture_baseline and state.baseline_run_id and not state.baseline_per_feature:
            feature_ids = _feature_ids_from_bundle(bundle)
            if feature_ids:
                state.baseline_per_feature.update(
                    _pin_test_craftr_baseline_per_feature(
                        target_url=target_url,
                        source_path=source_path,
                        project_id=project_id,
                        feature_ids=feature_ids,
                        test_craftr_url=test_craftr_url,
                        baseline_run_id=state.baseline_run_id,
                    )
                )
            elif _pin_existing_test_craftr_project_baseline(
                test_craftr_url=test_craftr_url,
                project_id=project_id,
                run_id=state.baseline_run_id,
            ):
                logger.info("Pinned project-level TestCraftr baseline")

        steward_kwargs: dict[str, Any] = {}
        if (
            probe_test_craftr
            and pipeline_state.status in {"passed", "partial", "integration_failed"}
        ):
            if test_craftr_mode == "local":
                run_id, issues, scores, report_path, infra_failed = (
                    _run_local_test_craftr(
                        contract_path=run_dir / "outputs" / "behavior-contract.v1.json",
                        target_url=target_url,
                        out_dir=run_dir / "test-craftr" / f"cycle-{cycle}",
                        workspace=workspace,
                        target_repo_path=target_path,
                        test_craftr_core_path=test_craftr_core_path,
                        allow_unexecuted=allow_unexecuted_contract,
                        browser_smoke=browser_smoke_contract,
                    )
                )
                if report_path:
                    state.verification_reports.append(report_path)
                if infra_failed and require_test_craftr:
                    console.print(
                        "[red]Local TestCraftr verification hit an infrastructure "
                        "failure; stopping factory before Steward review.[/red]"
                    )
                    state.stop_reason = FactoryStopReason.TEST_CRAFTR_UNAVAILABLE
                    return state
            else:
                run_id, issues, scores = _probe_test_craftr(
                    target_url=target_url,
                    source_path=source_path,
                    cycle=cycle,
                    project_id=project_id,
                    test_craftr_url=test_craftr_url,
                    baseline_run_id=state.baseline_run_id,
                    baseline_per_feature=state.baseline_per_feature or None,
                    changed_files=changed_files,
                )
            debt = classify_issues_to_debt(
                issues,
                known_routes=_known_routes_from_bundle(bundle),
            )
            if run_id:
                state.test_craftr_runs.append(run_id)
            elif require_test_craftr:
                console.print(
                    "[red]TestCraftr probe was required but returned no run_id; "
                    "stopping factory before Steward review.[/red]"
                )
                state.stop_reason = FactoryStopReason.TEST_CRAFTR_UNAVAILABLE
                return state
            state.last_product_debt = debt
            steward_kwargs["product_debt"] = debt
            steward_kwargs["last_test_craftr_scores"] = scores

        decision = run_product_steward(
            prd_path=source_path,
            bundle=bundle,
            completed=list(pipeline_state.completed_steps),
            target_path=target_path,
            run_dir=run_dir / "steward" / f"cycle-{cycle}",
            config=config,
            model=builder_model,
            max_budget_usd=max_budget_usd,
            **steward_kwargs,
        )
        state.decisions.append(decision)

        # Phase B.5 — record this cycle in the cross-project capability ledger.
        try:
            from ncdev.core.capability_ledger import record_cycle
            from ncdev.pipeline.metrics import compute_run_metrics

            record_cycle(
                metrics=compute_run_metrics(pipeline_state),
                steps=list(pipeline_state.completed_steps),
                cycle=cycle,
                steward_disposition=decision.disposition.value,
                capability_lessons=list(decision.capability_lessons),
            )
        except Exception as exc:  # noqa: BLE001
            # The ledger is best-effort telemetry — never fail a build over it.
            console.print(f"[yellow]capability ledger write skipped: {exc}[/yellow]")

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
        if decision.disposition == Disposition.INSERT_FEATURES:
            try:
                inserted = insert_features(run_dir / "outputs", decision.new_features)
            except ValueError as exc:
                console.print(f"[red]Steward feature insertion rejected: {exc}[/red]")
                state.stop_reason = FactoryStopReason.STEWARD_UNRECOVERABLE
                return state
            console.print(
                f"  [green]Inserted {inserted} Steward feature(s); "
                "re-entering pipeline[/green]"
            )
            continue
        if decision.disposition == Disposition.REWRITE_ACCEPTANCE:
            try:
                applied = apply_amendments(run_dir / "outputs", decision.amendments)
            except (KeyError, ValueError) as exc:
                console.print(f"[red]Steward acceptance rewrite rejected: {exc}[/red]")
                state.stop_reason = FactoryStopReason.STEWARD_UNRECOVERABLE
                return state
            console.print(
                f"  [green]Applied {applied} Steward amendment(s); "
                "re-entering pipeline[/green]"
            )
            continue
        if decision.disposition == Disposition.RERUN_CHARTER:
            archive_path = archive_and_clear_charter(run_dir / "outputs")
            console.print(
                f"  [yellow]Archived charter to {archive_path}; regenerating[/yellow]"
            )
            regenerated_bundle, charter_session = generate_charter(
                prd_path=source_path,
                output_dir=run_dir / "outputs",
                target_repo=target_repo_path,
                model=builder_model,
                max_budget_usd=max_budget_usd,
                log_path=run_dir / "logs" / f"charter-rerun-cycle-{cycle}.jsonl",
                config=config,
            )
            if regenerated_bundle is None:
                console.print(
                    "[red]Steward charter rerun failed: "
                    f"{charter_session.summary()}[/red]"
                )
                state.stop_reason = FactoryStopReason.STEWARD_UNRECOVERABLE
                return state
            console.print("  [green]Charter regenerated; re-entering pipeline[/green]")
            continue

    state.stop_reason = FactoryStopReason.BUDGET_EXHAUSTED
    return state
