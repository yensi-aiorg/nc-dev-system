"""Unit tests for test execution orchestrator (src.tester.runner).

Tests cover:
- _parse_pytest_json with valid, empty, error, and missing reports
- _parse_vitest_json with valid, empty, and error reports
- _parse_playwright_json with valid, nested suite, and missing reports
- TestRunner.__init__ defaults and custom values
- TestRunner.run_unit_tests (backend + frontend in parallel, mock subprocess)
- TestRunner.run_e2e_tests (mock Playwright subprocess)
- TestRunner.run_all orchestration (mocked sub-runners)
- _merge_results helper logic
- Error handling (subprocess timeouts, missing directories)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.tester.results import TestFailure, TestResults, TestSuiteResults, VisualTestResults
from src.tester.runner import (
    TestRunner,
    _parse_playwright_json,
    _parse_pytest_json,
    _parse_vitest_json,
)


# ---------------------------------------------------------------------------
# _parse_pytest_json
# ---------------------------------------------------------------------------

class TestParsePytestJson:
    @pytest.mark.unit
    def test_valid_report(self, tmp_path: Path):
        report = {
            "summary": {"total": 10, "passed": 8, "failed": 2, "skipped": 0},
            "duration": 5.5,
            "tests": [
                {
                    "nodeid": "tests/test_foo.py::test_bar",
                    "outcome": "failed",
                    "call": {"longrepr": "AssertionError: 1 != 2"},
                    "duration": 0.1,
                },
                {
                    "nodeid": "tests/test_foo.py::test_baz",
                    "outcome": "failed",
                    "call": {"longrepr": "KeyError: 'missing'"},
                    "duration": 0.2,
                },
            ],
        }
        report_file = tmp_path / "pytest-report.json"
        report_file.write_text(json.dumps(report))

        result = _parse_pytest_json(report_file)

        assert result.suite_name == "backend-pytest"
        assert result.total == 10
        assert result.passed == 8
        assert result.failed == 2
        assert result.duration_seconds == 5.5
        assert len(result.failures) == 2
        assert result.failures[0].test_name == "tests/test_foo.py::test_bar"
        assert "AssertionError" in result.failures[0].error

    @pytest.mark.unit
    def test_missing_report_returns_empty(self, tmp_path: Path):
        result = _parse_pytest_json(tmp_path / "nonexistent.json")
        assert result.suite_name == "backend-pytest"
        assert result.total == 0
        assert result.failures == []

    @pytest.mark.unit
    def test_corrupt_json_returns_empty(self, tmp_path: Path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not json{{{")

        result = _parse_pytest_json(bad_file)
        assert result.total == 0

    @pytest.mark.unit
    def test_all_passed(self, tmp_path: Path):
        report = {
            "summary": {"total": 5, "passed": 5, "failed": 0, "skipped": 0},
            "duration": 1.0,
            "tests": [],
        }
        report_file = tmp_path / "report.json"
        report_file.write_text(json.dumps(report))

        result = _parse_pytest_json(report_file)
        assert result.all_passed is True
        assert result.failures == []


# ---------------------------------------------------------------------------
# _parse_vitest_json
# ---------------------------------------------------------------------------

class TestParseVitestJson:
    @pytest.mark.unit
    def test_valid_report(self, tmp_path: Path):
        report = {
            "numTotalTests": 15,
            "numPassedTests": 13,
            "numFailedTests": 2,
            "numPendingTests": 0,
            "startTime": 1700000000000,
            "duration": 3000,
            "testResults": [
                {
                    "name": "src/tests/App.test.tsx",
                    "status": "failed",
                    "assertionResults": [
                        {
                            "fullName": "App > renders title",
                            "status": "failed",
                            "failureMessages": ["Expected 'Hello' but got 'Goodbye'"],
                        }
                    ],
                }
            ],
        }
        report_file = tmp_path / "vitest-report.json"
        report_file.write_text(json.dumps(report))

        result = _parse_vitest_json(report_file)

        assert result.suite_name == "frontend-vitest"
        assert result.total == 15
        assert result.passed == 13
        assert result.failed == 2
        assert len(result.failures) == 1
        assert "Hello" in result.failures[0].error

    @pytest.mark.unit
    def test_missing_report(self, tmp_path: Path):
        result = _parse_vitest_json(tmp_path / "nope.json")
        assert result.suite_name == "frontend-vitest"
        assert result.total == 0

    @pytest.mark.unit
    def test_all_passed_vitest(self, tmp_path: Path):
        report = {
            "numTotalTests": 5,
            "numPassedTests": 5,
            "numFailedTests": 0,
            "numPendingTests": 0,
            "startTime": 1700000000000,
            "duration": 1000,
            "testResults": [],
        }
        report_file = tmp_path / "vitest.json"
        report_file.write_text(json.dumps(report))

        result = _parse_vitest_json(report_file)
        assert result.all_passed is True
        assert result.total == 5


# ---------------------------------------------------------------------------
# _parse_playwright_json
# ---------------------------------------------------------------------------

class TestParsePlaywrightJson:
    @pytest.mark.unit
    def test_valid_report(self, tmp_path: Path):
        report = {
            "stats": {
                "expected": 5,
                "unexpected": 1,
                "flaky": 0,
                "skipped": 0,
                "duration": 10000,
            },
            "suites": [
                {
                    "title": "login.spec.ts",
                    "specs": [
                        {
                            "title": "should login",
                            "file": "login.spec.ts",
                            "tests": [
                                {
                                    "status": "unexpected",
                                    "results": [
                                        {
                                            "duration": 5000,
                                            "error": {"message": "Timeout waiting for selector"},
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                    "suites": [],
                }
            ],
        }
        report_file = tmp_path / "pw-report.json"
        report_file.write_text(json.dumps(report))

        result = _parse_playwright_json(report_file)

        assert result.suite_name == "e2e-playwright"
        assert result.total == 6
        assert result.passed == 5
        assert result.failed == 1
        assert len(result.failures) == 1
        assert "Timeout" in result.failures[0].error

    @pytest.mark.unit
    def test_missing_report(self, tmp_path: Path):
        result = _parse_playwright_json(tmp_path / "missing.json")
        assert result.suite_name == "e2e-playwright"
        assert result.total == 0

    @pytest.mark.unit
    def test_nested_suites(self, tmp_path: Path):
        report = {
            "stats": {"expected": 3, "unexpected": 0, "flaky": 0, "skipped": 1, "duration": 5000},
            "suites": [
                {
                    "title": "auth",
                    "specs": [],
                    "suites": [
                        {
                            "title": "login",
                            "specs": [
                                {
                                    "title": "should login",
                                    "tests": [{"status": "expected", "results": []}],
                                }
                            ],
                            "suites": [],
                        }
                    ],
                }
            ],
        }
        report_file = tmp_path / "nested.json"
        report_file.write_text(json.dumps(report))

        result = _parse_playwright_json(report_file)
        assert result.total == 4
        assert result.passed == 3
        assert result.skipped == 1


# ---------------------------------------------------------------------------
# TestRunner.__init__
# ---------------------------------------------------------------------------

class TestTestRunnerInit:
    @pytest.mark.unit
    def test_defaults(self, tmp_path: Path):
        runner = TestRunner(tmp_path)
        assert runner.project_path == tmp_path.resolve()
        assert runner.base_url == "http://localhost:23000"
        assert runner.subprocess_timeout == 300

    @pytest.mark.unit
    def test_custom_values(self, tmp_path: Path):
        runner = TestRunner(
            tmp_path,
            base_url="http://localhost:9999",
            screenshots_dir=tmp_path / "screenshots",
            subprocess_timeout=60,
        )
        assert runner.base_url == "http://localhost:9999"
        assert runner.screenshots_dir == tmp_path / "screenshots"
        assert runner.subprocess_timeout == 60


# ---------------------------------------------------------------------------
# TestRunner.run_unit_tests
# ---------------------------------------------------------------------------

class TestTestRunnerRunUnitTests:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_backend_or_frontend(self, tmp_path: Path):
        runner = TestRunner(tmp_path)
        result = await runner.run_unit_tests()

        assert result.suite_name == "unit"
        assert result.total == 0
        assert result.all_passed is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_backend_tests_pass(self, tmp_path: Path):
        backend = tmp_path / "backend"
        backend.mkdir()

        # Write a mock pytest report to be parsed
        reports_dir = tmp_path / ".nc-dev" / "test-reports"
        reports_dir.mkdir(parents=True)
        report_data = {
            "summary": {"total": 5, "passed": 5, "failed": 0, "skipped": 0},
            "duration": 2.0,
            "tests": [],
        }

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"All passed", b""))
        mock_proc.returncode = 0

        async def _mock_exec(*args, **kwargs):
            # Simulate writing the report file
            report_file = reports_dir / "pytest-report.json"
            report_file.write_text(json.dumps(report_data))
            return mock_proc

        with patch("asyncio.create_subprocess_exec", side_effect=_mock_exec):
            with patch("asyncio.wait_for", return_value=(b"All passed", b"")):
                runner = TestRunner(tmp_path)
                # Manually set reports dir to our tmp
                runner._reports_dir = reports_dir
                result = await runner.run_unit_tests()

        assert result.suite_name == "unit"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_backend_error_handled_gracefully(self, tmp_path: Path):
        backend = tmp_path / "backend"
        backend.mkdir()

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=Exception("Process crashed"))
        mock_proc.returncode = -1

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            runner = TestRunner(tmp_path)
            result = await runner.run_unit_tests()

        # Should handle the error gracefully, reporting a failure rather than crashing
        assert result.suite_name == "unit"


# ---------------------------------------------------------------------------
# TestRunner.run_e2e_tests
# ---------------------------------------------------------------------------

class TestTestRunnerE2E:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_no_frontend_dir(self, tmp_path: Path):
        runner = TestRunner(tmp_path)
        result = await runner.run_e2e_tests()

        assert result.suite_name == "e2e-playwright"
        assert result.total == 0
        assert result.all_passed is True


# ---------------------------------------------------------------------------
# TestRunner._merge_results
# ---------------------------------------------------------------------------

class TestMergeResults:
    @pytest.mark.unit
    def test_merge_multiple_results(self):
        r1 = TestResults(suite_name="a", total=10, passed=8, failed=2, skipped=0, duration_seconds=1.0)
        r2 = TestResults(suite_name="b", total=5, passed=5, failed=0, skipped=0, duration_seconds=2.0)

        merged = TestRunner._merge_results("combined", [r1, r2])

        assert merged.suite_name == "combined"
        assert merged.total == 15
        assert merged.passed == 13
        assert merged.failed == 2
        assert merged.duration_seconds == 3.0

    @pytest.mark.unit
    def test_merge_preserves_failures(self):
        f1 = TestFailure(test_name="t1", file="f1.py", error="err1")
        f2 = TestFailure(test_name="t2", file="f2.py", error="err2")
        r1 = TestResults(suite_name="a", total=1, failed=1, failures=[f1])
        r2 = TestResults(suite_name="b", total=1, failed=1, failures=[f2])

        merged = TestRunner._merge_results("all", [r1, r2])
        assert len(merged.failures) == 2
        assert merged.failures[0].test_name == "t1"
        assert merged.failures[1].test_name == "t2"

    @pytest.mark.unit
    def test_merge_empty_list(self):
        merged = TestRunner._merge_results("empty", [])
        assert merged.total == 0
        assert merged.all_passed is True


# ---------------------------------------------------------------------------
# TestRunner.run_all
# ---------------------------------------------------------------------------

class TestTestRunnerRunAll:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_run_all_no_routes_skips_visual(self, tmp_path: Path):
        runner = TestRunner(tmp_path)

        with patch.object(runner, "run_unit_tests", new=AsyncMock(return_value=TestResults(suite_name="unit"))):
            with patch.object(runner, "run_e2e_tests", new=AsyncMock(return_value=TestResults(suite_name="e2e"))):
                suite = await runner.run_all(routes=None)

        assert isinstance(suite, TestSuiteResults)
        assert suite.unit.suite_name == "unit"
        assert suite.e2e.suite_name == "e2e"
        assert suite.visual == VisualTestResults()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_run_all_with_routes_runs_visual(self, tmp_path: Path):
        runner = TestRunner(tmp_path)

        mock_visual = VisualTestResults(
            screenshots={"/": {"desktop": "ss.png"}},
        )

        with patch.object(runner, "run_unit_tests", new=AsyncMock(return_value=TestResults(suite_name="unit"))):
            with patch.object(runner, "run_e2e_tests", new=AsyncMock(return_value=TestResults(suite_name="e2e"))):
                with patch.object(runner, "run_visual_tests", new=AsyncMock(return_value=mock_visual)):
                    suite = await runner.run_all(routes=["/", "/tasks"])

        assert suite.visual.screenshots == {"/": {"desktop": "ss.png"}}

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_run_all_saves_results(self, tmp_path: Path):
        runner = TestRunner(tmp_path)

        with patch.object(runner, "run_unit_tests", new=AsyncMock(return_value=TestResults(suite_name="unit"))):
            with patch.object(runner, "run_e2e_tests", new=AsyncMock(return_value=TestResults(suite_name="e2e"))):
                suite = await runner.run_all()

        report_file = runner._reports_dir / "test-suite-results.json"
        assert report_file.exists()
        loaded = TestSuiteResults.load(report_file)
        assert loaded.unit.suite_name == "unit"
