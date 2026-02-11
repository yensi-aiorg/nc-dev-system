"""Unit tests for FallbackStrategy and related classes (src.builder.fallback).

Tests cover:
- BuildMethod enum
- BuildAttempt dataclass
- BuildResult dataclass and summary()
- SonnetRunner (mock subprocess)
- FallbackStrategy.execute_with_fallback
  - Codex succeeds on first attempt
  - Codex fails once, succeeds on retry
  - Codex double failure, Sonnet fallback succeeds
  - All builders fail (escalation to manual)
- FallbackStrategy.execute_parallel
- Review failure triggers retry
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.builder.codex_runner import CodexResult, CodexRunner, CodexRunnerError
from src.builder.fallback import (
    BuildAttempt,
    BuildMethod,
    BuildResult,
    FallbackStrategy,
    SonnetRunner,
)
from src.builder.reviewer import ReviewResult
from src.builder.worktree import WorktreeInfo


# ---------------------------------------------------------------------------
# BuildMethod enum
# ---------------------------------------------------------------------------


class TestBuildMethod:
    @pytest.mark.unit
    def test_values(self):
        assert BuildMethod.CODEX == "codex"
        assert BuildMethod.SONNET == "sonnet"
        assert BuildMethod.MANUAL == "manual"

    @pytest.mark.unit
    def test_string_comparison(self):
        assert BuildMethod.CODEX.value == "codex"


# ---------------------------------------------------------------------------
# BuildAttempt dataclass
# ---------------------------------------------------------------------------


class TestBuildAttempt:
    @pytest.mark.unit
    def test_defaults(self):
        attempt = BuildAttempt(
            method=BuildMethod.CODEX,
            attempt_number=1,
            success=False,
            started_at="2026-01-15T10:00:00Z",
            duration_seconds=10.0,
        )
        assert attempt.errors == []
        assert attempt.review_passed is False
        assert attempt.files_created == []
        assert attempt.files_modified == []


# ---------------------------------------------------------------------------
# BuildResult dataclass
# ---------------------------------------------------------------------------


class TestBuildResult:
    @pytest.mark.unit
    def test_success_summary(self):
        result = BuildResult(
            success=True,
            feature_name="auth",
            method="codex",
            attempts=1,
            total_duration_seconds=30.0,
        )
        summary = result.summary()
        assert "auth" in summary
        assert "SUCCESS" in summary
        assert "codex" in summary
        assert "30.0s" in summary

    @pytest.mark.unit
    def test_failure_summary_with_errors(self):
        result = BuildResult(
            success=False,
            feature_name="tasks",
            method="manual",
            attempts=3,
            errors=["err1", "err2"],
            total_duration_seconds=120.5,
        )
        summary = result.summary()
        assert "FAILED" in summary
        assert "tasks" in summary
        assert "Errors: 2" in summary

    @pytest.mark.unit
    def test_defaults(self):
        result = BuildResult(
            success=True,
            feature_name="test",
            method="codex",
            attempts=1,
        )
        assert result.result == {}
        assert result.errors == []
        assert result.attempt_history == []
        assert result.review is None
        assert result.total_duration_seconds == 0.0


# ---------------------------------------------------------------------------
# SonnetRunner
# ---------------------------------------------------------------------------


class TestSonnetRunner:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_successful_execution(self, tmp_path: Path):
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        stdout_json = json.dumps({"result": "ok"})

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            return_value=(stdout_json.encode("utf-8"), b"")
        )
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            runner = SonnetRunner(timeout_seconds=30)
            result = await runner.run(
                prompt="Build the feature",
                worktree_path=str(worktree),
            )

        assert result.success is True
        assert result.exit_code == 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_worktree_not_found(self, tmp_path: Path):
        runner = SonnetRunner()
        result = await runner.run(
            prompt="Build something",
            worktree_path=str(tmp_path / "missing"),
        )
        assert result.success is False
        assert any("not found" in e for e in result.errors)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_binary_not_found(self, tmp_path: Path):
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("claude not found"),
        ):
            runner = SonnetRunner(claude_binary="claude-nonexistent")
            result = await runner.run(
                prompt="Build something",
                worktree_path=str(worktree),
            )

        assert result.success is False
        assert any("not found" in e for e in result.errors)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_permission_denied(self, tmp_path: Path):
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=PermissionError("no perms"),
        ):
            runner = SonnetRunner()
            result = await runner.run(
                prompt="Build something",
                worktree_path=str(worktree),
            )

        assert result.success is False
        assert any("Permission denied" in e for e in result.errors)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_timeout(self, tmp_path: Path):
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        mock_process = AsyncMock()
        mock_process.kill = MagicMock()
        mock_process.returncode = None

        async def mock_communicate():
            return (b"", b"")

        mock_process.communicate = mock_communicate

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
                runner = SonnetRunner(timeout_seconds=1)
                result = await runner.run(
                    prompt="Build something",
                    worktree_path=str(worktree),
                )

        assert result.success is False
        assert any("timed out" in e for e in result.errors)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_nonzero_exit(self, tmp_path: Path):
        worktree = tmp_path / "worktree"
        worktree.mkdir()

        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(
            return_value=(b"", b"ERROR: compilation failed")
        )
        mock_process.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            runner = SonnetRunner()
            result = await runner.run(
                prompt="Build something",
                worktree_path=str(worktree),
            )

        assert result.success is False
        assert result.exit_code == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_available_true(self):
        mock_process = AsyncMock()
        mock_process.communicate = AsyncMock(return_value=(b"claude v1.0", b""))
        mock_process.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            with patch("asyncio.wait_for", return_value=(b"claude v1.0", b"")):
                runner = SonnetRunner()
                result = await runner.check_available()

        assert result is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_check_available_false(self):
        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError(),
        ):
            runner = SonnetRunner()
            result = await runner.check_available()

        assert result is False


# ---------------------------------------------------------------------------
# FallbackStrategy helpers
# ---------------------------------------------------------------------------


def _make_mock_worktree_manager(tmp_path: Path) -> MagicMock:
    """Create a mock WorktreeManager."""
    wt_path = tmp_path / "worktree"
    wt_path.mkdir(exist_ok=True)
    info = WorktreeInfo(
        name="test-feature",
        path=wt_path,
        branch="nc-dev/test-feature",
        feature="test feature",
    )
    mgr = MagicMock()
    mgr.create = AsyncMock(return_value=info)
    return mgr


def _make_mock_prompt_generator(tmp_path: Path) -> MagicMock:
    """Create a mock PromptGenerator."""
    prompt_path = tmp_path / "prompt.md"
    prompt_path.write_text("Build the feature")
    gen = MagicMock()
    gen.generate_and_save = AsyncMock(return_value=("Build the feature", prompt_path))
    return gen


def _make_codex_result(success: bool, errors: list[str] | None = None) -> CodexResult:
    """Create a CodexResult for testing."""
    return CodexResult(
        success=success,
        files_created=["app.py"] if success else [],
        files_modified=[],
        test_results={"passed": 5, "failed": 0} if success else {},
        errors=errors or [],
        duration_seconds=10.0,
        exit_code=0 if success else 1,
    )


def _make_review_result(passed: bool, issues: list[str] | None = None) -> ReviewResult:
    """Create a ReviewResult for testing."""
    return ReviewResult(
        passed=passed,
        issues=issues or [],
    )


# ---------------------------------------------------------------------------
# FallbackStrategy.execute_with_fallback
# ---------------------------------------------------------------------------


class TestFallbackStrategyExecute:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_codex_succeeds_first_attempt(self, tmp_path: Path):
        wt_mgr = _make_mock_worktree_manager(tmp_path)
        prompt_gen = _make_mock_prompt_generator(tmp_path)

        codex_runner = MagicMock()
        codex_runner.run = AsyncMock(return_value=_make_codex_result(success=True))

        reviewer = MagicMock()
        reviewer.review = AsyncMock(return_value=_make_review_result(passed=True))

        strategy = FallbackStrategy(
            worktree_manager=wt_mgr,
            prompt_generator=prompt_gen,
            codex_runner=codex_runner,
            reviewer=reviewer,
        )

        feature = {"name": "auth", "description": "Authentication"}
        result = await strategy.execute_with_fallback(
            feature=feature,
            architecture={"project_name": "test"},
            project_path=str(tmp_path),
        )

        assert result.success is True
        assert result.method == "codex"
        assert result.attempts == 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_codex_fails_then_succeeds_retry(self, tmp_path: Path):
        wt_mgr = _make_mock_worktree_manager(tmp_path)
        prompt_gen = _make_mock_prompt_generator(tmp_path)

        call_count = 0

        async def codex_run_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_codex_result(success=False, errors=["build error"])
            return _make_codex_result(success=True)

        codex_runner = MagicMock()
        codex_runner.run = AsyncMock(side_effect=codex_run_side_effect)

        reviewer = MagicMock()
        reviewer.review = AsyncMock(return_value=_make_review_result(passed=True))

        strategy = FallbackStrategy(
            worktree_manager=wt_mgr,
            prompt_generator=prompt_gen,
            codex_runner=codex_runner,
            reviewer=reviewer,
        )

        feature = {"name": "auth"}
        result = await strategy.execute_with_fallback(
            feature=feature,
            architecture={},
            project_path=str(tmp_path),
        )

        assert result.success is True
        assert result.method == "codex"
        assert result.attempts == 2

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_codex_double_failure_sonnet_succeeds(self, tmp_path: Path):
        wt_mgr = _make_mock_worktree_manager(tmp_path)
        prompt_gen = _make_mock_prompt_generator(tmp_path)

        codex_runner = MagicMock()
        codex_runner.run = AsyncMock(
            return_value=_make_codex_result(success=False, errors=["fail"])
        )

        reviewer = MagicMock()
        reviewer.review = AsyncMock(return_value=_make_review_result(passed=True))

        sonnet_runner = MagicMock()
        sonnet_runner.run = AsyncMock(
            return_value=CodexResult(
                success=True,
                files_created=["feature.py"],
                exit_code=0,
                duration_seconds=20.0,
            )
        )

        strategy = FallbackStrategy(
            worktree_manager=wt_mgr,
            prompt_generator=prompt_gen,
            codex_runner=codex_runner,
            reviewer=reviewer,
            sonnet_runner=sonnet_runner,
        )

        feature = {"name": "tasks"}
        result = await strategy.execute_with_fallback(
            feature=feature,
            architecture={},
            project_path=str(tmp_path),
            max_codex_attempts=2,
        )

        assert result.success is True
        assert result.method == "sonnet"
        assert result.attempts == 3  # 2 codex + 1 sonnet

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_all_fail_escalates_to_manual(self, tmp_path: Path):
        wt_mgr = _make_mock_worktree_manager(tmp_path)
        prompt_gen = _make_mock_prompt_generator(tmp_path)

        codex_runner = MagicMock()
        codex_runner.run = AsyncMock(
            return_value=_make_codex_result(success=False, errors=["codex fail"])
        )

        reviewer = MagicMock()
        reviewer.review = AsyncMock(return_value=_make_review_result(passed=False, issues=["bad code"]))

        sonnet_runner = MagicMock()
        sonnet_runner.run = AsyncMock(
            return_value=CodexResult(
                success=False,
                errors=["sonnet fail"],
                exit_code=1,
                duration_seconds=15.0,
            )
        )

        strategy = FallbackStrategy(
            worktree_manager=wt_mgr,
            prompt_generator=prompt_gen,
            codex_runner=codex_runner,
            reviewer=reviewer,
            sonnet_runner=sonnet_runner,
        )

        feature = {"name": "dashboard"}
        result = await strategy.execute_with_fallback(
            feature=feature,
            architecture={},
            project_path=str(tmp_path),
            max_codex_attempts=2,
        )

        assert result.success is False
        assert result.method == "manual"
        assert len(result.errors) > 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_codex_runner_error_handled(self, tmp_path: Path):
        wt_mgr = _make_mock_worktree_manager(tmp_path)
        prompt_gen = _make_mock_prompt_generator(tmp_path)

        codex_runner = MagicMock()
        codex_runner.run = AsyncMock(
            side_effect=CodexRunnerError("process crashed")
        )

        reviewer = MagicMock()
        reviewer.review = AsyncMock(return_value=_make_review_result(passed=True))

        sonnet_runner = MagicMock()
        sonnet_runner.run = AsyncMock(
            return_value=CodexResult(success=True, exit_code=0, duration_seconds=5.0)
        )

        strategy = FallbackStrategy(
            worktree_manager=wt_mgr,
            prompt_generator=prompt_gen,
            codex_runner=codex_runner,
            reviewer=reviewer,
            sonnet_runner=sonnet_runner,
        )

        feature = {"name": "auth"}
        result = await strategy.execute_with_fallback(
            feature=feature,
            architecture={},
            project_path=str(tmp_path),
            max_codex_attempts=2,
        )

        assert result.success is True
        assert result.method == "sonnet"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_review_failure_triggers_retry(self, tmp_path: Path):
        wt_mgr = _make_mock_worktree_manager(tmp_path)
        prompt_gen = _make_mock_prompt_generator(tmp_path)

        codex_runner = MagicMock()
        codex_runner.run = AsyncMock(return_value=_make_codex_result(success=True))

        review_call_count = 0

        async def review_side_effect(*args, **kwargs):
            nonlocal review_call_count
            review_call_count += 1
            if review_call_count == 1:
                return _make_review_result(passed=False, issues=["TODO found"])
            return _make_review_result(passed=True)

        reviewer = MagicMock()
        reviewer.review = AsyncMock(side_effect=review_side_effect)

        strategy = FallbackStrategy(
            worktree_manager=wt_mgr,
            prompt_generator=prompt_gen,
            codex_runner=codex_runner,
            reviewer=reviewer,
        )

        feature = {"name": "auth"}
        result = await strategy.execute_with_fallback(
            feature=feature,
            architecture={},
            project_path=str(tmp_path),
            max_codex_attempts=2,
        )

        assert result.success is True
        assert result.attempts == 2

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_sonnet_review_failure_escalates(self, tmp_path: Path):
        wt_mgr = _make_mock_worktree_manager(tmp_path)
        prompt_gen = _make_mock_prompt_generator(tmp_path)

        codex_runner = MagicMock()
        codex_runner.run = AsyncMock(
            return_value=_make_codex_result(success=False, errors=["fail"])
        )

        reviewer = MagicMock()
        reviewer.review = AsyncMock(
            return_value=_make_review_result(passed=False, issues=["bad output"])
        )

        sonnet_runner = MagicMock()
        sonnet_runner.run = AsyncMock(
            return_value=CodexResult(success=True, exit_code=0, duration_seconds=10.0)
        )

        strategy = FallbackStrategy(
            worktree_manager=wt_mgr,
            prompt_generator=prompt_gen,
            codex_runner=codex_runner,
            reviewer=reviewer,
            sonnet_runner=sonnet_runner,
        )

        feature = {"name": "tasks"}
        result = await strategy.execute_with_fallback(
            feature=feature,
            architecture={},
            project_path=str(tmp_path),
            max_codex_attempts=2,
        )

        assert result.success is False
        assert result.method == "manual"


# ---------------------------------------------------------------------------
# FallbackStrategy.execute_parallel
# ---------------------------------------------------------------------------


class TestFallbackStrategyParallel:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_parallel_all_succeed(self, tmp_path: Path):
        wt_mgr = _make_mock_worktree_manager(tmp_path)
        prompt_gen = _make_mock_prompt_generator(tmp_path)

        codex_runner = MagicMock()
        codex_runner.run = AsyncMock(return_value=_make_codex_result(success=True))

        reviewer = MagicMock()
        reviewer.review = AsyncMock(return_value=_make_review_result(passed=True))

        strategy = FallbackStrategy(
            worktree_manager=wt_mgr,
            prompt_generator=prompt_gen,
            codex_runner=codex_runner,
            reviewer=reviewer,
        )

        features = [
            {"name": "auth"},
            {"name": "tasks"},
            {"name": "dashboard"},
        ]

        results = await strategy.execute_parallel(
            features=features,
            architecture={},
            project_path=str(tmp_path),
            max_parallel=2,
        )

        assert len(results) == 3
        assert all(r.success for r in results)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_parallel_with_exception(self, tmp_path: Path):
        wt_mgr = _make_mock_worktree_manager(tmp_path)
        prompt_gen = _make_mock_prompt_generator(tmp_path)

        call_count = 0

        async def codex_run_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("Unexpected crash")
            return _make_codex_result(success=True)

        codex_runner = MagicMock()
        codex_runner.run = AsyncMock(side_effect=codex_run_side_effect)

        reviewer = MagicMock()
        reviewer.review = AsyncMock(return_value=_make_review_result(passed=True))

        strategy = FallbackStrategy(
            worktree_manager=wt_mgr,
            prompt_generator=prompt_gen,
            codex_runner=codex_runner,
            reviewer=reviewer,
        )

        features = [{"name": "auth"}, {"name": "tasks"}, {"name": "dashboard"}]

        results = await strategy.execute_parallel(
            features=features,
            architecture={},
            project_path=str(tmp_path),
            max_parallel=3,
        )

        assert len(results) == 3
        # At least one should have failed from the exception
        failed = [r for r in results if not r.success]
        assert len(failed) >= 1


# ---------------------------------------------------------------------------
# FallbackStrategy attempt history
# ---------------------------------------------------------------------------


class TestFallbackStrategyHistory:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_attempt_history_populated(self, tmp_path: Path):
        wt_mgr = _make_mock_worktree_manager(tmp_path)
        prompt_gen = _make_mock_prompt_generator(tmp_path)

        codex_runner = MagicMock()
        codex_runner.run = AsyncMock(return_value=_make_codex_result(success=True))

        reviewer = MagicMock()
        reviewer.review = AsyncMock(return_value=_make_review_result(passed=True))

        strategy = FallbackStrategy(
            worktree_manager=wt_mgr,
            prompt_generator=prompt_gen,
            codex_runner=codex_runner,
            reviewer=reviewer,
        )

        feature = {"name": "auth"}
        result = await strategy.execute_with_fallback(
            feature=feature,
            architecture={},
            project_path=str(tmp_path),
        )

        assert len(result.attempt_history) == 1
        assert result.attempt_history[0].method == BuildMethod.CODEX
        assert result.attempt_history[0].success is True
        assert result.attempt_history[0].review_passed is True
