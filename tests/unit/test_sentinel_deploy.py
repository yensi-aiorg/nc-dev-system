from datetime import datetime, timezone

from ncdev.core.config import SentinelServiceConfig
from ncdev.core.models import (
    ErrorContext,
    ErrorDetail,
    ErrorFrequency,
    ErrorSeverity,
    ErrorSource,
    SentinelFailureReport,
    ServiceInfo,
)
from ncdev.core.sentinel_deploy import (
    DeployResult,
    build_pr_body,
    open_and_merge_to_staging,
)


def _report():
    return SentinelFailureReport(
        report_id="rep-9",
        service=ServiceInfo(
            name="svc",
            version="1",
            git_sha="abc",
            git_repo="git@github.com:o/svc.git",
        ),
        source=ErrorSource.BACKEND,
        severity=ErrorSeverity.HIGH,
        error=ErrorDetail(
            error_type="ERR",
            error_code="E1",
            message="boom in handler",
            file="app.py",
            line=10,
        ),
        frequency=ErrorFrequency(
            last_hour=1,
            last_24h=1,
            first_seen=datetime.now(timezone.utc),
        ),
        context=ErrorContext(),
        detected_at=datetime.now(timezone.utc),
    )


def _full_service(**kw):
    base = dict(
        repo_path="/srv/svc",
        repo_clone_url="git@github.com:o/svc.git",
        staging_branch="staging",
        deploy_command="echo deployed",
        staging_url="http://staging",
        test_commands={"backend": "pytest"},
        pr_labels=["sentinel-auto"],
    )
    base.update(kw)
    return SentinelServiceConfig(**base)


def test_missing_deploy_config_fails_loud_without_touching_git(tmp_path, monkeypatch):
    from ncdev.core import sentinel_deploy as sd

    touched = []
    monkeypatch.setattr(sd, "_run_git", lambda *a, **k: touched.append(1) or (0, "", ""))
    monkeypatch.setattr(sd, "_run_gh", lambda *a, **k: touched.append(1) or (0, "", ""))
    svc = SentinelServiceConfig()
    result = open_and_merge_to_staging(tmp_path, svc, _report(), "sentinel/fix/rep-9")
    assert result.ok is False
    assert "deploy_command" in result.error
    assert touched == []


def test_happy_path_pushes_pr_merges_deploys(tmp_path, monkeypatch):
    from ncdev.core import sentinel_deploy as sd

    calls = []

    def fake_git(args, **kw):
        calls.append(("git", args))
        if args[:2] == ["rev-parse", "origin/staging"]:
            return (0, "staging-sha-1\n", "")
        return (0, "", "")

    def fake_gh(args, **kw):
        calls.append(("gh", args))
        if args[0] == "pr" and args[1] == "create":
            return (0, "https://github.com/o/svc/pull/42\n", "")
        return (0, "", "")

    deploy_calls = []
    monkeypatch.setattr(sd, "_run_git", fake_git)
    monkeypatch.setattr(sd, "_run_gh", fake_gh)
    monkeypatch.setattr(
        sd,
        "_run_deploy_command",
        lambda cmd, cwd: deploy_calls.append(cmd) or (0, "deployed", ""),
    )
    result = open_and_merge_to_staging(
        tmp_path,
        _full_service(),
        _report(),
        "sentinel/fix/rep-9",
    )
    assert isinstance(result, DeployResult)
    assert result.ok is True
    assert result.pr_url == "https://github.com/o/svc/pull/42"
    assert result.merged is True
    assert result.deployed is True
    assert deploy_calls == ["echo deployed"]


def test_push_failure_aborts_before_pr(tmp_path, monkeypatch):
    from ncdev.core import sentinel_deploy as sd

    def fake_git(args, **kw):
        if args[0] == "push":
            return (1, "", "permission denied")
        return (0, "", "")

    gh_called = []
    monkeypatch.setattr(sd, "_run_git", fake_git)
    monkeypatch.setattr(sd, "_run_gh", lambda *a, **k: gh_called.append(1) or (0, "", ""))
    result = open_and_merge_to_staging(
        tmp_path,
        _full_service(),
        _report(),
        "sentinel/fix/rep-9",
    )
    assert result.ok is False
    assert "push" in result.error.lower()
    assert gh_called == []


def test_deploy_command_failure_keeps_merged_true(tmp_path, monkeypatch):
    from ncdev.core import sentinel_deploy as sd

    def fake_git(args, **kw):
        if args[:2] == ["rev-parse", "origin/staging"]:
            return (0, "sha\n", "")
        return (0, "", "")

    def fake_gh(args, **kw):
        if args[:2] == ["pr", "create"]:
            return (0, "https://github.com/o/svc/pull/7\n", "")
        return (0, "", "")

    monkeypatch.setattr(sd, "_run_git", fake_git)
    monkeypatch.setattr(sd, "_run_gh", fake_gh)
    monkeypatch.setattr(sd, "_run_deploy_command", lambda cmd, cwd: (1, "", "deploy blew up"))
    result = open_and_merge_to_staging(
        tmp_path,
        _full_service(),
        _report(),
        "sentinel/fix/rep-9",
    )
    assert result.merged is True
    assert result.deployed is False
    assert result.ok is False


def test_build_pr_body_includes_error_detail():
    body = build_pr_body(_report(), commit_sha="deadbeef")
    assert "boom in handler" in body
    assert "rep-9" in body
    assert "app.py" in body
