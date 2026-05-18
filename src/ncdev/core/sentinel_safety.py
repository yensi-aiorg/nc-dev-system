"""Safety mechanisms for Sentinel fix mode: circuit breaker, scope guard, deduplication, cooldown."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from ncdev.core.models import SentinelFailureReport

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


@dataclass
class SafetyVerdict:
    allowed: bool
    reason: str = ""


@dataclass
class SentinelSafetyGate:
    """Single entry point for all Sentinel fix safety checks.

    Owns one CircuitBreaker, ScopeGuard, DeduplicationTracker, and
    CooldownTracker. The fix orchestrator calls preflight() before
    starting, check_scope() after the fix produces a diff, and
    record_outcome() when done.

    NOTE: the trackers hold in-process state. For the HTTP intake
    (multiple runs in one process) a single shared SentinelSafetyGate
    instance must be used across runs - construct it once at the
    intake-app level, not per-run. The orchestrator accepts an
    optional injected gate for exactly this reason.
    """

    circuit_breaker: CircuitBreaker = field(default_factory=CircuitBreaker)
    scope_guard: ScopeGuard = field(default_factory=ScopeGuard)
    dedup: DeduplicationTracker = field(default_factory=DeduplicationTracker)
    cooldown: CooldownTracker = field(default_factory=CooldownTracker)

    def preflight(self, report: SentinelFailureReport) -> SafetyVerdict:
        """Check before a fix run starts.

        Blocks when:
          - the circuit breaker is tripped for this service
          - the service is in cooldown after a recent failure
          - an identical fix (same dedup key) is already active
        Returns SafetyVerdict(allowed=False, reason=...) on the first
        block, else SafetyVerdict(allowed=True).
        """
        service = report.service.name
        if self.circuit_breaker.is_tripped(service):
            return SafetyVerdict(False, f"Circuit breaker tripped for service: {service}")
        if self.cooldown.is_cooling_down(service):
            return SafetyVerdict(False, f"Service is cooling down after recent failure: {service}")

        key = self._dedup_key(report)
        if self.dedup.is_active(key):
            return SafetyVerdict(False, f"Duplicate active fix already exists for key: {key}")

        return SafetyVerdict(True)

    def claim(self, report: SentinelFailureReport, run_id: str) -> None:
        """Mark this report's dedup key active for run_id.

        Call right after a successful preflight, before doing work.
        """
        self.dedup.mark_active(self._dedup_key(report), run_id)

    def release(self, report: SentinelFailureReport) -> None:
        """Clear the dedup key.

        Call in a finally-block so a crashed run doesn't wedge the key forever.
        """
        self.dedup.mark_complete(self._dedup_key(report))

    def check_scope(
        self,
        files_changed: int,
        lines_changed: int,
        changed_paths: list[str],
        *,
        extra_protected: list[str] | None = None,
    ) -> SafetyVerdict:
        """Wrap ScopeGuard.check.

        extra_protected (from the service config's protected_files) is checked
        in addition to the built-in _PROTECTED_PATTERNS - a changed path
        containing any extra_protected entry is blocked.
        """
        ok, reason = self.scope_guard.check(files_changed, lines_changed, changed_paths)
        if not ok:
            return SafetyVerdict(False, reason)

        protected_entries = [entry for entry in extra_protected or [] if entry]
        for path in changed_paths:
            for protected in protected_entries:
                if protected in path:
                    return SafetyVerdict(False, f"Protected file modified: {path}")

        return SafetyVerdict(True)

    def record_outcome(self, report: SentinelFailureReport, *, success: bool) -> None:
        """On success record circuit breaker success; on failure record failure."""
        service = report.service.name
        if success:
            self.circuit_breaker.record_success(service)
            return

        self.circuit_breaker.record_failure(service)
        self.cooldown.record_failure(service)

    @staticmethod
    def _dedup_key(report: SentinelFailureReport) -> str:
        return DeduplicationTracker.make_key(
            report.service.name,
            report.error.file,
            report.error.function,
            report.error.error_type,
        )
