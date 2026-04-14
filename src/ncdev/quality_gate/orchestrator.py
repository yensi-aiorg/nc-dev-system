"""Quality Gate Orchestrator — the main build-test-fix loop."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine

import httpx

from ncdev.quality_gate.config import QualityGateConfig
from ncdev.quality_gate.manifest import ManifestGenerator
from ncdev.quality_gate.models import (
    CycleResult,
    FixManifest,
    PipelineState,
    QualityScores,
)

logger = logging.getLogger(__name__)


class QualityGateOrchestrator:
    """Trigger Test Craftr -> wait -> generate manifest -> trigger fix -> repeat."""

    def __init__(self, config: QualityGateConfig) -> None:
        self.config = config
        self.manifest_generator = ManifestGenerator()

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------

    def init_state(self, project_name: str, target_url: str) -> PipelineState:
        """Create an initial pipeline state with phase='pending'."""
        return PipelineState(
            project_name=project_name,
            target_url=target_url,
            current_cycle=0,
            max_cycles=self.config.max_cycles,
            phase="pending",
        )

    def should_continue(self, state: PipelineState, scores: QualityScores) -> bool:
        """Decide whether to run another cycle.

        Returns False when:
        - All three thresholds are met (pipeline passed).
        - current_cycle >= max_cycles (budget exhausted).
        - Regression detected (any score decreased from previous cycle).
        """
        # All thresholds met?
        if (
            scores.core_flow >= self.config.core_flow_threshold
            and scores.resilience >= self.config.resilience_threshold
            and scores.polish >= self.config.polish_threshold
        ):
            return False

        # Max cycles reached?
        if state.current_cycle >= state.max_cycles:
            return False

        # Regression check — compare with previous cycle.
        if state.cycles:
            prev = state.cycles[-1].scores
            if (
                scores.core_flow < prev.core_flow
                or scores.resilience < prev.resilience
                or scores.polish < prev.polish
            ):
                return False

        return True

    # ------------------------------------------------------------------
    # Test Craftr HTTP helpers
    # ------------------------------------------------------------------

    async def trigger_test_run(
        self, target_url: str, prd_content: str, cycle: int, project_id: str = ""
    ) -> str:
        """POST to Test Craftr /api/pipeline/runs, returns run_id."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.config.test_craftr_url}/api/pipeline/runs",
                json={
                    "target_url": target_url,
                    "prd_content": prd_content,
                    "cycle": cycle,
                    "project_id": project_id,
                },
                timeout=30.0,
            )
            resp.raise_for_status()
            return resp.json()["run_id"]

    async def wait_for_results(
        self, run_id: str, poll_interval: float = 15
    ) -> dict[str, Any]:
        """GET /api/runs/{id}, poll until status is completed/failed/stopped."""
        terminal = {"completed", "failed", "stopped"}
        async with httpx.AsyncClient() as client:
            while True:
                resp = await client.get(
                    f"{self.config.test_craftr_url}/api/runs/{run_id}",
                    timeout=30.0,
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("status") in terminal:
                    return data
                await asyncio.sleep(poll_interval)

    async def fetch_issues(self, run_id: str) -> list[dict[str, Any]]:
        """GET /api/runs/{id}/issues."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.config.test_craftr_url}/api/runs/{run_id}/issues",
                timeout=30.0,
            )
            resp.raise_for_status()
            return resp.json().get("issues", [])

    # ------------------------------------------------------------------
    # Manifest delegation
    # ------------------------------------------------------------------

    def generate_manifest(
        self,
        run_id: str,
        target_path: str,
        issues: list[dict[str, Any]],
        scores: dict[str, Any],
    ) -> FixManifest:
        """Delegate to ManifestGenerator."""
        return self.manifest_generator.generate(
            run_id=run_id,
            target_path=target_path,
            tc_issues=issues,
            scores=scores,
        )

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run(
        self,
        project_name: str,
        target_url: str,
        target_path: str,
        prd_content: str,
        fix_callback: Callable[[FixManifest], Coroutine[Any, Any, int]] | None = None,
    ) -> PipelineState:
        """Execute the full quality-gate loop.

        Parameters
        ----------
        fix_callback:
            An async callable that receives a FixManifest and returns the
            number of issues fixed.  If *None*, the loop still records cycles
            but never attempts fixes.
        """
        state = self.init_state(project_name, target_url)
        state.phase = "testing"

        project_id = project_name.lower().replace(" ", "-")

        while True:
            state.current_cycle += 1
            logger.info("Quality gate cycle %d started", state.current_cycle)

            # 1. Trigger test run
            run_id = await self.trigger_test_run(target_url, prd_content, state.current_cycle, project_id=project_id)

            # 2. Wait for results
            result_data = await self.wait_for_results(run_id)

            # Check for infrastructure failures
            if result_data.get("status") in ("failed", "stopped"):
                state.phase = "failed"
                logger.error(
                    "Test Craftr run %s %s: %s",
                    run_id,
                    result_data["status"],
                    result_data.get("status_message", "unknown error"),
                )
                break

            # 3. Fetch issues
            issues = await self.fetch_issues(run_id)

            # 4. Compute scores
            scores_dict = result_data.get("scores", {"core_flow": 0, "resilience": 0, "polish": 0})
            scores = QualityScores(**scores_dict)

            # 5. Detect regression
            regression = False
            if state.cycles:
                prev = state.cycles[-1].scores
                if (
                    scores.core_flow < prev.core_flow
                    or scores.resilience < prev.resilience
                    or scores.polish < prev.polish
                ):
                    regression = True

            # 6. Record cycle result
            cycle_passed = (
                scores.core_flow >= self.config.core_flow_threshold
                and scores.resilience >= self.config.resilience_threshold
                and scores.polish >= self.config.polish_threshold
            )

            cycle_result = CycleResult(
                cycle=state.current_cycle,
                scores=scores,
                issues_found=len(issues),
                issues_fixed=0,
                passed=cycle_passed,
                regression=regression,
            )

            # 7. If thresholds met or regression detected, stop without fixing.
            if cycle_passed or regression:
                state.cycles.append(cycle_result)
                state.final_scores = scores
                state.phase = "passed" if cycle_passed else "failed"
                break

            # 8. Generate manifest and run fix callback.
            if issues and fix_callback is not None:
                manifest = self.generate_manifest(run_id, target_path, issues, scores_dict)
                state.phase = "fixing"
                issues_fixed = await fix_callback(manifest)
                cycle_result.issues_fixed = issues_fixed

            state.cycles.append(cycle_result)

            # 9. Check cycle budget AFTER fixes so every cycle gets its fixes.
            if not self.should_continue(state, scores):
                state.final_scores = scores
                state.phase = "failed"
                break

            state.phase = "testing"

        return state
