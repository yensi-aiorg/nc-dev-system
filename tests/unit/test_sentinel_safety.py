"""Tests for SentinelSafetyGate."""
from __future__ import annotations


def _report(service: str = "svc", file: str = "app.py", function: str = "parse", etype: str = "ERR"):
    from datetime import datetime, timezone

    from ncdev.core.models import (
        ErrorContext,
        ErrorDetail,
        ErrorFrequency,
        ErrorSeverity,
        ErrorSource,
        SentinelFailureReport,
        ServiceInfo,
    )

    return SentinelFailureReport(
        report_id="rep-1",
        service=ServiceInfo(
            name=service,
            version="1",
            git_sha="x",
            git_repo="git@github.com:o/r.git",
        ),
        source=ErrorSource.BACKEND,
        severity=ErrorSeverity.HIGH,
        error=ErrorDetail(
            error_type=etype,
            error_code="E1",
            message="boom",
            file=file,
            function=function,
        ),
        frequency=ErrorFrequency(
            last_hour=1,
            last_24h=1,
            first_seen=datetime.now(timezone.utc),
        ),
        context=ErrorContext(),
        detected_at=datetime.now(timezone.utc),
    )


def test_preflight_allows_clean_service() -> None:
    from ncdev.core.sentinel_safety import SentinelSafetyGate

    gate = SentinelSafetyGate()
    assert gate.preflight(_report()).allowed is True


def test_preflight_blocks_when_circuit_tripped() -> None:
    from ncdev.core.sentinel_safety import SentinelSafetyGate

    gate = SentinelSafetyGate()
    for _ in range(3):
        gate.circuit_breaker.record_failure("svc")
    v = gate.preflight(_report(service="svc"))
    assert v.allowed is False
    assert "circuit" in v.reason.lower()


def test_preflight_blocks_when_cooling_down() -> None:
    from ncdev.core.sentinel_safety import SentinelSafetyGate

    gate = SentinelSafetyGate()
    gate.cooldown.record_failure("svc")
    v = gate.preflight(_report(service="svc"))
    assert v.allowed is False
    assert "cool" in v.reason.lower()


def test_preflight_blocks_duplicate_active_fix() -> None:
    from ncdev.core.sentinel_safety import SentinelSafetyGate

    gate = SentinelSafetyGate()
    report = _report()
    gate.claim(report, "run-1")
    v = gate.preflight(report)
    assert v.allowed is False
    assert "active" in v.reason.lower() or "duplicate" in v.reason.lower()


def test_release_clears_dedup_key() -> None:
    from ncdev.core.sentinel_safety import SentinelSafetyGate

    gate = SentinelSafetyGate()
    report = _report()
    gate.claim(report, "run-1")
    gate.release(report)
    assert gate.preflight(report).allowed is True


def test_check_scope_blocks_extra_protected_file() -> None:
    from ncdev.core.sentinel_safety import SentinelSafetyGate

    gate = SentinelSafetyGate()
    v = gate.check_scope(
        files_changed=1,
        lines_changed=5,
        changed_paths=["src/secrets/keys.py"],
        extra_protected=["src/secrets/"],
    )
    assert v.allowed is False
    assert "secrets" in v.reason.lower() or "protected" in v.reason.lower()


def test_check_scope_allows_within_limits() -> None:
    from ncdev.core.sentinel_safety import SentinelSafetyGate

    gate = SentinelSafetyGate()
    v = gate.check_scope(
        files_changed=2,
        lines_changed=30,
        changed_paths=["src/app.py", "tests/test_app.py"],
    )
    assert v.allowed is True


def test_record_outcome_failure_trips_then_success_resets() -> None:
    from ncdev.core.sentinel_safety import SentinelSafetyGate

    gate = SentinelSafetyGate()
    report = _report(service="svc")
    for _ in range(3):
        gate.record_outcome(report, success=False)
    assert gate.circuit_breaker.is_tripped("svc") is True
    gate.record_outcome(report, success=True)
    assert gate.circuit_breaker.is_tripped("svc") is False
