"""End-to-end composition tests for the production-readiness gates.

These tests don't validate any single component — they validate that
the five changes (per-feature acceptance, strict state scanner,
mandatory charter validator, halt-on-failed, integration gate)
COMPOSE to actually catch the gross-skip failure mode the user
reported.

Each scenario constructs a realistic charter + simulated builder
behavior and asserts the run lands on the right status.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

from ncdev.pipeline.charter import (
    validate_charter_completeness,
    write_charter,
    load_charter,
)
from ncdev.pipeline.engine import run_pipeline
from ncdev.pipeline.models import (
    AssetManifest,
    CharterBundle,
    FeatureAcceptance,
    FeatureQueueDoc,
    FeatureStep,
    StepResult,
    StepStatus,
    TargetProjectContract,
    VerificationContract,
)
from ncdev.pipeline.asset_manifest import save_feature_manifest
import pytest


# ---------------------------------------------------------------------------
# Helpers — realistic two-feature web project bundle
# ---------------------------------------------------------------------------


def _make_realistic_bundle() -> CharterBundle:
    return CharterBundle(
        contract=TargetProjectContract(
            project_name="myapp", project_type="web",
            backend_framework="fastapi", frontend_framework="react",
            ports={"backend": 23001, "frontend": 23000},
            design_archetype="Technical Elegance",
        ),
        verification=VerificationContract(
            backend_health_url="http://localhost:23001/api/health",
            backend_test_command="exit 0",
            frontend_test_command="",
            required_files=["README.md"],
        ),
        feature_queue=FeatureQueueDoc(
            project_name="myapp",
            features=[
                FeatureStep(
                    feature_id="f01-scaffold",
                    title="Scaffold",
                    description="Skeleton + health",
                    acceptance_criteria=["health works"],
                    acceptance=FeatureAcceptance(
                        required_files=["README.md"],
                        required_routes=["/api/health"],
                    ),
                ),
                FeatureStep(
                    feature_id="f02-auth",
                    title="Auth",
                    description="Login",
                    acceptance_criteria=["login works"],
                    depends_on_features=["f01-scaffold"],
                    acceptance=FeatureAcceptance(
                        required_files=["src/auth.py"],
                        required_routes=["/api/auth/login"],
                    ),
                ),
            ],
        ),
    )


def _setup_workspace(tmp_path: Path) -> tuple[Path, Path]:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "prd.md").write_text("# PRD\n")
    target = workspace / "target"
    target.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=target, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=target, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=target, check=True)
    (target / ".gitignore").write_text("*.pyc\n")
    subprocess.run(["git", "add", "-A"], cwd=target, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=target, check=True)
    return workspace, target


# ---------------------------------------------------------------------------
# Composition scenarios
# ---------------------------------------------------------------------------


def test_charter_with_empty_acceptance_is_rejected() -> None:
    """A charter that doesn't populate per-feature acceptance is the
    upstream cause of silent skips. The validator must reject it before
    the engine ever sees a build session."""
    bundle = _make_realistic_bundle()
    bundle.feature_queue.features[0].acceptance = FeatureAcceptance()
    violations = validate_charter_completeness(bundle)
    assert any("'f01-scaffold'" in v and "empty acceptance" in v for v in violations)


def test_charter_without_test_command_is_rejected() -> None:
    bundle = _make_realistic_bundle()
    bundle.verification.backend_test_command = ""
    bundle.verification.frontend_test_command = ""
    violations = validate_charter_completeness(bundle)
    assert any("backend_test_command or frontend_test_command" in v for v in violations)


def test_load_charter_strict_aborts_run_on_invalid(tmp_path: Path) -> None:
    """A charter file on disk that fails validation must raise on load,
    so the engine can write charter-error.json and abort cleanly."""
    bundle = _make_realistic_bundle()
    bundle.feature_queue.features[0].acceptance = FeatureAcceptance()
    write_charter(bundle, tmp_path)
    with pytest.raises(ValueError, match="Charter rejected"):
        load_charter(tmp_path, strict=True)


def test_run_halts_on_first_failed_feature(tmp_path: Path, monkeypatch) -> None:
    """A FAILED feature must stop the run. The previous gross-skip
    behavior of marching on with [BROKEN] commits should no longer
    occur by default."""
    workspace, target = _setup_workspace(tmp_path)
    bundle = _make_realistic_bundle()

    monkeypatch.setattr(
        "ncdev.pipeline.engine.generate_charter",
        lambda **kwargs: (bundle, SimpleNamespace(summary=lambda: "ok")),
    )
    monkeypatch.setattr(
        "ncdev.pipeline.engine.run_design_phase",
        lambda **kwargs: SimpleNamespace(skipped=True, hard_failed=False, design_doc=None),
    )
    monkeypatch.setattr(
        "ncdev.pipeline.state_scanner.scan_completed_features",
        lambda target_path, features: [],
    )

    attempted: list[str] = []

    def fake_executor(*, feature, **kwargs):  # noqa: ARG001
        attempted.append(feature.feature_id)
        return StepResult(
            feature_id=feature.feature_id,
            status=StepStatus.FAILED,
            verification=None,
        )

    monkeypatch.setattr(
        "ncdev.pipeline.engine.execute_feature_claude_driven", fake_executor
    )

    state = run_pipeline(
        workspace=workspace,
        source_path=workspace / "prd.md",
        target_repo_path=target,
    )

    assert attempted == ["f01-scaffold"], (
        "f02 must NOT be attempted after f01 FAILED — that was the gross-skip path"
    )
    assert state.status == "failed"


def test_passed_features_still_get_integration_failed_when_routes_dont_respond(
    tmp_path: Path, monkeypatch
) -> None:
    """Per-feature PASSED is necessary but not sufficient. If the
    integration gate finds required_routes unreachable, the run is
    integration_failed regardless of feature counts."""
    workspace, target = _setup_workspace(tmp_path)
    bundle = _make_realistic_bundle()
    # Disable test commands so the gate's only failing clause is routes
    bundle.verification.backend_test_command = ""

    monkeypatch.setattr(
        "ncdev.pipeline.engine.generate_charter",
        lambda **kwargs: (bundle, SimpleNamespace(summary=lambda: "ok")),
    )
    monkeypatch.setattr(
        "ncdev.pipeline.engine.run_design_phase",
        lambda **kwargs: SimpleNamespace(skipped=True, hard_failed=False, design_doc=None),
    )
    monkeypatch.setattr(
        "ncdev.pipeline.state_scanner.scan_completed_features",
        lambda target_path, features: [],
    )

    def fake_executor(*, feature, **kwargs):  # noqa: ARG001
        # Seed the asset manifest so clause-1 passes; we want the route
        # probe (clause 3) to be the failing clause.
        save_feature_manifest(
            target,
            AssetManifest(feature_id=feature.feature_id, assets=[]),
        )
        return StepResult(feature_id=feature.feature_id, status=StepStatus.PASSED)

    monkeypatch.setattr(
        "ncdev.pipeline.engine.execute_feature_claude_driven", fake_executor
    )
    monkeypatch.setattr(
        "ncdev.pipeline.integration_gate._probe", lambda url, *, timeout: False
    )

    state = run_pipeline(
        workspace=workspace,
        source_path=workspace / "prd.md",
        target_repo_path=target,
    )

    assert state.status == "integration_failed", (
        "Both features PASSED but routes unreachable — must be integration_failed, "
        "NOT passed/partial"
    )
    integration = state.metadata.get("integration", {})
    failures = integration.get("failures", [])
    assert any("required_route unreachable" in f for f in failures)


def test_passed_features_with_all_gates_satisfied_yields_passed(
    tmp_path: Path, monkeypatch
) -> None:
    """The happy path: both features PASS, integration gate passes, run
    status is `passed`. Demonstrates the gates don't false-positive."""
    workspace, target = _setup_workspace(tmp_path)
    bundle = _make_realistic_bundle()
    # Drop required_files we can't easily satisfy in a tiny test
    bundle.verification.required_files = []

    monkeypatch.setattr(
        "ncdev.pipeline.engine.generate_charter",
        lambda **kwargs: (bundle, SimpleNamespace(summary=lambda: "ok")),
    )
    monkeypatch.setattr(
        "ncdev.pipeline.engine.run_design_phase",
        lambda **kwargs: SimpleNamespace(skipped=True, hard_failed=False, design_doc=None),
    )
    monkeypatch.setattr(
        "ncdev.pipeline.state_scanner.scan_completed_features",
        lambda target_path, features: [],
    )

    def fake_executor(*, feature, **kwargs):  # noqa: ARG001
        save_feature_manifest(
            target,
            AssetManifest(feature_id=feature.feature_id, assets=[]),
        )
        return StepResult(feature_id=feature.feature_id, status=StepStatus.PASSED)

    monkeypatch.setattr(
        "ncdev.pipeline.engine.execute_feature_claude_driven", fake_executor
    )
    # Routes all reachable
    monkeypatch.setattr(
        "ncdev.pipeline.integration_gate._probe", lambda url, *, timeout: True
    )

    state = run_pipeline(
        workspace=workspace,
        source_path=workspace / "prd.md",
        target_repo_path=target,
    )

    assert state.status == "passed"
    assert state.completed_features == 2
    integration = state.metadata.get("integration", {})
    assert integration.get("passed") is True
    assert integration.get("routes_probed") == 2
