"""Tests for Phase E Claude-driven feature executor."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest


from ncdev.claude_session import ClaudeSessionResult
from ncdev.pipeline.asset_manifest import save_feature_manifest
from ncdev.pipeline.claude_executor import (
    _ensure_git_identity,
    _load_prior_verdict_findings,
    build_feature_prompt,
    execute_feature_claude_driven,
)
from ncdev.pipeline.models import (
    AssetManifest,
    CharterBundle,
    FeatureQueueDoc,
    FeatureStep,
    StepStatus,
    TargetProjectContract,
    VerificationContract,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_feature(fid: str = "f01-scaffold") -> FeatureStep:
    return FeatureStep(
        feature_id=fid,
        title="Scaffold",
        description="Boot skeleton + health endpoint",
        acceptance_criteria=["Health endpoint returns 200"],
        test_requirements=["Integration test hits /api/health"],
    )


def _make_bundle(required_files: list[str] | None = None) -> CharterBundle:
    # Test-only bundle: empty test commands + no health URL so the
    # grounded verifier (stubbed in these unit tests) has nothing real
    # to run against a non-existent server.
    return CharterBundle(
        contract=TargetProjectContract(project_name="myapp", project_type="web"),
        verification=VerificationContract(
            backend_health_url="",
            backend_test_command="",
            frontend_test_command="",
            minimum_test_count=0,
            required_files=required_files or [],
            prohibited_patterns=["TODO"],
            assets_manifest_required=True,
        ),
        feature_queue=FeatureQueueDoc(project_name="myapp", features=[_make_feature()]),
    )


def _init_git(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=str(path), check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=str(path), check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=str(path), check=True)
    (path / "README.md").write_text("initial")
    subprocess.run(["git", "add", "-A"], cwd=str(path), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(path), check=True)


def _seed_manifest(target: Path, feature_id: str) -> None:
    save_feature_manifest(target, AssetManifest(feature_id=feature_id, assets=[]))


@pytest.fixture(autouse=True)
def _stub_grounded_verify(monkeypatch):
    """Keep executor unit tests hermetic w.r.t. the grounded verifier.

    The grounded verifier is a separate subsystem with its own test
    suite (tests/test_pipeline/test_grounded_verify*), and it spawns a
    real Claude judge session + runs test commands. Executor unit tests
    stub it to a passing verdict by default so they exercise the
    executor's wiring and status decision, not the verifier internals.
    """
    from ncdev.pipeline.models import StepVerification

    monkeypatch.setattr(
        "ncdev.pipeline.grounded_verify.grounded_verify",
        lambda *a, **kw: StepVerification(overall_passed=True, failure_reasons=[]),
    )


# ---------------------------------------------------------------------------
# Prompt shape
# ---------------------------------------------------------------------------


def test_prompt_has_expected_structure(tmp_path: Path):
    feature = _make_feature()
    prompt = build_feature_prompt(
        feature=feature,
        target_path=tmp_path,
        charter_dir=tmp_path / "outputs",
        prior_feature_ids=[],
        project_id="myapp",
    )
    # Feature identity
    assert "f01-scaffold" in prompt
    assert "Scaffold" in prompt
    # Points to the charter artifacts on disk, does NOT inline them
    assert "target-project-contract.json" in prompt
    assert "verification-contract.json" in prompt
    assert "design-system.json" in prompt
    # Instructs skill usage
    assert "test-driven-development" in prompt
    assert "verification-before-completion" in prompt
    assert "systematic-debugging" in prompt
    # Codex protocol referenced (detail is in system prompt)
    assert "Codex" in prompt
    # Asset manifest section spliced in
    assert ".ncdev/assets-needed/f01-scaffold.json" in prompt


def test_prompt_mentions_prior_features(tmp_path: Path):
    prompt = build_feature_prompt(
        feature=_make_feature("f03-auth"),
        target_path=tmp_path,
        charter_dir=tmp_path / "outputs",
        prior_feature_ids=["f01-scaffold", "f02-db"],
        project_id="myapp",
    )
    assert "f01-scaffold, f02-db" in prompt


def test_prompt_handles_empty_acceptance_criteria(tmp_path: Path):
    feature = FeatureStep(
        feature_id="f01",
        title="X",
        description="Y",
        acceptance_criteria=[],
    )
    prompt = build_feature_prompt(
        feature=feature,
        target_path=tmp_path,
        charter_dir=tmp_path,
        prior_feature_ids=[],
        project_id="p",
    )
    assert "infer from description" in prompt


# ---------------------------------------------------------------------------
# Repair loop closes — prior verdict findings reach the rebuild prompt
# ---------------------------------------------------------------------------


def test_prior_verdict_in_pinned_run_reaches_builder_prompt(tmp_path: Path):
    """Regression: the factory pins a single run_dir and reuses it for
    every repair cycle. The prior attempt's verdict.json therefore lives
    at run_dir/steps/<fid>/verdict.json (NOT a sibling run). Before this
    fix, _load_prior_verdict_findings excluded the current run_dir, so the
    prior FAIL reasons never reached the rebuild prompt and the repair
    loop never closed.

    Simulate the repair attempt against the real pinned-run topology and
    assert the verbatim FAIL reason + repair guidance flow through into
    the composed builder prompt.
    """
    import json

    run_dir = tmp_path / "run"
    fid = "f03-auth"
    step_dir = run_dir / "steps" / fid
    step_dir.mkdir(parents=True)
    (step_dir / "verdict.json").write_text(
        json.dumps({
            "verdict": "FAIL",
            "reasons": ["missing 401 handling"],
            "repair_guidance": ["add auth guard"],
        }),
        encoding="utf-8",
    )

    # The function must read THIS pinned run's own prior verdict.
    findings = _load_prior_verdict_findings(
        feature_id=fid,
        current_run_dir=run_dir,
    )
    assert "missing 401 handling" in findings
    assert "add auth guard" in findings

    # And it must flow into the composed builder prompt at the existing
    # call site that consumed the old prior_*_findings argument.
    prompt = build_feature_prompt(
        feature=_make_feature(fid),
        target_path=tmp_path,
        charter_dir=tmp_path / "outputs",
        prior_feature_ids=[],
        project_id="myapp",
        prior_verdict_findings=findings,
    )
    assert "missing 401 handling" in prompt
    assert "add auth guard" in prompt


def test_prior_pass_in_pinned_run_yields_no_repair_note(tmp_path: Path):
    """A PASS verdict for this feature in the pinned run must NOT be
    surfaced as a repair note."""
    import json

    run_dir = tmp_path / "run"
    fid = "f03-auth"
    step_dir = run_dir / "steps" / fid
    step_dir.mkdir(parents=True)
    (step_dir / "verdict.json").write_text(
        json.dumps({"verdict": "PASS", "reasons": [], "repair_guidance": []}),
        encoding="utf-8",
    )

    findings = _load_prior_verdict_findings(feature_id=fid, current_run_dir=run_dir)
    assert findings == ""


# ---------------------------------------------------------------------------
# Executor happy path
# ---------------------------------------------------------------------------


def test_passed_when_session_succeeds_and_commits(tmp_path: Path):
    target = tmp_path / "app"
    target.mkdir()
    _init_git(target)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        # Simulate Claude making a commit + writing a manifest
        _seed_manifest(target, "f01-scaffold")
        (target / "app.py").write_text("print('hi')")
        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "feat(f01-scaffold): hi"],
                       cwd=str(target), check=True)
        return ClaudeSessionResult(
            success=True, final_text="done", exit_code=0,
            duration_seconds=2.0, total_cost_usd=0.42,
        )

    bundle = _make_bundle()
    with patch("ncdev.pipeline.claude_executor.run_ai_session", side_effect=fake_session):
        result = execute_feature_claude_driven(
            feature=_make_feature(),
            target_path=target,
            run_dir=tmp_path / "run",
            charter_bundle=bundle,
            prior_results=[],
            project_id="myapp",
        )

    assert result.status == StepStatus.PASSED
    assert result.commit_sha != ""
    assert "app.py" in result.files_created
    # Session metadata captured on disk
    assert (tmp_path / "run" / "steps" / "f01-scaffold" / "result.json").exists()
    assert (tmp_path / "run" / "steps" / "f01-scaffold" / "signals.json").exists()


# ---------------------------------------------------------------------------
# Build prompt — implementer discipline (post-TestCraftr-run hardening)
# ---------------------------------------------------------------------------


def test_prompt_demands_per_criterion_self_verification(tmp_path: Path):
    """The build prompt must require self-checking every acceptance
    criterion — implementers were stopping one criterion short."""
    prompt = build_feature_prompt(
        feature=_make_feature(), target_path=tmp_path,
        charter_dir=tmp_path / "outputs", prior_feature_ids=[],
        project_id="myapp",
    )
    assert "EVERY acceptance criterion" in prompt
    assert "one criterion short" in prompt


def test_prompt_warns_against_cosmetic_and_wrong_component_fixes(tmp_path: Path):
    """The build prompt must warn against cosmetic band-aids and fixing
    a component the QA probe never exercises — both observed failures."""
    prompt = build_feature_prompt(
        feature=_make_feature(), target_path=tmp_path,
        charter_dir=tmp_path / "outputs", prior_feature_ids=[],
        project_id="myapp",
    )
    assert "cosmetic change" in prompt.lower()
    assert "wrong component" in prompt.lower()
    assert "2xx" in prompt


# ---------------------------------------------------------------------------
# Executor failure paths
# ---------------------------------------------------------------------------


def test_failed_when_no_commit_made(tmp_path: Path):
    target = tmp_path / "app"
    target.mkdir()
    _init_git(target)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        # Claude session ran but did nothing
        return ClaudeSessionResult(
            success=True, final_text="I'm confused", exit_code=0,
        )

    bundle = _make_bundle()
    with patch("ncdev.pipeline.claude_executor.run_ai_session", side_effect=fake_session):
        result = execute_feature_claude_driven(
            feature=_make_feature(),
            target_path=target,
            run_dir=tmp_path / "run",
            charter_bundle=bundle,
            prior_results=[],
            project_id="myapp",
        )
    assert result.status == StepStatus.FAILED


def test_dirty_working_tree_committed_as_broken(tmp_path: Path):
    target = tmp_path / "app"
    target.mkdir()
    _init_git(target)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        # Claude made changes but didn't commit — orchestrator must
        # commit with [BROKEN] tag so the next feature has context.
        (target / "half_done.py").write_text("# TODO implement")
        return ClaudeSessionResult(success=False, final_text="gave up", exit_code=1)

    bundle = _make_bundle()
    with patch("ncdev.pipeline.claude_executor.run_ai_session", side_effect=fake_session):
        result = execute_feature_claude_driven(
            feature=_make_feature(),
            target_path=target,
            run_dir=tmp_path / "run",
            charter_bundle=bundle,
            prior_results=[],
            project_id="myapp",
        )

    assert result.status == StepStatus.FAILED
    # A [BROKEN] commit should exist
    log = subprocess.run(
        ["git", "log", "--oneline"],
        cwd=str(target), capture_output=True, text=True, check=True,
    )
    assert "[BROKEN]" in log.stdout


def test_ensure_git_identity_sets_fallback_when_none_configured(
    tmp_path: Path, monkeypatch
):
    """v4 defect #6: with no git identity, every commit (including the
    [BROKEN] recoverability commit) fails and the dirty tree poisons the
    next cycle. _ensure_git_identity must guarantee commits succeed.

    The host machine usually has a global git identity, which would mask
    the defect — so we null out global+system config for this test."""
    empty_global = tmp_path / "empty-gitconfig"
    empty_global.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty_global))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(empty_global))

    target = tmp_path / "noident"
    target.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=str(target), check=True)

    _ensure_git_identity(target)

    email = subprocess.run(
        ["git", "config", "user.email"],
        cwd=str(target), capture_output=True, text=True,
    )
    assert email.stdout.strip() == "ncdev@localhost"
    # A commit must now actually succeed.
    (target / "f.txt").write_text("x")
    subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
    commit = subprocess.run(
        ["git", "commit", "-m", "test"],
        cwd=str(target), capture_output=True, text=True,
    )
    assert commit.returncode == 0


def test_ensure_git_identity_leaves_existing_identity_untouched(tmp_path: Path):
    target = tmp_path / "hasident"
    target.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=str(target), check=True)
    subprocess.run(
        ["git", "config", "user.email", "real@dev.com"],
        cwd=str(target), check=True,
    )

    _ensure_git_identity(target)

    email = subprocess.run(
        ["git", "config", "user.email"],
        cwd=str(target), capture_output=True, text=True,
    )
    assert email.stdout.strip() == "real@dev.com"

