"""Tests for quality gate data models."""

import pytest

from ncdev.quality_gate.models import (
    CycleResult,
    FixIssue,
    FixManifest,
    IssueEvidence,
    PipelineState,
    QualityScores,
)
from ncdev.quality_gate.config import QualityGateConfig


class TestQualityScores:
    def test_defaults(self):
        scores = QualityScores()
        assert scores.core_flow == 0
        assert scores.resilience == 0
        assert scores.polish == 0

    def test_custom_values(self):
        scores = QualityScores(core_flow=95, resilience=80, polish=70)
        assert scores.core_flow == 95
        assert scores.resilience == 80
        assert scores.polish == 70


class TestFixIssue:
    def test_all_fields(self):
        issue = FixIssue(
            id="ISS-001",
            priority="high",
            persona="admin",
            category="auth",
            title="Login fails on expired token",
            flow="login",
            expected="Redirect to login page",
            actual="500 error page",
            root_cause_hint="Token refresh not implemented",
            reproduction=["Open app", "Wait for token expiry", "Click any link"],
            evidence=IssueEvidence(
                screenshot="/tmp/screenshot.png",
                console_errors=["TypeError: Cannot read property 'token'"],
                network_log="/tmp/network.har",
                video_clip="/tmp/clip.mp4",
            ),
            affected_files_hint=["src/auth/token.py", "src/auth/middleware.py"],
        )
        assert issue.id == "ISS-001"
        assert issue.priority == "high"
        assert issue.persona == "admin"
        assert issue.category == "auth"
        assert issue.title == "Login fails on expired token"
        assert issue.flow == "login"
        assert issue.expected == "Redirect to login page"
        assert issue.actual == "500 error page"
        assert issue.root_cause_hint == "Token refresh not implemented"
        assert len(issue.reproduction) == 3
        assert issue.evidence.screenshot == "/tmp/screenshot.png"
        assert len(issue.evidence.console_errors) == 1
        assert len(issue.affected_files_hint) == 2

    def test_default_evidence(self):
        issue = FixIssue(
            id="ISS-002",
            priority="low",
            persona="user",
            category="ui",
            title="Button misaligned",
            flow="dashboard",
            expected="Button centered",
            actual="Button off-center",
            root_cause_hint="CSS margin issue",
            reproduction=["Open dashboard"],
        )
        assert issue.evidence == IssueEvidence()
        assert issue.affected_files_hint == []


class TestFixManifest:
    def test_with_issues(self):
        issue = FixIssue(
            id="ISS-001",
            priority="critical",
            persona="user",
            category="data",
            title="Data loss on save",
            flow="editor",
            expected="Data persisted",
            actual="Data lost",
            root_cause_hint="Transaction not committed",
            reproduction=["Edit document", "Click save"],
        )
        manifest = FixManifest(
            run_id="run-abc-123",
            target_path="/app",
            scores=QualityScores(core_flow=60, resilience=40, polish=50),
            issues=[issue],
        )
        assert manifest.run_id == "run-abc-123"
        assert manifest.target_path == "/app"
        assert manifest.scores.core_flow == 60
        assert len(manifest.issues) == 1
        assert manifest.issues[0].id == "ISS-001"

    def test_empty_issues(self):
        manifest = FixManifest(
            run_id="run-empty",
            target_path="/app",
            scores=QualityScores(core_flow=100, resilience=90, polish=95),
            issues=[],
        )
        assert len(manifest.issues) == 0


class TestPipelineState:
    def test_defaults(self):
        state = PipelineState(project_name="my-app", target_url="http://localhost:3000")
        assert state.project_name == "my-app"
        assert state.target_url == "http://localhost:3000"
        assert state.current_cycle == 0
        assert state.max_cycles == 3
        assert state.phase == "pending"
        assert state.cycles == []
        assert state.final_scores is None

    def test_with_cycles(self):
        cycle = CycleResult(
            cycle=1,
            scores=QualityScores(core_flow=80, resilience=60, polish=70),
            issues_found=5,
            issues_fixed=3,
            passed=False,
        )
        state = PipelineState(
            project_name="my-app",
            target_url="http://localhost:3000",
            current_cycle=1,
            phase="testing",
            cycles=[cycle],
        )
        assert state.current_cycle == 1
        assert state.phase == "testing"
        assert len(state.cycles) == 1
        assert state.cycles[0].issues_found == 5


class TestCycleResult:
    def test_fields(self):
        result = CycleResult(
            cycle=2,
            scores=QualityScores(core_flow=100, resilience=85, polish=90),
            issues_found=2,
            issues_fixed=2,
            passed=True,
        )
        assert result.cycle == 2
        assert result.scores.core_flow == 100
        assert result.issues_found == 2
        assert result.issues_fixed == 2
        assert result.passed is True
        assert result.regression is False

    def test_regression_flag(self):
        result = CycleResult(
            cycle=3,
            scores=QualityScores(core_flow=70, resilience=50, polish=60),
            issues_found=8,
            issues_fixed=1,
            passed=False,
            regression=True,
        )
        assert result.regression is True


class TestQualityGateConfig:
    def test_defaults(self):
        config = QualityGateConfig()
        assert config.enabled is False
        assert config.test_craftr_url == "http://localhost:16630"
        assert config.redis_url == "redis://localhost:16633"
        assert config.max_cycles == 3
        assert config.core_flow_threshold == 100
        assert config.resilience_threshold == 70
        assert config.polish_threshold == 80
