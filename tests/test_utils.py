"""Unit tests for utility functions (src.utils).

Tests cover:
- run_command (success, failure, timeout, list vs string, env vars, capture=False)
- sanitize_name (various inputs)
- load_json / load_json_list / save_json (use tmp_path)
- ensure_dir
- format_duration
- validate_port
- check_port_available / check_ports_available
- wait_for_health (mock httpx)
- PHASE_NAMES / PHASE_COLORS constants
- Rich output helpers (print_phase_header, print_summary_table, etc.)
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.utils import (
    PHASE_COLORS,
    PHASE_NAMES,
    check_port_available,
    check_ports_available,
    create_progress,
    ensure_dir,
    format_duration,
    load_json,
    load_json_list,
    print_error,
    print_phase_header,
    print_success,
    print_summary_table,
    print_warning,
    run_command,
    sanitize_name,
    save_json,
    validate_port,
    wait_for_health,
)


# ---------------------------------------------------------------------------
# run_command
# ---------------------------------------------------------------------------


class TestRunCommand:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_successful_command_list(self):
        returncode, stdout, stderr = await run_command(["echo", "hello"])
        assert returncode == 0
        assert "hello" in stdout

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_successful_command_string(self):
        returncode, stdout, stderr = await run_command("echo hello")
        assert returncode == 0
        assert "hello" in stdout

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_failed_command(self):
        returncode, stdout, stderr = await run_command(
            ["python", "-c", "import sys; sys.exit(1)"]
        )
        assert returncode != 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_command_with_cwd(self, tmp_path: Path):
        returncode, stdout, stderr = await run_command(
            ["python", "-c", "import os; print(os.getcwd())"], cwd=tmp_path
        )
        assert returncode == 0
        # Resolve both to handle symlinks/case differences across platforms
        assert Path(stdout.strip()).resolve() == tmp_path.resolve()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_command_timeout(self):
        returncode, stdout, stderr = await run_command(
            ["python", "-c", "import time; time.sleep(10)"], timeout=1
        )
        assert returncode == -1
        assert "timed out" in stderr

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_command_with_env(self):
        returncode, stdout, stderr = await run_command(
            ["python", "-c", "import os; print(os.environ['TEST_VAR'])"],
            env={"TEST_VAR": "test_value"},
        )
        assert returncode == 0
        assert "test_value" in stdout

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_command_nonexistent_shell(self):
        # Use shell mode to avoid FileNotFoundError from create_subprocess_exec
        returncode, stdout, stderr = await run_command(
            "nonexistent-binary-12345-xyz"
        )
        # Shell reports "not found" / "not recognized" and returns non-zero
        assert returncode != 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_command_returns_stderr(self):
        returncode, stdout, stderr = await run_command(
            ["python", "-c", "import sys; sys.stderr.write('error_msg\\n')"],
            timeout=10,
        )
        # stderr should contain the message
        assert "error_msg" in stderr


# ---------------------------------------------------------------------------
# sanitize_name
# ---------------------------------------------------------------------------


class TestSanitizeName:
    @pytest.mark.unit
    def test_simple_name(self):
        assert sanitize_name("User Authentication") == "user-authentication"

    @pytest.mark.unit
    def test_special_chars(self):
        assert sanitize_name("  2FA (TOTP)  ") == "2fa-totp"

    @pytest.mark.unit
    def test_multiple_spaces(self):
        assert sanitize_name("my   cool   feature") == "my-cool-feature"

    @pytest.mark.unit
    def test_underscores_preserved(self):
        result = sanitize_name("my_feature_v2")
        assert "_" in result

    @pytest.mark.unit
    def test_hyphens_preserved(self):
        result = sanitize_name("my-feature")
        assert result == "my-feature"

    @pytest.mark.unit
    def test_leading_trailing_hyphens_stripped(self):
        result = sanitize_name("---leading---trailing---")
        assert not result.startswith("-")
        assert not result.endswith("-")

    @pytest.mark.unit
    def test_consecutive_hyphens_collapsed(self):
        result = sanitize_name("a - - b")
        assert "--" not in result

    @pytest.mark.unit
    def test_empty_string(self):
        result = sanitize_name("")
        assert result == ""

    @pytest.mark.unit
    def test_uppercase_lowered(self):
        assert sanitize_name("MyFeature") == "myfeature"

    @pytest.mark.unit
    def test_dots_replaced(self):
        result = sanitize_name("version.2.0")
        assert "." not in result


# ---------------------------------------------------------------------------
# load_json / save_json
# ---------------------------------------------------------------------------


class TestJsonIO:
    @pytest.mark.unit
    def test_load_json_dict(self, tmp_path: Path):
        data = {"key": "value", "number": 42}
        filepath = tmp_path / "test.json"
        filepath.write_text(json.dumps(data))

        result = load_json(filepath)
        assert result == data

    @pytest.mark.unit
    def test_load_json_list_wraps_in_dict(self, tmp_path: Path):
        data = [1, 2, 3]
        filepath = tmp_path / "test.json"
        filepath.write_text(json.dumps(data))

        result = load_json(filepath)
        assert result == {"_root": [1, 2, 3]}

    @pytest.mark.unit
    def test_load_json_file_not_found(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_json(tmp_path / "missing.json")

    @pytest.mark.unit
    def test_load_json_invalid_json(self, tmp_path: Path):
        filepath = tmp_path / "bad.json"
        filepath.write_text("not valid json")

        with pytest.raises(json.JSONDecodeError):
            load_json(filepath)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_save_json_dict(self, tmp_path: Path):
        data = {"key": "value"}
        filepath = tmp_path / "output.json"

        await save_json(data, filepath)

        assert filepath.exists()
        loaded = json.loads(filepath.read_text())
        assert loaded == data

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_save_json_list(self, tmp_path: Path):
        data = [1, 2, 3]
        filepath = tmp_path / "output.json"

        await save_json(data, filepath)

        assert filepath.exists()
        loaded = json.loads(filepath.read_text())
        assert loaded == data

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_save_json_creates_parents(self, tmp_path: Path):
        filepath = tmp_path / "deep" / "nested" / "output.json"
        await save_json({"test": True}, filepath)

        assert filepath.exists()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_save_json_pretty_printed(self, tmp_path: Path):
        data = {"key": "value"}
        filepath = tmp_path / "output.json"
        await save_json(data, filepath)

        text = filepath.read_text()
        assert "\n" in text  # Pretty-printed has newlines
        assert "  " in text  # Indentation


# ---------------------------------------------------------------------------
# load_json_list
# ---------------------------------------------------------------------------


class TestLoadJsonList:
    @pytest.mark.unit
    def test_load_list(self, tmp_path: Path):
        data = [{"name": "a"}, {"name": "b"}]
        filepath = tmp_path / "list.json"
        filepath.write_text(json.dumps(data))

        result = load_json_list(filepath)
        assert result == data

    @pytest.mark.unit
    def test_load_nonlist_wraps(self, tmp_path: Path):
        data = {"name": "single"}
        filepath = tmp_path / "dict.json"
        filepath.write_text(json.dumps(data))

        result = load_json_list(filepath)
        assert result == [data]

    @pytest.mark.unit
    def test_missing_file_returns_empty(self, tmp_path: Path):
        result = load_json_list(tmp_path / "missing.json")
        assert result == []


# ---------------------------------------------------------------------------
# ensure_dir
# ---------------------------------------------------------------------------


class TestEnsureDir:
    @pytest.mark.unit
    def test_creates_new_dir(self, tmp_path: Path):
        new_dir = tmp_path / "new" / "nested" / "dir"
        result = ensure_dir(new_dir)
        assert new_dir.exists()
        assert new_dir.is_dir()
        assert result == new_dir.resolve()

    @pytest.mark.unit
    def test_existing_dir_no_error(self, tmp_path: Path):
        existing = tmp_path / "existing"
        existing.mkdir()
        result = ensure_dir(existing)
        assert result == existing.resolve()

    @pytest.mark.unit
    def test_returns_resolved_path(self, tmp_path: Path):
        rel_dir = tmp_path / "some" / "dir"
        result = ensure_dir(rel_dir)
        assert result.is_absolute()


# ---------------------------------------------------------------------------
# format_duration
# ---------------------------------------------------------------------------


class TestFormatDuration:
    @pytest.mark.unit
    def test_seconds_only(self):
        assert format_duration(3.7) == "3.7s"

    @pytest.mark.unit
    def test_minutes_and_seconds(self):
        assert format_duration(65.2) == "1m 5s"

    @pytest.mark.unit
    def test_hours_minutes_seconds(self):
        assert format_duration(3661.0) == "1h 1m 1s"

    @pytest.mark.unit
    def test_zero(self):
        assert format_duration(0.0) == "0.0s"

    @pytest.mark.unit
    def test_negative(self):
        assert format_duration(-5.0) == "0.0s"

    @pytest.mark.unit
    def test_large_value(self):
        result = format_duration(7200.0)
        assert "2h" in result

    @pytest.mark.unit
    def test_exactly_one_minute(self):
        result = format_duration(60.0)
        assert "1m" in result

    @pytest.mark.unit
    def test_fractional_seconds_below_minute(self):
        result = format_duration(45.3)
        assert result == "45.3s"


# ---------------------------------------------------------------------------
# validate_port
# ---------------------------------------------------------------------------


class TestValidatePort:
    @pytest.mark.unit
    def test_valid_port(self):
        assert validate_port(23000) is True
        assert validate_port(23001) is True
        assert validate_port(25000) is True

    @pytest.mark.unit
    def test_invalid_port_below_23000(self):
        assert validate_port(3000) is False
        assert validate_port(8080) is False
        assert validate_port(22999) is False

    @pytest.mark.unit
    def test_boundary(self):
        assert validate_port(23000) is True
        assert validate_port(22999) is False


# ---------------------------------------------------------------------------
# check_port_available / check_ports_available
# ---------------------------------------------------------------------------


class TestCheckPorts:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_port_available(self):
        # Port 59999 should almost certainly be free
        result = await check_port_available(59999)
        assert isinstance(result, bool)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_ports_available_returns_dict(self):
        result = await check_ports_available([59997, 59998, 59999])
        assert isinstance(result, dict)
        assert len(result) == 3
        for port in [59997, 59998, 59999]:
            assert port in result
            assert isinstance(result[port], bool)


# ---------------------------------------------------------------------------
# wait_for_health
# ---------------------------------------------------------------------------


class TestWaitForHealth:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_immediate_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await wait_for_health(
                "http://localhost:23001/health",
                timeout=5,
                interval=1,
            )

        assert result is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_timeout_returns_false(self):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await wait_for_health(
                "http://localhost:23001/health",
                timeout=2,
                interval=1,
            )

        assert result is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_eventual_success(self):
        call_count = 0

        async def get_side_effect(url):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise httpx.ConnectError("not ready")
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            return mock_resp

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=get_side_effect)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await wait_for_health(
                "http://localhost:23001/health",
                timeout=30,
                interval=1,
            )

        assert result is True
        assert call_count >= 3

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_non_200_keeps_trying(self):
        call_count = 0

        async def get_side_effect(url):
            nonlocal call_count
            call_count += 1
            mock_resp = MagicMock()
            if call_count < 3:
                mock_resp.status_code = 503
            else:
                mock_resp.status_code = 200
            return mock_resp

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=get_side_effect)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await wait_for_health(
                "http://localhost:23001/health",
                timeout=30,
                interval=1,
            )

        assert result is True


# ---------------------------------------------------------------------------
# PHASE_NAMES / PHASE_COLORS constants
# ---------------------------------------------------------------------------


class TestPhaseConstants:
    @pytest.mark.unit
    def test_phase_names_all_present(self):
        for i in range(1, 7):
            assert i in PHASE_NAMES
        assert PHASE_NAMES[1] == "UNDERSTAND"
        assert PHASE_NAMES[2] == "SCAFFOLD"
        assert PHASE_NAMES[3] == "BUILD"
        assert PHASE_NAMES[4] == "VERIFY"
        assert PHASE_NAMES[5] == "HARDEN"
        assert PHASE_NAMES[6] == "DELIVER"

    @pytest.mark.unit
    def test_phase_colors_all_present(self):
        for i in range(1, 7):
            assert i in PHASE_COLORS
            assert isinstance(PHASE_COLORS[i], str)


# ---------------------------------------------------------------------------
# Rich output helpers (smoke tests - verify they don't raise)
# ---------------------------------------------------------------------------


class TestRichOutputHelpers:
    @pytest.mark.unit
    def test_print_phase_header(self):
        # Should not raise
        print_phase_header(1, "UNDERSTAND")
        print_phase_header(6, "DELIVER")

    @pytest.mark.unit
    def test_print_summary_table(self):
        # Should not raise
        print_summary_table(
            {"Key1": "Value1", "Key2": "Value2"},
            title="Test Summary",
        )

    @pytest.mark.unit
    def test_print_success(self):
        print_success("All tests passed")

    @pytest.mark.unit
    def test_print_error(self):
        print_error("Something failed")

    @pytest.mark.unit
    def test_print_warning(self):
        print_warning("Check your config")

    @pytest.mark.unit
    def test_create_progress(self):
        progress = create_progress()
        assert progress is not None
