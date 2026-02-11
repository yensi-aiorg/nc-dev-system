"""Fix-retest loop management.

After an initial test run, failures are grouped by feature/component and
routed back to a builder agent for targeted fixes.  The loop continues
for up to *max_iterations* rounds or until all tests pass.

The builder interaction is abstracted behind a callback so this module
works with any builder implementation (Codex, Sonnet fallback, etc.).
"""

from __future__ import annotations

import asyncio
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .results import TestFailure, TestResults, TestSuiteResults, VisualTestResults
from .runner import TestRunner

console = Console()

# Type alias for the builder callback.
# Signature: async (feature_name, failures, project_path) -> bool
#   Returns True if the builder believes it has applied a fix.
BuilderCallback = Callable[
    [str, list[TestFailure], str],
    Awaitable[bool],
]


# ---------------------------------------------------------------------------
# Failure grouping
# ---------------------------------------------------------------------------

_FEATURE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # backend: tests/unit/test_services/test_auth_service.py -> "auth"
    ("backend-service", re.compile(r"test_services[/\\]test_(\w+?)_service")),
    # backend: tests/unit/test_<feature>.py or tests/integration/test_api/test_<feature>.py
    ("backend", re.compile(r"test_(?:api[/\\])?test_(\w+)")),
    # frontend: src/components/features/<Feature>/ -> "feature"
    ("frontend-component", re.compile(r"components[/\\]features[/\\](\w+)")),
    # frontend: stores/use<Feature>Store -> "feature"
    ("frontend-store", re.compile(r"stores[/\\]use(\w+)Store")),
    # frontend: pages/<Feature>Page -> "feature"
    ("frontend-page", re.compile(r"pages[/\\](\w+)Page")),
    # e2e: e2e/<feature>.spec.ts
    ("e2e", re.compile(r"e2e[/\\](\w+)\.spec")),
    # generic fallback: extract the last path segment before the test file
    ("generic", re.compile(r"[/\\](\w+)[/\\][^/\\]+$")),
]


def _infer_feature(failure: TestFailure) -> str:
    """Attempt to infer a feature name from the test file path or test name."""
    candidates = [failure.file, failure.test_name]
    for text in candidates:
        for _category, pattern in _FEATURE_PATTERNS:
            match = pattern.search(text)
            if match:
                return match.group(1).lower()
    # Ultimate fallback: use the file stem
    if failure.file:
        return Path(failure.file).stem.removeprefix("test_").lower()
    return "unknown"


def _group_failures_by_feature(
    failures: list[TestFailure],
) -> dict[str, list[TestFailure]]:
    """Group a flat list of failures into ``{feature: [failures]}``."""
    groups: dict[str, list[TestFailure]] = defaultdict(list)
    for failure in failures:
        feature = _infer_feature(failure)
        groups[feature].append(failure)
    return dict(groups)


# ---------------------------------------------------------------------------
# FixRetestLoop
# ---------------------------------------------------------------------------


class FixRetestLoop:
    """Manages iterative fix-retest cycles after a failing test run.

    Parameters
    ----------
    max_iterations:
        Maximum number of fix-retest rounds before giving up.
    retest_scope:
        Controls which tests are re-run after a fix.  ``"failed"`` re-runs
        only the previously-failing tests; ``"all"`` runs the entire suite.
    routes:
        Routes for visual re-testing.  If ``None``, visual tests are
        skipped during the loop.
    """

    def __init__(
        self,
        max_iterations: int = 3,
        *,
        retest_scope: str = "failed",
        routes: Optional[list[str]] = None,
    ) -> None:
        if max_iterations < 1:
            raise ValueError("max_iterations must be >= 1")
        self.max_iterations = max_iterations
        self.retest_scope = retest_scope
        self.routes = routes

    # -- Public API ----------------------------------------------------------

    async def run(
        self,
        project_path: str | Path,
        test_results: TestSuiteResults,
        builder_callback: BuilderCallback,
        *,
        base_url: str = "http://localhost:23000",
    ) -> TestSuiteResults:
        """Execute the fix-retest loop.

        For each iteration:
          1. Collect all failures from *test_results*.
          2. Group them by feature/component.
          3. Invoke *builder_callback* for each feature group.
          4. Re-run the relevant tests.
          5. Return immediately if everything passes; otherwise continue.

        Returns the :class:`TestSuiteResults` from the last test run.
        """
        project_path = Path(project_path).resolve()
        current_results = test_results

        if current_results.overall_passed:
            console.print("[green]All tests already passing -- nothing to fix.[/green]")
            return current_results

        runner = TestRunner(
            project_path,
            base_url=base_url,
        )

        for iteration in range(1, self.max_iterations + 1):
            console.print(
                Panel(
                    f"[bold]Fix-Retest Iteration {iteration}/{self.max_iterations}[/bold]",
                    style="magenta",
                )
            )

            # 1. Collect failures
            all_failures = self._collect_all_failures(current_results)
            if not all_failures:
                console.print("[green]No failures remaining.[/green]")
                return current_results

            # 2. Group by feature
            grouped = _group_failures_by_feature(all_failures)
            self._print_failure_summary(grouped, iteration)

            # 3. Send to builders
            fix_applied = await self._dispatch_fixes(
                grouped, builder_callback, str(project_path)
            )

            if not fix_applied:
                console.print(
                    "[yellow]No fixes were applied in this iteration. "
                    "Stopping loop.[/yellow]"
                )
                break

            # 4. Re-run tests
            current_results = await self._retest(runner, current_results)

            # 5. Check if we're green
            if current_results.overall_passed:
                console.print(
                    f"[green bold]All tests passing after iteration {iteration}![/green bold]"
                )
                return current_results

            remaining = self._collect_all_failures(current_results)
            console.print(
                f"[yellow]{len(remaining)} failure(s) remaining after iteration {iteration}.[/yellow]"
            )

        # Exhausted iterations
        remaining_count = len(self._collect_all_failures(current_results))
        console.print(
            f"[red]Fix-retest loop exhausted after {self.max_iterations} iterations. "
            f"{remaining_count} failure(s) remain.[/red]"
        )
        return current_results

    # -- Internal ------------------------------------------------------------

    @staticmethod
    def _collect_all_failures(results: TestSuiteResults) -> list[TestFailure]:
        """Flatten all failures from unit, e2e, and visual results."""
        failures: list[TestFailure] = []
        failures.extend(results.unit.failures)
        failures.extend(results.e2e.failures)

        # Convert vision failures into TestFailure objects so the builder
        # can process them uniformly.
        for vr in results.visual.vision_results:
            if not vr.passed:
                for issue in vr.issues:
                    failures.append(
                        TestFailure(
                            test_name=f"visual:{vr.route}:{vr.viewport}",
                            file=vr.screenshot_path,
                            error=f"[{issue.severity}] {issue.description}",
                        )
                    )

        for cr in results.visual.comparison_results:
            if not cr.passed:
                failures.append(
                    TestFailure(
                        test_name=f"comparison:{cr.route}:{cr.viewport}",
                        file=cr.actual_path,
                        error="; ".join(cr.issues) or f"Similarity {cr.similarity:.4f} < {cr.threshold:.4f}",
                    )
                )
        return failures

    async def _dispatch_fixes(
        self,
        grouped: dict[str, list[TestFailure]],
        builder_callback: BuilderCallback,
        project_path: str,
    ) -> bool:
        """Invoke the builder callback for each feature group.

        Returns ``True`` if at least one group reported a fix.
        """
        any_fixed = False

        # Run builder callbacks sequentially to avoid conflicting edits
        for feature, failures in grouped.items():
            console.print(
                f"  [cyan]Requesting fix for '{feature}' "
                f"({len(failures)} failure(s))...[/cyan]"
            )
            try:
                fixed = await builder_callback(feature, failures, project_path)
                if fixed:
                    any_fixed = True
                    console.print(f"  [green]Builder reports fix applied for '{feature}'.[/green]")
                else:
                    console.print(f"  [yellow]Builder could not fix '{feature}'.[/yellow]")
            except Exception as exc:
                console.print(
                    f"  [red]Builder errored on '{feature}': {exc}[/red]"
                )

        return any_fixed

    async def _retest(
        self,
        runner: TestRunner,
        previous: TestSuiteResults,
    ) -> TestSuiteResults:
        """Re-run tests after fixes have been applied.

        When ``retest_scope`` is ``"failed"`` only unit and E2E suites are
        re-run (visual tests always re-run because fixes may change the UI).
        When ``"all"``, the full suite is re-run.
        """
        if self.retest_scope == "all":
            return await runner.run_all(routes=self.routes)

        # Scope: "failed" -- re-run only the failing suites
        unit = previous.unit
        e2e = previous.e2e
        visual = previous.visual

        if not previous.unit.all_passed:
            unit = await runner.run_unit_tests()

        if not previous.e2e.all_passed:
            e2e = await runner.run_e2e_tests()

        if self.routes and not previous.visual.all_passed:
            visual = await runner.run_visual_tests(self.routes)

        return TestSuiteResults(
            unit=unit,
            e2e=e2e,
            visual=visual,
            metadata={
                **previous.metadata,
                "retest_scope": self.retest_scope,
            },
        )

    @staticmethod
    def _print_failure_summary(
        grouped: dict[str, list[TestFailure]],
        iteration: int,
    ) -> None:
        """Print a Rich table summarising failures by feature."""
        table = Table(
            title=f"Failures grouped by feature (iteration {iteration})",
            show_lines=True,
        )
        table.add_column("Feature", style="cyan")
        table.add_column("Count", justify="right")
        table.add_column("Sample error", max_width=80)

        for feature, failures in sorted(grouped.items()):
            sample = failures[0].error[:120].replace("\n", " ")
            table.add_row(feature, str(len(failures)), sample)

        console.print(table)
