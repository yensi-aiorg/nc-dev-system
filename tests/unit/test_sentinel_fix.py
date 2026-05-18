from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ncdev.core.config import NCDevConfig, SentinelServiceConfig
from ncdev.core.models import (
    ErrorContext,
    ErrorDetail,
    ErrorFrequency,
    ErrorSeverity,
    ErrorSource,
    FixOutcome,
    SentinelFailureReport,
    SentinelTaskStatus,
    ServiceInfo,
)
from ncdev.core.sentinel_deploy import DeployResult, RollbackResult, StagingVerification
from ncdev.core.sentinel_safety import SentinelSafetyGate
from ncdev.sentinel_reproduce import ReproductionResult


def _report(*, service_name: str = "citebot", git_sha: str = "HEAD") -> SentinelFailureReport:
    now = datetime.now(timezone.utc)
    return SentinelFailureReport(
        report_id="rep-123",
        service=ServiceInfo(
            name=service_name,
            version="1.0",
            git_sha=git_sha,
            git_repo="git@example.com:org/citebot.git",
        ),
        source=ErrorSource.BACKEND,
        severity=ErrorSeverity.HIGH,
        error=ErrorDetail(
            error_type="NULL_POINTER",
            error_code="E500",
            message="NoneType has no attribute foo",
            file="app.py",
            line=1,
            function="fixed",
        ),
        frequency=ErrorFrequency(
            last_hour=5,
            last_24h=80,
            first_seen=now,
            affected_users=12,
        ),
        context=ErrorContext(),
        detected_at=now,
    )


def _write_report(tmp_path: Path, report: SentinelFailureReport) -> Path:
    path = tmp_path / "report.json"
    path.write_text(report.model_dump_json(), encoding="utf-8")
    return path


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(
        repo,
        "-c",
        "user.email=t@example.com",
        "-c",
        "user.name=Test User",
        "commit",
        "-q",
        "-m",
        message,
    )
    return _git(repo, "rev-parse", "HEAD")


def _source_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "source"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "app.py").write_text("def fixed():\n    return False\n", encoding="utf-8")
    sha = _commit(repo, "init")
    return repo, sha


def _config_with_service(repo: Path, *, callback_url: str = "") -> NCDevConfig:
    cfg = NCDevConfig()
    cfg.sentinel.services["citebot"] = SentinelServiceConfig(
        repo_path=str(repo),
        repo_clone_url="",
        language="python",
        test_commands={"backend": "python -m pytest -q"},
    )
    cfg.sentinel.callback.url = callback_url
    cfg.sentinel.callback.api_key = "test-key"
    cfg.sentinel.callback.retry_count = 1
    cfg.sentinel.callback.retry_delay_seconds = 0
    return cfg


def _deploy_config_with_service(repo: Path, *, callback_url: str = "") -> NCDevConfig:
    cfg = _config_with_service(repo, callback_url=callback_url)
    cfg.sentinel.services["citebot"].repo_clone_url = str(repo)
    cfg.sentinel.services["citebot"].deploy_command = "echo deploy"
    cfg.sentinel.services["citebot"].staging_url = "https://staging.example"
    return cfg


def _fake_bundle(monkeypatch: pytest.MonkeyPatch) -> None:
    from ncdev.core import engine

    monkeypatch.setattr(
        engine,
        "synthesize_charter_from_sentinel_report",
        lambda *args, **kwargs: object(),
    )


def _write_repro_test(repo: Path) -> None:
    tests_dir = repo / "tests"
    tests_dir.mkdir(exist_ok=True)
    (tests_dir / "test_repro.py").write_text(
        "from app import fixed\n\n\ndef test_repro():\n    assert fixed()\n",
        encoding="utf-8",
    )


def _patch_reproduce(monkeypatch: pytest.MonkeyPatch, *, reproduced: bool) -> None:
    from ncdev.core import engine

    def fake_reproduce(
        report: SentinelFailureReport,
        repo_dir: Path,
        **_: Any,
    ) -> ReproductionResult:
        if reproduced:
            _write_repro_test(repo_dir)
            return ReproductionResult(
                reproduced=True,
                test_path="tests/test_repro.py",
                reason="reproduced",
            )
        return ReproductionResult(reproduced=False, reason="not reproducible")

    monkeypatch.setattr(engine, "reproduce_failure", fake_reproduce)


def _patch_factory(
    monkeypatch: pytest.MonkeyPatch,
    *,
    fix_app: bool = True,
    extra_files: int = 0,
) -> list[Path]:
    from ncdev.core import engine

    calls: list[Path] = []

    def fake_factory(**kwargs: Any) -> SimpleNamespace:
        repo = kwargs["target_repo_path"]
        calls.append(repo)
        if fix_app:
            (repo / "app.py").write_text(
                "def fixed():\n    return True\n",
                encoding="utf-8",
            )
        for index in range(extra_files):
            (repo / f"extra_{index}.py").write_text("# extra\n", encoding="utf-8")
        _commit(repo, "fix sentinel report")
        return SimpleNamespace(cycles_run=1)

    monkeypatch.setattr(engine, "run_factory_with_bundle", fake_factory)
    return calls


def _run(
    tmp_path: Path,
    report_path: Path,
    cfg: NCDevConfig,
    *,
    gate: SentinelSafetyGate | None = None,
    dry_run: bool = False,
):
    from ncdev.core.engine import run_sentinel_fix

    workspace = tmp_path / "workspace"
    workspace.mkdir(exist_ok=True)
    return run_sentinel_fix(
        workspace=workspace,
        report_path=report_path,
        target_repo_path=tmp_path / "target",
        dry_run=dry_run,
        run_id="sentinel-test",
        config=cfg,
        safety_gate=gate,
    )


def _fix_result(state) -> dict[str, Any]:
    return state.metadata["fix_result"]


def test_unknown_service_is_blocked(tmp_path: Path) -> None:
    report_path = _write_report(tmp_path, _report(service_name="ghost"))
    state = _run(tmp_path, report_path, NCDevConfig())

    assert state.status == SentinelTaskStatus.BLOCKED
    assert _fix_result(state)["outcome"] == FixOutcome.BLOCKED.value
    assert "not registered" in _fix_result(state)["outcome_detail"]


def test_safety_preflight_block_is_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ncdev.core import engine

    repo, sha = _source_repo(tmp_path)
    report_path = _write_report(tmp_path, _report(git_sha=sha))
    cfg = _config_with_service(repo)
    gate = SentinelSafetyGate()
    gate.circuit_breaker.threshold = 1
    gate.circuit_breaker.record_failure("citebot")
    monkeypatch.setattr(
        engine,
        "_clone_and_checkout",
        lambda **kwargs: pytest.fail("clone should not be attempted"),
    )

    state = _run(tmp_path, report_path, cfg, gate=gate)

    assert state.status == SentinelTaskStatus.BLOCKED
    assert _fix_result(state)["outcome"] == FixOutcome.BLOCKED.value


def test_cannot_reproduce_halts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, sha = _source_repo(tmp_path)
    report_path = _write_report(tmp_path, _report(git_sha=sha))
    _patch_reproduce(monkeypatch, reproduced=False)
    _fake_bundle(monkeypatch)
    factory_calls = _patch_factory(monkeypatch)

    state = _run(tmp_path, report_path, _config_with_service(repo))

    assert _fix_result(state)["outcome"] == FixOutcome.CANNOT_REPRODUCE.value
    assert factory_calls == []


def test_repro_test_still_fails_is_fix_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, sha = _source_repo(tmp_path)
    report_path = _write_report(tmp_path, _report(git_sha=sha))
    _patch_reproduce(monkeypatch, reproduced=True)
    _fake_bundle(monkeypatch)
    _patch_factory(monkeypatch, fix_app=False)

    state = _run(tmp_path, report_path, _config_with_service(repo))

    assert _fix_result(state)["outcome"] == FixOutcome.FIX_FAILED.value


def test_over_scope_is_validation_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, sha = _source_repo(tmp_path)
    report_path = _write_report(tmp_path, _report(git_sha=sha))
    _patch_reproduce(monkeypatch, reproduced=True)
    _fake_bundle(monkeypatch)
    _patch_factory(monkeypatch, fix_app=True, extra_files=2)
    gate = SentinelSafetyGate()
    gate.scope_guard.max_files = 1

    state = _run(tmp_path, report_path, _config_with_service(repo), gate=gate)

    assert _fix_result(state)["outcome"] == FixOutcome.VALIDATION_FAILED.value
    assert "Too many files changed" in _fix_result(state)["outcome_detail"]


def test_happy_path_is_fixed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, sha = _source_repo(tmp_path)
    report_path = _write_report(tmp_path, _report(git_sha=sha))
    _patch_reproduce(monkeypatch, reproduced=True)
    _fake_bundle(monkeypatch)
    _patch_factory(monkeypatch, fix_app=True)
    gate = SentinelSafetyGate()
    record_calls: list[bool] = []

    def record_outcome(report: SentinelFailureReport, *, success: bool) -> None:
        record_calls.append(success)

    monkeypatch.setattr(gate, "record_outcome", record_outcome)

    state = _run(tmp_path, report_path, _config_with_service(repo), gate=gate)

    assert state.status == SentinelTaskStatus.PASSED
    assert _fix_result(state)["outcome"] == FixOutcome.FIXED.value
    assert record_calls == [True]
    result_path = Path(state.run_dir) / "outputs" / "fix-result.json"
    assert result_path.exists()


def test_fixed_locally_and_staging_verified_sets_pr_url(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ncdev.core import engine

    repo, sha = _source_repo(tmp_path)
    report_path = _write_report(tmp_path, _report(git_sha=sha))
    _patch_reproduce(monkeypatch, reproduced=True)
    _fake_bundle(monkeypatch)
    factory_calls = _patch_factory(monkeypatch, fix_app=True)

    def fake_deploy(
        repo_dir: Path,
        svc: SentinelServiceConfig,
        report: SentinelFailureReport,
        branch: str,
        *,
        commit_sha: str = "",
    ) -> DeployResult:
        assert repo_dir == factory_calls[0]
        assert branch == "sentinel/fix/rep-123"
        assert commit_sha
        return DeployResult(
            ok=True,
            pr_url="https://github.com/org/repo/pull/42",
            fix_branch=branch,
            merged=True,
            deployed=True,
            staging_sha_before="staging-before",
            staging_sha_after="staging-after",
        )

    monkeypatch.setattr(engine, "open_and_merge_to_staging", fake_deploy)
    monkeypatch.setattr(
        engine,
        "verify_on_staging",
        lambda *a, **k: StagingVerification(
            verified=True,
            staging_reachable=True,
            repro_test_passed=True,
        ),
    )
    monkeypatch.setattr(engine, "rollback_if_unsafe", lambda *a, **k: None)

    state = _run(tmp_path, report_path, _deploy_config_with_service(repo))
    result = _fix_result(state)

    assert result["outcome"] == FixOutcome.FIXED.value
    assert result["pr_url"] == "https://github.com/org/repo/pull/42"
    assert result["fix_branch"] == "sentinel/fix/rep-123"
    assert _git(factory_calls[0], "branch", "--show-current") == "sentinel/fix/rep-123"


def test_staging_verification_failure_rolls_back_and_validation_failed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ncdev.core import engine

    repo, sha = _source_repo(tmp_path)
    report_path = _write_report(tmp_path, _report(git_sha=sha))
    _patch_reproduce(monkeypatch, reproduced=True)
    _fake_bundle(monkeypatch)
    _patch_factory(monkeypatch, fix_app=True)
    gate = SentinelSafetyGate()
    record_calls: list[bool] = []
    rollback_calls: list[bool] = []

    monkeypatch.setattr(
        gate,
        "record_outcome",
        lambda report, *, success: record_calls.append(success),
    )
    monkeypatch.setattr(
        engine,
        "open_and_merge_to_staging",
        lambda *a, **k: DeployResult(
            ok=True,
            pr_url="https://github.com/org/repo/pull/43",
            fix_branch="sentinel/fix/rep-123",
            merged=True,
            deployed=True,
            staging_sha_before="staging-before",
        ),
    )
    monkeypatch.setattr(
        engine,
        "verify_on_staging",
        lambda *a, **k: StagingVerification(
            verified=False,
            staging_reachable=True,
            repro_test_passed=False,
            detail="repro failed on staging",
        ),
    )
    monkeypatch.setattr(
        engine,
        "rollback_if_unsafe",
        lambda *a, **k: rollback_calls.append(True) or RollbackResult(ok=True),
    )

    state = _run(tmp_path, report_path, _deploy_config_with_service(repo), gate=gate)
    result = _fix_result(state)

    assert result["outcome"] == FixOutcome.VALIDATION_FAILED.value
    assert result["pr_url"] == "https://github.com/org/repo/pull/43"
    assert "rollback ok=True" in result["outcome_detail"]
    assert rollback_calls == [True]
    assert record_calls == [False]


def test_missing_deploy_config_keeps_fixed_local_no_pr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ncdev.core import engine

    repo, sha = _source_repo(tmp_path)
    report_path = _write_report(tmp_path, _report(git_sha=sha))
    _patch_reproduce(monkeypatch, reproduced=True)
    _fake_bundle(monkeypatch)
    _patch_factory(monkeypatch, fix_app=True)
    monkeypatch.setattr(
        engine,
        "open_and_merge_to_staging",
        lambda *a, **k: pytest.fail("deploy should not be attempted"),
    )

    state = _run(tmp_path, report_path, _config_with_service(repo))
    result = _fix_result(state)

    assert result["outcome"] == FixOutcome.FIXED.value
    assert result["pr_url"] is None
    assert result["fix_branch"] == "sentinel/fix/rep-123"
    assert "skipped" in result["outcome_detail"]


def test_callback_fires_once_with_final_post_deploy_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ncdev.core import engine

    repo, sha = _source_repo(tmp_path)
    report_path = _write_report(tmp_path, _report(git_sha=sha))
    _patch_reproduce(monkeypatch, reproduced=True)
    _fake_bundle(monkeypatch)
    _patch_factory(monkeypatch, fix_app=True)
    order: list[str] = []
    sent_results = []

    monkeypatch.setattr(
        engine,
        "open_and_merge_to_staging",
        lambda *a, **k: order.append("deploy")
        or DeployResult(
            ok=True,
            pr_url="https://github.com/org/repo/pull/44",
            fix_branch="sentinel/fix/rep-123",
            merged=True,
            deployed=True,
            staging_sha_before="staging-before",
        ),
    )
    monkeypatch.setattr(
        engine,
        "verify_on_staging",
        lambda *a, **k: order.append("verify")
        or StagingVerification(verified=True, staging_reachable=True),
    )
    monkeypatch.setattr(engine, "rollback_if_unsafe", lambda *a, **k: None)

    def fake_send_fix_result(**kwargs: Any) -> bool:
        order.append("callback")
        sent_results.append(kwargs["result"])
        return True

    monkeypatch.setattr(engine, "send_fix_result", fake_send_fix_result)

    state = _run(
        tmp_path,
        report_path,
        _deploy_config_with_service(repo, callback_url="https://sentinel.example/cb"),
    )

    assert _fix_result(state)["outcome"] == FixOutcome.FIXED.value
    assert len(sent_results) == 1
    assert sent_results[0].pr_url == "https://github.com/org/repo/pull/44"
    assert order == ["deploy", "verify", "callback"]


def test_dry_run_short_circuits(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ncdev.core import engine

    report_path = _write_report(tmp_path, _report())
    cfg = NCDevConfig()
    monkeypatch.setattr(
        engine,
        "_clone_and_checkout",
        lambda **kwargs: pytest.fail("clone should not be attempted"),
    )

    state = _run(tmp_path, report_path, cfg, dry_run=True)

    assert state.status == SentinelTaskStatus.PASSED
    assert "fix_result" not in state.metadata


def test_callback_invoked_when_url_configured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ncdev.core import engine

    repo, sha = _source_repo(tmp_path)
    report_path = _write_report(tmp_path, _report(git_sha=sha))
    _patch_reproduce(monkeypatch, reproduced=True)
    _fake_bundle(monkeypatch)
    _patch_factory(monkeypatch, fix_app=True)
    sent_results = []

    def fake_send_fix_result(**kwargs: Any) -> bool:
        sent_results.append(kwargs["result"])
        assert kwargs["callback_url"] == "https://sentinel.example/callback"
        assert kwargs["api_key"] == "test-key"
        return True

    monkeypatch.setattr(engine, "send_fix_result", fake_send_fix_result)

    state = _run(
        tmp_path,
        report_path,
        _config_with_service(repo, callback_url="https://sentinel.example/callback"),
    )

    assert _fix_result(state)["outcome"] == FixOutcome.FIXED.value
    assert len(sent_results) == 1
    assert sent_results[0].outcome == FixOutcome.FIXED
