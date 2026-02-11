"""Unit tests for the AccessibilityChecker module.

Tests axe-core Playwright subprocess mocking, static analysis fallback,
violation categorisation, scoring, and edge cases.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.hardener.accessibility import (
    AccessibilityChecker,
    AccessibilityResult,
    AccessibilityViolation,
    RouteAccessibility,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def checker() -> AccessibilityChecker:
    """Fresh AccessibilityChecker instance."""
    return AccessibilityChecker()


@pytest.fixture
def project_with_frontend(tmp_path):
    """Create a project with frontend/src containing TSX files."""
    src = tmp_path / "frontend" / "src"
    src.mkdir(parents=True)
    return tmp_path


# ---------------------------------------------------------------------------
# Data Model Tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestAccessibilityModels:
    """Test the Pydantic models used in accessibility checking."""

    def test_violation_creation(self):
        v = AccessibilityViolation(
            id="color-contrast",
            impact="serious",
            description="Elements must have sufficient color contrast.",
            help_url="https://dequeuniversity.com/rules/axe/4.8/color-contrast",
            nodes=5,
        )
        assert v.id == "color-contrast"
        assert v.impact == "serious"
        assert v.nodes == 5

    def test_violation_defaults(self):
        v = AccessibilityViolation(
            id="test-rule",
            impact="minor",
            description="Test",
        )
        assert v.help_url == ""
        assert v.nodes == 1

    def test_route_accessibility_defaults(self):
        ra = RouteAccessibility()
        assert ra.violations == []
        assert ra.passes == 0
        assert ra.incomplete == 0
        assert ra.url == ""

    def test_accessibility_result_defaults(self):
        result = AccessibilityResult()
        assert result.routes == {}
        assert result.total_violations == 0
        assert result.critical_violations == 0
        assert result.serious_violations == 0
        assert result.passed is True
        assert result.score == 100.0


# ---------------------------------------------------------------------------
# Result Parsing Tests (_parse_results)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestResultParsing:
    """Test parsing of raw axe-core JSON output."""

    def test_parse_empty_dict(self, checker):
        result = checker._parse_results({})
        assert result.total_violations == 0
        assert result.passed is True
        assert result.score == 100.0

    def test_parse_clean_route(self, checker):
        raw = {
            "/": {
                "violations": [],
                "passes": 42,
                "incomplete": 2,
                "url": "http://localhost:23000/",
            }
        }
        result = checker._parse_results(raw)
        assert "/" in result.routes
        assert result.routes["/"].passes == 42
        assert result.routes["/"].incomplete == 2
        assert result.total_violations == 0
        assert result.passed is True

    def test_parse_critical_violation(self, checker):
        raw = {
            "/": {
                "violations": [
                    {
                        "id": "image-alt",
                        "impact": "critical",
                        "description": "Images must have alternative text.",
                        "helpUrl": "https://example.com/rule",
                        "nodes": 3,
                    }
                ],
                "passes": 30,
                "incomplete": 0,
                "url": "http://localhost:23000/",
            }
        }
        result = checker._parse_results(raw)
        assert result.total_violations == 1
        assert result.critical_violations == 1
        assert result.passed is False
        assert result.score == 85.0  # 100 - 15

    def test_parse_serious_violation(self, checker):
        raw = {
            "/login": {
                "violations": [
                    {
                        "id": "label",
                        "impact": "serious",
                        "description": "Form elements must have labels.",
                        "helpUrl": "",
                        "nodes": 2,
                    }
                ],
                "passes": 20,
                "incomplete": 0,
                "url": "http://localhost:23000/login",
            }
        }
        result = checker._parse_results(raw)
        assert result.serious_violations == 1
        assert result.passed is False
        assert result.score == 92.0  # 100 - 8

    def test_parse_moderate_violation(self, checker):
        raw = {
            "/": {
                "violations": [
                    {
                        "id": "meta-viewport",
                        "impact": "moderate",
                        "description": "Viewport meta issue.",
                        "helpUrl": "",
                        "nodes": 1,
                    }
                ],
                "passes": 15,
                "incomplete": 0,
                "url": "http://localhost:23000/",
            }
        }
        result = checker._parse_results(raw)
        assert result.total_violations == 1
        assert result.critical_violations == 0
        assert result.serious_violations == 0
        assert result.passed is True  # moderate doesn't fail
        assert result.score == 97.0  # 100 - 3

    def test_parse_minor_violation(self, checker):
        raw = {
            "/": {
                "violations": [
                    {
                        "id": "some-minor-rule",
                        "impact": "minor",
                        "description": "Minor issue.",
                        "helpUrl": "",
                        "nodes": 1,
                    }
                ],
                "passes": 10,
                "incomplete": 0,
                "url": "http://localhost:23000/",
            }
        }
        result = checker._parse_results(raw)
        assert result.passed is True
        assert result.score == 99.0  # 100 - 1

    def test_parse_multiple_routes_with_violations(self, checker):
        raw = {
            "/": {
                "violations": [
                    {"id": "image-alt", "impact": "critical", "description": "Alt missing.", "helpUrl": "", "nodes": 1},
                ],
                "passes": 10,
                "incomplete": 0,
                "url": "http://localhost:23000/",
            },
            "/login": {
                "violations": [
                    {"id": "label", "impact": "serious", "description": "Label missing.", "helpUrl": "", "nodes": 1},
                    {"id": "color-contrast", "impact": "serious", "description": "Low contrast.", "helpUrl": "", "nodes": 3},
                ],
                "passes": 20,
                "incomplete": 0,
                "url": "http://localhost:23000/login",
            },
        }
        result = checker._parse_results(raw)
        assert result.total_violations == 3
        assert result.critical_violations == 1
        assert result.serious_violations == 2
        assert result.passed is False
        # 100 - 15 (critical) - 8 (serious) - 8 (serious) = 69
        assert result.score == 69.0

    def test_score_floors_at_zero(self, checker):
        """Many critical violations should floor score at 0."""
        violations = [
            {"id": f"rule-{i}", "impact": "critical", "description": f"Issue {i}", "helpUrl": "", "nodes": 1}
            for i in range(10)
        ]
        raw = {
            "/": {
                "violations": violations,
                "passes": 0,
                "incomplete": 0,
                "url": "http://localhost:23000/",
            }
        }
        result = checker._parse_results(raw)
        assert result.score == 0.0


# ---------------------------------------------------------------------------
# Playwright Subprocess Tests (check method)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestAxeAuditSubprocess:
    """Test check() method with mocked subprocess calls."""

    @pytest.mark.asyncio
    async def test_check_clean_results(self, checker):
        """Successful axe-core run with no violations."""
        mock_output = json.dumps({
            "/": {
                "violations": [],
                "passes": 50,
                "incomplete": 1,
                "url": "http://localhost:23000/",
            }
        })

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(
            return_value=(mock_output.encode("utf-8"), b"")
        )
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await checker.check(
                project_url="http://localhost:23000",
                routes=["/"],
            )

        assert result.total_violations == 0
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_check_with_violations(self, checker):
        """Successful axe-core run with violations detected."""
        mock_output = json.dumps({
            "/": {
                "violations": [
                    {
                        "id": "image-alt",
                        "impact": "critical",
                        "description": "Missing alt text.",
                        "helpUrl": "",
                        "nodes": 2,
                    }
                ],
                "passes": 40,
                "incomplete": 0,
                "url": "http://localhost:23000/",
            }
        })

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(
            return_value=(mock_output.encode("utf-8"), b"")
        )
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await checker.check(
                project_url="http://localhost:23000",
                routes=["/"],
            )

        assert result.total_violations == 1
        assert result.critical_violations == 1
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_check_node_not_found(self, checker):
        """Missing 'node' should return empty results."""
        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("node not found"),
        ):
            result = await checker.check(
                project_url="http://localhost:23000",
                routes=["/"],
            )

        assert result.total_violations == 0
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_check_nonzero_exit(self, checker):
        """Non-zero exit should return empty results."""
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b"error"))
        mock_proc.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await checker.check(
                project_url="http://localhost:23000",
                routes=["/"],
            )

        assert result.total_violations == 0

    @pytest.mark.asyncio
    async def test_check_timeout(self, checker):
        """Timeout should return empty results."""
        import asyncio as aio

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.communicate = AsyncMock(side_effect=aio.TimeoutError)
            mock_exec.return_value = mock_proc

            with patch("asyncio.wait_for", side_effect=aio.TimeoutError):
                result = await checker.check(
                    project_url="http://localhost:23000",
                    routes=["/"],
                )

        assert result.total_violations == 0

    @pytest.mark.asyncio
    async def test_check_invalid_json(self, checker):
        """Invalid JSON should return empty results."""
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(
            return_value=(b"not json at all", b"")
        )
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await checker.check(
                project_url="http://localhost:23000",
                routes=["/"],
            )

        assert result.total_violations == 0

    @pytest.mark.asyncio
    async def test_check_empty_stdout(self, checker):
        """Empty stdout should return empty results."""
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            result = await checker.check(
                project_url="http://localhost:23000",
                routes=["/"],
            )

        assert result.total_violations == 0


# ---------------------------------------------------------------------------
# Static Analysis Fallback Tests (check_static)
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestStaticAnalysis:
    """Test the static source-level accessibility analysis fallback."""

    @pytest.mark.asyncio
    async def test_static_detects_missing_alt_text(self, checker, project_with_frontend):
        """TSX with <img> missing alt should be flagged as critical."""
        tsx_file = project_with_frontend / "frontend" / "src" / "Gallery.tsx"
        tsx_file.write_text(
            '<div>\n'
            '  <img src="/photo.jpg" />\n'
            '  <img src="/another.jpg">\n'
            '</div>\n',
            encoding="utf-8",
        )

        result = await checker.check_static(str(project_with_frontend))

        all_violations = []
        for ra in result.routes.values():
            all_violations.extend(ra.violations)

        alt_issues = [v for v in all_violations if v.id == "missing-alt-text"]
        assert len(alt_issues) >= 1
        assert alt_issues[0].impact == "critical"

    @pytest.mark.asyncio
    async def test_static_detects_empty_link(self, checker, project_with_frontend):
        """TSX with empty <a> tags should be flagged as serious."""
        tsx_file = project_with_frontend / "frontend" / "src" / "Nav.tsx"
        tsx_file.write_text(
            '<nav>\n'
            '  <a href="/home"></a>\n'
            '</nav>\n',
            encoding="utf-8",
        )

        result = await checker.check_static(str(project_with_frontend))

        all_violations = []
        for ra in result.routes.values():
            all_violations.extend(ra.violations)

        empty_links = [v for v in all_violations if v.id == "empty-link"]
        assert len(empty_links) >= 1
        assert empty_links[0].impact == "serious"

    @pytest.mark.asyncio
    async def test_static_detects_empty_button(self, checker, project_with_frontend):
        """TSX with empty <button> tags should be flagged."""
        tsx_file = project_with_frontend / "frontend" / "src" / "Button.tsx"
        tsx_file.write_text(
            '<div>\n'
            '  <button></button>\n'
            '</div>\n',
            encoding="utf-8",
        )

        result = await checker.check_static(str(project_with_frontend))

        all_violations = []
        for ra in result.routes.values():
            all_violations.extend(ra.violations)

        empty_buttons = [v for v in all_violations if v.id == "empty-button"]
        assert len(empty_buttons) >= 1

    @pytest.mark.asyncio
    async def test_static_clean_file_no_violations(self, checker, project_with_frontend):
        """A properly accessible TSX file should have no violations."""
        tsx_file = project_with_frontend / "frontend" / "src" / "Good.tsx"
        tsx_file.write_text(
            '<div>\n'
            '  <img src="/photo.jpg" alt="A nice photo" />\n'
            '  <a href="/home">Home</a>\n'
            '  <button>Click me</button>\n'
            '</div>\n',
            encoding="utf-8",
        )

        result = await checker.check_static(str(project_with_frontend))

        all_violations = []
        for ra in result.routes.values():
            all_violations.extend(ra.violations)

        # Should have no violations for alt, link, or button
        assert len([v for v in all_violations if v.id in ("missing-alt-text", "empty-link", "empty-button")]) == 0

    @pytest.mark.asyncio
    async def test_static_no_frontend_returns_empty(self, checker, tmp_path):
        """check_static with no frontend/src returns empty result."""
        result = await checker.check_static(str(tmp_path))
        assert result.total_violations == 0
        assert result.passed is True
        assert result.score == 100.0

    @pytest.mark.asyncio
    async def test_static_critical_violation_fails(self, checker, project_with_frontend):
        """Static analysis with critical violations should mark as failed."""
        tsx_file = project_with_frontend / "frontend" / "src" / "Bad.tsx"
        tsx_file.write_text(
            '<img src="/no-alt.jpg" />\n',
            encoding="utf-8",
        )

        result = await checker.check_static(str(project_with_frontend))
        assert result.passed is False
        assert result.critical_violations > 0


# ---------------------------------------------------------------------------
# Display Tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestPrintReport:
    """Test that print_report does not raise."""

    def test_print_report_empty(self, checker):
        result = AccessibilityResult()
        checker.print_report(result)

    def test_print_report_with_violations(self, checker):
        v = AccessibilityViolation(
            id="image-alt",
            impact="critical",
            description="Missing alt text.",
            help_url="https://example.com",
            nodes=2,
        )
        ra = RouteAccessibility(
            violations=[v],
            passes=20,
            incomplete=0,
            url="http://localhost:23000/",
        )
        result = AccessibilityResult(
            routes={"/": ra},
            total_violations=1,
            critical_violations=1,
            passed=False,
            score=85.0,
        )
        checker.print_report(result)
