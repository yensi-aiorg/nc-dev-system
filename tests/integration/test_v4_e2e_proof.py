"""v4 end-to-end proof.

Exercises the real chain — feature executor -> the REAL Verification
Gauntlet -> StepResult -> run report — with only the AI boundary
sessions stubbed (the build session and the L8 oracle reviewer; L5/L6
have nothing to act on here). The design's headline success criterion
is proven directly: the anti-bypass layer catches a planted stub and
the feature is blocked because of it.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ncdev.claude_session import ClaudeSessionResult
from ncdev.pipeline.claude_executor import execute_feature_claude_driven
from ncdev.pipeline.gauntlet import layers_oracle
from ncdev.pipeline.models import (
    CharterBundle,
    FeatureAcceptance,
    FeatureQueueDoc,
    FeatureStep,
    PipelineRunState,
    StepStatus,
    TargetProjectContract,
    VerificationContract,
)
from ncdev.pipeline.run_report import build_run_report


def _init_git(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=str(path), check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=str(path), check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=str(path), check=True)
    (path / "README.md").write_text("init")
    subprocess.run(["git", "add", "-A"], cwd=str(path), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(path), check=True)


def _feature() -> FeatureStep:
    return FeatureStep(
        feature_id="f02-payments",
        title="Payment charging",
        description="Charge a card through the payment gateway",
        acceptance_criteria=["charge() actually charges via the gateway"],
        acceptance=FeatureAcceptance(required_files=["app/payment.py"]),
    )


def _bundle() -> CharterBundle:
    return CharterBundle(
        contract=TargetProjectContract(project_name="shop", project_type="api"),
        verification=VerificationContract(
            backend_health_url="", backend_test_command="",
            frontend_test_command="", minimum_test_count=0,
            assets_manifest_required=True,
        ),
        feature_queue=FeatureQueueDoc(project_name="shop", features=[_feature()]),
    )


@pytest.fixture(autouse=True)
def _stub_oracle(monkeypatch):
    """Stub only the L8 oracle's AI session — every other gauntlet
    layer (notably L7 anti-bypass) runs for real in this proof."""
    import json

    monkeypatch.setattr(
        layers_oracle, "_run_review_session",
        lambda *a, **k: (True, json.dumps({"criteria": [], "overall": "pass"})),
    )


def _run_feature(target: Path, run_dir: Path, body: str):
    """Build a feature whose session commits app/payment.py with `body`."""
    from ncdev.pipeline import asset_manifest
    from ncdev.pipeline.models import AssetManifest

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        asset_manifest.save_feature_manifest(
            target, AssetManifest(feature_id="f02-payments", assets=[]),
        )
        pkg = target / "app"
        pkg.mkdir(exist_ok=True)
        (pkg / "payment.py").write_text(body)
        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "feat(f02-payments): charging"],
            cwd=str(target), check=True,
        )
        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)

    from unittest.mock import patch

    with patch("ncdev.pipeline.claude_executor.run_ai_session", side_effect=fake_session):
        return execute_feature_claude_driven(
            feature=_feature(), target_path=target, run_dir=run_dir,
            charter_bundle=_bundle(), prior_results=[], project_id="shop",
        )


def test_planted_stub_is_caught_by_the_gauntlet(tmp_path: Path):
    """A feature that builds, commits, and verifies cleanly is STILL
    blocked when its production code contains a stubbed integration —
    the headline v4 success criterion."""
    target = tmp_path / "shop"
    target.mkdir()
    _init_git(target)
    run_dir = tmp_path / "run"

    # The build session "charges a card" with a planted stub.
    result = _run_feature(
        target, run_dir,
        body="def charge(card):\n    raise NotImplementedError  # wire later\n",
    )

    assert result.status == StepStatus.FAILED
    assert "gauntlet BLOCKED" in result.error_message
    assert "L7-anti-bypass" in result.error_message
    assert (run_dir / "steps" / "f02-payments" / "gauntlet.json").exists()

    # The run report surfaces the blocking failure for a human.
    state = PipelineRunState(
        run_id="proof-1", command="factory", status="partial",
        target_path=str(target),
    )
    state.completed_steps = [result]
    report = build_run_report(state, run_dir)
    fr = report.features[0]
    assert fr.gauntlet_passed is False
    assert any("L7-anti-bypass" in b for b in fr.gauntlet_blocking)
    assert "f02-payments" in report.to_markdown()


def test_clean_feature_clears_the_gauntlet(tmp_path: Path):
    """The control case: real working code with no stub markers passes
    the same gauntlet — proving the proof above is not a false alarm."""
    target = tmp_path / "shop"
    target.mkdir()
    _init_git(target)
    run_dir = tmp_path / "run"

    result = _run_feature(
        target, run_dir,
        body=(
            "def charge(card, gateway):\n"
            "    return gateway.charge(card.token, card.amount)\n"
        ),
    )

    assert result.status == StepStatus.PASSED
    assert "gauntlet BLOCKED" not in result.error_message
