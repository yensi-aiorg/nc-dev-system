"""Tests for the Claude session runner primitive.

The runner shells out to the real ``claude`` CLI, so these tests fake the
subprocess layer. They verify:
- The command is composed correctly (tools, model, system prompt, budget)
- Stream-json events are parsed into structured signals (tool calls,
  skills invoked, codex shell-outs, files touched)
- Timeouts, missing CLI, and non-zero exits produce well-formed results
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from ncdev import claude_session
from ncdev.claude_session import (
    ClaudeSessionResult,
    DEFAULT_BUILD_TOOLS,
    DEFAULT_PLAN_TOOLS,
    run_claude_session,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeProc:
    """Minimal stand-in for subprocess.Popen.

    Supports the production interface: iteration over stdout, iteration
    over stderr (for the drain thread), poll(), wait(), kill(), pid,
    terminate(). Good enough for verifying event parsing + argv
    composition without spawning a real child.
    """

    _next_pid = 10000

    def __init__(self, stdout_lines: list[str], returncode: int = 0, stderr: str = ""):
        _FakeProc._next_pid += 1
        self.pid = _FakeProc._next_pid
        self._stdout_lines = stdout_lines
        self.returncode = returncode
        self.stdout = iter(stdout_lines)
        self.stderr = _FakeStderr(stderr)
        self._done = True   # synchronous fake — process is "complete" immediately

    def poll(self):
        return self.returncode if self._done else None

    def wait(self, timeout=None):  # noqa: ARG002
        return self.returncode

    def kill(self):
        pass

    def terminate(self):
        pass


class _FakeStderr:
    def __init__(self, text: str):
        self._text = text

    def __iter__(self):
        if self._text:
            yield self._text
        return

    def read(self) -> str:
        return self._text


def _popen_factory(stdout_events: list[dict], returncode: int = 0, stderr: str = ""):
    """Return a Popen stand-in that streams the given JSON events."""
    lines = [json.dumps(ev) + "\n" for ev in stdout_events]
    captured: dict = {}

    def _popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return _FakeProc(lines, returncode=returncode, stderr=stderr)

    return _popen, captured


# ---------------------------------------------------------------------------
# Command composition
# ---------------------------------------------------------------------------


def test_command_includes_stream_json_and_tools(tmp_path: Path):
    popen, captured = _popen_factory([{"type": "result", "result": "ok"}])

    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
            run_claude_session(
                "plan this",
                cwd=tmp_path,
                tools=DEFAULT_PLAN_TOOLS,
                include_codex_protocol=False,
            )

    cmd = captured["cmd"]
    assert cmd[0] == "claude"
    assert "--print" not in cmd  # we use -p
    assert "-p" in cmd
    assert "--output-format" in cmd
    assert cmd[cmd.index("--output-format") + 1] == "stream-json"
    # --verbose is required by recent claude CLI when combining --print
    # with --output-format=stream-json; regression-guard so the flag isn't
    # silently dropped.
    assert "--verbose" in cmd
    tools_idx = cmd.index("--allowedTools") + 1
    assert cmd[tools_idx] == ",".join(DEFAULT_PLAN_TOOLS)


def test_default_build_tools_include_bash_skill_task():
    # These are the three tools that unlock the new architecture.
    assert "Bash" in DEFAULT_BUILD_TOOLS
    assert "Skill" in DEFAULT_BUILD_TOOLS
    assert "Task" in DEFAULT_BUILD_TOOLS


def test_plan_tools_exclude_write_beyond_artifacts():
    assert "Bash" not in DEFAULT_PLAN_TOOLS
    assert "Edit" not in DEFAULT_PLAN_TOOLS
    # Write stays — planning sessions write charter/queue JSON.
    assert "Write" in DEFAULT_PLAN_TOOLS


def test_max_budget_flag_passed_when_specified(tmp_path: Path):
    popen, captured = _popen_factory([{"type": "result", "result": "done"}])

    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
            run_claude_session(
                "build",
                cwd=tmp_path,
                max_budget_usd=2.50,
                include_codex_protocol=False,
            )

    cmd = captured["cmd"]
    assert "--max-budget-usd" in cmd
    idx = cmd.index("--max-budget-usd")
    assert cmd[idx + 1] == "2.5000"


def test_codex_protocol_prepended_to_system_prompt(tmp_path: Path):
    popen, captured = _popen_factory([{"type": "result", "result": "done"}])

    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
            run_claude_session(
                "build",
                cwd=tmp_path,
                append_system_prompt="project charter here",
                include_codex_protocol=True,
            )

    cmd = captured["cmd"]
    assert "--append-system-prompt" in cmd
    idx = cmd.index("--append-system-prompt")
    system_text = cmd[idx + 1]
    # Protocol file content is included verbatim
    assert "Codex Protocol" in system_text
    assert "codex exec --full-auto" in system_text
    # Caller's own prompt appended after
    assert "project charter here" in system_text


def test_include_codex_protocol_false_omits_protocol(tmp_path: Path):
    popen, captured = _popen_factory([{"type": "result", "result": "done"}])

    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
            run_claude_session(
                "plan only",
                cwd=tmp_path,
                append_system_prompt="just this",
                include_codex_protocol=False,
            )

    cmd = captured["cmd"]
    idx = cmd.index("--append-system-prompt")
    assert cmd[idx + 1] == "just this"


# ---------------------------------------------------------------------------
# Event parsing
# ---------------------------------------------------------------------------


def test_tool_calls_extracted_from_stream(tmp_path: Path):
    events = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Read",
                     "input": {"file_path": "src/app.py"}},
                    {"type": "tool_use", "name": "Bash",
                     "input": {"command": "codex exec --full-auto 'Task: impl'"}},
                    {"type": "tool_use", "name": "Skill",
                     "input": {"skill": "test-driven-development"}},
                    {"type": "tool_use", "name": "Task",
                     "input": {"subagent_type": "code-reviewer",
                               "description": "review feature"}},
                    {"type": "tool_use", "name": "Write",
                     "input": {"file_path": "src/new_file.py", "content": "..."}},
                ],
            },
        },
        {"type": "result", "result": "done", "total_cost_usd": 0.42},
    ]
    popen, _ = _popen_factory(events)

    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
            result = run_claude_session(
                "build", cwd=tmp_path, include_codex_protocol=False,
            )

    assert result.success is True
    assert result.total_cost_usd == 0.42
    # All five tool calls captured
    assert len(result.tool_calls) == 5
    tool_names = [t.tool for t in result.tool_calls]
    assert tool_names == ["Read", "Bash", "Skill", "Task", "Write"]
    # Skill name parsed out
    assert "test-driven-development" in result.skills_invoked
    # Codex shell-out recognized
    assert len(result.codex_invocations) == 1
    assert "codex exec --full-auto" in result.codex_invocations[0]
    # Subagent dispatched
    assert "code-reviewer" in result.subagents_dispatched
    # File touched
    assert "src/new_file.py" in result.files_touched


def test_final_text_from_result_event(tmp_path: Path):
    events = [
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "thinking"}]}},
        {"type": "result", "result": "build complete", "total_cost_usd": 0.10},
    ]
    popen, _ = _popen_factory(events)
    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
            result = run_claude_session("x", cwd=tmp_path, include_codex_protocol=False)
    assert result.final_text == "build complete"


def test_final_text_falls_back_to_last_assistant_message(tmp_path: Path):
    # No result event — runner falls back to extracting from last assistant event
    events = [
        {"type": "assistant",
         "message": {"content": [{"type": "text", "text": "final answer"}]}},
    ]
    popen, _ = _popen_factory(events)
    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
            result = run_claude_session("x", cwd=tmp_path, include_codex_protocol=False)
    assert result.final_text == "final answer"


def test_on_event_callback_invoked_per_event(tmp_path: Path):
    events = [
        {"type": "assistant", "message": {"content": []}},
        {"type": "result", "result": "ok"},
    ]
    popen, _ = _popen_factory(events)

    seen: list[dict] = []

    def cb(ev):
        seen.append(ev)

    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
            run_claude_session(
                "x", cwd=tmp_path, on_event=cb, include_codex_protocol=False,
            )

    assert len(seen) == 2


def test_on_event_exception_does_not_crash_session(tmp_path: Path):
    events = [{"type": "result", "result": "ok"}]
    popen, _ = _popen_factory(events)

    def bad_cb(_ev):
        raise RuntimeError("boom")

    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
            result = run_claude_session(
                "x", cwd=tmp_path, on_event=bad_cb, include_codex_protocol=False,
            )
    assert result.success is True


def test_event_log_written_as_jsonl(tmp_path: Path):
    events = [
        {"type": "assistant", "message": {"content": []}},
        {"type": "result", "result": "ok"},
    ]
    popen, _ = _popen_factory(events)
    log_path = tmp_path / "logs" / "session.jsonl"

    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
            run_claude_session(
                "x", cwd=tmp_path, log_path=log_path, include_codex_protocol=False,
            )

    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["type"] == "assistant"
    assert json.loads(lines[1])["type"] == "result"


def test_malformed_json_line_is_tolerated(tmp_path: Path):
    # Claude CLI occasionally emits debug noise — runner must not crash.
    lines = [
        "not a json line\n",
        json.dumps({"type": "result", "result": "ok"}) + "\n",
    ]

    def popen(cmd, **kwargs):  # noqa: ARG001
        return _FakeProc(lines, returncode=0)

    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
            result = run_claude_session(
                "x", cwd=tmp_path, include_codex_protocol=False,
            )
    assert result.success is True
    assert result.final_text == "ok"


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_claude_cli_missing_returns_structured_error(tmp_path: Path):
    with patch("ncdev.claude_session.shutil.which", return_value=None):
        result = run_claude_session("x", cwd=tmp_path)
    assert result.success is False
    assert result.exit_code == -1
    assert "claude CLI not found" in (result.error or "")


def test_non_zero_exit_marked_unsuccessful(tmp_path: Path):
    events = [{"type": "result", "result": "partial"}]
    popen, _ = _popen_factory(events, returncode=2, stderr="something broke")

    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
            result = run_claude_session(
                "x", cwd=tmp_path, include_codex_protocol=False,
            )

    assert result.success is False
    assert result.exit_code == 2
    assert result.stderr == "something broke"
    assert "exited with code 2" in (result.error or "")


def test_ncdev_hooks_wired_in_by_default(tmp_path: Path):
    """When enable_ncdev_hooks=True (default) and the bundled settings
    file exists, --settings is passed to claude."""
    popen, captured = _popen_factory([{"type": "result", "result": "ok"}])

    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
            run_claude_session(
                "do thing", cwd=tmp_path, include_codex_protocol=False,
            )
    cmd = captured["cmd"]
    assert "--settings" in cmd
    idx = cmd.index("--settings")
    settings_path = cmd[idx + 1]
    assert settings_path.endswith("settings.json")


def test_enable_ncdev_hooks_false_omits_settings(tmp_path: Path):
    popen, captured = _popen_factory([{"type": "result", "result": "ok"}])
    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
            run_claude_session(
                "x", cwd=tmp_path, include_codex_protocol=False,
                enable_ncdev_hooks=False,
            )
    cmd = captured["cmd"]
    assert "--settings" not in cmd


def test_caller_supplied_settings_path_wins(tmp_path: Path):
    user_settings = tmp_path / "custom-settings.json"
    user_settings.write_text("{}")
    popen, captured = _popen_factory([{"type": "result", "result": "ok"}])
    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
            run_claude_session(
                "x", cwd=tmp_path, include_codex_protocol=False,
                settings_path=user_settings,
            )
    cmd = captured["cmd"]
    idx = cmd.index("--settings")
    assert cmd[idx + 1] == str(user_settings)


def test_events_not_retained_by_default(tmp_path: Path):
    """Codex flag: in-memory event list is wasteful on long runs.
    Default is now OFF — result.events should be empty unless asked."""
    events = [
        {"type": "assistant", "message": {"content": []}},
        {"type": "result", "result": "ok"},
    ]
    popen, _ = _popen_factory(events)
    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
            result = run_claude_session(
                "x", cwd=tmp_path, include_codex_protocol=False,
            )
    assert result.events == []
    # But final_text still resolves via the ring buffer
    assert result.final_text == "ok"


def test_retain_events_flag_opt_in(tmp_path: Path):
    events = [
        {"type": "assistant", "message": {"content": []}},
        {"type": "result", "result": "ok"},
    ]
    popen, _ = _popen_factory(events)
    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
            result = run_claude_session(
                "x", cwd=tmp_path,
                include_codex_protocol=False,
                retain_events=True,
            )
    assert len(result.events) == 2


def test_watchdog_actually_kills_hung_subprocess(tmp_path: Path):
    """Integration — spawn a real process that never exits, verify
    run_claude_session kills it via the watchdog within ~timeout seconds.

    This is Codex's critical issue: stdout-block deadlock. If the
    watchdog isn't wired, this test hangs forever.
    """
    import sys as _sys

    # Stand-in for `claude` — a python inline script that hangs reading stdin.
    # We point shutil.which at this to fool the preflight check.
    fake_cli = tmp_path / "fake-claude"
    fake_cli.write_text(
        "#!/usr/bin/env python3\nimport sys, time\n"
        "# never produces output, never exits\n"
        "while True:\n    time.sleep(1)\n",
        encoding="utf-8",
    )
    fake_cli.chmod(0o755)

    import subprocess as _sp

    orig_popen = _sp.Popen

    def fake_popen(cmd, **kwargs):
        # Replace the claude executable with our hanging script
        new_cmd = [_sys.executable, str(fake_cli)] + list(cmd[1:])
        return orig_popen(new_cmd, **kwargs)

    start = time.time()
    with patch("ncdev.claude_session.shutil.which", return_value=str(fake_cli)):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=fake_popen):
            result = run_claude_session(
                "x", cwd=tmp_path,
                timeout=2,   # wall-clock kill after 2s
                include_codex_protocol=False,
            )
    elapsed = time.time() - start

    # Hard upper bound: watchdog + wait should terminate within ~10s even
    # on a slow CI runner. No test should take 2 minutes, which is what
    # would happen if the watchdog were broken.
    assert elapsed < 15, f"watchdog failed to kill: elapsed={elapsed:.1f}s"
    assert result.success is False
    assert "timed out" in (result.error or "")


def test_stderr_backpressure_does_not_deadlock(tmp_path: Path):
    """Integration — child emits massive stderr while stdout is light.
    Without the stderr-drain thread, the pipe fills and the child hangs.
    """
    import sys as _sys
    fake_cli = tmp_path / "fake-claude"
    fake_cli.write_text(
        "#!/usr/bin/env python3\nimport sys, json\n"
        # Emit one result event on stdout, then flood stderr with ~2MB
        # of output and exit cleanly.
        'print(json.dumps({"type":"result","result":"ok"}))\n'
        "sys.stdout.flush()\n"
        "for _ in range(20000):\n"
        '    sys.stderr.write("x" * 100 + "\\n")\n'
        "sys.stderr.flush()\n",
        encoding="utf-8",
    )
    fake_cli.chmod(0o755)

    import subprocess as _sp
    orig_popen = _sp.Popen

    def fake_popen(cmd, **kwargs):
        new_cmd = [_sys.executable, str(fake_cli)] + list(cmd[1:])
        return orig_popen(new_cmd, **kwargs)

    start = time.time()
    with patch("ncdev.claude_session.shutil.which", return_value=str(fake_cli)):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=fake_popen):
            result = run_claude_session(
                "x", cwd=tmp_path,
                timeout=15,
                include_codex_protocol=False,
            )
    elapsed = time.time() - start
    # Must complete cleanly — not timeout, not hang
    assert elapsed < 10, f"stderr backpressure deadlocked: elapsed={elapsed:.1f}s"
    assert result.success is True
    assert result.final_text == "ok"
    assert len(result.stderr) > 100_000    # captured the flood


def test_summary_includes_key_signals(tmp_path: Path):
    events = [
        {
            "type": "assistant",
            "message": {"content": [
                {"type": "tool_use", "name": "Skill",
                 "input": {"skill": "verification-before-completion"}},
                {"type": "tool_use", "name": "Bash",
                 "input": {"command": "codex exec --full-auto 'x'"}},
            ]},
        },
        {"type": "result", "result": "ok", "total_cost_usd": 1.23},
    ]
    popen, _ = _popen_factory(events)
    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
            result = run_claude_session(
                "x", cwd=tmp_path, include_codex_protocol=False,
            )
    s = result.summary()
    assert "success=True" in s
    assert "cost=$1.230" in s
    assert "skills=verification-before-completion" in s
    assert "codex=1" in s
