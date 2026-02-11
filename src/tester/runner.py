"""Test execution orchestrator.

Runs the full test pyramid for a generated project:

- **Unit tests** -- backend (pytest) and frontend (vitest)
- **E2E tests** -- Playwright browser tests
- **Visual tests** -- screenshot capture + AI vision analysis

Results are collected into :class:`TestSuiteResults` for downstream
consumption by the reporter and fix-loop modules.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any, Optional

from rich.console import Console
from rich.panel import Panel

from .comparator import ScreenshotComparator
from .results import (
    ComparisonResult,
    TestFailure,
    TestResults,
    TestSuiteResults,
    VisionResult,
    VisualTestResults,
)
from .screenshot import DESKTOP, MOBILE, ScreenshotCapture, Viewport
from .vision import VisionAnalyzer

console = Console()

# ---------------------------------------------------------------------------
# JSON report parsers
# ---------------------------------------------------------------------------


def _parse_pytest_json(report_path: Path) -> TestResults:
    """Parse a pytest-json-report output file into :class:`TestResults`.

    Expected structure (subset)::

        {
          "summary": {"total": N, "passed": N, "failed": N, "skipped": N},
          "duration": float,
          "tests": [
            {
              "nodeid": "...",
              "outcome": "passed"|"failed"|"skipped",
              "call": {"longrepr": "..."},
              "duration": float
            }, ...
          ]
        }
    """
    if not report_path.exists():
        return TestResults(suite_name="backend-pytest")

    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return TestResults(suite_name="backend-pytest")

    summary = data.get("summary", {})
    failures: list[TestFailure] = []
    for test in data.get("tests", []):
        if test.get("outcome") == "failed":
            call_info = test.get("call", {})
            failures.append(
                TestFailure(
                    test_name=test.get("nodeid", "unknown"),
                    file=test.get("nodeid", "unknown").split("::")[0],
                    error=call_info.get("longrepr", "No details available"),
                    stdout=call_info.get("stdout", ""),
                    duration_seconds=test.get("duration", 0.0),
                )
            )

    return TestResults(
        suite_name="backend-pytest",
        total=summary.get("total", 0),
        passed=summary.get("passed", 0),
        failed=summary.get("failed", 0),
        skipped=summary.get("skipped", 0),
        duration_seconds=data.get("duration", 0.0),
        failures=failures,
    )


def _parse_vitest_json(report_path: Path) -> TestResults:
    """Parse a Vitest JSON reporter output file into :class:`TestResults`.

    Expected structure (subset)::

        {
          "numTotalTests": N,
          "numPassedTests": N,
          "numFailedTests": N,
          "numPendingTests": N,
          "startTime": epoch_ms,
          "testResults": [
            {
              "name": "...",
              "status": "passed"|"failed",
              "assertionResults": [
                {
                  "fullName": "...",
                  "status": "passed"|"failed",
                  "failureMessages": ["..."]
                }
              ]
            }
          ]
        }
    """
    if not report_path.exists():
        return TestResults(suite_name="frontend-vitest")

    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return TestResults(suite_name="frontend-vitest")

    failures: list[TestFailure] = []
    for suite in data.get("testResults", []):
        for assertion in suite.get("assertionResults", []):
            if assertion.get("status") == "failed":
                failures.append(
                    TestFailure(
                        test_name=assertion.get("fullName", "unknown"),
                        file=suite.get("name", "unknown"),
                        error="\n".join(assertion.get("failureMessages", [])),
                    )
                )

    start_time = data.get("startTime", 0)
    end_time = data.get("startTime", 0) + data.get("duration", 0)
    duration = (end_time - start_time) / 1000.0 if start_time else 0.0

    return TestResults(
        suite_name="frontend-vitest",
        total=data.get("numTotalTests", 0),
        passed=data.get("numPassedTests", 0),
        failed=data.get("numFailedTests", 0),
        skipped=data.get("numPendingTests", 0),
        duration_seconds=max(0.0, duration),
        failures=failures,
    )


def _parse_playwright_json(report_path: Path) -> TestResults:
    """Parse a Playwright JSON reporter output into :class:`TestResults`.

    Expected structure (subset)::

        {
          "stats": {
            "expected": N,
            "unexpected": N,
            "skipped": N,
            "duration": ms
          },
          "suites": [...]
        }
    """
    if not report_path.exists():
        return TestResults(suite_name="e2e-playwright")

    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return TestResults(suite_name="e2e-playwright")

    stats = data.get("stats", {})
    expected = stats.get("expected", 0)
    unexpected = stats.get("unexpected", 0)
    flaky = stats.get("flaky", 0)
    skipped = stats.get("skipped", 0)
    total = expected + unexpected + flaky + skipped

    failures: list[TestFailure] = []
    _extract_playwright_failures(data.get("suites", []), failures)

    return TestResults(
        suite_name="e2e-playwright",
        total=total,
        passed=expected + flaky,
        failed=unexpected,
        skipped=skipped,
        duration_seconds=stats.get("duration", 0) / 1000.0,
        failures=failures,
    )


def _extract_playwright_failures(
    suites: list[dict[str, Any]], out: list[TestFailure]
) -> None:
    """Recursively walk Playwright suites to collect failures."""
    for suite in suites:
        for spec in suite.get("specs", []):
            for test in spec.get("tests", []):
                if test.get("status") == "unexpected":
                    for result in test.get("results", []):
                        error_text = ""
                        if result.get("error", {}).get("message"):
                            error_text = result["error"]["message"]
                        out.append(
                            TestFailure(
                                test_name=spec.get("title", "unknown"),
                                file=spec.get("file", suite.get("title", "unknown")),
                                error=error_text or "Test failed unexpectedly",
                                duration_seconds=result.get("duration", 0) / 1000.0,
                            )
                        )
        # Recurse into nested suites
        _extract_playwright_failures(suite.get("suites", []), out)


# ---------------------------------------------------------------------------
# TestRunner
# ---------------------------------------------------------------------------


class TestRunner:
    """Orchestrates test execution for a generated project.

    Parameters
    ----------
    project_path:
        Root directory of the generated project (containing ``backend/``
        and ``frontend/`` subdirectories).
    base_url:
        Base URL of the running frontend application (used for visual
        tests and screenshots).
    screenshots_dir:
        Directory for storing captured screenshots.
    reference_dir:
        Directory containing reference/baseline screenshots for
        comparison.  If ``None``, visual comparison is skipped.
    """

    def __init__(
        self,
        project_path: str | Path,
        *,
        base_url: str = "http://localhost:23000",
        screenshots_dir: Optional[str | Path] = None,
        reference_dir: Optional[str | Path] = None,
        subprocess_timeout: int = 300,
    ) -> None:
        self.project_path = Path(project_path).resolve()
        self.base_url = base_url
        self.screenshots_dir = Path(
            screenshots_dir or self.project_path / ".nc-dev" / "screenshots"
        )
        self.reference_dir = Path(reference_dir) if reference_dir else None
        self.subprocess_timeout = subprocess_timeout

        # Report output locations
        self._reports_dir = self.project_path / ".nc-dev" / "test-reports"
        self._reports_dir.mkdir(parents=True, exist_ok=True)

    # -- Public API ----------------------------------------------------------

    async def run_unit_tests(self) -> TestResults:
        """Run backend (pytest) and frontend (vitest) unit tests in parallel.

        Returns a merged :class:`TestResults` instance.
        """
        console.print(Panel("[bold]Running unit tests[/bold]", style="blue"))

        backend_task = asyncio.create_task(self._run_backend_tests())
        frontend_task = asyncio.create_task(self._run_frontend_tests())

        backend_results, frontend_results = await asyncio.gather(
            backend_task, frontend_task, return_exceptions=True
        )

        # Handle exceptions gracefully
        if isinstance(backend_results, BaseException):
            console.print(f"[red]Backend tests errored: {backend_results}[/red]")
            backend_results = TestResults(
                suite_name="backend-pytest",
                failures=[
                    TestFailure(
                        test_name="backend-execution",
                        file="",
                        error=str(backend_results),
                    )
                ],
                failed=1,
                total=1,
            )
        if isinstance(frontend_results, BaseException):
            console.print(f"[red]Frontend tests errored: {frontend_results}[/red]")
            frontend_results = TestResults(
                suite_name="frontend-vitest",
                failures=[
                    TestFailure(
                        test_name="frontend-execution",
                        file="",
                        error=str(frontend_results),
                    )
                ],
                failed=1,
                total=1,
            )

        merged = self._merge_results(
            "unit", [backend_results, frontend_results]
        )
        self._log_results("Unit", merged)
        return merged

    async def run_e2e_tests(self) -> TestResults:
        """Run Playwright end-to-end tests.

        Returns a :class:`TestResults` instance.
        """
        console.print(Panel("[bold]Running E2E tests[/bold]", style="blue"))
        results = await self._run_playwright_tests()
        self._log_results("E2E", results)
        return results

    async def run_visual_tests(
        self,
        routes: list[str],
        *,
        viewports: Optional[list[Viewport]] = None,
        vision_context: str = "",
    ) -> VisualTestResults:
        """Capture screenshots and run AI vision + comparison analysis.

        Parameters
        ----------
        routes:
            List of URL paths to capture (e.g. ``["/", "/tasks", "/login"]``).
        viewports:
            Viewports to use.  Defaults to desktop (1440x900) and mobile
            (375x812).
        vision_context:
            Additional context string passed to the vision analysers.
        """
        console.print(Panel("[bold]Running visual tests[/bold]", style="blue"))
        effective_viewports = viewports or [DESKTOP, MOBILE]

        # 1) Capture screenshots
        capturer = ScreenshotCapture(
            self.base_url,
            self.screenshots_dir,
            viewports=effective_viewports,
        )
        screenshots = await capturer.capture_all_routes(routes)

        # Serialise paths to strings for the results model
        screenshots_str: dict[str, dict[str, str]] = {}
        screenshots_paths: dict[str, dict[str, Path]] = {}
        for route, vp_map in screenshots.items():
            screenshots_str[route] = {vp: str(p) for vp, p in vp_map.items()}
            screenshots_paths[route] = dict(vp_map)

        # 2) AI vision analysis
        analyzer = VisionAnalyzer()
        vision_results: list[VisionResult] = await analyzer.analyze_batch(
            screenshots_paths, context=vision_context
        )

        # 3) Comparison against references (if available)
        comparison_results: list[ComparisonResult] = []
        if self.reference_dir and self.reference_dir.exists():
            comparator = ScreenshotComparator(
                diff_dir=self.screenshots_dir / "diffs",
            )
            comparison_results = await comparator.compare_all(
                self.screenshots_dir, self.reference_dir
            )

        visual = VisualTestResults(
            screenshots=screenshots_str,
            vision_results=vision_results,
            comparison_results=comparison_results,
        )

        status = "[green]PASSED[/green]" if visual.all_passed else "[red]FAILED[/red]"
        console.print(
            f"Visual tests: {status} | "
            f"{sum(len(v) for v in screenshots_str.values())} screenshots, "
            f"{sum(len(vr.issues) for vr in vision_results)} vision issues, "
            f"{sum(1 for cr in comparison_results if not cr.passed)} comparison failures"
        )
        return visual

    async def run_all(
        self,
        routes: Optional[list[str]] = None,
    ) -> TestSuiteResults:
        """Run the complete test suite: unit + E2E + visual.

        Parameters
        ----------
        routes:
            Routes for visual testing.  If ``None``, visual testing is
            skipped.
        """
        console.print(
            Panel(
                f"[bold]Full test suite for {self.project_path.name}[/bold]",
                style="cyan",
            )
        )
        start = time.monotonic()

        unit = await self.run_unit_tests()
        e2e = await self.run_e2e_tests()

        visual = VisualTestResults()
        if routes:
            visual = await self.run_visual_tests(routes)

        suite = TestSuiteResults(
            unit=unit,
            e2e=e2e,
            visual=visual,
            metadata={
                "project_path": str(self.project_path),
                "base_url": self.base_url,
                "total_duration_seconds": round(time.monotonic() - start, 2),
            },
        )

        # Persist results
        report_path = self._reports_dir / "test-suite-results.json"
        suite.save(report_path)
        console.print(f"[dim]Results saved to {report_path}[/dim]")

        console.print(suite.summary_text())
        return suite

    # -- Backend tests -------------------------------------------------------

    async def _run_backend_tests(self) -> TestResults:
        """Run pytest in the ``backend/`` directory."""
        backend_dir = self.project_path / "backend"
        if not backend_dir.exists():
            console.print("[yellow]No backend/ directory found, skipping backend tests.[/yellow]")
            return TestResults(suite_name="backend-pytest")

        report_file = self._reports_dir / "pytest-report.json"
        cmd = [
            "python",
            "-m",
            "pytest",
            "tests/",
            "-v",
            "--tb=short",
            "--json-report",
            f"--json-report-file={report_file}",
            "--timeout=60",
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(backend_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=self.subprocess_timeout,
        )

        if proc.returncode not in (0, 1):
            # returncode 1 = test failures; anything else is an execution error
            error = stderr.decode().strip() or stdout.decode().strip()
            console.print(f"[red]pytest execution error (rc={proc.returncode}):[/red]\n{error[:500]}")

        return _parse_pytest_json(report_file)

    # -- Frontend tests ------------------------------------------------------

    async def _run_frontend_tests(self) -> TestResults:
        """Run vitest in the ``frontend/`` directory."""
        frontend_dir = self.project_path / "frontend"
        if not frontend_dir.exists():
            console.print("[yellow]No frontend/ directory found, skipping frontend tests.[/yellow]")
            return TestResults(suite_name="frontend-vitest")

        report_file = self._reports_dir / "vitest-report.json"
        cmd = [
            "npx",
            "vitest",
            "run",
            "--reporter=json",
            f"--outputFile={report_file}",
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(frontend_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=self.subprocess_timeout,
        )

        # Vitest writes JSON to the output file; if it wrote to stdout instead,
        # capture it.
        if not report_file.exists() and stdout:
            try:
                json.loads(stdout.decode())
                report_file.parent.mkdir(parents=True, exist_ok=True)
                report_file.write_bytes(stdout)
            except (json.JSONDecodeError, OSError):
                pass

        return _parse_vitest_json(report_file)

    # -- E2E tests -----------------------------------------------------------

    async def _run_playwright_tests(self) -> TestResults:
        """Run Playwright E2E tests in the ``frontend/`` directory."""
        frontend_dir = self.project_path / "frontend"
        if not frontend_dir.exists():
            console.print("[yellow]No frontend/ directory found, skipping E2E tests.[/yellow]")
            return TestResults(suite_name="e2e-playwright")

        report_file = self._reports_dir / "playwright-report.json"
        cmd = [
            "npx",
            "playwright",
            "test",
            "--reporter=json",
        ]

        env_patch = {"PLAYWRIGHT_JSON_OUTPUT_NAME": str(report_file)}

        import os
        env = {**os.environ, **env_patch}

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(frontend_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=self.subprocess_timeout,
        )

        # Playwright JSON reporter may write to stdout
        if not report_file.exists() and stdout:
            try:
                json.loads(stdout.decode())
                report_file.parent.mkdir(parents=True, exist_ok=True)
                report_file.write_bytes(stdout)
            except (json.JSONDecodeError, OSError):
                pass

        return _parse_playwright_json(report_file)

    # -- Helpers -------------------------------------------------------------

    @staticmethod
    def _merge_results(name: str, parts: list[TestResults]) -> TestResults:
        """Merge multiple :class:`TestResults` into one."""
        total = sum(p.total for p in parts)
        passed = sum(p.passed for p in parts)
        failed = sum(p.failed for p in parts)
        skipped = sum(p.skipped for p in parts)
        duration = sum(p.duration_seconds for p in parts)
        failures: list[TestFailure] = []
        for p in parts:
            failures.extend(p.failures)

        return TestResults(
            suite_name=name,
            total=total,
            passed=passed,
            failed=failed,
            skipped=skipped,
            duration_seconds=round(duration, 3),
            failures=failures,
        )

    @staticmethod
    def _log_results(label: str, results: TestResults) -> None:
        """Print a one-line summary of results."""
        color = "green" if results.all_passed else "red"
        console.print(
            f"[{color}]{label}: {results.passed}/{results.total} passed, "
            f"{results.failed} failed, {results.skipped} skipped "
            f"({results.duration_seconds:.1f}s)[/{color}]"
        )
