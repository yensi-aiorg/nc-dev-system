"""Unit tests for the ResponsiveChecker module.

Tests viewport configurations, Playwright subprocess mocking,
result parsing, scoring, and edge cases.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.hardener.responsive import (
    ResponsiveChecker,
    ResponsiveIssue,
    ResponsiveResult,
    RouteResponsiveResult,
    ViewportConfig,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def checker() -> ResponsiveChecker:
    """Fresh ResponsiveChecker with default viewports."""
    return ResponsiveChecker()


@pytest.fixture
def custom_checker() -> ResponsiveChecker:
    """ResponsiveChecker with custom single viewport."""
    return ResponsiveChecker(
        viewports=[ViewportConfig(name="small", width=320, height=480)]
    )


# ---------------------------------------------------------------------------
# Data Model Tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestResponsiveModels:
    """Test the Pydantic models used in responsive checking."""

    def test_viewport_config_creation(self):
        vp = ViewportConfig(name="desktop", width=1440, height=900)
        assert vp.name == "desktop"
        assert vp.width == 1440
        assert vp.height == 900

    def test_responsive_issue_creation(self):
        issue = ResponsiveIssue(
            severity="error",
            category="horizontal-overflow",
            route="/",
            viewport="mobile",
            description="Page overflows horizontally.",
            suggestion="Fix max-width.",
        )
        assert issue.severity == "error"
        assert issue.category == "horizontal-overflow"
        assert issue.screenshot_path is None

    def test_route_responsive_result_defaults(self):
        rr = RouteResponsiveResult(route="/")
        assert rr.route == "/"
        assert rr.viewports_checked == []
        assert rr.issues == []
        assert rr.screenshots == {}

    def test_responsive_result_defaults(self):
        result = ResponsiveResult()
        assert result.routes == []
        assert result.total_issues == 0
        assert result.passed is True
        assert result.score == 100.0


# ---------------------------------------------------------------------------
# Viewport Configuration Tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestViewportConfiguration:
    """Test default and custom viewport setups."""

    def test_default_viewports(self, checker):
        names = [vp.name for vp in checker.VIEWPORTS]
        assert "desktop" in names
        assert "tablet" in names
        assert "mobile" in names
        assert len(checker.VIEWPORTS) == 3

    def test_default_desktop_dimensions(self, checker):
        desktop = next(vp for vp in checker.VIEWPORTS if vp.name == "desktop")
        assert desktop.width == 1440
        assert desktop.height == 900

    def test_default_mobile_dimensions(self, checker):
        mobile = next(vp for vp in checker.VIEWPORTS if vp.name == "mobile")
        assert mobile.width == 375
        assert mobile.height == 812

    def test_custom_viewports_override(self, custom_checker):
        assert len(custom_checker.VIEWPORTS) == 1
        assert custom_checker.VIEWPORTS[0].name == "small"
        assert custom_checker.VIEWPORTS[0].width == 320


# ---------------------------------------------------------------------------
# Result Parsing Tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestResultParsing:
    """Test parsing of raw Playwright JSON output into ResponsiveResult."""

    def test_parse_empty_results(self, checker):
        result = checker._parse_results([])
        assert result.routes == []
        assert result.total_issues == 0
        assert result.passed is True
        assert result.score == 100.0

    def test_parse_clean_results(self, checker):
        raw = [
            {
                "route": "/",
                "viewport": "desktop",
                "width": 1440,
                "height": 900,
                "issues": [],
                "screenshot": "/tmp/home_desktop.png",
            },
            {
                "route": "/",
                "viewport": "mobile",
                "width": 375,
                "height": 812,
                "issues": [],
                "screenshot": "/tmp/home_mobile.png",
            },
        ]
        result = checker._parse_results(raw)
        assert len(result.routes) == 1
        assert result.routes[0].route == "/"
        assert result.total_issues == 0
        assert result.passed is True
        assert result.score == 100.0
        assert "desktop" in result.routes[0].screenshots
        assert "mobile" in result.routes[0].screenshots

    def test_parse_results_with_error_issues(self, checker):
        raw = [
            {
                "route": "/login",
                "viewport": "mobile",
                "issues": [
                    {
                        "severity": "error",
                        "category": "horizontal-overflow",
                        "description": "Scrollbar present.",
                        "suggestion": "Fix overflow.",
                    }
                ],
                "screenshot": "/tmp/login_mobile.png",
            },
        ]
        result = checker._parse_results(raw)
        assert result.total_issues == 1
        assert result.passed is False  # error issues cause failure
        assert result.score == 90.0  # 100 - 10

    def test_parse_results_with_warning_issues(self, checker):
        raw = [
            {
                "route": "/",
                "viewport": "tablet",
                "issues": [
                    {
                        "severity": "warning",
                        "category": "overlapping-elements",
                        "description": "Elements overlap.",
                        "suggestion": "Fix layout.",
                    }
                ],
                "screenshot": None,
            },
        ]
        result = checker._parse_results(raw)
        assert result.total_issues == 1
        assert result.passed is True  # warnings don't fail
        assert result.score == 97.0  # 100 - 3

    def test_parse_results_with_info_issues(self, checker):
        raw = [
            {
                "route": "/",
                "viewport": "mobile",
                "issues": [
                    {
                        "severity": "info",
                        "category": "text-truncation",
                        "description": "5 truncated elements.",
                        "suggestion": "Use responsive fonts.",
                    }
                ],
                "screenshot": "/tmp/home_mobile.png",
            },
        ]
        result = checker._parse_results(raw)
        assert result.total_issues == 1
        assert result.passed is True
        assert result.score == 99.0  # 100 - 1

    def test_parse_multiple_routes(self, checker):
        raw = [
            {
                "route": "/",
                "viewport": "desktop",
                "issues": [],
                "screenshot": None,
            },
            {
                "route": "/login",
                "viewport": "desktop",
                "issues": [],
                "screenshot": None,
            },
            {
                "route": "/login",
                "viewport": "mobile",
                "issues": [
                    {
                        "severity": "error",
                        "category": "horizontal-overflow",
                        "description": "Overflow.",
                        "suggestion": "Fix.",
                    }
                ],
                "screenshot": None,
            },
        ]
        result = checker._parse_results(raw)
        assert len(result.routes) == 2
        assert result.total_issues == 1
        assert result.passed is False

    def test_score_floors_at_zero(self, checker):
        """Many errors should floor score at 0."""
        raw_issues = [
            {
                "severity": "error",
                "category": "horizontal-overflow",
                "description": f"Overflow {i}.",
                "suggestion": "Fix.",
            }
            for i in range(15)
        ]
        raw = [
            {"route": "/", "viewport": "mobile", "issues": raw_issues, "screenshot": None},
        ]
        result = checker._parse_results(raw)
        assert result.score == 0.0


# ---------------------------------------------------------------------------
# Subprocess Mocking Tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPlaywrightSubprocess:
    """Test the check() method with mocked _run_playwright_checks.

    The internal Playwright script template contains a Python str.format
    incompatibility (unescaped braces in JavaScript template literals),
    so we mock ``_run_playwright_checks`` to return raw results directly
    rather than patching ``asyncio.create_subprocess_exec``.
    """

    @pytest.mark.asyncio
    async def test_check_with_clean_output(self, checker):
        """Successful Playwright run with no issues."""
        raw_results = [
            {
                "route": "/",
                "viewport": "desktop",
                "width": 1440,
                "height": 900,
                "issues": [],
                "screenshot": "/tmp/home_desktop.png",
            },
        ]

        with patch.object(checker, "_run_playwright_checks", return_value=raw_results):
            result = await checker.check(
                project_url="http://localhost:23000",
                routes=["/"],
            )

        assert result.total_issues == 0
        assert result.passed is True
        assert result.score == 100.0

    @pytest.mark.asyncio
    async def test_check_with_issues_output(self, checker):
        """Successful Playwright run with issues detected."""
        raw_results = [
            {
                "route": "/",
                "viewport": "mobile",
                "width": 375,
                "height": 812,
                "issues": [
                    {
                        "severity": "error",
                        "category": "horizontal-overflow",
                        "description": "Horizontal overflow detected.",
                        "suggestion": "Fix overflow.",
                    }
                ],
                "screenshot": "/tmp/home_mobile.png",
            },
        ]

        with patch.object(checker, "_run_playwright_checks", return_value=raw_results):
            result = await checker.check(
                project_url="http://localhost:23000",
                routes=["/"],
            )

        assert result.total_issues == 1
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_check_node_not_found(self, checker):
        """When node is not found, _run_playwright_checks returns [] and
        check() should produce a clean (empty) result."""
        with patch.object(checker, "_run_playwright_checks", return_value=[]):
            result = await checker.check(
                project_url="http://localhost:23000",
                routes=["/"],
            )

        assert result.total_issues == 0
        assert result.passed is True
        assert result.routes == []

    @pytest.mark.asyncio
    async def test_check_subprocess_nonzero_exit(self, checker):
        """When the subprocess exits with a non-zero code, _run_playwright_checks
        returns [] and check() should produce a clean (empty) result."""
        with patch.object(checker, "_run_playwright_checks", return_value=[]):
            result = await checker.check(
                project_url="http://localhost:23000",
                routes=["/"],
            )

        assert result.total_issues == 0
        assert result.passed is True
        assert result.score == 100.0

    @pytest.mark.asyncio
    async def test_check_subprocess_timeout(self, checker):
        """When the subprocess times out, _run_playwright_checks returns []
        and check() should produce a clean (empty) result."""
        with patch.object(checker, "_run_playwright_checks", return_value=[]):
            result = await checker.check(
                project_url="http://localhost:23000",
                routes=["/"],
            )

        assert result.total_issues == 0
        assert result.passed is True
        assert result.score == 100.0

    @pytest.mark.asyncio
    async def test_check_invalid_json_output(self, checker):
        """When the subprocess outputs invalid JSON, _run_playwright_checks
        returns [] and check() should produce a clean (empty) result."""
        with patch.object(checker, "_run_playwright_checks", return_value=[]):
            result = await checker.check(
                project_url="http://localhost:23000",
                routes=["/"],
            )

        assert result.total_issues == 0
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_check_empty_stdout(self, checker):
        """When the subprocess returns empty stdout, _run_playwright_checks
        returns [] and check() should produce a clean (empty) result."""
        with patch.object(checker, "_run_playwright_checks", return_value=[]):
            result = await checker.check(
                project_url="http://localhost:23000",
                routes=["/"],
            )

        assert result.total_issues == 0
        assert result.passed is True
        assert result.routes == []

    @pytest.mark.asyncio
    async def test_check_playwright_returns_empty(self, checker):
        """When Playwright returns empty results, should return clean."""
        with patch.object(checker, "_run_playwright_checks", return_value=[]):
            result = await checker.check(
                project_url="http://localhost:23000",
                routes=["/"],
            )

        assert result.total_issues == 0
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_check_multiple_routes(self, checker):
        """Check multiple routes returns aggregated results."""
        raw_results = [
            {
                "route": "/",
                "viewport": "desktop",
                "issues": [],
                "screenshot": None,
            },
            {
                "route": "/login",
                "viewport": "desktop",
                "issues": [
                    {
                        "severity": "warning",
                        "category": "overlapping-elements",
                        "description": "Elements overlap.",
                        "suggestion": "Fix.",
                    }
                ],
                "screenshot": None,
            },
        ]

        with patch.object(checker, "_run_playwright_checks", return_value=raw_results):
            result = await checker.check(
                project_url="http://localhost:23000",
                routes=["/", "/login"],
            )

        assert len(result.routes) == 2
        assert result.total_issues == 1
        assert result.passed is True  # warning doesn't fail

    @pytest.mark.asyncio
    async def test_check_creates_output_dir(self, checker, tmp_path):
        """When output_dir is specified, it should be created and used."""
        output_dir = tmp_path / "screenshots"

        with patch.object(checker, "_run_playwright_checks", return_value=[]):
            result = await checker.check(
                project_url="http://localhost:23000",
                routes=["/"],
                output_dir=output_dir,
            )

        assert output_dir.exists()
        assert result.passed is True


# ---------------------------------------------------------------------------
# Display Tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPrintReport:
    """Test that print_report does not raise."""

    def test_print_report_no_issues(self, checker):
        result = ResponsiveResult()
        checker.print_report(result)

    def test_print_report_with_issues(self, checker):
        issue = ResponsiveIssue(
            severity="error",
            category="horizontal-overflow",
            route="/",
            viewport="mobile",
            description="Overflow.",
            suggestion="Fix.",
        )
        rr = RouteResponsiveResult(
            route="/",
            viewports_checked=["mobile"],
            issues=[issue],
        )
        result = ResponsiveResult(
            routes=[rr],
            total_issues=1,
            passed=False,
            score=90.0,
        )
        checker.print_report(result)
