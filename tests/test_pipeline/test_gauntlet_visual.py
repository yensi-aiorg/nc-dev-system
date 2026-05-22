"""Tests for L5 — visual verification layer."""
from __future__ import annotations

from pathlib import Path

from ncdev.pipeline.gauntlet import GauntletContext, LayerStatus
from ncdev.pipeline.gauntlet import layers_visual
from ncdev.pipeline.gauntlet.layers_visual import _locate_screenshot, layer_visual
from ncdev.pipeline.models import (
    FeatureAcceptance,
    FeatureStep,
    VerificationContract,
)


def _ctx(tmp_path: Path, *, shots: list[str], run: bool = True) -> GauntletContext:
    return GauntletContext(
        feature=FeatureStep(
            feature_id="f01", title="Dashboard", description="d",
            acceptance_criteria=["dashboard renders charts"],
            acceptance=FeatureAcceptance(required_screenshots=shots),
        ),
        contract=VerificationContract(),
        repo=tmp_path,
        run_commands=run,
    )


def _make_png(repo: Path, rel: str) -> Path:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n")  # PNG magic — content irrelevant
    return path


def test_visual_skipped_when_no_required_screenshots(tmp_path: Path) -> None:
    result = layer_visual(_ctx(tmp_path, shots=[]))
    assert result.status == LayerStatus.SKIPPED


def test_visual_skipped_when_commands_disabled(tmp_path: Path) -> None:
    result = layer_visual(_ctx(tmp_path, shots=["dashboard"], run=False))
    assert result.status == LayerStatus.SKIPPED


def test_locate_screenshot_matches_by_token(tmp_path: Path) -> None:
    _make_png(tmp_path, ".ncdev/evidence/dashboard-desktop-1440x900.png")
    found = _locate_screenshot(tmp_path, "dashboard-shell")
    assert found is not None and found.name.startswith("dashboard")


def test_visual_blocks_when_required_screenshot_missing(tmp_path: Path) -> None:
    result = layer_visual(_ctx(tmp_path, shots=["dashboard"]))
    assert result.status == LayerStatus.FAILED
    assert result.is_blocking_failure is True
    assert any("missing" in f for f in result.findings)


def test_visual_passes_when_screenshot_present_and_clean(tmp_path: Path, monkeypatch) -> None:
    _make_png(tmp_path, "evidence/screenshots/dashboard.png")
    monkeypatch.setattr(
        layers_visual, "_review_screenshot", lambda *a, **k: (True, "looks good"),
    )
    result = layer_visual(_ctx(tmp_path, shots=["dashboard"]))
    assert result.status == LayerStatus.PASSED
    assert result.blocking is True


def test_visual_blocks_when_vision_judges_screen_broken(tmp_path: Path, monkeypatch) -> None:
    _make_png(tmp_path, "docs/screenshots/dashboard.png")
    monkeypatch.setattr(
        layers_visual, "_review_screenshot",
        lambda *a, **k: (False, "500 error banner across the top"),
    )
    result = layer_visual(_ctx(tmp_path, shots=["dashboard"]))
    assert result.status == LayerStatus.FAILED
    assert result.is_blocking_failure is True
    assert any("error banner" in f for f in result.findings)


def test_visual_no_verdict_is_nonblocking_error(tmp_path: Path, monkeypatch) -> None:
    _make_png(tmp_path, "evidence/screenshots/dashboard.png")
    monkeypatch.setattr(
        layers_visual, "_review_screenshot",
        lambda *a, **k: (False, "__no_verdict__"),
    )
    result = layer_visual(_ctx(tmp_path, shots=["dashboard"]))
    assert result.status == LayerStatus.ERROR
    assert result.blocking is False
