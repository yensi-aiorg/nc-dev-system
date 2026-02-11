"""Unit tests for code review (src.builder.reviewer).

Tests cover:
- BuildReviewer.review() with various scenarios
- Test result parsing (_parse_pytest_output, _parse_vitest_output)
- Prohibited pattern scanning
- Expected file checking
- Git diff stats and changed file detection
- quick_check convenience method
- ReviewResult data structure
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.builder.reviewer import (
    BuildReviewer,
    ReviewIssue,
    ReviewResult,
    TestRunResult,
    _parse_pytest_output,
    _parse_vitest_output,
    _run_command,
)


# ---------------------------------------------------------------------------
# _parse_pytest_output
# ---------------------------------------------------------------------------

class TestParsePytestOutput:
    @pytest.mark.unit
    def test_all_passed(self):
        output = "========================= 5 passed in 1.23s ========================="
        result = _parse_pytest_output(output)
        assert result.passed == 5
        assert result.failed == 0
        assert result.total == 5
        assert result.success is True

    @pytest.mark.unit
    def test_mixed_results(self):
        output = "=================== 3 passed, 2 failed, 1 error in 4.56s ==================="
        result = _parse_pytest_output(output)
        assert result.passed == 3
        assert result.failed == 2
        assert result.errors == 1
        assert result.total == 6
        assert result.success is False

    @pytest.mark.unit
    def test_with_skipped(self):
        output = "=================== 10 passed, 2 skipped in 0.5s ==================="
        result = _parse_pytest_output(output)
        assert result.passed == 10
        assert result.skipped == 2
        assert result.total == 12
        assert result.success is True

    @pytest.mark.unit
    def test_no_tests_ran(self):
        output = "========================== no tests ran in 0.01s =========================="
        result = _parse_pytest_output(output)
        assert result.success is True

    @pytest.mark.unit
    def test_error_in_output(self):
        output = "FAILED some_test\nError: something broke"
        result = _parse_pytest_output(output)
        assert result.success is False

    @pytest.mark.unit
    def test_empty_output(self):
        result = _parse_pytest_output("")
        assert result.total == 0
        assert result.output == ""


# ---------------------------------------------------------------------------
# _parse_vitest_output
# ---------------------------------------------------------------------------

class TestParseVitestOutput:
    @pytest.mark.unit
    def test_all_passed(self):
        output = "Tests  5 passed (5)"
        result = _parse_vitest_output(output)
        assert result.passed == 5
        assert result.total == 5
        assert result.success is True

    @pytest.mark.unit
    def test_mixed_results(self):
        output = "Tests  3 passed | 2 failed (5)"
        result = _parse_vitest_output(output)
        assert result.passed == 3
        assert result.failed == 2
        assert result.total == 5
        assert result.success is False

    @pytest.mark.unit
    def test_with_skipped(self):
        output = "Tests  4 passed | 1 skipped (5)"
        result = _parse_vitest_output(output)
        assert result.passed == 4
        assert result.skipped == 1
        assert result.total == 5
        assert result.success is True

    @pytest.mark.unit
    def test_fallback_fail_indicator(self):
        output = "FAIL src/tests/component.test.tsx"
        result = _parse_vitest_output(output)
        assert result.success is False

    @pytest.mark.unit
    def test_fallback_pass_indicator(self):
        output = "PASS src/tests/component.test.tsx"
        result = _parse_vitest_output(output)
        assert result.success is True


# ---------------------------------------------------------------------------
# ReviewResult
# ---------------------------------------------------------------------------

class TestReviewResult:
    @pytest.mark.unit
    def test_summary_passed(self):
        result = ReviewResult(
            passed=True,
            files_changed=["a.py", "b.ts"],
            test_results={"total": {"passed": 10, "failed": 0}},
        )
        summary = result.summary()
        assert "PASSED" in summary
        assert "2" in summary

    @pytest.mark.unit
    def test_summary_failed(self):
        result = ReviewResult(
            passed=False,
            issues=["Test failure", "TODO found"],
        )
        summary = result.summary()
        assert "FAILED" in summary
        assert "2" in summary


# ---------------------------------------------------------------------------
# BuildReviewer._check_expected_files
# ---------------------------------------------------------------------------

class TestCheckExpectedFiles:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_all_files_present(self, tmp_path: Path):
        (tmp_path / "a.py").write_text("code")
        (tmp_path / "b.py").write_text("code")

        reviewer = BuildReviewer()
        missing = await reviewer._check_expected_files(tmp_path, ["a.py", "b.py"])
        assert missing == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_missing_files_reported(self, tmp_path: Path):
        (tmp_path / "a.py").write_text("code")

        reviewer = BuildReviewer()
        missing = await reviewer._check_expected_files(tmp_path, ["a.py", "c.py"])
        assert "c.py" in missing
        assert "a.py" not in missing


# ---------------------------------------------------------------------------
# BuildReviewer._scan_prohibited_patterns
# ---------------------------------------------------------------------------

class TestScanProhibitedPatterns:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_detects_todo_comment(self, tmp_path: Path):
        code_file = tmp_path / "service.py"
        code_file.write_text("# TODO: implement this\ndef func(): pass\n")

        reviewer = BuildReviewer()
        issues = await reviewer._scan_prohibited_patterns(tmp_path, ["service.py"])

        assert len(issues) > 0
        assert any("TODO" in i.message for i in issues)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_detects_console_log(self, tmp_path: Path):
        code_file = tmp_path / "component.tsx"
        code_file.write_text('console.log("debug")\n')

        reviewer = BuildReviewer()
        issues = await reviewer._scan_prohibited_patterns(tmp_path, ["component.tsx"])

        assert len(issues) > 0
        assert any("console.log" in i.message for i in issues)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_clean_code_no_issues(self, tmp_path: Path):
        code_file = tmp_path / "clean.py"
        code_file.write_text("def add(a: int, b: int) -> int:\n    return a + b\n")

        reviewer = BuildReviewer()
        issues = await reviewer._scan_prohibited_patterns(tmp_path, ["clean.py"])

        assert issues == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_skips_non_source_files(self, tmp_path: Path):
        txt_file = tmp_path / "notes.txt"
        txt_file.write_text("# TODO: this should be skipped\n")

        reviewer = BuildReviewer()
        issues = await reviewer._scan_prohibited_patterns(tmp_path, ["notes.txt"])

        assert issues == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_detects_placeholder_pass(self, tmp_path: Path):
        code_file = tmp_path / "stub.py"
        code_file.write_text("def handler():\n    pass  # placeholder\n")

        reviewer = BuildReviewer()
        issues = await reviewer._scan_prohibited_patterns(tmp_path, ["stub.py"])

        assert len(issues) > 0

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_detects_not_yet_implemented(self, tmp_path: Path):
        code_file = tmp_path / "page.tsx"
        code_file.write_text('export default () => <div>Not yet implemented</div>\n')

        reviewer = BuildReviewer()
        issues = await reviewer._scan_prohibited_patterns(tmp_path, ["page.tsx"])

        assert len(issues) > 0
        assert any("Not yet implemented" in i.message for i in issues)


# ---------------------------------------------------------------------------
# BuildReviewer.review (full integration mock)
# ---------------------------------------------------------------------------

class TestBuildReviewerReview:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_review_all_passing(self, tmp_path: Path):
        reviewer = BuildReviewer()

        # Create a worktree with clean code
        wt = tmp_path / "worktree"
        wt.mkdir()
        (wt / "clean.py").write_text("def greet(): return 'hello'\n")

        # Mock all subprocess calls
        async def _mock_cmd(*args, cwd=None, timeout=120.0, env=None):
            cmd = " ".join(str(a) for a in args)
            if "diff --stat" in cmd:
                return (0, "clean.py | 1 +", "")
            if "diff --name-only" in cmd:
                return (0, "clean.py", "")
            if "pytest" in cmd:
                return (0, "=== 3 passed in 0.5s ===", "")
            if "vitest" in cmd:
                return (-1, "", "Command not found: npx")
            if "ruff" in cmd:
                return (-1, "", "Command not found: ruff")
            if "eslint" in cmd:
                return (-1, "", "Command not found: npx")
            return (0, "", "")

        with patch("src.builder.reviewer._run_command", side_effect=_mock_cmd):
            result = await reviewer.review(
                str(wt),
                {"name": "test-feature", "expected_files": ["clean.py"]},
            )

        assert result.passed is True
        assert "clean.py" in result.files_changed

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_review_with_test_failure(self, tmp_path: Path):
        reviewer = BuildReviewer()

        wt = tmp_path / "worktree"
        wt.mkdir()
        backend_dir = wt / "backend" / "tests"
        backend_dir.mkdir(parents=True)

        async def _mock_cmd(*args, cwd=None, timeout=120.0, env=None):
            cmd = " ".join(str(a) for a in args)
            if "diff --name-only" in cmd:
                return (0, "file.py", "")
            if "diff --stat" in cmd:
                return (0, "file.py | 1 +", "")
            if "pytest" in cmd:
                return (1, "=== 2 passed, 1 failed in 1.0s ===", "")
            if "status" in cmd:
                return (0, "", "")
            return (0, "", "Command not found")

        with patch("src.builder.reviewer._run_command", side_effect=_mock_cmd):
            result = await reviewer.review(str(wt), {"name": "feat"})

        assert result.passed is False
        assert any("failed" in issue.lower() for issue in result.issues)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_review_no_files_changed(self, tmp_path: Path):
        reviewer = BuildReviewer()
        wt = tmp_path / "worktree"
        wt.mkdir()

        async def _mock_cmd(*args, cwd=None, timeout=120.0, env=None):
            return (1, "", "")

        with patch("src.builder.reviewer._run_command", side_effect=_mock_cmd):
            result = await reviewer.review(str(wt), {"name": "feat"})

        assert result.passed is False
        assert any("No files were changed" in i for i in result.issues)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_review_missing_expected_files(self, tmp_path: Path):
        reviewer = BuildReviewer()
        wt = tmp_path / "worktree"
        wt.mkdir()

        async def _mock_cmd(*args, cwd=None, timeout=120.0, env=None):
            cmd = " ".join(str(a) for a in args)
            if "diff --name-only" in cmd:
                return (0, "other.py", "")
            if "diff --stat" in cmd:
                return (0, "other.py | 1 +", "")
            return (0, "", "Command not found")

        with patch("src.builder.reviewer._run_command", side_effect=_mock_cmd):
            result = await reviewer.review(
                str(wt),
                {"name": "feat", "expected_files": ["missing.py"]},
            )

        assert any("missing.py" in i for i in result.issues)


# ---------------------------------------------------------------------------
# BuildReviewer.quick_check
# ---------------------------------------------------------------------------

class TestBuildReviewerQuickCheck:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_quick_check_passes_clean_code(self, tmp_path: Path):
        reviewer = BuildReviewer()
        wt = tmp_path / "worktree"
        wt.mkdir()
        (wt / "clean.py").write_text("x = 1\n")

        async def _mock_cmd(*args, cwd=None, timeout=120.0, env=None):
            cmd = " ".join(str(a) for a in args)
            if "diff --name-only" in cmd:
                return (0, "clean.py", "")
            if "pytest" in cmd:
                return (-1, "", "Command not found: python")
            if "vitest" in cmd:
                return (-1, "", "Command not found: npx")
            if "status" in cmd:
                return (0, "", "")
            return (0, "", "")

        with patch("src.builder.reviewer._run_command", side_effect=_mock_cmd):
            result = await reviewer.quick_check(str(wt))

        assert result is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_quick_check_fails_with_todo(self, tmp_path: Path):
        reviewer = BuildReviewer()
        wt = tmp_path / "worktree"
        wt.mkdir()
        (wt / "bad.py").write_text("# TODO: fix this\n")

        async def _mock_cmd(*args, cwd=None, timeout=120.0, env=None):
            cmd = " ".join(str(a) for a in args)
            if "diff --name-only" in cmd:
                return (0, "bad.py", "")
            return (0, "", "Command not found")

        with patch("src.builder.reviewer._run_command", side_effect=_mock_cmd):
            result = await reviewer.quick_check(str(wt))

        assert result is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_quick_check_fails_no_changes(self, tmp_path: Path):
        reviewer = BuildReviewer()
        wt = tmp_path / "worktree"
        wt.mkdir()

        async def _mock_cmd(*args, cwd=None, timeout=120.0, env=None):
            return (1, "", "")

        with patch("src.builder.reviewer._run_command", side_effect=_mock_cmd):
            result = await reviewer.quick_check(str(wt))

        assert result is False
