"""Tests for the mode-aware AI session dispatcher."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from ncdev import ai_session
from ncdev.ai_session import (
    MODE_IMPLEMENTER,
    MODE_ORCHESTRATOR,
    run_ai_session,
    run_codex_session,
)
from ncdev.claude_session import ClaudeSessionResult
from ncdev.v2.config import NCDevV2Config


# ---------------------------------------------------------------------------
# Mode tables
# ---------------------------------------------------------------------------


def test_mode_tables_cover_every_preset():
    """If we add a new mode preset, these maps must have entries for it."""
    from ncdev.v2.config import MODE_PRESETS
    expected = set(MODE_PRESETS.keys())
    assert set(MODE_ORCHESTRATOR.keys()) == expected
    assert set(MODE_IMPLEMENTER.keys()) == expected


def test_claude_plan_codex_build_orchestrator_is_claude_implementer_is_codex():
    assert MODE_ORCHESTRATOR["claude_plan_codex_build"] == "claude"
    assert MODE_IMPLEMENTER["claude_plan_codex_build"] == "codex"


def test_codex_only_has_codex_for_both():
    assert MODE_ORCHESTRATOR["codex_only"] == "codex"
    assert MODE_IMPLEMENTER["codex_only"] == "codex"


def test_claude_only_has_claude_for_both():
    assert MODE_ORCHESTRATOR["claude_only"] == "claude"
    assert MODE_IMPLEMENTER["claude_only"] == "claude"


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def _claude_result() -> ClaudeSessionResult:
    return ClaudeSessionResult(success=True, final_text="claude did it", exit_code=0)


def _codex_result() -> ClaudeSessionResult:
    return ClaudeSessionResult(success=True, final_text="codex did it", exit_code=0)


def test_claude_plan_codex_build_routes_to_claude_with_protocol(tmp_path: Path):
    cfg = NCDevV2Config(mode="claude_plan_codex_build")
    captured: dict = {}

    def fake_claude(prompt, **kwargs):
        captured.update(kwargs)
        return _claude_result()

    with patch("ncdev.ai_session.run_claude_session", side_effect=fake_claude):
        result = run_ai_session("do it", cwd=tmp_path, config=cfg)

    assert result.final_text == "claude did it"
    # Codex protocol MUST be injected — this is the whole point of
    # claude_plan_codex_build
    assert captured["include_codex_protocol"] is True


def test_claude_only_routes_to_claude_without_protocol(tmp_path: Path):
    cfg = NCDevV2Config(mode="claude_only")
    captured: dict = {}

    def fake_claude(prompt, **kwargs):
        captured.update(kwargs)
        return _claude_result()

    with patch("ncdev.ai_session.run_claude_session", side_effect=fake_claude):
        run_ai_session("do it", cwd=tmp_path, config=cfg)

    # No Codex delegation in claude_only mode
    assert captured["include_codex_protocol"] is False


def test_codex_only_routes_to_codex(tmp_path: Path):
    cfg = NCDevV2Config(mode="codex_only")
    captured: dict = {}

    def fake_codex(prompt, **kwargs):
        captured["prompt"] = prompt
        captured.update(kwargs)
        return _codex_result()

    with patch("ncdev.ai_session.run_codex_session", side_effect=fake_codex):
        result = run_ai_session("do it", cwd=tmp_path, config=cfg)

    assert result.final_text == "codex did it"
    assert "prompt" in captured


def test_codex_only_does_not_call_claude(tmp_path: Path):
    """codex_only must not spawn a Claude session under any circumstances."""
    cfg = NCDevV2Config(mode="codex_only")

    def fake_claude(*a, **k):  # noqa: ARG001
        raise AssertionError("Claude must not be invoked in codex_only mode")

    with patch("ncdev.ai_session.run_claude_session", side_effect=fake_claude):
        with patch("ncdev.ai_session.run_codex_session", return_value=_codex_result()):
            run_ai_session("x", cwd=tmp_path, config=cfg)


def test_claude_only_does_not_call_codex(tmp_path: Path):
    cfg = NCDevV2Config(mode="claude_only")

    def fake_codex(*a, **k):  # noqa: ARG001
        raise AssertionError("Codex session must not be invoked in claude_only mode")

    with patch("ncdev.ai_session.run_codex_session", side_effect=fake_codex):
        with patch("ncdev.ai_session.run_claude_session", return_value=_claude_result()):
            run_ai_session("x", cwd=tmp_path, config=cfg)


def test_openrouter_raises_not_implemented(tmp_path: Path):
    cfg = NCDevV2Config(mode="openrouter")
    with pytest.raises(NotImplementedError, match="API-only"):
        run_ai_session("x", cwd=tmp_path, config=cfg)


def test_custom_mode_defaults_to_claude(tmp_path: Path):
    cfg = NCDevV2Config(mode="custom")
    captured: dict = {}

    def fake_claude(prompt, **kwargs):
        captured.update(kwargs)
        return _claude_result()

    with patch("ncdev.ai_session.run_claude_session", side_effect=fake_claude):
        run_ai_session("x", cwd=tmp_path, config=cfg)
    # custom → claude orchestrator, codex implementer → protocol on
    assert captured["include_codex_protocol"] is True


def test_explicit_include_codex_protocol_wins_over_mode_default(tmp_path: Path):
    """Caller can override the mode-inferred default."""
    cfg = NCDevV2Config(mode="claude_plan_codex_build")  # would default True
    captured: dict = {}

    def fake_claude(prompt, **kwargs):
        captured.update(kwargs)
        return _claude_result()

    with patch("ncdev.ai_session.run_claude_session", side_effect=fake_claude):
        run_ai_session(
            "x", cwd=tmp_path, config=cfg, include_codex_protocol=False,
        )
    assert captured["include_codex_protocol"] is False


# ---------------------------------------------------------------------------
# run_codex_session
# ---------------------------------------------------------------------------


def test_run_codex_session_errors_when_cli_missing(tmp_path: Path):
    with patch("ncdev.ai_session.shutil.which", return_value=None):
        result = run_codex_session("task", cwd=tmp_path)
    assert result.success is False
    assert "codex CLI not found" in (result.error or "")


def test_run_codex_session_builds_correct_argv(tmp_path: Path):
    captured: dict = {}

    class FakeProc:
        returncode = 0
        stdout = "codex output"
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return FakeProc()

    with patch("ncdev.ai_session.shutil.which", return_value="/usr/bin/codex"):
        with patch("ncdev.ai_session.subprocess.run", side_effect=fake_run):
            result = run_codex_session("build feature X", cwd=tmp_path)

    cmd = captured["cmd"]
    assert cmd[0] == "codex"
    assert cmd[1] == "exec"
    assert "--full-auto" in cmd
    assert "--sandbox" in cmd
    assert "danger-full-access" in cmd
    # Prompt is last arg
    assert "build feature X" in cmd[-1]
    assert "codex_only mode" in cmd[-1]
    assert result.success is True


def test_run_codex_session_honours_timeout(tmp_path: Path):
    import subprocess as sp

    def fake_run(cmd, **kwargs):
        raise sp.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout", 0))

    with patch("ncdev.ai_session.shutil.which", return_value="/usr/bin/codex"):
        with patch("ncdev.ai_session.subprocess.run", side_effect=fake_run):
            result = run_codex_session("x", cwd=tmp_path, timeout=5)
    assert result.success is False
    assert "timed out" in (result.error or "")


def test_run_codex_session_writes_log(tmp_path: Path):
    class FakeProc:
        returncode = 0
        stdout = "the work"
        stderr = ""

    log_path = tmp_path / "logs" / "codex.log"

    with patch("ncdev.ai_session.shutil.which", return_value="/usr/bin/codex"):
        with patch("ncdev.ai_session.subprocess.run", return_value=FakeProc()):
            run_codex_session("x", cwd=tmp_path, log_path=log_path)

    assert log_path.exists()
    body = log_path.read_text(encoding="utf-8")
    assert "RUNNER: codex" in body
    assert "the work" in body
