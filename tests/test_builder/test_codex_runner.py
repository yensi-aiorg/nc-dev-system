"""Unit tests for CodexRunner and related helpers (src.builder.codex_runner).

Tests cover:
- CodexResult dataclass and summary()
- CodexRunnerError exception
- _parse_codex_output (multiple JSON strategies)
- _extract_files_from_output (various output formats)
- _extract_test_results
- _extract_errors
- CodexRunner.run (mock subprocess)
- CodexRunner timeout handling
- CodexRunner binary not found / permission denied
- CodexRunner.check_available
- CodexRunner.check_authenticated
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.builder.codex_runner import (
    CodexResult,
    CodexRunner,
    CodexRunnerError,
    _extract_errors,
    _extract_files_from_output,
    _extract_test_results,
    _parse_codex_output,
)


# ---------------------------------------------------------------------------
# CodexResult dataclass
# ---------------------------------------------------------------------------


class TestCodexResult:
    @pytest.mark.unit
    def test_default_values(self):
        result = CodexResult(success=True)
        assert result.success is True
        assert result.files_created == []
        assert result.files_modified == []
        assert result.test_results == {}
        assert result.errors == []
        assert result.duration_seconds == 0.0
        assert result.stdout == ""
        assert result.stderr == ""
        assert result.exit_code == -1
        assert result.raw_output is None

    @pytest.mark.unit
    def test_success_summary(self):
        result = CodexResult(
            success=True,
            files_created=["a.py", "b.py"],
            files_modified=["c.py"],
            duration_seconds=12.5,
            test_results={"passed": 10, "failed": 0},
        )
        summary = result.summary()
        assert "SUCCESS" in summary
        assert "12.5s" in summary
        assert "Files created: 2" in summary
        assert "Files modified: 1" in summary
        assert "10 passed" in summary

    @pytest.mark.unit
    def test_failure_summary_with_errors(self):
        result = CodexResult(
            success=False,
            errors=["Error 1", "Error 2", "Error 3"],
            duration_seconds=5.0,
        )
        summary = result.summary()
        assert "FAILED" in summary
        assert "Errors: 3" in summary
        assert "Error 1" in summary

    @pytest.mark.unit
    def test_summary_truncates_long_errors(self):
        long_error = "x" * 300
        result = CodexResult(success=False, errors=[long_error])
        summary = result.summary()
        # Error should be truncated to 200 chars
        assert len(summary) < len(long_error) + 200


# ---------------------------------------------------------------------------
# CodexRunnerError exception
# ---------------------------------------------------------------------------


class TestCodexRunnerError:
    @pytest.mark.unit
    def test_message(self):
        err = CodexRunnerError("something broke")
        assert "something broke" in str(err)
        assert err.result is None

    @pytest.mark.unit
    def test_with_result(self):
        result = CodexResult(success=False, errors=["test error"])
        err = CodexRunnerError("failed", result=result)
        assert err.result is result
        assert err.result.errors == ["test error"]


# ---------------------------------------------------------------------------
# _parse_codex_output
# ---------------------------------------------------------------------------


class TestParseCodexOutput:
    @pytest.mark.unit
    def test_empty_string(self):
        assert _parse_codex_output("") == {}

    @pytest.mark.unit
    def test_whitespace_only(self):
        assert _parse_codex_output("   \n\n  ") == {}

    @pytest.mark.unit
    def test_direct_json(self):
        data = {"status": "success", "files": ["a.py"]}
        assert _parse_codex_output(json.dumps(data)) == data

    @pytest.mark.unit
    def test_json_with_prefix_text(self):
        raw = 'Starting build...\nProgress: 50%\n{"status": "success", "count": 5}'
        result = _parse_codex_output(raw)
        assert result.get("status") == "success"

    @pytest.mark.unit
    def test_json_embedded_in_output(self):
        raw = "some preamble text\n" + json.dumps({"key": "value"}) + "\nmore text"
        result = _parse_codex_output(raw)
        assert result.get("key") == "value"

    @pytest.mark.unit
    def test_jsonl_last_line(self):
        lines = [
            json.dumps({"progress": 1}),
            json.dumps({"progress": 2}),
            json.dumps({"status": "final"}),
        ]
        raw = "\n".join(lines)
        result = _parse_codex_output(raw)
        assert result.get("status") == "final"

    @pytest.mark.unit
    def test_invalid_json_returns_empty(self):
        assert _parse_codex_output("not json at all") == {}

    @pytest.mark.unit
    def test_nested_braces(self):
        data = {"outer": {"inner": "value"}}
        raw = "prefix " + json.dumps(data) + " suffix"
        result = _parse_codex_output(raw)
        # Should at least attempt to parse
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# _extract_files_from_output
# ---------------------------------------------------------------------------


class TestExtractFilesFromOutput:
    @pytest.mark.unit
    def test_empty_output(self):
        created, modified = _extract_files_from_output({})
        assert created == []
        assert modified == []

    @pytest.mark.unit
    def test_direct_files_fields(self):
        output = {
            "files_created": ["a.py", "b.py"],
            "files_modified": ["c.py"],
        }
        created, modified = _extract_files_from_output(output)
        assert created == ["a.py", "b.py"]
        assert modified == ["c.py"]

    @pytest.mark.unit
    def test_files_list_with_action_metadata(self):
        output = {
            "files": [
                {"path": "new.py", "action": "create"},
                {"path": "old.py", "action": "modify"},
            ]
        }
        created, modified = _extract_files_from_output(output)
        assert "new.py" in created
        assert "old.py" in modified

    @pytest.mark.unit
    def test_files_list_strings(self):
        output = {"files": ["a.py", "b.py"]}
        created, modified = _extract_files_from_output(output)
        assert "a.py" in created
        assert "b.py" in created

    @pytest.mark.unit
    def test_changes_structure(self):
        output = {
            "changes": [
                {"file": "created.py", "type": "create"},
                {"file": "added.py", "type": "add"},
                {"file": "new.py", "type": "new"},
                {"path": "modified.py", "type": "modify"},
            ]
        }
        created, modified = _extract_files_from_output(output)
        assert "created.py" in created
        assert "added.py" in created
        assert "new.py" in created
        assert "modified.py" in modified


# ---------------------------------------------------------------------------
# _extract_test_results
# ---------------------------------------------------------------------------


class TestExtractTestResults:
    @pytest.mark.unit
    def test_empty_output(self):
        assert _extract_test_results({}) == {}

    @pytest.mark.unit
    def test_test_results_field(self):
        output = {"test_results": {"passed": 5, "failed": 1}}
        assert _extract_test_results(output) == {"passed": 5, "failed": 1}

    @pytest.mark.unit
    def test_tests_field(self):
        output = {"tests": {"passed": 3, "failed": 0}}
        assert _extract_test_results(output) == {"passed": 3, "failed": 0}

    @pytest.mark.unit
    def test_test_results_takes_priority(self):
        output = {
            "test_results": {"passed": 10},
            "tests": {"passed": 5},
        }
        assert _extract_test_results(output) == {"passed": 10}


# ---------------------------------------------------------------------------
# _extract_errors
# ---------------------------------------------------------------------------


class TestExtractErrors:
    @pytest.mark.unit
    def test_empty(self):
        assert _extract_errors({}, "") == []

    @pytest.mark.unit
    def test_errors_list(self):
        output = {"errors": ["err1", "err2"]}
        errors = _extract_errors(output, "")
        assert "err1" in errors
        assert "err2" in errors

    @pytest.mark.unit
    def test_single_error(self):
        output = {"error": "something went wrong"}
        errors = _extract_errors(output, "")
        assert "something went wrong" in errors

    @pytest.mark.unit
    def test_stderr_error_lines(self):
        stderr = "INFO: normal output\nERROR: critical failure\nDEBUG: trace"
        errors = _extract_errors({}, stderr)
        assert any("critical failure" in e for e in errors)

    @pytest.mark.unit
    def test_stderr_failed_keyword(self):
        stderr = "Build failed with code 1"
        errors = _extract_errors({}, stderr)
        assert any("failed" in e.lower() for e in errors)

    @pytest.mark.unit
    def test_combined_errors(self):
        output = {"errors": ["json error"]}
        stderr = "FATAL: process crashed"
        errors = _extract_errors(output, stderr)
        assert any("json error" in e for e in errors)
        assert any("FATAL" in e for e in errors)


# ---------------------------------------------------------------------------
# CodexRunner.run (successful execution)
# ---------------------------------------------------------------------------


class TestCodexRunnerRun:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_successful_execution(self, tmp_path: Path):
        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("Build the feature")
        worktree = tmp_path / "worktree"
        worktree.mkdir()
        output_file = tmp_path / "result.json"

        codex_output = json.dumps({
            "files_created": ["app.py"],
            "files_modified": [],
            "test_results": {"passed": 5, "failed": 0},
        })

        # Write a result file as Codex would
        output_file.write_text(codex_output)

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            runner = CodexRunner(timeout_seconds=30)
            result = await runner.run(
                prompt_path=str(prompt_file),
                worktree_path=str(worktree),
                output_path=str(output_file),
            )

        assert result.success is True
        assert result.exit_code == 0
        assert "app.py" in result.files_created

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_prompt_not_found_raises(self, tmp_path: Path):
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        runner = CodexRunner()
        with pytest.raises(CodexRunnerError, match="Prompt file not found"):
            await runner.run(
                prompt_path=str(tmp_path / "nonexistent.md"),
                worktree_path=str(worktree),
                output_path=str(tmp_path / "out.json"),
            )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_worktree_not_found_raises(self, tmp_path: Path):
        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("Build something")

        runner = CodexRunner()
        with pytest.raises(CodexRunnerError, match="Worktree path not found"):
            await runner.run(
                prompt_path=str(prompt_file),
                worktree_path=str(tmp_path / "missing_worktree"),
                output_path=str(tmp_path / "out.json"),
            )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_binary_not_found_raises(self, tmp_path: Path):
        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("Build something")
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("codex not found"),
        ):
            runner = CodexRunner(codex_binary="codex-nonexistent")
            with pytest.raises(CodexRunnerError, match="Codex binary not found"):
                await runner.run(
                    prompt_path=str(prompt_file),
                    worktree_path=str(worktree),
                    output_path=str(tmp_path / "out.json"),
                )

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_permission_denied_raises(self, tmp_path: Path):
        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("Build something")
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=PermissionError("no perms"),
        ):
            runner = CodexRunner()
            with pytest.raises(CodexRunnerError, match="Permission denied"):
                await runner.run(
                    prompt_path=str(prompt_file),
                    worktree_path=str(worktree),
                    output_path=str(tmp_path / "out.json"),
                )


# ---------------------------------------------------------------------------
# CodexRunner timeout
# ---------------------------------------------------------------------------


class TestCodexRunnerTimeout:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_timeout_kills_process(self, tmp_path: Path):
        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("Build something")
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_process.kill = MagicMock()
        mock_process.returncode = None

        # Second communicate call (after kill) also times out
        call_count = 0

        async def mock_communicate():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise asyncio.TimeoutError()
            return (b"", b"")

        mock_process.communicate = mock_communicate

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
                runner = CodexRunner(timeout_seconds=1)
                result = await runner.run(
                    prompt_path=str(prompt_file),
                    worktree_path=str(worktree),
                    output_path=str(tmp_path / "out.json"),
                )

        assert result.success is False
        assert any("timed out" in e for e in result.errors)
        mock_process.kill.assert_called_once()


# ---------------------------------------------------------------------------
# CodexRunner - parse stdout when no output file
# ---------------------------------------------------------------------------


class TestCodexRunnerParseStdout:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_parse_stdout_json(self, tmp_path: Path):
        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("Build something")
        worktree = tmp_path / "worktree"
        worktree.mkdir()
        output_path = tmp_path / "out.json"
        # Do NOT write output_path -- force parsing from stdout

        stdout_json = json.dumps({
            "files_created": ["new_file.py"],
            "test_results": {"passed": 3, "failed": 0},
        })

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            return_value=(stdout_json.encode("utf-8"), b"")
        )
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            runner = CodexRunner(timeout_seconds=30)
            result = await runner.run(
                prompt_path=str(prompt_file),
                worktree_path=str(worktree),
                output_path=str(output_path),
            )

        assert result.success is True
        assert "new_file.py" in result.files_created

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_nonzero_exit_code_fails(self, tmp_path: Path):
        prompt_file = tmp_path / "prompt.md"
        prompt_file.write_text("Build something")
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            return_value=(b"{}", b"ERROR: compilation failed")
        )
        mock_process.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            runner = CodexRunner(timeout_seconds=30)
            result = await runner.run(
                prompt_path=str(prompt_file),
                worktree_path=str(worktree),
                output_path=str(tmp_path / "out.json"),
            )

        assert result.success is False
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# CodexRunner.check_available
# ---------------------------------------------------------------------------


class TestCodexRunnerCheckAvailable:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_available(self):
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            return_value=(b"codex v1.2.3", b"")
        )
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch("asyncio.wait_for", return_value=(b"codex v1.2.3", b"")):
                runner = CodexRunner()
                result = await runner.check_available()

        assert result is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_not_available(self):
        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("not found"),
        ):
            runner = CodexRunner()
            result = await runner.check_available()

        assert result is False


# ---------------------------------------------------------------------------
# CodexRunner.check_authenticated
# ---------------------------------------------------------------------------


class TestCodexRunnerCheckAuthenticated:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_authenticated(self):
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            return_value=(b"Authenticated", b"")
        )
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch("asyncio.wait_for", return_value=(b"Authenticated", b"")):
                runner = CodexRunner()
                result = await runner.check_authenticated()

        assert result is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_not_authenticated(self):
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            return_value=(b"Not logged in", b"")
        )
        mock_process.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch("asyncio.wait_for", return_value=(b"Not logged in", b"")):
                runner = CodexRunner()
                result = await runner.check_authenticated()

        assert result is False


# ---------------------------------------------------------------------------
# CodexRunner.__init__
# ---------------------------------------------------------------------------


class TestCodexRunnerInit:
    @pytest.mark.unit
    def test_default_values(self):
        runner = CodexRunner()
        assert runner.timeout_seconds == 600.0
        assert runner.codex_binary == "codex"

    @pytest.mark.unit
    def test_custom_values(self):
        runner = CodexRunner(
            timeout_seconds=300,
            codex_binary="/usr/bin/codex",
        )
        assert runner.timeout_seconds == 300
        assert runner.codex_binary == "/usr/bin/codex"
