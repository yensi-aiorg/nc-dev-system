"""
Integration test for the quality gate pipeline.
Tests orchestrator logic, manifest generation, and scoring without requiring
Test Craftr to be running.

Run: pytest tests/integration/test_quality_gate_e2e.py -v
"""

import pytest

from ncdev.quality_gate.config import QualityGateConfig
from ncdev.quality_gate.manifest import ManifestGenerator
from ncdev.quality_gate.models import CycleResult, PipelineState, QualityScores
from ncdev.quality_gate.orchestrator import QualityGateOrchestrator


@pytest.fixture
def config():
    return QualityGateConfig(
        enabled=True, test_craftr_url="http://localhost:16630", max_cycles=3
    )


@pytest.fixture
def orchestrator(config):
    return QualityGateOrchestrator(config)


@pytest.fixture
def manifest_gen():
    return ManifestGenerator()


class TestOrchestrationLogic:
    def test_init_state_creates_pending_state(self, orchestrator):
        state = orchestrator.init_state("Test Project", "http://localhost:3000")
        assert state.project_name == "Test Project"
        assert state.target_url == "http://localhost:3000"
        assert state.phase == "pending"
        assert state.current_cycle == 0
        assert state.max_cycles == 3
        assert state.cycles == []

    def test_should_continue_below_threshold(self, orchestrator):
        state = PipelineState(
            project_name="Test", target_url="http://localhost:3000"
        )
        scores = QualityScores(core_flow=80, resilience=50, polish=60)
        assert orchestrator.should_continue(state, scores) is True

    def test_should_stop_when_all_thresholds_met(self, orchestrator):
        state = PipelineState(
            project_name="Test", target_url="http://localhost:3000"
        )
        scores = QualityScores(core_flow=100, resilience=75, polish=85)
        assert orchestrator.should_continue(state, scores) is False

    def test_should_stop_at_max_cycles(self, orchestrator):
        state = PipelineState(
            project_name="Test",
            target_url="http://localhost:3000",
            current_cycle=3,
        )
        scores = QualityScores(core_flow=80, resilience=50, polish=60)
        assert orchestrator.should_continue(state, scores) is False

    def test_should_stop_on_regression(self, orchestrator):
        state = PipelineState(
            project_name="Test",
            target_url="http://localhost:3000",
            current_cycle=2,
            cycles=[
                CycleResult(
                    cycle=1,
                    scores=QualityScores(
                        core_flow=80, resilience=50, polish=60
                    ),
                    issues_found=15,
                    issues_fixed=10,
                    passed=False,
                )
            ],
        )
        regressed_scores = QualityScores(core_flow=75, resilience=45, polish=55)
        assert orchestrator.should_continue(state, regressed_scores) is False


class TestManifestGeneration:
    def test_converts_tc_issues_to_fix_manifest(self, manifest_gen):
        tc_issues = [
            {
                "id": "tc-1",
                "title": "Button broken",
                "severity": "critical",
                "type": "functionality",
                "status": "open",
                "context": {
                    "url": "/dashboard",
                    "action_attempted": "Click submit",
                    "expected": "Form submits",
                    "actual": "Nothing happens",
                },
            },
            {
                "id": "tc-2",
                "title": "Missing empty state",
                "severity": "medium",
                "type": "ux",
                "status": "open",
                "context": {
                    "url": "/projects",
                    "action_attempted": "View empty list",
                    "expected": "Empty state message",
                    "actual": "Blank area",
                },
            },
        ]
        manifest = manifest_gen.generate(
            "run_123",
            "/tmp/app",
            tc_issues,
            {"core_flow": 50, "resilience": 30, "polish": 60},
        )
        assert len(manifest.issues) == 2
        assert manifest.issues[0].priority == "P0"  # critical first
        assert manifest.issues[1].priority == "P2"  # medium second
        assert manifest.scores.core_flow == 50

    def test_severity_mapping_complete(self, manifest_gen):
        for sev, expected in [
            ("critical", "P0"),
            ("high", "P1"),
            ("medium", "P2"),
            ("low", "P3"),
        ]:
            assert manifest_gen._severity_to_priority(sev) == expected

    def test_groups_related_by_url(self, manifest_gen):
        issues = [
            {"id": "1", "context": {"url": "/a"}},
            {"id": "2", "context": {"url": "/a"}},
            {"id": "3", "context": {"url": "/b"}},
        ]
        groups = manifest_gen._group_related(issues)
        assert len(groups) == 2


class TestFullPipelineScenarios:
    def test_passing_scenario(self, orchestrator):
        """Simulate: scores meet threshold on first check."""
        state = orchestrator.init_state("Good App", "http://localhost:3000")
        scores = QualityScores(core_flow=100, resilience=85, polish=90)
        assert orchestrator.should_continue(state, scores) is False
        # Would be "passed" in real run

    def test_improvement_scenario(self, orchestrator):
        """Simulate: scores improve across cycles."""
        state = PipelineState(
            project_name="Improving",
            target_url="http://localhost:3000",
            current_cycle=1,
            cycles=[
                CycleResult(
                    cycle=1,
                    scores=QualityScores(
                        core_flow=60, resilience=30, polish=50
                    ),
                    issues_found=20,
                    issues_fixed=15,
                    passed=False,
                )
            ],
        )
        improved = QualityScores(core_flow=85, resilience=55, polish=70)
        assert (
            orchestrator.should_continue(state, improved) is True
        )  # Still below thresholds, keep going

    def test_regression_halts(self, orchestrator):
        """Simulate: cycle 2 scores worse than cycle 1."""
        state = PipelineState(
            project_name="Regressing",
            target_url="http://localhost:3000",
            current_cycle=2,
            cycles=[
                CycleResult(
                    cycle=1,
                    scores=QualityScores(
                        core_flow=80, resilience=50, polish=60
                    ),
                    issues_found=15,
                    issues_fixed=10,
                    passed=False,
                )
            ],
        )
        worse = QualityScores(core_flow=70, resilience=40, polish=55)
        assert orchestrator.should_continue(state, worse) is False
