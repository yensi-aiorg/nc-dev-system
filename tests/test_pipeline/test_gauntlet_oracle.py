"""Tests for L8 — oracle review layer."""
from __future__ import annotations

import json
from pathlib import Path

from ncdev.pipeline.gauntlet import GauntletContext, LayerStatus
from ncdev.pipeline.gauntlet import layers_oracle
from ncdev.pipeline.gauntlet.layers_oracle import (
    _parse_verdict,
    _select_reviewer,
    layer_oracle,
)
from ncdev.pipeline.models import FeatureStep, VerificationContract

_DIFF = "+++ b/src/api.py\n+def fetch():\n+    return 1\n"


def _ctx(tmp_path: Path, *, diff: str = _DIFF, builder: str = "claude", run: bool = True):
    return GauntletContext(
        feature=FeatureStep(
            feature_id="f01", title="Demo", description="d",
            acceptance_criteria=["fetch returns data"],
        ),
        contract=VerificationContract(),
        repo=tmp_path,
        diff=diff,
        builder_provider=builder,
        run_commands=run,
    )


def test_reviewer_is_decorrelated_from_builder() -> None:
    assert _select_reviewer("claude") == "codex"
    assert _select_reviewer("codex") == "claude"


def test_parse_verdict_handles_fenced_json() -> None:
    text = 'here is my review\n```json\n{"overall": "pass", "criteria": []}\n```\n'
    parsed = _parse_verdict(text)
    assert parsed == {"overall": "pass", "criteria": []}


def test_parse_verdict_handles_bare_json() -> None:
    parsed = _parse_verdict('{"overall": "fail", "criteria": []}')
    assert parsed["overall"] == "fail"


def test_parse_verdict_returns_none_on_garbage() -> None:
    assert _parse_verdict("no json here at all") is None


def test_oracle_skipped_without_diff(tmp_path: Path) -> None:
    result = layer_oracle(_ctx(tmp_path, diff=""))
    assert result.status == LayerStatus.SKIPPED


def test_oracle_skipped_when_commands_disabled(tmp_path: Path) -> None:
    result = layer_oracle(_ctx(tmp_path, run=False))
    assert result.status == LayerStatus.SKIPPED


def test_oracle_passes_when_all_criteria_met(tmp_path: Path, monkeypatch) -> None:
    verdict = json.dumps({
        "criteria": [{"index": 1, "verdict": "met", "reason": "ok"}],
        "overall": "pass",
    })
    monkeypatch.setattr(
        layers_oracle, "_run_review_session", lambda *a, **k: (True, verdict),
    )
    result = layer_oracle(_ctx(tmp_path))
    assert result.status == LayerStatus.PASSED
    assert result.blocking is True


def test_oracle_blocks_when_criterion_not_met(tmp_path: Path, monkeypatch) -> None:
    verdict = json.dumps({
        "criteria": [
            {"index": 1, "verdict": "not_met", "reason": "fetch is a stub"},
        ],
        "overall": "fail",
    })
    monkeypatch.setattr(
        layers_oracle, "_run_review_session", lambda *a, **k: (True, verdict),
    )
    result = layer_oracle(_ctx(tmp_path))
    assert result.status == LayerStatus.FAILED
    assert result.is_blocking_failure is True
    assert any("stub" in f for f in result.findings)


def test_oracle_unparseable_verdict_is_nonblocking_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        layers_oracle, "_run_review_session", lambda *a, **k: (True, "i refuse"),
    )
    result = layer_oracle(_ctx(tmp_path))
    assert result.status == LayerStatus.ERROR
    assert result.blocking is False  # oracle malfunction must not brick builds


def test_oracle_session_crash_is_nonblocking_error(tmp_path: Path, monkeypatch) -> None:
    def boom(*a, **k):
        raise RuntimeError("cli gone")

    monkeypatch.setattr(layers_oracle, "_run_review_session", boom)
    result = layer_oracle(_ctx(tmp_path))
    assert result.status == LayerStatus.ERROR
    assert result.blocking is False
