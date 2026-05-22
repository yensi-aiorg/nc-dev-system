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


def test_pip_audit_excluded_without_requirements_file(tmp_path: Path) -> None:
    """pip-audit with no target audits the ambient environment, not the
    project — so it only applies when the repo ships requirements.txt."""
    from ncdev.pipeline.gauntlet.layers_static import _scanners_for

    names = {s[0] for s in _scanners_for(tmp_path)}
    assert "pip-audit" not in names
    assert "bandit" in names  # repo-scoped scanners always apply


def test_pip_audit_included_and_scoped_with_requirements_file(tmp_path: Path) -> None:
    from ncdev.pipeline.gauntlet.layers_static import _scanners_for

    (tmp_path / "requirements.txt").write_text("flask==2.0.0\n")
    scanners = {s[0]: s[1] for s in _scanners_for(tmp_path)}
    assert "pip-audit" in scanners
    # Must be pointed at the repo's file, not left to audit the ambient env.
    assert "-r" in scanners["pip-audit"]
    assert "requirements.txt" in scanners["pip-audit"]


def test_which_finds_binary_next_to_interpreter(tmp_path: Path, monkeypatch) -> None:
    """_which must locate pip-installed console scripts next to
    sys.executable even when the venv bin dir is not on PATH."""
    import sys

    from ncdev.pipeline.gauntlet.layers_static import _which

    fake_bin = tmp_path / "py" / "bin"
    fake_bin.mkdir(parents=True)
    (fake_bin / "myscanner").write_text("#!/bin/sh\n")
    monkeypatch.setattr(sys, "executable", str(fake_bin / "python"))
    assert _which("myscanner") == str(fake_bin / "myscanner")
    assert _which("definitely-not-installed-xyz") is None


def test_security_skipped_when_no_scanner_installed(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(layers_static, "_which", lambda _b: None)
    result = layer_security(_ctx(tmp_path))
    assert result.status == LayerStatus.SKIPPED
    assert result.blocking is False


def test_security_passes_when_scanner_clean(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        layers_static, "_which",
        lambda b: "/usr/bin/bandit" if b == "bandit" else None,
    )
    monkeypatch.setattr(
        layers_static, "run_shell", lambda *a, **k: (True, 0, "no issues"),
    )
    result = layer_security(_ctx(tmp_path))
    assert result.status == LayerStatus.PASSED
    assert "bandit" in result.summary


def test_security_fails_and_blocks_when_scanner_flags(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        layers_static, "_which",
        lambda b: "/usr/bin/bandit" if b == "bandit" else None,
    )
    monkeypatch.setattr(
        layers_static, "run_shell",
        lambda *a, **k: (False, 1, "HIGH: hardcoded password"),
    )
    result = layer_security(_ctx(tmp_path))
    assert result.status == LayerStatus.FAILED
    assert result.blocking is True
    assert result.is_blocking_failure is True
