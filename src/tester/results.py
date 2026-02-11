"""Test results collection, aggregation, and reporting.

Provides Pydantic v2 models for representing test outcomes at every level:
individual failures, per-suite results, visual analysis results, and
aggregated suite-wide summaries.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field, computed_field


# ---------------------------------------------------------------------------
# Individual failure
# ---------------------------------------------------------------------------

class TestFailure(BaseModel):
    """A single failed test case with diagnostic details."""

    test_name: str = Field(..., description="Fully-qualified test name")
    file: str = Field(..., description="Relative file path containing the test")
    error: str = Field(..., description="Error message or assertion details")
    stdout: str = Field(default="", description="Captured stdout output")
    duration_seconds: float = Field(default=0.0, description="Wall-clock time of the failed test")


# ---------------------------------------------------------------------------
# Per-suite results (unit, integration, e2e, ...)
# ---------------------------------------------------------------------------

class TestResults(BaseModel):
    """Results from a single test suite execution (e.g. pytest or vitest)."""

    suite_name: str = Field(default="", description="Name such as 'backend-unit' or 'frontend-vitest'")
    total: int = Field(default=0, ge=0)
    passed: int = Field(default=0, ge=0)
    failed: int = Field(default=0, ge=0)
    skipped: int = Field(default=0, ge=0)
    duration_seconds: float = Field(default=0.0, ge=0.0)
    failures: list[TestFailure] = Field(default_factory=list)

    @computed_field  # type: ignore[misc]
    @property
    def all_passed(self) -> bool:
        """True when no failures were recorded."""
        return self.failed == 0


# ---------------------------------------------------------------------------
# Vision analysis result
# ---------------------------------------------------------------------------

class VisionIssue(BaseModel):
    """A single visual issue found by AI analysis."""

    severity: str = Field(default="warning", description="'critical', 'warning', or 'info'")
    description: str = Field(..., description="Human-readable issue description")
    element: str = Field(default="", description="CSS selector or element description, if applicable")
    suggestion: str = Field(default="", description="Suggested fix")


class VisionResult(BaseModel):
    """Result of AI vision analysis for a single screenshot."""

    screenshot_path: str = Field(..., description="Path to the analysed screenshot")
    route: str = Field(default="", description="Route that was captured")
    viewport: str = Field(default="", description="Viewport name (desktop / mobile)")
    passed: bool = Field(default=True, description="Overall pass/fail verdict")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Analyser confidence")
    issues: list[VisionIssue] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list, description="General improvement suggestions")
    analyzer: str = Field(default="", description="Which analyser produced this result ('ollama' / 'claude')")
    raw_response: str = Field(default="", description="Raw analyser output for debugging")

    @computed_field  # type: ignore[misc]
    @property
    def has_issues(self) -> bool:
        """True when at least one issue was detected."""
        return len(self.issues) > 0


# ---------------------------------------------------------------------------
# Screenshot comparison result
# ---------------------------------------------------------------------------

class ComparisonResult(BaseModel):
    """Result of comparing an actual screenshot against a reference."""

    route: str = Field(..., description="Route that was captured")
    viewport: str = Field(..., description="Viewport name")
    similarity: float = Field(default=1.0, ge=0.0, le=1.0, description="Similarity score (1.0 = identical)")
    passed: bool = Field(default=True, description="Whether similarity >= threshold")
    threshold: float = Field(default=0.95, ge=0.0, le=1.0, description="Pass/fail threshold used")
    actual_path: str = Field(default="", description="Path to the actual screenshot")
    reference_path: str = Field(default="", description="Path to the reference screenshot")
    diff_path: Optional[str] = Field(default=None, description="Path to the generated diff image, if any")
    issues: list[str] = Field(default_factory=list, description="Human-readable difference descriptions")


# ---------------------------------------------------------------------------
# Visual test results (aggregate of screenshots + vision + comparison)
# ---------------------------------------------------------------------------

class VisualTestResults(BaseModel):
    """Aggregated visual testing outcomes."""

    screenshots: dict[str, dict[str, str]] = Field(
        default_factory=dict,
        description="route -> viewport -> screenshot file path",
    )
    vision_results: list[VisionResult] = Field(default_factory=list)
    comparison_results: list[ComparisonResult] = Field(default_factory=list)

    @computed_field  # type: ignore[misc]
    @property
    def all_passed(self) -> bool:
        """True when every vision and comparison check passed."""
        vision_ok = all(vr.passed for vr in self.vision_results)
        comparison_ok = all(cr.passed for cr in self.comparison_results)
        return vision_ok and comparison_ok


# ---------------------------------------------------------------------------
# Top-level suite results
# ---------------------------------------------------------------------------

class TestSuiteResults(BaseModel):
    """Complete test-run summary spanning unit, E2E, and visual testing."""

    unit: TestResults = Field(default_factory=TestResults)
    e2e: TestResults = Field(default_factory=TestResults)
    visual: VisualTestResults = Field(default_factory=VisualTestResults)
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO-8601 timestamp of when the results were generated",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary metadata (project name, commit SHA, etc.)",
    )

    @computed_field  # type: ignore[misc]
    @property
    def overall_passed(self) -> bool:
        """True when unit, E2E, and visual tests all passed."""
        return self.unit.all_passed and self.e2e.all_passed and self.visual.all_passed

    # -- Serialisation helpers -----------------------------------------------

    def to_json(self, indent: int = 2) -> str:
        """Serialise the full results to a JSON string."""
        return self.model_dump_json(indent=indent)

    def save(self, path: Path) -> None:
        """Persist results to a JSON file, creating parent directories as needed."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "TestSuiteResults":
        """Load previously-saved results from a JSON file."""
        raw = Path(path).read_text(encoding="utf-8")
        return cls.model_validate_json(raw)

    # -- Summary helpers -----------------------------------------------------

    def summary_dict(self) -> dict[str, Any]:
        """Return a condensed summary suitable for logs and reports."""
        return {
            "overall_passed": self.overall_passed,
            "timestamp": self.timestamp,
            "unit": {
                "total": self.unit.total,
                "passed": self.unit.passed,
                "failed": self.unit.failed,
                "skipped": self.unit.skipped,
            },
            "e2e": {
                "total": self.e2e.total,
                "passed": self.e2e.passed,
                "failed": self.e2e.failed,
                "skipped": self.e2e.skipped,
            },
            "visual": {
                "screenshots_count": sum(
                    len(viewports) for viewports in self.visual.screenshots.values()
                ),
                "vision_issues": sum(
                    len(vr.issues) for vr in self.visual.vision_results
                ),
                "comparison_failures": sum(
                    1 for cr in self.visual.comparison_results if not cr.passed
                ),
            },
        }

    def summary_text(self) -> str:
        """Human-readable multi-line summary."""
        lines: list[str] = []
        status = "PASSED" if self.overall_passed else "FAILED"
        lines.append(f"Test Suite Results  [{status}]  {self.timestamp}")
        lines.append("-" * 60)

        for label, results in [("Unit", self.unit), ("E2E", self.e2e)]:
            mark = "ok" if results.all_passed else "FAIL"
            lines.append(
                f"  {label:10s}  {results.passed}/{results.total} passed, "
                f"{results.failed} failed, {results.skipped} skipped  "
                f"({results.duration_seconds:.1f}s)  [{mark}]"
            )

        vis = self.visual
        n_screenshots = sum(len(v) for v in vis.screenshots.values())
        n_vision_issues = sum(len(vr.issues) for vr in vis.vision_results)
        n_cmp_fail = sum(1 for cr in vis.comparison_results if not cr.passed)
        vis_mark = "ok" if vis.all_passed else "FAIL"
        lines.append(
            f"  {'Visual':10s}  {n_screenshots} screenshots, "
            f"{n_vision_issues} vision issues, "
            f"{n_cmp_fail} comparison failures  [{vis_mark}]"
        )
        lines.append("-" * 60)
        return "\n".join(lines)
