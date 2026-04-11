"""Unit tests for src/memory.py — memory monitoring and guardrail utilities."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.memory import (
    MemoryPressure,
    MemorySnapshot,
    check_memory_pressure,
    cleanup_resources,
    get_memory_snapshot,
    log_memory_checkpoint,
)


# ---------------------------------------------------------------------------
# TestGetMemorySnapshot
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetMemorySnapshot:
    """Verify get_memory_snapshot() returns a valid MemorySnapshot."""

    def test_returns_memory_snapshot_instance(self):
        snapshot = get_memory_snapshot()
        assert isinstance(snapshot, MemorySnapshot)

    def test_total_gb_is_positive(self):
        snapshot = get_memory_snapshot()
        assert snapshot.total_gb > 0

    def test_used_gb_is_non_negative(self):
        snapshot = get_memory_snapshot()
        assert snapshot.used_gb >= 0

    def test_available_gb_is_non_negative(self):
        snapshot = get_memory_snapshot()
        assert snapshot.available_gb >= 0

    def test_percent_is_between_0_and_100(self):
        snapshot = get_memory_snapshot()
        assert 0.0 <= snapshot.percent <= 100.0

    def test_used_does_not_exceed_total(self):
        snapshot = get_memory_snapshot()
        # Allow a small tolerance for measurement timing
        assert snapshot.used_gb <= snapshot.total_gb + 0.1

    def test_snapshot_is_frozen(self):
        snapshot = get_memory_snapshot()
        with pytest.raises((AttributeError, TypeError)):
            snapshot.total_gb = 999.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TestCheckMemoryPressure
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCheckMemoryPressure:
    """Verify check_memory_pressure() classifies correctly for each tier."""

    def _mock_snapshot(self, percent: float) -> MemorySnapshot:
        return MemorySnapshot(
            total_gb=64.0,
            used_gb=64.0 * percent / 100.0,
            available_gb=64.0 * (1 - percent / 100.0),
            percent=percent,
        )

    def test_ok_when_below_high_threshold(self):
        with patch("src.memory.get_memory_snapshot", return_value=self._mock_snapshot(50.0)):
            pressure = check_memory_pressure(high_threshold=80.0, critical_threshold=90.0)
        assert pressure is MemoryPressure.OK

    def test_high_when_between_thresholds(self):
        with patch("src.memory.get_memory_snapshot", return_value=self._mock_snapshot(85.0)):
            pressure = check_memory_pressure(high_threshold=80.0, critical_threshold=90.0)
        assert pressure is MemoryPressure.HIGH

    def test_critical_when_above_critical_threshold(self):
        with patch("src.memory.get_memory_snapshot", return_value=self._mock_snapshot(95.0)):
            pressure = check_memory_pressure(high_threshold=80.0, critical_threshold=90.0)
        assert pressure is MemoryPressure.CRITICAL

    def test_exactly_at_high_threshold_is_high(self):
        with patch("src.memory.get_memory_snapshot", return_value=self._mock_snapshot(80.0)):
            pressure = check_memory_pressure(high_threshold=80.0, critical_threshold=90.0)
        assert pressure is MemoryPressure.HIGH

    def test_exactly_at_critical_threshold_is_critical(self):
        with patch("src.memory.get_memory_snapshot", return_value=self._mock_snapshot(90.0)):
            pressure = check_memory_pressure(high_threshold=80.0, critical_threshold=90.0)
        assert pressure is MemoryPressure.CRITICAL

    def test_custom_thresholds_respected(self):
        with patch("src.memory.get_memory_snapshot", return_value=self._mock_snapshot(60.0)):
            pressure = check_memory_pressure(high_threshold=55.0, critical_threshold=70.0)
        assert pressure is MemoryPressure.HIGH

    def test_returns_memory_pressure_enum(self):
        with patch("src.memory.get_memory_snapshot", return_value=self._mock_snapshot(40.0)):
            pressure = check_memory_pressure()
        assert isinstance(pressure, MemoryPressure)


# ---------------------------------------------------------------------------
# TestCleanupResources
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
class TestCleanupResources:
    """Verify cleanup_resources() issues the expected subprocess calls."""

    async def test_pkill_chromium_called(self):
        with patch("src.memory.run_command", new_callable=AsyncMock) as mock_run:
            await cleanup_resources()
        calls = [call.args[0] for call in mock_run.call_args_list]
        assert "pkill -f chromium" in calls

    async def test_pkill_playwright_called(self):
        with patch("src.memory.run_command", new_callable=AsyncMock) as mock_run:
            await cleanup_resources()
        calls = [call.args[0] for call in mock_run.call_args_list]
        assert "pkill -f playwright" in calls

    async def test_docker_compose_down_not_called_without_project_dir(self):
        with patch("src.memory.run_command", new_callable=AsyncMock) as mock_run:
            await cleanup_resources(project_dir=None)
        calls = [call.args[0] for call in mock_run.call_args_list]
        assert "docker compose down" not in calls

    async def test_docker_compose_down_called_with_project_dir(self):
        with patch("src.memory.run_command", new_callable=AsyncMock) as mock_run:
            await cleanup_resources(project_dir="/some/project")
        calls = [call.args[0] for call in mock_run.call_args_list]
        assert "docker compose down" in calls

    async def test_docker_compose_down_uses_project_dir_as_cwd(self):
        with patch("src.memory.run_command", new_callable=AsyncMock) as mock_run:
            await cleanup_resources(project_dir="/some/project")
        # Find the docker compose call and verify cwd kwarg
        docker_call = next(
            c for c in mock_run.call_args_list if c.args[0] == "docker compose down"
        )
        assert docker_call.kwargs.get("cwd") == "/some/project"

    async def test_gc_collect_called(self):
        with patch("src.memory.run_command", new_callable=AsyncMock):
            with patch("src.memory.gc.collect") as mock_gc:
                await cleanup_resources()
        mock_gc.assert_called_once()

    async def test_accepts_path_object_for_project_dir(self):
        with patch("src.memory.run_command", new_callable=AsyncMock) as mock_run:
            await cleanup_resources(project_dir=Path("/tmp/myproject"))
        calls = [call.args[0] for call in mock_run.call_args_list]
        assert "docker compose down" in calls


# ---------------------------------------------------------------------------
# TestLogMemoryCheckpoint
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestLogMemoryCheckpoint:
    """Verify log_memory_checkpoint() returns the expected tuple types."""

    def test_returns_tuple(self):
        result = log_memory_checkpoint("test-label")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_first_element_is_memory_snapshot(self):
        snapshot, _ = log_memory_checkpoint("test-label")
        assert isinstance(snapshot, MemorySnapshot)

    def test_second_element_is_memory_pressure(self):
        _, pressure = log_memory_checkpoint("test-label")
        assert isinstance(pressure, MemoryPressure)

    def test_snapshot_matches_current_state(self):
        mock_snapshot = MemorySnapshot(
            total_gb=32.0, used_gb=16.0, available_gb=16.0, percent=50.0
        )
        with patch("src.memory.get_memory_snapshot", return_value=mock_snapshot):
            with patch(
                "src.memory.check_memory_pressure", return_value=MemoryPressure.OK
            ):
                snapshot, pressure = log_memory_checkpoint("any-label")

        assert snapshot is mock_snapshot
        assert pressure is MemoryPressure.OK

    def test_label_does_not_affect_return_type(self):
        for label in ["start", "post-build", "cleanup", ""]:
            snapshot, pressure = log_memory_checkpoint(label)
            assert isinstance(snapshot, MemorySnapshot)
            assert isinstance(pressure, MemoryPressure)
