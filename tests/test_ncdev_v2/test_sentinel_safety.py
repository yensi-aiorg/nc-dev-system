"""Tests for sentinel_safety: CircuitBreaker, ScopeGuard, DeduplicationTracker, CooldownTracker."""
from __future__ import annotations

import time

import pytest

from ncdev.v2.sentinel_safety import (
    CircuitBreaker,
    CooldownTracker,
    DeduplicationTracker,
    ScopeGuard,
)


# ---------------------------------------------------------------------------
# CircuitBreaker
# ---------------------------------------------------------------------------


class TestCircuitBreaker:
    def test_not_tripped_initially(self) -> None:
        cb = CircuitBreaker()
        assert not cb.is_tripped("svc-a")

    def test_trips_after_threshold_failures(self) -> None:
        cb = CircuitBreaker(threshold=3)
        cb.record_failure("svc-a")
        assert not cb.is_tripped("svc-a")
        cb.record_failure("svc-a")
        assert not cb.is_tripped("svc-a")
        cb.record_failure("svc-a")
        assert cb.is_tripped("svc-a")

    def test_resets_on_success(self) -> None:
        cb = CircuitBreaker(threshold=2)
        cb.record_failure("svc-a")
        cb.record_failure("svc-a")
        assert cb.is_tripped("svc-a")
        cb.record_success("svc-a")
        assert not cb.is_tripped("svc-a")

    def test_manual_reset(self) -> None:
        cb = CircuitBreaker(threshold=1)
        cb.record_failure("svc-a")
        assert cb.is_tripped("svc-a")
        cb.reset("svc-a")
        assert not cb.is_tripped("svc-a")

    def test_independent_per_service(self) -> None:
        cb = CircuitBreaker(threshold=2)
        cb.record_failure("svc-a")
        cb.record_failure("svc-a")
        assert cb.is_tripped("svc-a")
        assert not cb.is_tripped("svc-b")

    def test_auto_resets_after_reset_seconds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        base = 1000.0
        monkeypatch.setattr(time, "monotonic", lambda: base)
        cb = CircuitBreaker(threshold=1, reset_seconds=60)
        cb.record_failure("svc-a")
        assert cb.is_tripped("svc-a")

        monkeypatch.setattr(time, "monotonic", lambda: base + 61)
        assert not cb.is_tripped("svc-a")

    def test_still_tripped_before_reset_window(self, monkeypatch: pytest.MonkeyPatch) -> None:
        base = 1000.0
        monkeypatch.setattr(time, "monotonic", lambda: base)
        cb = CircuitBreaker(threshold=1, reset_seconds=60)
        cb.record_failure("svc-a")

        monkeypatch.setattr(time, "monotonic", lambda: base + 59)
        assert cb.is_tripped("svc-a")

    def test_failure_count_accumulates(self) -> None:
        cb = CircuitBreaker(threshold=5)
        for _ in range(4):
            cb.record_failure("svc-a")
        assert not cb.is_tripped("svc-a")
        cb.record_failure("svc-a")
        assert cb.is_tripped("svc-a")

    def test_reset_unknown_service_is_safe(self) -> None:
        cb = CircuitBreaker()
        cb.reset("unknown-svc")  # must not raise

    def test_record_success_unknown_service_is_safe(self) -> None:
        cb = CircuitBreaker()
        cb.record_success("unknown-svc")  # must not raise


# ---------------------------------------------------------------------------
# ScopeGuard
# ---------------------------------------------------------------------------


class TestScopeGuard:
    def test_accepts_small_changes(self) -> None:
        sg = ScopeGuard(max_files=10, max_lines=200)
        ok, msg = sg.check(3, 50, ["src/app.py", "src/utils.py"])
        assert ok
        assert msg == ""

    def test_rejects_too_many_files(self) -> None:
        sg = ScopeGuard(max_files=5)
        ok, msg = sg.check(6, 10, [])
        assert not ok
        assert "Too many files" in msg
        assert "6" in msg

    def test_accepts_exactly_max_files(self) -> None:
        sg = ScopeGuard(max_files=5)
        ok, _ = sg.check(5, 10, [])
        assert ok

    def test_rejects_too_many_lines(self) -> None:
        sg = ScopeGuard(max_lines=100)
        ok, msg = sg.check(1, 101, [])
        assert not ok
        assert "Too many lines" in msg
        assert "101" in msg

    def test_accepts_exactly_max_lines(self) -> None:
        sg = ScopeGuard(max_lines=100)
        ok, _ = sg.check(1, 100, [])
        assert ok

    def test_rejects_dockerfile(self) -> None:
        sg = ScopeGuard()
        ok, msg = sg.check(1, 5, ["services/api/Dockerfile"])
        assert not ok
        assert "Protected file" in msg

    def test_rejects_docker_compose(self) -> None:
        sg = ScopeGuard()
        ok, msg = sg.check(1, 5, ["docker-compose.yml"])
        assert not ok
        assert "Protected file" in msg

    def test_rejects_github_dir(self) -> None:
        sg = ScopeGuard()
        ok, msg = sg.check(1, 5, [".github/workflows/ci.yml"])
        assert not ok
        assert "Protected file" in msg

    def test_rejects_env_file(self) -> None:
        sg = ScopeGuard()
        ok, msg = sg.check(1, 5, [".env"])
        assert not ok
        assert "Protected file" in msg

    def test_rejects_env_development(self) -> None:
        sg = ScopeGuard()
        ok, msg = sg.check(1, 5, [".env.development"])
        assert not ok
        assert "Protected file" in msg

    def test_rejects_makefile(self) -> None:
        sg = ScopeGuard()
        ok, msg = sg.check(1, 5, ["Makefile"])
        assert not ok
        assert "Protected file" in msg

    def test_rejects_gitlab_ci(self) -> None:
        sg = ScopeGuard()
        ok, msg = sg.check(1, 5, [".gitlab-ci.yml"])
        assert not ok
        assert "Protected file" in msg

    def test_rejects_jenkinsfile(self) -> None:
        sg = ScopeGuard()
        ok, msg = sg.check(1, 5, ["Jenkinsfile"])
        assert not ok
        assert "Protected file" in msg

    def test_files_limit_checked_before_line_limit(self) -> None:
        sg = ScopeGuard(max_files=2, max_lines=10)
        ok, msg = sg.check(3, 500, [])
        assert not ok
        assert "Too many files" in msg

    def test_empty_paths_list(self) -> None:
        sg = ScopeGuard()
        ok, _ = sg.check(0, 0, [])
        assert ok


# ---------------------------------------------------------------------------
# DeduplicationTracker
# ---------------------------------------------------------------------------


class TestDeduplicationTracker:
    def test_not_active_initially(self) -> None:
        dt = DeduplicationTracker()
        key = DeduplicationTracker.make_key("svc", "file.py", "func", "ValueError")
        assert not dt.is_active(key)

    def test_active_after_mark(self) -> None:
        dt = DeduplicationTracker()
        key = DeduplicationTracker.make_key("svc", "file.py", "func", "ValueError")
        dt.mark_active(key, "run-001")
        assert dt.is_active(key)

    def test_not_active_after_complete(self) -> None:
        dt = DeduplicationTracker()
        key = DeduplicationTracker.make_key("svc", "file.py", "func", "ValueError")
        dt.mark_active(key, "run-001")
        dt.mark_complete(key)
        assert not dt.is_active(key)

    def test_mark_complete_unknown_key_is_safe(self) -> None:
        dt = DeduplicationTracker()
        dt.mark_complete("nonexistent-key")  # must not raise

    def test_make_key_with_none_file_and_function(self) -> None:
        key = DeduplicationTracker.make_key("svc", None, None, "RuntimeError")
        assert key == "svc:::RuntimeError"

    def test_make_key_is_deterministic(self) -> None:
        k1 = DeduplicationTracker.make_key("svc", "f.py", "fn", "Err")
        k2 = DeduplicationTracker.make_key("svc", "f.py", "fn", "Err")
        assert k1 == k2

    def test_different_keys_are_independent(self) -> None:
        dt = DeduplicationTracker()
        k1 = DeduplicationTracker.make_key("svc", "a.py", "fn", "Err")
        k2 = DeduplicationTracker.make_key("svc", "b.py", "fn", "Err")
        dt.mark_active(k1, "run-001")
        assert dt.is_active(k1)
        assert not dt.is_active(k2)

    def test_run_id_stored(self) -> None:
        dt = DeduplicationTracker()
        key = DeduplicationTracker.make_key("svc", "f.py", "fn", "Err")
        dt.mark_active(key, "run-xyz")
        assert dt._active[key] == "run-xyz"


# ---------------------------------------------------------------------------
# CooldownTracker
# ---------------------------------------------------------------------------


class TestCooldownTracker:
    def test_not_cooling_initially(self) -> None:
        ct = CooldownTracker()
        assert not ct.is_cooling_down("svc-a")

    def test_cooling_immediately_after_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        base = 1000.0
        monkeypatch.setattr(time, "monotonic", lambda: base)
        ct = CooldownTracker(cooldown_seconds=300)
        ct.record_failure("svc-a")
        assert ct.is_cooling_down("svc-a")

    def test_not_cooling_after_cooldown_expires(self, monkeypatch: pytest.MonkeyPatch) -> None:
        base = 1000.0
        monkeypatch.setattr(time, "monotonic", lambda: base)
        ct = CooldownTracker(cooldown_seconds=300)
        ct.record_failure("svc-a")

        monkeypatch.setattr(time, "monotonic", lambda: base + 301)
        assert not ct.is_cooling_down("svc-a")

    def test_still_cooling_before_expiry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        base = 1000.0
        monkeypatch.setattr(time, "monotonic", lambda: base)
        ct = CooldownTracker(cooldown_seconds=300)
        ct.record_failure("svc-a")

        monkeypatch.setattr(time, "monotonic", lambda: base + 299)
        assert ct.is_cooling_down("svc-a")

    def test_independent_per_service(self, monkeypatch: pytest.MonkeyPatch) -> None:
        base = 1000.0
        monkeypatch.setattr(time, "monotonic", lambda: base)
        ct = CooldownTracker(cooldown_seconds=300)
        ct.record_failure("svc-a")
        assert ct.is_cooling_down("svc-a")
        assert not ct.is_cooling_down("svc-b")

    def test_cooldown_resets_on_new_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        base = 1000.0
        monkeypatch.setattr(time, "monotonic", lambda: base)
        ct = CooldownTracker(cooldown_seconds=300)
        ct.record_failure("svc-a")

        # Advance close to expiry
        monkeypatch.setattr(time, "monotonic", lambda: base + 290)
        ct.record_failure("svc-a")

        # Advance past original expiry but not the new one
        monkeypatch.setattr(time, "monotonic", lambda: base + 320)
        assert ct.is_cooling_down("svc-a")

    def test_exactly_at_cooldown_boundary(self, monkeypatch: pytest.MonkeyPatch) -> None:
        base = 1000.0
        monkeypatch.setattr(time, "monotonic", lambda: base)
        ct = CooldownTracker(cooldown_seconds=300)
        ct.record_failure("svc-a")

        # Exactly at boundary: elapsed == cooldown_seconds → not cooling (< is False)
        monkeypatch.setattr(time, "monotonic", lambda: base + 300)
        assert not ct.is_cooling_down("svc-a")
