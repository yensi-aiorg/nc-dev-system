# tests/test_grounded_verify/test_integration_gate.py
"""Tests for the product-level integration gate prompt builder (Task 2) and gate function (Task 3)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from ncdev.pipeline.grounded_verify.models import EvidenceBundle, EvidenceItem
from ncdev.pipeline.models import (
    CharterBundle,
    FeatureAcceptance,
    FeatureQueueDoc,
    FeatureStep,
    StepResult,
    StepStatus,
    TargetProjectContract,
    VerificationContract,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@dataclass
class FakeSession:
    final_text: str
    total_cost_usd: float = 0.01
    success: bool = True


def _make_bundle(
    *,
    start_command: str = "",
    stop_command: str = "",
    backend_health_url: str = "",
    frontend_url: str = "",
    boot_timeout_seconds: int = 5,
    backend_test_command: str = "",
    frontend_test_command: str = "",
    e2e_test_command: str = "",
    lint_command: str = "",
    build_command: str = "",
    features: list | None = None,
    project_name: str = "TestProject",
) -> CharterBundle:
    """Build a minimal but fully-typed CharterBundle for unit tests."""
    contract = TargetProjectContract(project_name=project_name)
    verification = VerificationContract(
        start_command=start_command,
        stop_command=stop_command,
        backend_health_url=backend_health_url,
        frontend_url=frontend_url,
        boot_timeout_seconds=boot_timeout_seconds,
        backend_test_command=backend_test_command,
        frontend_test_command=frontend_test_command,
        e2e_test_command=e2e_test_command,
        lint_command=lint_command,
        build_command=build_command,
    )
    feature_queue = FeatureQueueDoc(
        project_name=project_name,
        features=features or [
            FeatureStep(
                feature_id="f01",
                title="Echo endpoint",
                description="Implement /health and /echo",
                acceptance_criteria=["GET /health returns 200"],
                acceptance=FeatureAcceptance(required_routes=["/health"]),
            )
        ],
    )
    return CharterBundle(contract=contract, verification=verification, feature_queue=feature_queue)


def _make_completed(feature_id: str = "f01", status: StepStatus = StepStatus.PASSED) -> StepResult:
    return StepResult(feature_id=feature_id, status=status)


# ---------------------------------------------------------------------------
# Task 2: prompt builder
# ---------------------------------------------------------------------------

def test_integration_prompt_has_intent_evidence_and_rules():
    from ncdev.pipeline.grounded_verify.integration import build_integration_prompt

    ev = EvidenceBundle(
        items=[
            EvidenceItem(name="route:/health", exit_code=0, scope="route"),
            EvidenceItem(name="build", command="docker compose build", exit_code=0, scope="build"),
        ],
        changed_files=[],
    )
    p = build_integration_prompt("Echo service: /health + /api/v1/echo", ev, ["f01", "f02"])
    assert "intent" in p.lower() and ("not exact" in p.lower() or "alternate path" in p.lower())
    assert "route:/health" in p and "```json" in p


# ---------------------------------------------------------------------------
# Task 3: grounded_integration_gate
# ---------------------------------------------------------------------------

def test_hard_floor_app_wont_start_fails_without_judge(tmp_path: Path, monkeypatch):
    """Hard floor: if app start_command fails, return immediately — judge NOT called."""
    import ncdev.pipeline.grounded_verify.integration as intmod

    # Patch _run_shell to simulate start failure
    monkeypatch.setattr(intmod, "_run_shell", lambda *a, **k: (False, "boom: connection refused"))
    # Patch _wait_for_health — should NOT be called when hard floor fires
    def _bad_health(*a, **k):
        raise AssertionError("_wait_for_health should not be called")
    monkeypatch.setattr(intmod, "_wait_for_health", _bad_health)

    judge_called = {"n": 0}

    def stub_judge(*a, **k):
        judge_called["n"] += 1
        raise AssertionError("_run_judge must not be called when hard floor fires")

    monkeypatch.setattr(intmod, "_run_judge", stub_judge)

    from ncdev.pipeline.grounded_verify.integration import grounded_integration_gate

    bundle = _make_bundle(start_command="docker compose up -d")
    completed = [_make_completed()]

    result = grounded_integration_gate(
        bundle,
        tmp_path,
        completed,
        probe_health=False,
        run_test_commands=True,
        session_runner=lambda *a, **k: None,
    )

    assert result.passed is False
    assert any("did not start" in f for f in result.failures), f"failures: {result.failures}"
    assert result.app_started is False
    assert judge_called["n"] == 0


def test_pass_verdict_maps_to_result(tmp_path: Path, monkeypatch):
    """A PASS judge verdict → result.passed=True, result.failures=[]."""
    import ncdev.pipeline.grounded_verify.integration as intmod

    # All shell commands succeed
    monkeypatch.setattr(intmod, "_run_shell", lambda *a, **k: (True, "ok"))
    monkeypatch.setattr(intmod, "_wait_for_health", lambda *a, **k: True)
    monkeypatch.setattr(intmod, "_probe", lambda *a, **k: True)
    monkeypatch.setattr(intmod, "_resolve_url", lambda route, base: f"http://localhost/{route.lstrip('/')}")
    monkeypatch.setattr(intmod, "_derive_base_url", lambda url: "http://localhost")
    monkeypatch.setattr(intmod, "_tail", lambda s, n=400: s[-n:] if len(s) > n else s)

    from ncdev.pipeline.grounded_verify.models import Verdict

    monkeypatch.setattr(
        intmod, "_run_judge",
        lambda *a, **k: Verdict(verdict="PASS", confidence=0.95, reasons=[]),
    )

    from ncdev.pipeline.grounded_verify.integration import grounded_integration_gate

    bundle = _make_bundle(backend_test_command="python -m pytest")
    completed = [_make_completed()]

    result = grounded_integration_gate(
        bundle,
        tmp_path,
        completed,
        probe_health=True,
        run_test_commands=True,
        session_runner=lambda *a, **k: None,
    )

    assert result.passed is True
    assert result.failures == []


def test_fail_verdict_surfaces_reasons(tmp_path: Path, monkeypatch):
    """A FAIL judge verdict → result.passed=False, result.failures contains the reasons."""
    import ncdev.pipeline.grounded_verify.integration as intmod

    monkeypatch.setattr(intmod, "_run_shell", lambda *a, **k: (True, "ok"))
    monkeypatch.setattr(intmod, "_wait_for_health", lambda *a, **k: True)
    monkeypatch.setattr(intmod, "_probe", lambda *a, **k: True)
    monkeypatch.setattr(intmod, "_resolve_url", lambda route, base: f"http://localhost/{route.lstrip('/')}")
    monkeypatch.setattr(intmod, "_derive_base_url", lambda url: "http://localhost")
    monkeypatch.setattr(intmod, "_tail", lambda s, n=400: s[-n:] if len(s) > n else s)

    from ncdev.pipeline.grounded_verify.models import Verdict

    monkeypatch.setattr(
        intmod, "_run_judge",
        lambda *a, **k: Verdict(
            verdict="FAIL",
            confidence=0.8,
            reasons=["missing /api/v1/echo route", "echo handler returns 500"],
        ),
    )

    from ncdev.pipeline.grounded_verify.integration import grounded_integration_gate

    bundle = _make_bundle()
    completed = [_make_completed()]

    result = grounded_integration_gate(
        bundle,
        tmp_path,
        completed,
        probe_health=False,
        run_test_commands=False,
        session_runner=lambda *a, **k: None,
    )

    assert result.passed is False
    assert "missing /api/v1/echo route" in result.failures
    assert "echo handler returns 500" in result.failures
