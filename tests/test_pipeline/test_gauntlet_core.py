"""Tests for the Verification Gauntlet core + command layers (L0-L4)."""
from __future__ import annotations

from pathlib import Path

from ncdev.pipeline.gauntlet import (
    DEFAULT_LAYERS,
    GauntletContext,
    GauntletLayerResult,
    GauntletReport,
    LayerStatus,
    run_gauntlet,
)
from ncdev.pipeline.gauntlet.layers_command import (
    layer_compile,
    layer_lint,
    layer_unit_tests,
)
from ncdev.pipeline.models import FeatureStep, VerificationContract


def _ctx(tmp_path: Path, contract: VerificationContract, **kw) -> GauntletContext:
    return GauntletContext(
        feature=FeatureStep(
            feature_id="f01",
            title="Demo",
            description="Demo feature",
            acceptance_criteria=["works"],
        ),
        contract=contract,
        repo=tmp_path,
        **kw,
    )


# --- models ----------------------------------------------------------------


def test_report_passes_with_no_blocking_failure() -> None:
    report = GauntletReport(
        feature_id="f01",
        layers=[
            GauntletLayerResult("L0", LayerStatus.PASSED, True, "ok"),
            GauntletLayerResult("L1", LayerStatus.SKIPPED, False, "skip"),
        ],
    )
    assert report.passed is True
    assert report.blocking_failures == []


def test_report_blocked_by_blocking_failure() -> None:
    report = GauntletReport(
        feature_id="f01",
        layers=[
            GauntletLayerResult("L0", LayerStatus.PASSED, True, "ok"),
            GauntletLayerResult("L2", LayerStatus.FAILED, True, "tests failed"),
        ],
    )
    assert report.passed is False
    assert [layer.layer for layer in report.blocking_failures] == ["L2"]


def test_non_blocking_failure_does_not_block() -> None:
    report = GauntletReport(
        feature_id="f01",
        layers=[GauntletLayerResult("L8", LayerStatus.FAILED, False, "advisory")],
    )
    assert report.passed is True
    assert [layer.layer for layer in report.advisory_failures] == ["L8"]


def test_error_in_blocking_layer_blocks() -> None:
    layer = GauntletLayerResult("L6", LayerStatus.ERROR, True, "tool missing")
    assert layer.is_blocking_failure is True


# --- command layers --------------------------------------------------------


def test_command_layer_skipped_when_no_command(tmp_path: Path) -> None:
    result = layer_lint(_ctx(tmp_path, VerificationContract()))
    assert result.status == LayerStatus.SKIPPED
    assert result.blocking is False


def test_command_layer_skipped_when_commands_disabled(tmp_path: Path) -> None:
    contract = VerificationContract(lint_command="echo lint-ok")
    result = layer_lint(_ctx(tmp_path, contract, run_commands=False))
    assert result.status == LayerStatus.SKIPPED


def test_command_layer_passes_on_zero_exit(tmp_path: Path) -> None:
    contract = VerificationContract(lint_command="echo lint-ok && exit 0")
    result = layer_lint(_ctx(tmp_path, contract))
    assert result.status == LayerStatus.PASSED
    assert result.blocking is True


def test_command_layer_fails_and_blocks_on_nonzero_exit(tmp_path: Path) -> None:
    contract = VerificationContract(lint_command="echo broken && exit 3")
    result = layer_lint(_ctx(tmp_path, contract))
    assert result.status == LayerStatus.FAILED
    assert result.blocking is True
    assert result.is_blocking_failure is True
    assert "broken" in result.detail


def test_compile_layer_runs_typecheck_then_build(tmp_path: Path) -> None:
    # typecheck passes, build fails — layer must fail on build.
    contract = VerificationContract(
        typecheck_command="exit 0",
        build_command="echo build-broke && exit 1",
    )
    result = layer_compile(_ctx(tmp_path, contract))
    assert result.status == LayerStatus.FAILED
    assert "build" in result.summary


def test_unit_tests_layer_runs_backend_and_frontend(tmp_path: Path) -> None:
    contract = VerificationContract(
        backend_test_command="exit 0",
        frontend_test_command="exit 0",
    )
    result = layer_unit_tests(_ctx(tmp_path, contract))
    assert result.status == LayerStatus.PASSED
    assert len(result.findings) == 2


# --- orchestrator ----------------------------------------------------------


def test_run_gauntlet_aggregates_all_layers(tmp_path: Path) -> None:
    contract = VerificationContract(
        typecheck_command="exit 0",
        lint_command="exit 0",
        backend_test_command="exit 0",
    )
    report = run_gauntlet(_ctx(tmp_path, contract))
    assert report.feature_id == "f01"
    assert len(report.layers) == len(DEFAULT_LAYERS)
    assert report.passed is True


def test_run_gauntlet_blocks_on_failing_layer(tmp_path: Path) -> None:
    contract = VerificationContract(backend_test_command="exit 1")
    report = run_gauntlet(_ctx(tmp_path, contract))
    assert report.passed is False
    assert any(layer.layer == "L2-unit" for layer in report.blocking_failures)


def test_run_gauntlet_catches_crashing_layer_as_nonblocking_error(
    tmp_path: Path,
) -> None:
    def exploding_layer(ctx):  # noqa: ANN001, ARG001
        raise RuntimeError("kaboom")

    report = run_gauntlet(
        _ctx(tmp_path, VerificationContract()),
        layers=[exploding_layer],
    )
    assert len(report.layers) == 1
    crashed = report.layers[0]
    assert crashed.status == LayerStatus.ERROR
    assert crashed.blocking is False
    # A gauntlet bug must not brick the build.
    assert report.passed is True
    assert "kaboom" in crashed.summary


def test_summary_line_reports_verdict(tmp_path: Path) -> None:
    contract = VerificationContract(backend_test_command="exit 1")
    report = run_gauntlet(_ctx(tmp_path, contract))
    line = report.summary_line()
    assert "BLOCKED" in line
    assert "f01" in line
