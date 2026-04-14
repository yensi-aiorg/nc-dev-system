"""Unit tests for QualityGateOrchestrator — all HTTP calls mocked."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ncdev.quality_gate.config import QualityGateConfig
from ncdev.quality_gate.models import PipelineState, QualityScores
from ncdev.quality_gate.orchestrator import QualityGateOrchestrator


@pytest.fixture
def config() -> QualityGateConfig:
    return QualityGateConfig(
        enabled=True,
        test_craftr_url="http://localhost:16630",
        max_cycles=3,
        core_flow_threshold=100,
        resilience_threshold=70,
        polish_threshold=80,
    )


@pytest.fixture
def orch(config: QualityGateConfig) -> QualityGateOrchestrator:
    return QualityGateOrchestrator(config)


# ------------------------------------------------------------------
# init_state
# ------------------------------------------------------------------


class TestInitState:
    def test_creates_correct_pipeline_state(self, orch: QualityGateOrchestrator):
        state = orch.init_state("my-project", "http://localhost:3000")
        assert isinstance(state, PipelineState)
        assert state.project_name == "my-project"
        assert state.target_url == "http://localhost:3000"
        assert state.current_cycle == 0
        assert state.max_cycles == 3
        assert state.phase == "pending"
        assert state.cycles == []
        assert state.final_scores is None


# ------------------------------------------------------------------
# should_continue
# ------------------------------------------------------------------


class TestShouldContinue:
    def test_true_when_below_threshold(self, orch: QualityGateOrchestrator):
        state = orch.init_state("proj", "http://localhost:3000")
        state.current_cycle = 1
        scores = QualityScores(core_flow=80, resilience=60, polish=50)
        assert orch.should_continue(state, scores) is True

    def test_false_when_all_pass(self, orch: QualityGateOrchestrator):
        state = orch.init_state("proj", "http://localhost:3000")
        state.current_cycle = 1
        scores = QualityScores(core_flow=100, resilience=70, polish=80)
        assert orch.should_continue(state, scores) is False

    def test_false_when_max_cycles_reached(self, orch: QualityGateOrchestrator):
        state = orch.init_state("proj", "http://localhost:3000")
        state.current_cycle = 3  # equals max_cycles — budget exhausted
        scores = QualityScores(core_flow=80, resilience=60, polish=50)
        assert orch.should_continue(state, scores) is False

    def test_true_when_cycles_remaining(self, orch: QualityGateOrchestrator):
        state = orch.init_state("proj", "http://localhost:3000")
        state.current_cycle = 2  # still have cycle 3 left
        scores = QualityScores(core_flow=80, resilience=60, polish=50)
        assert orch.should_continue(state, scores) is True

    def test_false_on_regression(self, orch: QualityGateOrchestrator):
        from ncdev.quality_gate.models import CycleResult

        state = orch.init_state("proj", "http://localhost:3000")
        state.current_cycle = 2
        # Previous cycle had higher scores.
        state.cycles.append(
            CycleResult(
                cycle=1,
                scores=QualityScores(core_flow=90, resilience=60, polish=70),
                issues_found=5,
                issues_fixed=3,
                passed=False,
            )
        )
        # Current scores show regression in core_flow.
        scores = QualityScores(core_flow=85, resilience=65, polish=75)
        assert orch.should_continue(state, scores) is False


# ------------------------------------------------------------------
# trigger_test_run (mock HTTP)
# ------------------------------------------------------------------


class TestTriggerTestRun:
    async def test_returns_run_id(self, orch: QualityGateOrchestrator):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"run_id": "abc-123"}
        mock_response.raise_for_status = MagicMock()

        with patch("ncdev.quality_gate.orchestrator.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.post.return_value = mock_response
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            run_id = await orch.trigger_test_run("http://localhost:3000", "prd text", 1)
            assert run_id == "abc-123"


# ------------------------------------------------------------------
# wait_for_results (mock HTTP)
# ------------------------------------------------------------------


class TestWaitForResults:
    async def test_polls_until_completed(self, orch: QualityGateOrchestrator):
        pending = MagicMock()
        pending.json.return_value = {"status": "running"}
        pending.raise_for_status = MagicMock()

        completed = MagicMock()
        completed.json.return_value = {
            "status": "completed",
            "scores": {"core_flow": 95, "resilience": 80, "polish": 75},
        }
        completed.raise_for_status = MagicMock()

        with patch("ncdev.quality_gate.orchestrator.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get = AsyncMock(side_effect=[pending, completed])
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            with patch("ncdev.quality_gate.orchestrator.asyncio.sleep", new_callable=AsyncMock):
                data = await orch.wait_for_results("abc-123", poll_interval=0)
                assert data["status"] == "completed"


# ------------------------------------------------------------------
# run — full loop (mock HTTP)
# ------------------------------------------------------------------


class TestRunLoop:
    async def test_passes_on_first_cycle(self, orch: QualityGateOrchestrator):
        """All thresholds met on the first cycle -> state.phase = 'passed'."""
        orch.trigger_test_run = AsyncMock(return_value="run-1")
        orch.wait_for_results = AsyncMock(return_value={
            "status": "completed",
            "scores": {"core_flow": 100, "resilience": 70, "polish": 80},
        })
        orch.fetch_issues = AsyncMock(return_value=[])

        state = await orch.run("proj", "http://localhost:3000", "/tmp/proj", "prd")
        assert state.phase == "passed"
        assert state.current_cycle == 1
        assert len(state.cycles) == 1
        assert state.final_scores is not None
        assert state.final_scores.core_flow == 100

    async def test_fails_after_max_cycles(self, orch: QualityGateOrchestrator):
        """Never meets thresholds -> exhausts max_cycles -> state.phase = 'failed'."""
        orch.trigger_test_run = AsyncMock(return_value="run-x")
        orch.wait_for_results = AsyncMock(return_value={
            "status": "completed",
            "scores": {"core_flow": 50, "resilience": 40, "polish": 30},
        })
        orch.fetch_issues = AsyncMock(return_value=[
            {"id": "i1", "severity": "high", "type": "functionality", "title": "broken",
             "context": {"url": "/", "action_attempted": "click", "expected": "ok", "actual": "err"}},
        ])

        fix_cb = AsyncMock(return_value=1)
        state = await orch.run("proj", "http://localhost:3000", "/tmp/proj", "prd", fix_callback=fix_cb)
        assert state.phase == "failed"
        assert state.current_cycle == 3
        assert len(state.cycles) == 3

    async def test_stops_on_regression(self, orch: QualityGateOrchestrator):
        """Scores decrease on cycle 2 -> regression detected -> state.phase = 'failed'."""
        call_count = 0

        async def _mock_wait(run_id: str) -> dict:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"status": "completed", "scores": {"core_flow": 80, "resilience": 60, "polish": 70}}
            return {"status": "completed", "scores": {"core_flow": 75, "resilience": 55, "polish": 65}}

        orch.trigger_test_run = AsyncMock(return_value="run-r")
        orch.wait_for_results = AsyncMock(side_effect=_mock_wait)
        orch.fetch_issues = AsyncMock(return_value=[
            {"id": "i1", "severity": "low", "type": "visual", "title": "misalign",
             "context": {"url": "/", "action_attempted": "view", "expected": "aligned", "actual": "off"}},
        ])
        fix_cb = AsyncMock(return_value=1)

        state = await orch.run("proj", "http://localhost:3000", "/tmp/proj", "prd", fix_callback=fix_cb)
        assert state.phase == "failed"
        assert state.current_cycle == 2
        assert state.cycles[-1].regression is True
