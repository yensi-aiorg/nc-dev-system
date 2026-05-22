"""Tests for the static gauntlet layers: L6 security, L7 anti-bypass."""
from __future__ import annotations

from pathlib import Path

from ncdev.pipeline.gauntlet import GauntletContext, LayerStatus
from ncdev.pipeline.gauntlet import layers_static
from ncdev.pipeline.gauntlet.layers_static import layer_anti_bypass, layer_security
from ncdev.pipeline.models import FeatureStep, VerificationContract


def _ctx(tmp_path: Path, *, diff: str = "", run_commands: bool = True) -> GauntletContext:
    return GauntletContext(
        feature=FeatureStep(
            feature_id="f01", title="Demo", description="d",
            acceptance_criteria=["works"],
        ),
        contract=VerificationContract(),
        repo=tmp_path,
        diff=diff,
        run_commands=run_commands,
    )


# --- L7 anti-bypass --------------------------------------------------------


def test_anti_bypass_skipped_without_diff(tmp_path: Path) -> None:
    result = layer_anti_bypass(_ctx(tmp_path))
    assert result.status == LayerStatus.SKIPPED


def test_anti_bypass_flags_not_implemented_in_production(tmp_path: Path) -> None:
    diff = (
        "+++ b/backend/app/services/payment.py\n"
        "+def charge(card):\n"
        "+    raise NotImplementedError\n"
    )
    result = layer_anti_bypass(_ctx(tmp_path, diff=diff))
    assert result.status == LayerStatus.FAILED
    assert result.blocking is True
    assert any("payment.py" in f for f in result.findings)


def test_anti_bypass_ignores_not_implemented_in_test_files(tmp_path: Path) -> None:
    diff = (
        "+++ b/backend/tests/test_payment.py\n"
        "+def test_charge():\n"
        "+    raise NotImplementedError\n"
    )
    result = layer_anti_bypass(_ctx(tmp_path, diff=diff))
    assert result.status == LayerStatus.PASSED


def test_anti_bypass_flags_stub_comment(tmp_path: Path) -> None:
    diff = (
        "+++ b/src/api.py\n"
        "+def fetch():\n"
        "+    return {}  # stub — wire real API later\n"
    )
    result = layer_anti_bypass(_ctx(tmp_path, diff=diff))
    assert result.status == LayerStatus.FAILED


def test_anti_bypass_flags_mock_in_production_code(tmp_path: Path) -> None:
    diff = (
        "+++ b/src/gateway.py\n"
        "+from unittest.mock import MagicMock\n"
        "+client = MagicMock()\n"
    )
    result = layer_anti_bypass(_ctx(tmp_path, diff=diff))
    assert result.status == LayerStatus.FAILED


def test_anti_bypass_passes_clean_diff(tmp_path: Path) -> None:
    diff = (
        "+++ b/src/api.py\n"
        "+def fetch(client):\n"
        "+    return client.get('/users').json()\n"
    )
    result = layer_anti_bypass(_ctx(tmp_path, diff=diff))
    assert result.status == LayerStatus.PASSED
    assert result.blocking is True


# --- L6 security -----------------------------------------------------------


def test_security_skipped_when_commands_disabled(tmp_path: Path) -> None:
    result = layer_security(_ctx(tmp_path, run_commands=False))
    assert result.status == LayerStatus.SKIPPED


def test_security_skipped_when_no_scanner_installed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(layers_static, "_which", lambda _b: False)
    result = layer_security(_ctx(tmp_path))
    assert result.status == LayerStatus.SKIPPED
    assert result.blocking is False


def test_security_passes_when_scanner_clean(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(layers_static, "_which", lambda b: b == "bandit")
    monkeypatch.setattr(
        layers_static, "run_shell", lambda *a, **k: (True, 0, "no issues"),
    )
    result = layer_security(_ctx(tmp_path))
    assert result.status == LayerStatus.PASSED
    assert "bandit" in result.summary


def test_security_fails_and_blocks_when_scanner_flags(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(layers_static, "_which", lambda b: b == "bandit")
    monkeypatch.setattr(
        layers_static, "run_shell",
        lambda *a, **k: (False, 1, "HIGH: hardcoded password"),
    )
    result = layer_security(_ctx(tmp_path))
    assert result.status == LayerStatus.FAILED
    assert result.blocking is True
    assert result.is_blocking_failure is True
