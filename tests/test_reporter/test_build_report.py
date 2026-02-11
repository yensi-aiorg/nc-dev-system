"""Unit tests for build report generator (src.reporter.build_report).

Tests cover:
- BuildReportGenerator.generate() with full features and test results
- _render_summary section content
- _render_features table (implemented, partial, skipped)
- _render_test_results (pass/fail counts, suites, failed test details)
- _render_coverage (above/below threshold, per-module)
- _render_limitations (string and dict)
- _render_tech_stack (custom and default)
- Output file creation and structure
- Edge cases (empty features, no tests, no coverage)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.reporter.build_report import BuildReportGenerator


# ---------------------------------------------------------------------------
# BuildReportGenerator._render_summary
# ---------------------------------------------------------------------------

class TestRenderSummary:
    @pytest.mark.unit
    def test_includes_project_name(self):
        gen = BuildReportGenerator()
        lines = gen._render_summary({"project_name": "my-app"})
        text = "\n".join(lines)
        assert "my-app" in text

    @pytest.mark.unit
    def test_includes_duration(self):
        gen = BuildReportGenerator()
        lines = gen._render_summary({"duration_minutes": 12.5})
        text = "\n".join(lines)
        assert "12.5" in text

    @pytest.mark.unit
    def test_includes_git_info(self):
        gen = BuildReportGenerator()
        lines = gen._render_summary({
            "git_branch": "main",
            "git_commit": "abc123def456",
        })
        text = "\n".join(lines)
        assert "main" in text
        assert "abc123def456" in text

    @pytest.mark.unit
    def test_status_completed(self):
        gen = BuildReportGenerator()
        lines = gen._render_summary({"status": "completed"})
        text = "\n".join(lines)
        assert "Completed" in text

    @pytest.mark.unit
    def test_status_failed(self):
        gen = BuildReportGenerator()
        lines = gen._render_summary({"status": "failed"})
        text = "\n".join(lines)
        assert "Failed" in text

    @pytest.mark.unit
    def test_missing_optional_fields(self):
        gen = BuildReportGenerator()
        lines = gen._render_summary({})
        text = "\n".join(lines)
        assert "Build Summary" in text
        assert "N/A" in text


# ---------------------------------------------------------------------------
# BuildReportGenerator._render_features
# ---------------------------------------------------------------------------

class TestRenderFeatures:
    @pytest.mark.unit
    def test_all_implemented(self):
        gen = BuildReportGenerator()
        features = [
            {"name": "Auth", "status": "implemented", "priority": "P0", "complexity": "medium"},
            {"name": "Tasks", "status": "implemented", "priority": "P0", "complexity": "high"},
        ]
        lines = gen._render_features(features)
        text = "\n".join(lines)

        assert "Auth" in text
        assert "Tasks" in text
        assert "2/2" in text
        assert "100%" in text

    @pytest.mark.unit
    def test_mixed_status(self):
        gen = BuildReportGenerator()
        features = [
            {"name": "Auth", "status": "implemented"},
            {"name": "Tasks", "status": "partial"},
            {"name": "Chat", "status": "skipped"},
        ]
        lines = gen._render_features(features)
        text = "\n".join(lines)

        assert "Implemented" in text
        assert "Partial" in text
        assert "Skipped" in text
        assert "1/3" in text
        assert "33%" in text

    @pytest.mark.unit
    def test_empty_features(self):
        gen = BuildReportGenerator()
        lines = gen._render_features([])
        text = "\n".join(lines)
        assert "No features recorded" in text

    @pytest.mark.unit
    def test_default_values(self):
        gen = BuildReportGenerator()
        features = [{"name": "Unnamed"}]
        lines = gen._render_features(features)
        text = "\n".join(lines)
        assert "P1" in text  # default priority
        assert "Medium" in text  # default complexity


# ---------------------------------------------------------------------------
# BuildReportGenerator._render_test_results
# ---------------------------------------------------------------------------

class TestRenderTestResults:
    @pytest.mark.unit
    def test_full_results(self):
        gen = BuildReportGenerator()
        test_results = {
            "total": 50,
            "passed": 48,
            "failed": 2,
            "skipped": 0,
            "duration_seconds": 10.5,
        }
        lines = gen._render_test_results(test_results)
        text = "\n".join(lines)

        assert "50" in text
        assert "48" in text
        assert "2" in text
        assert "96.0%" in text
        assert "10.5s" in text

    @pytest.mark.unit
    def test_no_tests(self):
        gen = BuildReportGenerator()
        lines = gen._render_test_results({"total": 0})
        text = "\n".join(lines)
        assert "No test results available" in text

    @pytest.mark.unit
    def test_with_suites(self):
        gen = BuildReportGenerator()
        test_results = {
            "total": 20,
            "passed": 20,
            "failed": 0,
            "skipped": 0,
            "suites": [
                {"name": "backend-unit", "total": 15, "passed": 15, "failed": 0, "duration_seconds": 3.0},
                {"name": "frontend-vitest", "total": 5, "passed": 5, "failed": 0, "duration_seconds": 2.0},
            ],
        }
        lines = gen._render_test_results(test_results)
        text = "\n".join(lines)

        assert "Test Suites" in text
        assert "backend-unit" in text
        assert "frontend-vitest" in text

    @pytest.mark.unit
    def test_with_failed_tests(self):
        gen = BuildReportGenerator()
        test_results = {
            "total": 5,
            "passed": 4,
            "failed": 1,
            "skipped": 0,
            "failed_tests": [
                {"name": "test_foo", "error": "AssertionError: bad value"},
            ],
        }
        lines = gen._render_test_results(test_results)
        text = "\n".join(lines)

        assert "Failed Tests" in text
        assert "test_foo" in text
        assert "AssertionError" in text


# ---------------------------------------------------------------------------
# BuildReportGenerator._render_coverage
# ---------------------------------------------------------------------------

class TestRenderCoverage:
    @pytest.mark.unit
    def test_above_threshold(self):
        gen = BuildReportGenerator()
        lines = gen._render_coverage({"coverage_percent": 85.5})
        text = "\n".join(lines)

        assert "85.5%" in text
        assert "meets the target" in text

    @pytest.mark.unit
    def test_below_threshold(self):
        gen = BuildReportGenerator()
        lines = gen._render_coverage({"coverage_percent": 65.0})
        text = "\n".join(lines)

        assert "65.0%" in text
        assert "Warning" in text
        assert "below the target" in text

    @pytest.mark.unit
    def test_no_coverage_data(self):
        gen = BuildReportGenerator()
        lines = gen._render_coverage({})
        text = "\n".join(lines)
        assert "Coverage data not available" in text

    @pytest.mark.unit
    def test_per_module_coverage(self):
        gen = BuildReportGenerator()
        lines = gen._render_coverage({
            "coverage_percent": 82.0,
            "module_coverage": [
                {"name": "app.services", "statements": 100, "covered": 85, "missing": 15, "percent": 85.0},
                {"name": "app.api", "statements": 50, "covered": 40, "missing": 10, "percent": 80.0},
            ],
        })
        text = "\n".join(lines)

        assert "Per-Module Coverage" in text
        assert "app.services" in text
        assert "app.api" in text


# ---------------------------------------------------------------------------
# BuildReportGenerator._render_limitations
# ---------------------------------------------------------------------------

class TestRenderLimitations:
    @pytest.mark.unit
    def test_string_limitations(self):
        gen = BuildReportGenerator()
        lines = gen._render_limitations({
            "known_limitations": ["No email sending", "No real-time updates"],
        })
        text = "\n".join(lines)

        assert "No email sending" in text
        assert "No real-time updates" in text

    @pytest.mark.unit
    def test_dict_limitations(self):
        gen = BuildReportGenerator()
        lines = gen._render_limitations({
            "known_limitations": [
                {"title": "Email", "description": "No email integration"},
            ],
        })
        text = "\n".join(lines)

        assert "Email" in text
        assert "No email integration" in text

    @pytest.mark.unit
    def test_no_limitations(self):
        gen = BuildReportGenerator()
        lines = gen._render_limitations({})
        text = "\n".join(lines)
        assert "No known limitations" in text


# ---------------------------------------------------------------------------
# BuildReportGenerator._render_tech_stack
# ---------------------------------------------------------------------------

class TestRenderTechStack:
    @pytest.mark.unit
    def test_custom_tech_stack(self):
        gen = BuildReportGenerator()
        lines = gen._render_tech_stack({
            "technology_stack": {
                "backend": {"Python": "3.12", "FastAPI": "0.115"},
                "frontend": ["React 19", "TypeScript"],
            },
        })
        text = "\n".join(lines)

        assert "Backend" in text
        assert "Python" in text
        assert "3.12" in text
        assert "Frontend" in text
        assert "React 19" in text

    @pytest.mark.unit
    def test_default_tech_stack(self):
        gen = BuildReportGenerator()
        lines = gen._render_tech_stack({})
        text = "\n".join(lines)

        assert "Python" in text
        assert "FastAPI" in text
        assert "MongoDB" in text
        assert "React 19" in text
        assert "Zustand" in text
        assert "Docker" in text


# ---------------------------------------------------------------------------
# BuildReportGenerator.generate (full integration)
# ---------------------------------------------------------------------------

class TestBuildReportGeneratorGenerate:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_creates_file(self, tmp_path: Path):
        gen = BuildReportGenerator()
        features = [{"name": "Auth", "status": "implemented"}]
        test_results = {"total": 10, "passed": 10, "failed": 0, "skipped": 0}
        metadata = {"project_name": "My App", "status": "completed"}

        result = await gen.generate(features, test_results, metadata, tmp_path / "report.md")

        assert result.exists()
        content = result.read_text()
        assert "My App" in content
        assert "Build Report" in content

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_includes_all_sections(self, tmp_path: Path):
        gen = BuildReportGenerator()
        features = [{"name": "Tasks", "status": "implemented"}]
        test_results = {
            "total": 20,
            "passed": 19,
            "failed": 1,
            "skipped": 0,
            "coverage_percent": 85.0,
        }
        metadata = {
            "project_name": "Test App",
            "known_limitations": ["No real-time"],
        }

        result = await gen.generate(features, test_results, metadata, tmp_path / "report.md")
        content = result.read_text()

        assert "Build Summary" in content
        assert "Features Implemented" in content
        assert "Test Results" in content
        assert "Test Coverage" in content
        assert "Known Limitations" in content
        assert "Technology Stack" in content

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_creates_parent_dirs(self, tmp_path: Path):
        gen = BuildReportGenerator()
        output = tmp_path / "docs" / "reports" / "build.md"

        result = await gen.generate([], {}, {}, output)
        assert result.exists()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_returns_absolute_path(self, tmp_path: Path):
        gen = BuildReportGenerator()
        result = await gen.generate([], {}, {}, tmp_path / "report.md")
        assert result.is_absolute()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_includes_footer(self, tmp_path: Path):
        gen = BuildReportGenerator()
        result = await gen.generate([], {}, {}, tmp_path / "report.md")
        content = result.read_text()
        assert "auto-generated" in content
        assert "usage-guide.md" in content
        assert "api-documentation.md" in content

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_includes_timestamp(self, tmp_path: Path):
        gen = BuildReportGenerator()
        result = await gen.generate([], {}, {"project_name": "Test"}, tmp_path / "report.md")
        content = result.read_text()
        assert "Generated by NC Dev System on" in content
