"""Tests for Phase E Claude-driven feature executor."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from unittest.mock import patch


from ncdev.claude_session import ClaudeSessionResult
from ncdev.pipeline.asset_manifest import save_feature_manifest
from ncdev.pipeline.claude_executor import (
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
    # Test-only bundle: empty test commands + no health URL so
    # _post_session_verification doesn't try to run real pytest / probe
    # a non-existent server in unit tests.
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


def test_missing_asset_manifest_causes_verification_failure(tmp_path: Path):
    target = tmp_path / "app"
    target.mkdir()
    _init_git(target)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        # Claude commits code that references an asset but writes no manifest.
        src = target / "src" / "App.tsx"
        src.parent.mkdir(parents=True)
        src.write_text('<img src="/images/missing.png" />')
        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): commit"],
                       cwd=str(target), check=True)
        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)

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

    # Session "succeeded" and committed, but verification blocks the pass
    assert result.status == StepStatus.FAILED
    reasons = result.verification.failure_reasons if result.verification else []
    assert any("manifest" in r.lower() for r in reasons)


def test_prohibited_patterns_block_pass(tmp_path: Path):
    target = tmp_path / "app"
    target.mkdir()
    _init_git(target)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        _seed_manifest(target, "f01-scaffold")
        (target / "bad.py").write_text("# TODO something")
        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): bad"],
                       cwd=str(target), check=True)
        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)

    bundle = _make_bundle()  # prohibited_patterns=["TODO"]
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
    assert any("prohibited" in r.lower() for r in result.verification.failure_reasons)


def test_legacy_prohibited_pattern_outside_touched_files_does_not_block_pass(tmp_path: Path):
    """Post-hoc verification must stay feature-local.

    A brownfield repo can contain an old TODO in some untouched file; that
    should not fail a new clean feature, because the pre-commit hook only
    guards staged content and the executor already scopes asset checks
    feature-locally for the same reason.
    """
    target = tmp_path / "app"
    target.mkdir()
    _init_git(target)

    # Legacy debt that predates this feature.
    (target / "legacy.py").write_text("# TODO historical debt\n")
    subprocess.run(["git", "add", "legacy.py"], cwd=str(target), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "feat(legacy): existing debt"],
                   cwd=str(target), check=True)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        _seed_manifest(target, "f01-scaffold")
        (target / "clean.py").write_text("x = 1\n")
        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): clean"],
                       cwd=str(target), check=True)
        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)

    bundle = _make_bundle()  # prohibited_patterns=["TODO"]
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


def test_verification_runs_backend_test_command_when_configured(tmp_path: Path):
    """New enforcement: backend_test_command actually runs, not just documented."""
    target = tmp_path / "app"
    target.mkdir()
    _init_git(target)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        _seed_manifest(target, "f01-scaffold")
        (target / "a.py").write_text("x=1")
        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): a"],
                       cwd=str(target), check=True)
        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)

    bundle = _make_bundle()
    # Contract declares a test command that deliberately fails
    bundle.verification.backend_test_command = "false"  # exit 1

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
    reasons = result.verification.failure_reasons if result.verification else []
    assert any("backend tests failed" in r for r in reasons)


def test_health_probe_polls_until_app_comes_up(monkeypatch):
    """Codex R3 blocker: probe was single-shot; now it must poll and
    accept the app when it comes up within boot_timeout_seconds."""
    from ncdev.pipeline import claude_executor as ex

    attempts = {"count": 0}

    class FakeResp:
        def __init__(self, status):
            self.status_code = status

    def fake_get(url, timeout=None):  # noqa: ARG001
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise ConnectionError("app not up yet")
        return FakeResp(200)

    import httpx
    monkeypatch.setattr(httpx, "get", fake_get)

    result = ex._probe_health(
        "http://localhost:99999/health",
        timeout=10,
        per_request_timeout=1,
        poll_interval=0.05,
    )
    assert result is True
    # Multiple attempts were made — polling worked
    assert attempts["count"] >= 3


def test_health_probe_returns_false_when_budget_exhausted(monkeypatch):
    """Apps that never come up within the budget fail cleanly."""
    from ncdev.pipeline import claude_executor as ex

    def fake_get(url, timeout=None):  # noqa: ARG001
        raise ConnectionError("never up")

    import httpx
    monkeypatch.setattr(httpx, "get", fake_get)

    start = time.time()
    result = ex._probe_health(
        "http://localhost:99999/health",
        timeout=1,
        per_request_timeout=1,
        poll_interval=0.1,
    )
    elapsed = time.time() - start
    assert result is False
    # Must actually respect the budget — not give up immediately, not
    # run 10x longer.
    assert 0.8 <= elapsed < 3.0, f"probe ran for {elapsed:.2f}s, expected ~1s"


def test_health_probe_early_success_returns_immediately(monkeypatch):
    """If the app is already up, don't waste the budget polling."""
    from ncdev.pipeline import claude_executor as ex

    class FakeResp:
        status_code = 200

    def fake_get(url, timeout=None):  # noqa: ARG001
        return FakeResp()

    import httpx
    monkeypatch.setattr(httpx, "get", fake_get)

    start = time.time()
    result = ex._probe_health(
        "http://localhost:99999/health",
        timeout=30,
        per_request_timeout=5,
    )
    elapsed = time.time() - start
    assert result is True
    assert elapsed < 1.0


def test_health_probe_failure_blocks_pass_when_url_set(tmp_path: Path):
    """Codex R2: boot probe was soft-signal only. When the contract
    declares backend_health_url, we must enforce it — the user put
    the URL there intentionally."""
    target = tmp_path / "app"
    target.mkdir()
    _init_git(target)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        _seed_manifest(target, "f01-scaffold")
        (target / "a.py").write_text("x=1")
        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): a"],
                       cwd=str(target), check=True)
        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)

    bundle = _make_bundle()
    # Set a URL that definitely doesn't respond
    bundle.verification.backend_health_url = "http://127.0.0.1:1/health"
    bundle.verification.boot_timeout_seconds = 1

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
    reasons = result.verification.failure_reasons
    assert any("health URL unreachable" in r for r in reasons)


def test_health_probe_not_run_when_url_empty(tmp_path: Path):
    """Empty URL means contract says 'no web boot check' — skip probe."""
    target = tmp_path / "app"
    target.mkdir()
    _init_git(target)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        _seed_manifest(target, "f01-scaffold")
        (target / "a.py").write_text("x=1")
        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): a"],
                       cwd=str(target), check=True)
        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)

    bundle = _make_bundle()  # backend_health_url="" by default in _make_bundle
    assert bundle.verification.backend_health_url == ""

    with patch("ncdev.pipeline.claude_executor.run_ai_session", side_effect=fake_session):
        result = execute_feature_claude_driven(
            feature=_make_feature(),
            target_path=target,
            run_dir=tmp_path / "run",
            charter_bundle=bundle,
            prior_results=[],
            project_id="myapp",
        )
    # No health-URL failure — probe was skipped
    assert result.status == StepStatus.PASSED


def test_verification_enforces_minimum_test_count(tmp_path: Path):
    target = tmp_path / "app"
    target.mkdir()
    _init_git(target)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        _seed_manifest(target, "f01-scaffold")
        (target / "foo.py").write_text("pass")
        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): notests"],
                       cwd=str(target), check=True)
        return ClaudeSessionResult(success=True, final_text="ok", exit_code=0)

    bundle = _make_bundle()
    bundle.verification.minimum_test_count = 1
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
    assert any("test file count" in r for r in result.verification.failure_reasons)


def test_verification_regex_prohibited_pattern_matches(tmp_path: Path):
    """Codex flagged: `r'except:\\s*pass'` was substring-checked and never
    fired. With regex enforcement it must match."""
    target = tmp_path / "app"
    target.mkdir()
    _init_git(target)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        _seed_manifest(target, "f01-scaffold")
        (target / "bad.py").write_text("try:\n    x = 1\nexcept:   pass\n")
        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): bad"],
                       cwd=str(target), check=True)
        return ClaudeSessionResult(success=True, final_text="ok", exit_code=0)

    bundle = _make_bundle()
    bundle.verification.prohibited_patterns = [r"except:\s*pass"]
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
    assert any("prohibited" in r.lower() for r in result.verification.failure_reasons)


def test_required_files_missing_blocks_pass(tmp_path: Path):
    target = tmp_path / "app"
    target.mkdir()
    _init_git(target)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        _seed_manifest(target, "f01-scaffold")
        (target / "thing.py").write_text("x=1")
        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): x"],
                       cwd=str(target), check=True)
        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)

    bundle = _make_bundle(required_files=["docker-compose.yml", "README.md"])
    with patch("ncdev.pipeline.claude_executor.run_ai_session", side_effect=fake_session):
        result = execute_feature_claude_driven(
            feature=_make_feature(),
            target_path=target,
            run_dir=tmp_path / "run",
            charter_bundle=bundle,
            prior_results=[],
            project_id="myapp",
        )
    # docker-compose.yml missing — verification fails, but README.md already exists from _init_git.
    assert result.status == StepStatus.FAILED
    reasons = result.verification.failure_reasons
    assert any("docker-compose.yml" in r for r in reasons)
