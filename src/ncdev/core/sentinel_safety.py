"""Safety mechanisms for Sentinel fix mode: circuit breaker, scope guard, deduplication, cooldown."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

_PROTECTED_PATTERNS = (
    "Dockerfile",
    "docker-compose",
    ".github/",
    ".gitlab-ci",
    "Jenkinsfile",
    "Makefile",
    ".env",
)


@dataclass
class CircuitBreaker:
    threshold: int = 3
    reset_seconds: int = 3600
    _failures: dict[str, int] = field(default_factory=dict)
    _tripped_at: dict[str, float] = field(default_factory=dict)

    def record_failure(self, service: str) -> None:
        self._failures[service] = self._failures.get(service, 0) + 1
        if self._failures[service] >= self.threshold:
            self._tripped_at[service] = time.monotonic()

    def record_success(self, service: str) -> None:
        self._failures.pop(service, None)
        self._tripped_at.pop(service, None)

    def is_tripped(self, service: str) -> bool:
        if service not in self._tripped_at:
            return False
        elapsed = time.monotonic() - self._tripped_at[service]
        if elapsed >= self.reset_seconds:
            self.reset(service)
            return False
        return True

    def reset(self, service: str) -> None:
        self._failures.pop(service, None)
        self._tripped_at.pop(service, None)


@dataclass
class ScopeGuard:
    max_files: int = 10
    max_lines: int = 200

    def check(
        self,
        files_changed: int,
        lines_changed: int,
        changed_paths: list[str],
    ) -> tuple[bool, str]:
        if files_changed > self.max_files:
            return False, f"Too many files changed: {files_changed} > {self.max_files}"
        if lines_changed > self.max_lines:
            return False, f"Too many lines changed: {lines_changed} > {self.max_lines}"
        for path in changed_paths:
            for pattern in _PROTECTED_PATTERNS:
                if pattern in path:
                    return False, f"Protected file modified: {path}"
        return True, ""


@dataclass
class DeduplicationTracker:
    _active: dict[str, str] = field(default_factory=dict)

    @staticmethod
    def make_key(service: str, file: str | None, function: str | None, error_type: str) -> str:
        return f"{service}:{file or ''}:{function or ''}:{error_type}"

    def is_active(self, key: str) -> bool:
        return key in self._active

    def mark_active(self, key: str, run_id: str) -> None:
        self._active[key] = run_id

    def mark_complete(self, key: str) -> None:
        self._active.pop(key, None)


@dataclass
class CooldownTracker:
    cooldown_seconds: int = 300
    _last_failure: dict[str, float] = field(default_factory=dict)

    def record_failure(self, service: str) -> None:
        self._last_failure[service] = time.monotonic()

    def is_cooling_down(self, service: str) -> bool:
        if service not in self._last_failure:
            return False
        elapsed = time.monotonic() - self._last_failure[service]
        return elapsed < self.cooldown_seconds
