"""Memory monitoring and pressure management for the NC Dev System.

Provides utilities to snapshot system memory, classify memory pressure,
clean up orphan processes, and log named checkpoints.  This module is
part of the memory-safety guardrail that prevents runaway build pipelines
from exhausting host RAM.
"""

from __future__ import annotations

import gc
import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

import psutil

from src.utils import run_command

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums and dataclasses
# ---------------------------------------------------------------------------


class MemoryPressure(str, Enum):
    """Classification of current system memory pressure."""

    OK = "ok"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class MemorySnapshot:
    """Point-in-time snapshot of system virtual memory."""

    total_gb: float
    used_gb: float
    available_gb: float
    percent: float


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def get_memory_snapshot() -> MemorySnapshot:
    """Read current virtual memory statistics via psutil.

    Returns:
        A :class:`MemorySnapshot` with values in gigabytes and a usage
        percentage.
    """
    vm = psutil.virtual_memory()
    gb = 1024 ** 3
    return MemorySnapshot(
        total_gb=vm.total / gb,
        used_gb=vm.used / gb,
        available_gb=vm.available / gb,
        percent=vm.percent,
    )


def check_memory_pressure(
    high_threshold: float = 80.0,
    critical_threshold: float = 90.0,
) -> MemoryPressure:
    """Classify current memory pressure against configurable thresholds.

    Args:
        high_threshold: Percentage above which pressure is :attr:`MemoryPressure.HIGH`.
        critical_threshold: Percentage above which pressure is
            :attr:`MemoryPressure.CRITICAL`.

    Returns:
        The current :class:`MemoryPressure` level.
    """
    snapshot = get_memory_snapshot()
    pct = snapshot.percent

    if pct >= critical_threshold:
        logger.critical(
            "CRITICAL memory pressure: %.1f%% used (%.1f / %.1f GB)",
            pct,
            snapshot.used_gb,
            snapshot.total_gb,
        )
        return MemoryPressure.CRITICAL

    if pct >= high_threshold:
        logger.warning(
            "HIGH memory pressure: %.1f%% used (%.1f / %.1f GB)",
            pct,
            snapshot.used_gb,
            snapshot.total_gb,
        )
        return MemoryPressure.HIGH

    logger.info(
        "Memory OK: %.1f%% used (%.1f / %.1f GB)",
        pct,
        snapshot.used_gb,
        snapshot.total_gb,
    )
    return MemoryPressure.OK


async def cleanup_resources(project_dir: str | Path | None = None) -> None:
    """Kill orphan browser/Playwright processes and optionally stop Docker services.

    Steps performed:
    1. Kill lingering Chromium processes (``pkill -f chromium``).
    2. Kill lingering Playwright processes (``pkill -f playwright``).
    3. If *project_dir* is provided, run ``docker compose down`` in that directory.
    4. Call :func:`gc.collect` to reclaim Python-side memory.

    Args:
        project_dir: Optional path to a project whose Docker services should be
            stopped.  Pass ``None`` to skip the Docker step.
    """
    logger.info("cleanup_resources: killing orphan chromium/playwright processes")

    await run_command("pkill -f chromium", timeout=10)
    await run_command("pkill -f playwright", timeout=10)

    if project_dir is not None:
        logger.info("cleanup_resources: running docker compose down in %s", project_dir)
        await run_command("docker compose down", cwd=project_dir, timeout=60)

    gc.collect()
    logger.info("cleanup_resources: complete")


def log_memory_checkpoint(label: str) -> tuple[MemorySnapshot, MemoryPressure]:
    """Snapshot memory and log it at a named checkpoint.

    Args:
        label: A human-readable name for this checkpoint (e.g. ``"post-build"``).

    Returns:
        A ``(snapshot, pressure)`` tuple for the caller to act on if needed.
    """
    snapshot = get_memory_snapshot()
    pressure = check_memory_pressure()
    logger.info(
        "Memory checkpoint [%s]: %.1f%% used — pressure=%s",
        label,
        snapshot.percent,
        pressure.value,
    )
    return snapshot, pressure
