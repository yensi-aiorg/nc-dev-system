# tests/test_grounded_verify/test_integration_gate.py
"""Tests for the product-level integration gate prompt builder (Task 2) and gate function (Task 3)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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
    monkeypatch.setattr(intmod, "_probe_detail", lambda *a, **k: (True, "HTTP 200"))
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
    monkeypatch.setattr(intmod, "_probe_detail", lambda *a, **k: (True, "HTTP 200"))
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


# ---------------------------------------------------------------------------
# Task 4: Scenario regression — required_files at alternate path
# ---------------------------------------------------------------------------

@pytest.mark.llm
def test_required_file_at_alternate_path_passes(tmp_path: Path):
    """Regression: gate must PASS when required_files path differs from actual path.

    Reproduces the real smoke-build failure where the contract lists
    ``tests/test_echo.py`` but the file lives at ``backend/tests/test_echo.py``.
    The grounded judge sees the evidence and must correctly disregard the
    exact-path mismatch (grounding rule 1: alternate path counts).
    """
    # ------------------------------------------------------------------ #
    # Set up a COMPLETE, real echo service under tmp_path. The product
    # intent IS fully implemented — the ONLY discrepancy is that the test
    # file lives at backend/tests/test_echo.py while the contract's
    # required_files lists the bare tests/test_echo.py. The judge must
    # treat that as "satisfied at a reasonable alternate path", not absent.
    # ------------------------------------------------------------------ #
    (tmp_path / "backend" / "app").mkdir(parents=True)
    (tmp_path / "backend" / "app" / "__init__.py").write_text("")
    (tmp_path / "backend" / "app" / "main.py").write_text(
        "from fastapi import FastAPI\n\n"
        "app = FastAPI()\n\n"
        "@app.get('/health')\n"
        "def health():\n"
        "    return {'status': 'ok'}\n\n"
        "@app.get('/api/v1/echo')\n"
        "def echo(msg: str = ''):\n"
        "    return {'echo': msg}\n"
    )
    # The required test file — present, just at backend/tests/ not tests/
    (tmp_path / "backend" / "tests").mkdir(parents=True)
    (tmp_path / "backend" / "tests" / "test_echo.py").write_text(
        "from app.main import echo, health\n\n"
        "def test_echo_returns_msg():\n"
        "    assert echo('hello') == {'echo': 'hello'}\n\n"
        "def test_echo_defaults_empty():\n"
        "    assert echo() == {'echo': ''}\n\n"
        "def test_health_ok():\n"
        "    assert health() == {'status': 'ok'}\n"
    )

    # ------------------------------------------------------------------ #
    # Build the bundle
    # ------------------------------------------------------------------ #
    from ncdev.pipeline.models import FeatureAcceptance, FeatureStep

    bundle = _make_bundle(
        # Contract lists the *original* path — not where the file actually is
        features=[
            FeatureStep(
                feature_id="f01",
                title="Echo endpoint",
                description="Implement /health and /echo",
                acceptance_criteria=["GET /health returns 200"],
                acceptance=FeatureAcceptance(
                    required_files=["tests/test_echo.py"],  # exact path mismatch
                    required_routes=[],  # no route probing needed
                ),
            )
        ],
        # Trivially-passing test command — real shell, clean evidence
        backend_test_command="python -c \"print('ok')\"",
        # No start_command → hard floor is skipped
        start_command="",
    )
    completed = [_make_completed("f01")]

    # ------------------------------------------------------------------ #
    # Call the REAL gate with a real session_runner (LLM judge)
    # ------------------------------------------------------------------ #
    from ncdev.pipeline.grounded_verify.integration import grounded_integration_gate

    result = grounded_integration_gate(
        bundle,
        tmp_path,
        completed,
        probe_health=False,       # no live server needed
        run_test_commands=True,   # real shell — trivial command passes cleanly
    )

    assert result.passed is True, result.failures


# ---------------------------------------------------------------------------
# Fix #1: changed_files populated from git ls-files
# ---------------------------------------------------------------------------

def test_changed_files_passed_to_judge(tmp_path: Path, monkeypatch):
    """grounded_integration_gate must pass repo file inventory to the judge via EvidenceBundle.changed_files."""
    import ncdev.pipeline.grounded_verify.integration as intmod

    fake_files = ["backend/tests/test_echo.py", "backend/app/main.py"]

    def fake_run_shell(cmd: str, *, cwd, timeout):
        if "ls-files" in cmd:
            return True, "\n".join(fake_files) + "\n"
        return True, "ok"

    monkeypatch.setattr(intmod, "_run_shell", fake_run_shell)
    monkeypatch.setattr(intmod, "_wait_for_health", lambda *a, **k: True)
    monkeypatch.setattr(intmod, "_probe_detail", lambda *a, **k: (True, "HTTP 200"))
    monkeypatch.setattr(intmod, "_resolve_url", lambda route, base: f"http://localhost/{route.lstrip('/')}")
    monkeypatch.setattr(intmod, "_derive_base_url", lambda url: "http://localhost")
    monkeypatch.setattr(intmod, "_tail", lambda s, n=400: s[-n:] if len(s) > n else s)

    from ncdev.pipeline.grounded_verify.models import EvidenceBundle, Verdict

    captured: dict = {}

    def capturing_judge(prompt: str, *, target_path, session_runner):
        # Recover the bundle from what was passed to build_integration_prompt
        # by looking for the changed_files section in the prompt
        captured["prompt"] = prompt
        return Verdict(verdict="PASS", confidence=0.9, reasons=[])

    monkeypatch.setattr(intmod, "_run_judge", capturing_judge)

    # Also intercept build_integration_prompt to capture the bundle directly
    original_build = intmod.build_integration_prompt
    captured_bundle: dict = {}

    def capturing_build(intent, evidence, completed_ids, **kwargs):
        captured_bundle["bundle"] = evidence
        return original_build(intent, evidence, completed_ids, **kwargs)

    monkeypatch.setattr(intmod, "build_integration_prompt", capturing_build)

    from ncdev.pipeline.grounded_verify.integration import grounded_integration_gate

    bundle = _make_bundle()
    completed = [_make_completed()]

    grounded_integration_gate(
        bundle,
        tmp_path,
        completed,
        probe_health=False,
        run_test_commands=False,
        session_runner=lambda *a, **k: None,
    )

    evidence: EvidenceBundle = captured_bundle["bundle"]
    assert "backend/tests/test_echo.py" in evidence.changed_files
    assert "backend/app/main.py" in evidence.changed_files


# ---------------------------------------------------------------------------
# Fix #2: failed route records detail in output_tail
# ---------------------------------------------------------------------------

def test_failed_route_records_detail(tmp_path: Path, monkeypatch):
    """A failed route probe must capture the HTTP status/error detail in EvidenceItem.output_tail."""
    import ncdev.pipeline.grounded_verify.integration as intmod

    def fake_run_shell(cmd: str, *, cwd, timeout):
        if "ls-files" in cmd:
            return True, ""
        return True, "ok"

    monkeypatch.setattr(intmod, "_run_shell", fake_run_shell)
    monkeypatch.setattr(intmod, "_wait_for_health", lambda *a, **k: True)
    monkeypatch.setattr(intmod, "_probe_detail", lambda *a, **k: (False, "HTTP 500"))
    monkeypatch.setattr(intmod, "_resolve_url", lambda route, base: f"http://localhost/{route.lstrip('/')}")
    monkeypatch.setattr(intmod, "_derive_base_url", lambda url: "http://localhost")
    monkeypatch.setattr(intmod, "_tail", lambda s, n=400: s[-n:] if len(s) > n else s)

    from ncdev.pipeline.grounded_verify.models import Verdict

    captured_items: dict = {}

    original_build = intmod.build_integration_prompt

    def capturing_build(intent, evidence, completed_ids, **kwargs):
        captured_items["items"] = evidence.items
        return original_build(intent, evidence, completed_ids, **kwargs)

    monkeypatch.setattr(intmod, "build_integration_prompt", capturing_build)
    monkeypatch.setattr(
        intmod, "_run_judge",
        lambda *a, **k: Verdict(verdict="FAIL", confidence=0.9, reasons=["route failed"]),
    )

    from ncdev.pipeline.grounded_verify.integration import grounded_integration_gate

    bundle = _make_bundle(
        features=[
            __import__(
                "ncdev.pipeline.models",
                fromlist=["FeatureStep"],
            ).FeatureStep(
                feature_id="f01",
                title="Echo endpoint",
                description="Impl",
                acceptance_criteria=["GET /health returns 200"],
                acceptance=__import__(
                    "ncdev.pipeline.models",
                    fromlist=["FeatureAcceptance"],
                ).FeatureAcceptance(required_routes=["/health"]),
            )
        ],
        backend_health_url="http://localhost:8000/health",
    )
    completed = [_make_completed()]

    grounded_integration_gate(
        bundle,
        tmp_path,
        completed,
        probe_health=True,
        run_test_commands=False,
        session_runner=lambda *a, **k: None,
    )

    route_items = [it for it in captured_items["items"] if it.scope == "route"]
    assert route_items, "Expected at least one route EvidenceItem"
    failed = [it for it in route_items if it.exit_code == 1]
    assert failed, "Expected at least one failed route item"
    assert failed[0].output_tail == "HTTP 500"
