import subprocess
from datetime import datetime, timezone
from pathlib import Path

from ncdev.claude_session import ClaudeSessionResult
from ncdev.core.models import (
    ErrorContext,
    ErrorDetail,
    ErrorFrequency,
    ErrorSeverity,
    ErrorSource,
    SentinelFailureReport,
    ServiceInfo,
)
from ncdev.sentinel_reproduce import ReproductionResult, reproduce_failure


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "svc"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "app.py").write_text("def parse(x):\n    return x.foo\n", encoding="utf-8")
    (repo / "tests").mkdir()
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init"],
        cwd=repo,
        check=True,
    )
    return repo


def _report() -> SentinelFailureReport:
    return SentinelFailureReport(
        report_id="rep-1",
        service=ServiceInfo(
            name="svc",
            version="1",
            git_sha="abc",
            git_repo="git@github.com:o/svc.git",
        ),
        source=ErrorSource.BACKEND,
        severity=ErrorSeverity.HIGH,
        error=ErrorDetail(
            error_type="ATTR_ERROR",
            error_code="E1",
            message="NoneType has no attribute foo",
            file="app.py",
            line=2,
            function="parse",
        ),
        frequency=ErrorFrequency(
            last_hour=1,
            last_24h=1,
            first_seen=datetime.now(timezone.utc),
        ),
        context=ErrorContext(),
        detected_at=datetime.now(timezone.utc),
    )


def test_reproduced_true_when_session_writes_failing_test(monkeypatch, tmp_path):
    repo = _repo(tmp_path)
    from ncdev import sentinel_reproduce as sr

    def fake_session(prompt, **kwargs):
        # Simulate the session writing a FAILING test.
        (repo / "tests" / "test_repro.py").write_text(
            "def test_repro():\n    assert False, 'repro'\n",
            encoding="utf-8",
        )
        return ClaudeSessionResult(success=True, final_text="wrote test", exit_code=0)

    monkeypatch.setattr(sr, "run_ai_session", fake_session)
    result = reproduce_failure(_report(), repo)
    assert isinstance(result, ReproductionResult)
    assert result.reproduced is True
    assert "test_repro.py" in result.test_path
    assert "repro" in result.test_output


def test_reproduced_false_when_test_passes(monkeypatch, tmp_path):
    repo = _repo(tmp_path)
    from ncdev import sentinel_reproduce as sr

    def fake_session(prompt, **kwargs):
        # Session writes a PASSING test -- that hasn't reproduced anything.
        (repo / "tests" / "test_repro.py").write_text(
            "def test_repro():\n    assert True\n",
            encoding="utf-8",
        )
        return ClaudeSessionResult(success=True, final_text="wrote test", exit_code=0)

    monkeypatch.setattr(sr, "run_ai_session", fake_session)
    result = reproduce_failure(_report(), repo)
    assert result.reproduced is False
    assert "pass" in result.reason.lower()


def test_reproduced_false_when_no_test_written(monkeypatch, tmp_path):
    repo = _repo(tmp_path)
    from ncdev import sentinel_reproduce as sr

    def fake_session(prompt, **kwargs):
        return ClaudeSessionResult(success=True, final_text="did nothing", exit_code=0)

    monkeypatch.setattr(sr, "run_ai_session", fake_session)
    result = reproduce_failure(_report(), repo)
    assert result.reproduced is False
    assert "no" in result.reason.lower() and "test" in result.reason.lower()


def test_reproduced_false_when_session_fails(monkeypatch, tmp_path):
    repo = _repo(tmp_path)
    from ncdev import sentinel_reproduce as sr

    def fake_session(prompt, **kwargs):
        return ClaudeSessionResult(success=False, final_text="", exit_code=1)

    monkeypatch.setattr(sr, "run_ai_session", fake_session)
    result = reproduce_failure(_report(), repo)
    assert result.reproduced is False
