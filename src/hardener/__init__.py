"""Hardening Engine for the NC Dev System.

Orchestrates all hardening checks -- error audit, responsive design,
accessibility (WCAG AA), and performance -- returning a combined report
that grades the generated project's production readiness.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.hardener.accessibility import (
    AccessibilityChecker,
    AccessibilityResult,
)
from src.hardener.error_audit import (
    AuditIssue,
    AuditResult,
    ErrorAuditor,
)
from src.hardener.performance import (
    PerformanceAuditor,
    PerformanceIssue,
    PerformanceResult,
)
from src.hardener.responsive import (
    ResponsiveChecker,
    ResponsiveResult,
)

__all__ = [
    # Core engine
    "HardeningEngine",
    "HardeningReport",
    # Sub-modules
    "ErrorAuditor",
    "AuditResult",
    "AuditIssue",
    "ResponsiveChecker",
    "ResponsiveResult",
    "AccessibilityChecker",
    "AccessibilityResult",
    "PerformanceAuditor",
    "PerformanceResult",
    "PerformanceIssue",
]

console = Console()


# ---------------------------------------------------------------------------
# Report Model
# ---------------------------------------------------------------------------

class HardeningReport(BaseModel):
    """Combined report from all hardening checks."""

    project_path: str = Field(..., description="Path to the audited project")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO-8601 timestamp of the report",
    )

    error_audit: Optional[AuditResult] = Field(
        default=None, description="Error handling audit results"
    )
    responsive: Optional[ResponsiveResult] = Field(
        default=None, description="Responsive design check results"
    )
    accessibility: Optional[AccessibilityResult] = Field(
        default=None, description="Accessibility (WCAG AA) check results"
    )
    performance: Optional[PerformanceResult] = Field(
        default=None, description="Performance audit results"
    )

    overall_score: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Weighted average of all check scores",
    )
    passed: bool = Field(
        default=False,
        description="True if overall score >= 60 and no critical failures",
    )
    summary: str = Field(
        default="", description="Human-readable summary of the hardening results"
    )


# ---------------------------------------------------------------------------
# HardeningEngine
# ---------------------------------------------------------------------------

class HardeningEngine:
    """Orchestrates all hardening checks for a generated project.

    Usage::

        engine = HardeningEngine()
        report = await engine.run(
            project_path="/path/to/project",
            project_url="http://localhost:23000",
            routes=["/", "/login", "/dashboard"],
        )
        engine.print_report(report)
    """

    # Score weights for each check category
    WEIGHTS = {
        "error_audit": 0.30,
        "responsive": 0.20,
        "accessibility": 0.25,
        "performance": 0.25,
    }

    PASS_THRESHOLD = 60.0

    def __init__(
        self,
        error_auditor: ErrorAuditor | None = None,
        responsive_checker: ResponsiveChecker | None = None,
        accessibility_checker: AccessibilityChecker | None = None,
        performance_auditor: PerformanceAuditor | None = None,
    ) -> None:
        self._error_auditor = error_auditor or ErrorAuditor()
        self._responsive_checker = responsive_checker or ResponsiveChecker()
        self._accessibility_checker = accessibility_checker or AccessibilityChecker()
        self._performance_auditor = performance_auditor or PerformanceAuditor()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(
        self,
        project_path: str,
        project_url: str | None = None,
        routes: list[str] | None = None,
    ) -> HardeningReport:
        """Run all hardening checks and return a combined report.

        Parameters
        ----------
        project_path:
            Root directory of the generated project.
        project_url:
            Base URL of the running application. Required for responsive
            and accessibility checks. If not provided, those checks are
            skipped and only static analysis runs.
        routes:
            List of route paths to check (e.g. ``["/", "/login"]``).
            If not provided, defaults to ``["/"]``.

        Returns
        -------
        HardeningReport
            Combined results from all checks.
        """
        resolved_path = str(Path(project_path).resolve())
        routes = routes or ["/"]

        console.print(
            Panel(
                f"[bold]Hardening Engine[/bold]\n"
                f"Project: {resolved_path}\n"
                f"URL: {project_url or '(static analysis only)'}\n"
                f"Routes: {', '.join(routes)}",
                title="NC Dev System",
                border_style="blue",
            )
        )

        # Prepare coroutines for concurrent execution
        error_coro = self._run_error_audit(resolved_path)
        perf_coro = self._run_performance_audit(resolved_path)

        # Responsive and accessibility need a running server
        if project_url:
            responsive_coro = self._run_responsive_check(project_url, routes)
            a11y_coro = self._run_accessibility_check(project_url, routes)
        else:
            responsive_coro = _none_coro()
            # Fall back to static accessibility analysis
            a11y_coro = self._run_static_accessibility(resolved_path)

        error_result, responsive_result, a11y_result, perf_result = await asyncio.gather(
            error_coro,
            responsive_coro,
            a11y_coro,
            perf_coro,
        )

        # Calculate overall score
        overall_score = self._calculate_overall_score(
            error_result, responsive_result, a11y_result, perf_result
        )
        passed = overall_score >= self.PASS_THRESHOLD and not self._has_critical_failures(
            error_result, responsive_result, a11y_result, perf_result
        )

        summary = self._build_summary(
            error_result, responsive_result, a11y_result, perf_result,
            overall_score, passed,
        )

        return HardeningReport(
            project_path=resolved_path,
            error_audit=error_result,
            responsive=responsive_result,
            accessibility=a11y_result,
            performance=perf_result,
            overall_score=overall_score,
            passed=passed,
            summary=summary,
        )

    # ------------------------------------------------------------------
    # Individual check runners (with error isolation)
    # ------------------------------------------------------------------

    async def _run_error_audit(self, project_path: str) -> AuditResult | None:
        """Run error audit, returning None on internal failure."""
        console.print("  [dim]Running error handling audit...[/dim]")
        try:
            result = await self._error_auditor.audit(project_path)
            console.print(f"  [green]Error audit complete[/green] (score: {result.score})")
            return result
        except Exception as exc:
            console.print(f"  [red]Error audit failed: {exc}[/red]")
            return None

    async def _run_responsive_check(
        self, project_url: str, routes: list[str]
    ) -> ResponsiveResult | None:
        """Run responsive checks, returning None on internal failure."""
        console.print("  [dim]Running responsive design checks...[/dim]")
        try:
            result = await self._responsive_checker.check(project_url, routes)
            console.print(f"  [green]Responsive check complete[/green] (score: {result.score})")
            return result
        except Exception as exc:
            console.print(f"  [red]Responsive check failed: {exc}[/red]")
            return None

    async def _run_accessibility_check(
        self, project_url: str, routes: list[str]
    ) -> AccessibilityResult | None:
        """Run accessibility checks, returning None on internal failure."""
        console.print("  [dim]Running accessibility audit (axe-core)...[/dim]")
        try:
            result = await self._accessibility_checker.check(project_url, routes)
            console.print(f"  [green]Accessibility audit complete[/green] (score: {result.score})")
            return result
        except Exception as exc:
            console.print(f"  [red]Accessibility audit failed: {exc}[/red]")
            return None

    async def _run_static_accessibility(
        self, project_path: str
    ) -> AccessibilityResult | None:
        """Run static accessibility analysis when no URL is available."""
        console.print("  [dim]Running static accessibility analysis...[/dim]")
        try:
            result = await self._accessibility_checker.check_static(project_path)
            console.print(f"  [green]Static accessibility analysis complete[/green] (score: {result.score})")
            return result
        except Exception as exc:
            console.print(f"  [red]Static accessibility analysis failed: {exc}[/red]")
            return None

    async def _run_performance_audit(self, project_path: str) -> PerformanceResult | None:
        """Run performance audit, returning None on internal failure."""
        console.print("  [dim]Running performance audit...[/dim]")
        try:
            result = await self._performance_auditor.audit(project_path)
            console.print(f"  [green]Performance audit complete[/green] (score: {result.score})")
            return result
        except Exception as exc:
            console.print(f"  [red]Performance audit failed: {exc}[/red]")
            return None

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _calculate_overall_score(
        self,
        error_result: AuditResult | None,
        responsive_result: ResponsiveResult | None,
        a11y_result: AccessibilityResult | None,
        perf_result: PerformanceResult | None,
    ) -> float:
        """Calculate a weighted average of all available check scores."""
        scores: dict[str, float] = {}

        if error_result is not None:
            scores["error_audit"] = error_result.score
        if responsive_result is not None:
            scores["responsive"] = responsive_result.score
        if a11y_result is not None:
            scores["accessibility"] = a11y_result.score
        if perf_result is not None:
            scores["performance"] = perf_result.score

        if not scores:
            return 0.0

        # Re-normalise weights so they sum to 1.0 across available checks
        available_weight = sum(self.WEIGHTS[k] for k in scores)
        if available_weight == 0:
            return 0.0

        weighted_sum = sum(
            scores[k] * (self.WEIGHTS[k] / available_weight) for k in scores
        )
        return round(weighted_sum, 1)

    def _has_critical_failures(
        self,
        error_result: AuditResult | None,
        responsive_result: ResponsiveResult | None,
        a11y_result: AccessibilityResult | None,
        perf_result: PerformanceResult | None,
    ) -> bool:
        """Check whether any check has critical-level failures."""
        if error_result and error_result.score < 30:
            return True
        if responsive_result and not responsive_result.passed:
            return True
        if a11y_result and a11y_result.critical_violations > 0:
            return True
        if perf_result and any(i.severity == "error" for i in perf_result.issues):
            return True
        return False

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    def _build_summary(
        self,
        error_result: AuditResult | None,
        responsive_result: ResponsiveResult | None,
        a11y_result: AccessibilityResult | None,
        perf_result: PerformanceResult | None,
        overall_score: float,
        passed: bool,
    ) -> str:
        """Build a human-readable summary string."""
        parts: list[str] = []

        if passed:
            parts.append(f"Project PASSED hardening with an overall score of {overall_score}/100.")
        else:
            parts.append(f"Project FAILED hardening with an overall score of {overall_score}/100.")

        if error_result:
            parts.append(
                f"Error handling: {len(error_result.issues)} errors, "
                f"{len(error_result.warnings)} warnings (score: {error_result.score})."
            )
        else:
            parts.append("Error handling: check not available.")

        if responsive_result:
            status = "passed" if responsive_result.passed else "failed"
            parts.append(
                f"Responsive design: {status} with {responsive_result.total_issues} issues "
                f"(score: {responsive_result.score})."
            )
        else:
            parts.append("Responsive design: check not available (no project URL).")

        if a11y_result:
            parts.append(
                f"Accessibility: {a11y_result.total_violations} violations, "
                f"{a11y_result.critical_violations} critical "
                f"(score: {a11y_result.score})."
            )
        else:
            parts.append("Accessibility: check not available.")

        if perf_result:
            parts.append(
                f"Performance: {len(perf_result.issues)} issues "
                f"(score: {perf_result.score})."
            )
        else:
            parts.append("Performance: check not available.")

        return " ".join(parts)

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def print_report(self, report: HardeningReport) -> None:
        """Pretty-print the full hardening report to the console."""
        console.print("\n")
        console.print(
            Panel(
                f"[bold]Hardening Report[/bold]\n"
                f"Project: {report.project_path}\n"
                f"Timestamp: {report.timestamp}",
                border_style="blue",
            )
        )

        # Score table
        table = Table(title="Check Scores", show_lines=True)
        table.add_column("Check", width=24)
        table.add_column("Score", width=10, justify="right")
        table.add_column("Weight", width=10, justify="right")
        table.add_column("Status", width=10)

        checks = [
            ("Error Handling", report.error_audit),
            ("Responsive Design", report.responsive),
            ("Accessibility", report.accessibility),
            ("Performance", report.performance),
        ]
        weight_keys = ["error_audit", "responsive", "accessibility", "performance"]

        for (name, result), wkey in zip(checks, weight_keys):
            if result is None:
                table.add_row(name, "N/A", f"{self.WEIGHTS[wkey]:.0%}", "[dim]skipped[/dim]")
                continue

            score = getattr(result, "score", 0.0)
            score_color = "green" if score >= 80 else "yellow" if score >= 50 else "red"

            # Determine pass/fail
            if hasattr(result, "passed"):
                status = "[green]PASS[/green]" if result.passed else "[red]FAIL[/red]"
            elif score >= 60:
                status = "[green]PASS[/green]"
            else:
                status = "[red]FAIL[/red]"

            table.add_row(
                name,
                f"[{score_color}]{score:.1f}[/{score_color}]",
                f"{self.WEIGHTS[wkey]:.0%}",
                status,
            )

        console.print(table)

        # Overall
        overall_color = "green" if report.overall_score >= 80 else "yellow" if report.overall_score >= 50 else "red"
        overall_status = "[green bold]PASS[/green bold]" if report.passed else "[red bold]FAIL[/red bold]"
        console.print(
            f"\n[bold]Overall Score:[/bold] "
            f"[{overall_color}]{report.overall_score:.1f}/100[/{overall_color}]  |  "
            f"Status: {overall_status}\n"
        )
        console.print(f"[dim]{report.summary}[/dim]\n")

        # Delegate detailed output to each checker
        if report.error_audit:
            self._error_auditor.print_report(report.error_audit)
        if report.responsive:
            self._responsive_checker.print_report(report.responsive)
        if report.accessibility:
            self._accessibility_checker.print_report(report.accessibility)
        if report.performance:
            self._performance_auditor.print_report(report.performance)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _none_coro() -> None:
    """Async no-op returning None."""
    return None
