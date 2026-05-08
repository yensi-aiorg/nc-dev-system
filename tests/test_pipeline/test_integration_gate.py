"""Tests for Phase 5b integration gate."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from ncdev.pipeline.asset_manifest import save_feature_manifest
from ncdev.pipeline.integration_gate import (
    IntegrationResult,
    _derive_base_url,
    _resolve_url,
    run_integration_gate,
)
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


def _bundle(
    *,
    backend_health_url: str = "http://localhost:23001/api/health",
    backend_test_command: str = "",
    frontend_test_command: str = "",
    e2e_test_command: str = "",
    required_files: list[str] | None = None,
    features: list[FeatureStep] | None = None,
) -> CharterBundle:
    return CharterBundle(
        contract=TargetProjectContract(project_name="proj", project_type="web"),
        verification=VerificationContract(
            backend_health_url=backend_health_url,
            backend_test_command=backend_test_command,
            frontend_test_command=frontend_test_command,
            e2e_test_command=e2e_test_command,
            required_files=required_files or [],
        ),
        feature_queue=FeatureQueueDoc(
            project_name="proj",
            features=features or [],
        ),
    )


def _passed(feature_id: str) -> StepResult:
    return StepResult(feature_id=feature_id, status=StepStatus.PASSED)


def _seed_manifest(target: Path, feature_id: str) -> None:
    save_feature_manifest(target, AssetManifest(feature_id=feature_id, assets=[]))


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


def test_derive_base_url_strips_path() -> None:
    assert _derive_base_url("http://localhost:23001/api/health") == "http://localhost:23001"
    assert _derive_base_url("https://api.example.com/v1/healthz") == "https://api.example.com"


def test_derive_base_url_returns_empty_when_input_empty() -> None:
    assert _derive_base_url("") == ""


def test_resolve_url_passes_through_absolute() -> None:
    assert _resolve_url("https://example.com/x", "http://localhost") == "https://example.com/x"


def test_resolve_url_joins_relative_to_base() -> None:
    assert _resolve_url("/api/auth/login", "http://localhost:23001") == "http://localhost:23001/api/auth/login"
    assert _resolve_url("api/auth/login", "http://localhost:23001/") == "http://localhost:23001/api/auth/login"


def test_resolve_url_returns_none_when_no_base() -> None:
    assert _resolve_url("/api/x", "") is None


# ---------------------------------------------------------------------------
# Asset manifest coverage clause
# ---------------------------------------------------------------------------


def test_gate_passes_when_all_clauses_satisfied(tmp_path: Path) -> None:
    target = tmp_path / "app"
    target.mkdir()
    _seed_manifest(target, "f1")
    bundle = _bundle(
        features=[FeatureStep(
            feature_id="f1",
            title="x",
            description="x",
            acceptance_criteria=["x"],
        )],
    )

    result = run_integration_gate(
        bundle=bundle,
        target_path=target,
        completed=[_passed("f1")],
        probe_health=False,
        run_test_commands=False,
    )

    assert result.passed is True
    assert result.failures == []


def test_gate_fails_when_required_file_missing(tmp_path: Path) -> None:
    target = tmp_path / "app"
    target.mkdir()
    _seed_manifest(target, "f1")
    bundle = _bundle(
        required_files=["docker-compose.yml"],
        features=[FeatureStep(feature_id="f1", title="x", description="x", acceptance_criteria=["x"])],
    )

    result = run_integration_gate(
        bundle=bundle,
        target_path=target,
        completed=[_passed("f1")],
        probe_health=False,
        run_test_commands=False,
    )

    assert result.passed is False
    assert any("docker-compose.yml" in f for f in result.failures)
    assert result.contract_files_ok is False


def test_gate_fails_when_manifest_missing_for_passed_feature(tmp_path: Path) -> None:
    target = tmp_path / "app"
    target.mkdir()
    # Note: NOT seeding manifest, but PASSED feature requires one
    bundle = _bundle(
        features=[FeatureStep(feature_id="f1", title="x", description="x", acceptance_criteria=["x"])],
    )

    result = run_integration_gate(
        bundle=bundle,
        target_path=target,
        completed=[_passed("f1")],
        probe_health=False,
        run_test_commands=False,
    )

    assert result.passed is False
    assert result.asset_coverage_ok is False


def test_gate_skips_manifest_check_for_skipped_features(tmp_path: Path) -> None:
    """SKIPPED brownfield features predate the manifest contract — don't
    flag them."""
    target = tmp_path / "app"
    target.mkdir()
    bundle = _bundle(
        features=[FeatureStep(feature_id="f1", title="x", description="x", acceptance_criteria=["x"])],
    )

    result = run_integration_gate(
        bundle=bundle,
        target_path=target,
        completed=[StepResult(feature_id="f1", status=StepStatus.SKIPPED)],
        probe_health=False,
        run_test_commands=False,
    )

    # No PASSED features → manifest aggregate is the only check, and
    # aggregate works even with no manifests on disk.
    assert result.asset_coverage_ok is True


# ---------------------------------------------------------------------------
# required_routes probing
# ---------------------------------------------------------------------------


def test_gate_probes_required_routes_for_passed_features(tmp_path: Path) -> None:
    target = tmp_path / "app"
    target.mkdir()
    _seed_manifest(target, "f1")
    bundle = _bundle(
        features=[FeatureStep(
            feature_id="f1",
            title="auth",
            description="x",
            acceptance_criteria=["x"],
            acceptance=FeatureAcceptance(
                required_routes=["/api/auth/login", "/api/auth/logout"],
            ),
        )],
    )
    probed: list[str] = []

    def fake_probe(url: str, *, timeout: int) -> bool:
        probed.append(url)
        return True

    with patch("ncdev.pipeline.integration_gate._probe", side_effect=fake_probe):
        result = run_integration_gate(
            bundle=bundle,
            target_path=target,
            completed=[_passed("f1")],
            probe_health=True,
            run_test_commands=False,
        )

    assert result.routes_probed == 2
    assert result.passed is True
    assert "http://localhost:23001/api/auth/login" in probed
    assert "http://localhost:23001/api/auth/logout" in probed


def test_gate_fails_when_route_unreachable(tmp_path: Path) -> None:
    target = tmp_path / "app"
    target.mkdir()
    _seed_manifest(target, "f1")
    bundle = _bundle(
        features=[FeatureStep(
            feature_id="f1",
            title="auth",
            description="x",
            acceptance_criteria=["x"],
            acceptance=FeatureAcceptance(required_routes=["/api/auth"]),
        )],
    )

    with patch("ncdev.pipeline.integration_gate._probe", return_value=False):
        result = run_integration_gate(
            bundle=bundle,
            target_path=target,
            completed=[_passed("f1")],
            probe_health=True,
            run_test_commands=False,
        )

    assert result.passed is False
    assert any("required_route unreachable" in f for f in result.failures)
    assert result.routes_failed


def test_gate_does_not_probe_routes_for_skipped_features(tmp_path: Path) -> None:
    target = tmp_path / "app"
    target.mkdir()
    bundle = _bundle(
        features=[FeatureStep(
            feature_id="f1",
            title="x",
            description="x",
            acceptance_criteria=["x"],
            acceptance=FeatureAcceptance(required_routes=["/api/x"]),
        )],
    )

    with patch("ncdev.pipeline.integration_gate._probe") as mock_probe:
        result = run_integration_gate(
            bundle=bundle,
            target_path=target,
            completed=[StepResult(feature_id="f1", status=StepStatus.SKIPPED)],
            probe_health=True,
            run_test_commands=False,
        )

    mock_probe.assert_not_called()
    assert result.routes_probed == 0


def test_gate_flags_unresolvable_route_when_no_base_url(tmp_path: Path) -> None:
    target = tmp_path / "app"
    target.mkdir()
    _seed_manifest(target, "f1")
    bundle = _bundle(
        backend_health_url="",
        features=[FeatureStep(
            feature_id="f1",
            title="x",
            description="x",
            acceptance_criteria=["x"],
            acceptance=FeatureAcceptance(required_routes=["/api/x"]),
        )],
    )

    result = run_integration_gate(
        bundle=bundle,
        target_path=target,
        completed=[_passed("f1")],
        probe_health=True,
        run_test_commands=False,
    )

    assert result.passed is False
    assert any("cannot be resolved" in f for f in result.failures)


# ---------------------------------------------------------------------------
# Test command clauses
# ---------------------------------------------------------------------------


def test_gate_runs_backend_test_command_when_configured(tmp_path: Path) -> None:
    target = tmp_path / "app"
    target.mkdir()
    bundle = _bundle(
        backend_test_command="echo backend tests pass",
        features=[],
    )

    result = run_integration_gate(
        bundle=bundle,
        target_path=target,
        completed=[],
        probe_health=False,
        run_test_commands=True,
    )

    assert result.backend_tests_ok is True


def test_gate_fails_when_backend_test_command_fails(tmp_path: Path) -> None:
    target = tmp_path / "app"
    target.mkdir()
    bundle = _bundle(
        backend_test_command="exit 1",
        features=[],
    )

    result = run_integration_gate(
        bundle=bundle,
        target_path=target,
        completed=[],
        probe_health=False,
        run_test_commands=True,
    )

    assert result.passed is False
    assert result.backend_tests_ok is False
    assert any("backend test suite failed" in f for f in result.failures)


def test_gate_runs_e2e_when_configured(tmp_path: Path) -> None:
    target = tmp_path / "app"
    target.mkdir()
    bundle = _bundle(
        e2e_test_command="exit 0",
        features=[],
    )

    result = run_integration_gate(
        bundle=bundle,
        target_path=target,
        completed=[],
        probe_health=False,
        run_test_commands=True,
    )

    assert result.e2e_tests_ok is True


def test_gate_skips_test_commands_when_run_test_commands_false(tmp_path: Path) -> None:
    target = tmp_path / "app"
    target.mkdir()
    bundle = _bundle(
        backend_test_command="exit 1",  # would fail if run
        features=[],
    )

    result = run_integration_gate(
        bundle=bundle,
        target_path=target,
        completed=[],
        probe_health=False,
        run_test_commands=False,
    )

    assert result.backend_tests_ok is None
    assert result.passed is True


# ---------------------------------------------------------------------------
# IntegrationResult shape
# ---------------------------------------------------------------------------


def test_integration_result_default_state() -> None:
    r = IntegrationResult()
    assert r.passed is False
    assert r.failures == []
    assert r.routes_probed == 0
