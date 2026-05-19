from pathlib import Path

import pytest

from ncdev import claude_session
from ncdev.claude_session import ClaudeSessionResult


@pytest.fixture(autouse=True)
def _isolate_ledger(monkeypatch, tmp_path):
    """Every test in this file resolves against an empty ledger, so model
    resolution is deterministic regardless of any real ~/.ncdev state.
    Also makes the `claude` binary appear present so seam tests do not
    depend on the host PATH (the seam replaces the real spawn anyway)."""
    monkeypatch.setattr("ncdev.core.capability_ledger.Path.home", lambda: tmp_path)
    monkeypatch.setattr(claude_session.shutil, "which", lambda _: "/usr/bin/x")


def test_model_rejection_triggers_one_fallback_retry():
    calls = []

    def fake_executor(model):
        calls.append(model)
        if len(calls) == 1:  # first model (opus) rejected
            return ClaudeSessionResult(
                success=False, final_text="", exit_code=1,
                error="API error: you do not have access to this model",
            )
        return ClaudeSessionResult(success=True, final_text="ok", exit_code=0)

    result = claude_session.run_claude_session(
        "hi", cwd=Path("."), _session_executor=fake_executor,
    )
    assert result.success is True
    assert calls == ["opus", "sonnet"]


def test_no_retry_when_session_succeeds():
    calls = []

    def fake_executor(model):
        calls.append(model)
        return ClaudeSessionResult(success=True, final_text="ok", exit_code=0)

    claude_session.run_claude_session("hi", cwd=Path("."), _session_executor=fake_executor)
    assert calls == ["opus"]


def test_no_retry_for_explicit_pin():
    calls = []

    def fake_executor(model):
        calls.append(model)
        return ClaudeSessionResult(
            success=False, final_text="", exit_code=1, error="model not found",
        )

    claude_session.run_claude_session(
        "hi", cwd=Path("."), model="opus", _session_executor=fake_executor,
    )
    assert calls == ["opus"]


def test_no_retry_for_non_model_failure():
    calls = []

    def fake_executor(model):
        calls.append(model)
        return ClaudeSessionResult(
            success=False, final_text="", exit_code=1, error="timed out after 600s",
        )

    claude_session.run_claude_session("hi", cwd=Path("."), _session_executor=fake_executor)
    assert calls == ["opus"]
