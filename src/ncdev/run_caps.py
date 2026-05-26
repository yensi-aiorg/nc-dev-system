"""Factory run cap policy.

These caps live above individual Claude/Codex session timeouts. They bound
the whole factory loop so unattended runs stop predictably.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RunCaps:
    max_cycles: int
    max_budget_usd: float | None = None
    max_wall_time_minutes: float | None = None
    max_consecutive_failures: int = 3
    allow_unmetered: bool = False

    def __post_init__(self) -> None:
        if self.max_cycles < 1:
            raise ValueError("max_cycles must be >= 1")
        if self.max_budget_usd is not None and self.max_budget_usd < 0:
            raise ValueError("max_budget_usd must be >= 0")
        if (
            self.max_wall_time_minutes is not None
            and self.max_wall_time_minutes < 0
        ):
            raise ValueError("max_wall_time_minutes must be >= 0")
        if self.max_consecutive_failures < 1:
            raise ValueError("max_consecutive_failures must be >= 1")

    @property
    def wall_time_seconds(self) -> float | None:
        if self.max_wall_time_minutes is None:
            return None
        return self.max_wall_time_minutes * 60.0

    @property
    def budgeted(self) -> bool:
        return self.max_budget_usd is not None

    def wall_time_exhausted(self, *, elapsed_seconds: float) -> bool:
        limit = self.wall_time_seconds
        return limit is not None and elapsed_seconds >= limit
