"""Tests for the mode-aware AI session dispatcher."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from ncdev.ai_session import (
    MODE_IMPLEMENTER,
    MODE_ORCHESTRATOR,
    run_ai_session,
    run_codex_session,
)
from ncdev.claude_session import ClaudeSessionResult
from ncdev.core.config import NCDevConfig


@pytest.fixture(autouse=True)
def _skip_codex_version_probe(monkeypatch):
    from ncdev.core import capability_probe

    monkeypatch.setattr(capability_probe, "_run_version", lambda _: "")
    # These tests fake subprocess.Popen globally; the capability probe's
    # subprocess.run-based helpers must be stubbed too, or they break on
    # the faked Popen. Keep the probe hermetic.
    monkeypatch.setattr(capability_probe, "_run_help", lambda _: "")


# ---------------------------------------------------------------------------
# Mode tables
# ---------------------------------------------------------------------------


def test_mode_tables_cover_every_preset_except_custom():
    """Every non-custom preset must have an orchestrator/implementer
    entry. 'custom' is deliberately absent — it's resolved from the
    user's hand-tuned routing via _resolve_custom_providers."""
    from ncdev.core.config import MODE_PRESETS
    expected = set(MODE_PRESETS.keys()) - {"custom"}
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
    cfg = NCDevConfig(mode="claude_plan_codex_build")
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
    cfg = NCDevConfig(mode="claude_only")
    captured: dict = {}

    def fake_claude(prompt, **kwargs):
        captured.update(kwargs)
        return _claude_result()

    with patch("ncdev.ai_session.run_claude_session", side_effect=fake_claude):
        run_ai_session("do it", cwd=tmp_path, config=cfg)

    # No Codex delegation in claude_only mode
    assert captured["include_codex_protocol"] is False


def test_codex_only_routes_to_codex(tmp_path: Path):
    cfg = NCDevConfig(mode="codex_only")
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
    cfg = NCDevConfig(mode="codex_only")

    def fake_claude(*a, **k):  # noqa: ARG001
        raise AssertionError("Claude must not be invoked in codex_only mode")

    with patch("ncdev.ai_session.run_claude_session", side_effect=fake_claude):
        with patch("ncdev.ai_session.run_codex_session", return_value=_codex_result()):
            run_ai_session("x", cwd=tmp_path, config=cfg)


def test_claude_only_does_not_call_codex(tmp_path: Path):
    cfg = NCDevConfig(mode="claude_only")

    def fake_codex(*a, **k):  # noqa: ARG001
        raise AssertionError("Codex session must not be invoked in claude_only mode")

    with patch("ncdev.ai_session.run_codex_session", side_effect=fake_codex):
        with patch("ncdev.ai_session.run_claude_session", return_value=_claude_result()):
            run_ai_session("x", cwd=tmp_path, config=cfg)


def test_openrouter_raises_not_implemented(tmp_path: Path):
    cfg = NCDevConfig(mode="openrouter")
    with pytest.raises(NotImplementedError, match="API-only"):
        run_ai_session("x", cwd=tmp_path, config=cfg)


def test_custom_mode_honours_hand_tuned_routing_claude_everywhere(tmp_path: Path):
    """Codex R2 flagged: custom was hardcoded to claude+codex, ignoring
    the user's routing: block. Verify: user routes everything to
    anthropic_claude_code → Claude orchestrator, Claude implementer,
    protocol OFF (Claude isn't delegating)."""
    cfg = NCDevConfig(
        mode="custom",
        routing={
            "review": ["anthropic_claude_code"],
            "implementation": ["anthropic_claude_code"],
        },
    )
    captured: dict = {}

    def fake_claude(prompt, **kwargs):
        captured.update(kwargs)
        return _claude_result()

    with patch("ncdev.ai_session.run_claude_session", side_effect=fake_claude):
        run_ai_session("x", cwd=tmp_path, config=cfg)

    # orchestrator=claude, implementer=claude → NO codex protocol
    assert captured["include_codex_protocol"] is False


def test_custom_mode_routes_to_codex_when_user_requests_it(tmp_path: Path):
    """User flips everything to codex via custom — must actually route
    to codex runner, not fall back to Claude."""
    cfg = NCDevConfig(
        mode="custom",
        routing={
            "review": ["openai_codex"],
            "implementation": ["openai_codex"],
        },
    )
    called = {"claude": False, "codex": False}

    def fake_claude(*a, **k):  # noqa: ARG001
        called["claude"] = True
        return _claude_result()

    def fake_codex(*a, **k):  # noqa: ARG001
        called["codex"] = True
        return _codex_result()

    with patch("ncdev.ai_session.run_claude_session", side_effect=fake_claude):
        with patch("ncdev.ai_session.run_codex_session", side_effect=fake_codex):
            run_ai_session("x", cwd=tmp_path, config=cfg)

    assert called["codex"] is True, "custom mode must route to codex when user routes review+impl to codex"
    assert called["claude"] is False


def test_custom_mode_unknown_provider_returns_structured_failure(tmp_path: Path):
    """Codex R3: an unknown provider name in routing used to raise
    ValueError uncaught mid-run. Now must surface as a structured
    ClaudeSessionResult with success=False + actionable error."""
    cfg = NCDevConfig(
        mode="custom",
        routing={
            "review": ["something_weird"],
            "implementation": ["openai_codex"],
        },
    )
    result = run_ai_session("x", cwd=tmp_path, config=cfg)
    assert result.success is False
    assert result.exit_code == -1
    assert "custom mode" in (result.error or "")
    assert "something_weird" in (result.error or "")
    # Must not have spawned any runner
    assert result.final_text == ""


def test_custom_mode_plan_codex_build_like_routing(tmp_path: Path):
    """User configures custom to mimic claude_plan_codex_build: review=
    claude, implementation=codex → Claude orch WITH codex protocol."""
    cfg = NCDevConfig(
        mode="custom",
        routing={
            "review": ["anthropic_claude_code"],
            "implementation": ["openai_codex"],
        },
    )
    captured: dict = {}

    def fake_claude(prompt, **kwargs):
        captured.update(kwargs)
        return _claude_result()

    with patch("ncdev.ai_session.run_claude_session", side_effect=fake_claude):
        run_ai_session("x", cwd=tmp_path, config=cfg)

    # Claude orchestrates, Codex implements → protocol ON
    assert captured["include_codex_protocol"] is True


def test_explicit_include_codex_protocol_wins_over_mode_default(tmp_path: Path):
    """Caller can override the mode-inferred default."""
    cfg = NCDevConfig(mode="claude_plan_codex_build")  # would default True
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


class _FakeCodexProc:
    """Minimal Popen stand-in: stdout + stderr iterable, immediate exit."""

    _next_pid = 9000

    def __init__(self, stdout: str = "codex output\n", stderr: str = "", returncode: int = 0):
        _FakeCodexProc._next_pid += 1
        self.pid = _FakeCodexProc._next_pid
        self.stdout = iter([stdout] if stdout else [])
        self.stderr = iter([stderr] if stderr else [])
        self.returncode = returncode

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):  # noqa: ARG002
        return self.returncode

    def kill(self):
        pass

    def terminate(self):
        pass


def test_run_codex_session_builds_correct_argv(tmp_path: Path):
    captured: dict = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return _FakeCodexProc(stdout="codex output\n")

    with patch("ncdev.ai_session.shutil.which", return_value="/usr/bin/codex"):
        with patch("ncdev.ai_session.subprocess.Popen", side_effect=fake_popen):
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
    assert "codex output" in result.final_text


def test_run_codex_session_writes_log(tmp_path: Path):
    def fake_popen(cmd, **kwargs):  # noqa: ARG001
        return _FakeCodexProc(stdout="the work\n", stderr="")

    log_path = tmp_path / "logs" / "codex.log"

    with patch("ncdev.ai_session.shutil.which", return_value="/usr/bin/codex"):
        with patch("ncdev.ai_session.subprocess.Popen", side_effect=fake_popen):
            run_codex_session("x", cwd=tmp_path, log_path=log_path)

    assert log_path.exists()
    body = log_path.read_text(encoding="utf-8")
    assert "RUNNER: codex" in body
    assert "the work" in body


def test_run_codex_session_truncates_huge_stream(tmp_path: Path):
    """Codex R2 flagged: unbounded capture_output can blow RAM.
    Verify the tail-buffer caps memory for chatty runs."""
    huge = "x" * 1024   # 1KB per line
    lines = [huge + "\n"] * 200  # 200 KB total

    class HugeProc(_FakeCodexProc):
        def __init__(self):
            super().__init__(stdout="", returncode=0)
            self.stdout = iter(lines)

    with patch("ncdev.ai_session.shutil.which", return_value="/usr/bin/codex"):
        with patch("ncdev.ai_session.subprocess.Popen", side_effect=lambda *a, **k: HugeProc()):
            # Cap at 50 KB — result must be capped, no crash
            result = run_codex_session(
                "x", cwd=tmp_path, max_bytes_per_stream=50_000,
            )

    assert result.success is True
    assert len(result.final_text.encode("utf-8")) <= 60_000  # some tolerance


def test_tail_buffer_preserves_tail_of_oversized_chunk():
    """Codex R3 flagged: _TailBuffer(10).append('x' * 25) previously
    returned ''. Now must preserve the last 10 bytes."""
    from ncdev.ai_session import _TailBuffer

    buf = _TailBuffer(10)
    buf.append("x" * 25)
    text = buf.text()
    assert buf.truncated is True
    assert len(text.encode("utf-8")) <= 10
    # The tail is preserved — last 10 'x' characters
    assert text == "x" * 10


def test_tail_buffer_normal_eviction_across_chunks():
    """Multiple small chunks — head gets evicted as cap is exceeded."""
    from ncdev.ai_session import _TailBuffer

    buf = _TailBuffer(10)
    buf.append("aaaa")
    buf.append("bbbb")
    buf.append("cccc")    # total 12 > 10; head "aaaa" gets evicted
    text = buf.text()
    assert buf.truncated is True
    assert "cccc" in text
    # "aaaa" at the head was evicted; size must be under cap
    assert len(text.encode("utf-8")) <= 10


def test_tail_buffer_keeps_last_chunk_even_when_oversized_alone():
    """When only one chunk exists and it's oversized, slice its tail
    instead of losing everything."""
    from ncdev.ai_session import _TailBuffer

    buf = _TailBuffer(5)
    buf.append("1234567890")
    text = buf.text()
    assert text == "67890"


def test_run_codex_session_watchdog_kills_hung_child(tmp_path: Path):
    """Integration: actual hung child must be killed by the watchdog,
    same guarantee as run_claude_session."""
    import sys as _sys

    fake_cli = tmp_path / "fake-codex"
    fake_cli.write_text(
        "#!/usr/bin/env python3\nimport time\n"
        "while True:\n    time.sleep(1)\n",
        encoding="utf-8",
    )
    fake_cli.chmod(0o755)

    import subprocess as _sp
    orig_popen = _sp.Popen

    def fake_popen(cmd, **kwargs):
        new_cmd = [_sys.executable, str(fake_cli)] + list(cmd[1:])
        return orig_popen(new_cmd, **kwargs)

    start = time.time()
    with patch("ncdev.ai_session.shutil.which", return_value=str(fake_cli)):
        with patch("ncdev.ai_session.subprocess.Popen", side_effect=fake_popen):
            result = run_codex_session("x", cwd=tmp_path, timeout=2)
    elapsed = time.time() - start

    assert elapsed < 15, f"codex watchdog failed: {elapsed:.1f}s"
    assert result.success is False
    assert "timed out" in (result.error or "")
