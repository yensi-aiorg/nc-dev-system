"""Code review and test running for builder output.

Reviews the output produced by Codex builders or fallback agents: checks that
expected files were created, runs unit tests and linting, and scans for
prohibited patterns (TODOs, stubs, console.log, etc.).
"""

import asyncio
import re
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

# Patterns that are strictly prohibited in generated code
_PROHIBITED_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("TODO comment", re.compile(r"#\s*TODO|//\s*TODO|/\*\s*TODO", re.IGNORECASE)),
    (
        "Placeholder pass statement",
        re.compile(r"^\s*pass\s*#?\s*(placeholder|stub|implement)?", re.IGNORECASE | re.MULTILINE),
    ),
    (
        "Not yet implemented text",
        re.compile(r"not\s+yet\s+implemented|coming\s+soon", re.IGNORECASE),
    ),
    (
        "Empty exception handler",
        re.compile(r"except\s*(?:\w+\s*)?:\s*\n\s*pass\b"),
    ),
    (
        "console.log debug statement",
        re.compile(r"\bconsole\.log\("),
    ),
    (
        "Placeholder return True",
        re.compile(r"return\s+True\s*#\s*(placeholder|stub|temp)", re.IGNORECASE),
    ),
]

# File extensions to scan for prohibited patterns
_SCANNABLE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
}


@dataclass
class ReviewIssue:
    """A single issue found during review."""

    severity: str  # "error", "warning", "info"
    category: str  # "prohibited_pattern", "missing_file", "test_failure", "lint"
    message: str
    file: str = ""
    line: int = 0


@dataclass
class TestRunResult:
    """Result from running a test suite."""

    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    total: int = 0
    output: str = ""
    success: bool = False


@dataclass
class ReviewResult:
    """Structured result from a build review."""

    passed: bool
    files_changed: list[str] = field(default_factory=list)
    test_results: dict = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    detailed_issues: list[ReviewIssue] = field(default_factory=list)
    lint_output: str = ""
    diff_stats: str = ""

    def summary(self) -> str:
        """Return a human-readable summary."""
        status = "PASSED" if self.passed else "FAILED"
        lines = [
            f"Review: {status}",
            f"Files changed: {len(self.files_changed)}",
            f"Issues: {len(self.issues)}",
            f"Warnings: {len(self.warnings)}",
        ]
        if self.test_results:
            lines.append(
                f"Tests: {self.test_results.get('passed', 0)} passed, "
                f"{self.test_results.get('failed', 0)} failed"
            )
        return "\n".join(lines)


async def _run_command(
    *args: str,
    cwd: str | Path | None = None,
    timeout: float = 120.0,
    env: dict | None = None,
) -> tuple[int, str, str]:
    """Run a command and return (exit_code, stdout, stderr).

    Does not raise on non-zero exit code; callers should check exit_code.
    """
    import os

    run_env = os.environ.copy()
    if env:
        run_env.update(env)

    try:
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd) if cwd else None,
            env=run_env,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(), timeout=timeout
        )
    except FileNotFoundError:
        return -1, "", f"Command not found: {args[0]}"
    except asyncio.TimeoutError:
        process.kill()
        return -1, "", f"Command timed out after {timeout}s"

    return (
        process.returncode if process.returncode is not None else -1,
        stdout_bytes.decode("utf-8", errors="replace").strip(),
        stderr_bytes.decode("utf-8", errors="replace").strip(),
    )


def _parse_pytest_output(output: str) -> TestRunResult:
    """Parse pytest output to extract test counts.

    Looks for the summary line like:
      === 5 passed, 1 failed, 1 error in 2.34s ===
    """
    result = TestRunResult(output=output)

    # Match the pytest summary line
    summary_pattern = re.compile(
        r"=+\s*(.*?)\s*in\s+[\d.]+s\s*=+"
    )
    match = summary_pattern.search(output)

    if match:
        summary_text = match.group(1)

        passed_m = re.search(r"(\d+)\s+passed", summary_text)
        failed_m = re.search(r"(\d+)\s+failed", summary_text)
        error_m = re.search(r"(\d+)\s+error", summary_text)
        skipped_m = re.search(r"(\d+)\s+skipped", summary_text)

        if passed_m:
            result.passed = int(passed_m.group(1))
        if failed_m:
            result.failed = int(failed_m.group(1))
        if error_m:
            result.errors = int(error_m.group(1))
        if skipped_m:
            result.skipped = int(skipped_m.group(1))

        result.total = result.passed + result.failed + result.errors + result.skipped
        result.success = result.failed == 0 and result.errors == 0
    else:
        # Check for "no tests ran" scenario
        if "no tests ran" in output.lower():
            result.success = True  # No tests is not a failure
        elif "error" in output.lower() or "FAILED" in output:
            result.success = False

    return result


def _parse_vitest_output(output: str) -> TestRunResult:
    """Parse vitest output to extract test counts.

    Looks for lines like:
      Tests  5 passed (5)
      Tests  3 passed | 1 failed (4)
    """
    result = TestRunResult(output=output)

    # Vitest summary pattern
    tests_m = re.search(
        r"Tests\s+(?:(\d+)\s+passed)?(?:\s*\|\s*(\d+)\s+failed)?(?:\s*\|\s*(\d+)\s+skipped)?\s*\((\d+)\)",
        output,
    )

    if tests_m:
        result.passed = int(tests_m.group(1) or 0)
        result.failed = int(tests_m.group(2) or 0)
        result.skipped = int(tests_m.group(3) or 0)
        result.total = int(tests_m.group(4) or 0)
        result.success = result.failed == 0
    else:
        # Fallback: check for pass/fail indicators
        if "FAIL" in output:
            result.success = False
        elif "PASS" in output:
            result.success = True

    return result


class BuildReviewer:
    """Reviews builder output for quality, completeness, and convention compliance.

    Performs several checks:
    1. Git diff analysis to verify files were changed
    2. Expected file existence verification
    3. Unit test execution (pytest for backend, vitest for frontend)
    4. Linting execution (ruff for Python, eslint for TypeScript)
    5. Prohibited pattern scanning (TODOs, stubs, console.log, etc.)
    """

    def __init__(
        self,
        test_timeout: float = 120.0,
        lint_timeout: float = 60.0,
    ):
        """Initialize the reviewer.

        Args:
            test_timeout: Timeout in seconds for test execution.
            lint_timeout: Timeout in seconds for lint execution.
        """
        self.test_timeout = test_timeout
        self.lint_timeout = lint_timeout

    async def review(
        self,
        worktree_path: str,
        feature: dict,
    ) -> ReviewResult:
        """Review the builder output in a worktree.

        Runs all review checks and returns a comprehensive result.

        Args:
            worktree_path: Path to the git worktree with the builder's changes.
            feature: Feature specification dict with:
                - name (str): Feature name
                - expected_files (list[str]): Files that should have been created
                - test_command (str): Custom test command (optional)

        Returns:
            ReviewResult with all findings.
        """
        wt_path = Path(worktree_path)
        feature_name = feature.get("name", "unknown")
        expected_files = feature.get("expected_files", [])

        console.print(
            Panel(
                f"[cyan]Reviewing build output[/cyan]\n"
                f"  Feature: {feature_name}\n"
                f"  Worktree: {worktree_path}",
                title="Build Review",
                border_style="cyan",
            )
        )

        issues: list[str] = []
        warnings: list[str] = []
        detailed_issues: list[ReviewIssue] = []
        all_test_results: dict = {}

        # 1. Git diff stats
        diff_stats = await self._get_diff_stats(wt_path)
        files_changed = await self._get_changed_files(wt_path)

        if not files_changed:
            issues.append("No files were changed in the worktree.")
            detailed_issues.append(
                ReviewIssue(
                    severity="error",
                    category="missing_changes",
                    message="Builder produced no file changes.",
                )
            )

        # 2. Expected file check
        missing = await self._check_expected_files(wt_path, expected_files)
        for f in missing:
            issues.append(f"Expected file not created: {f}")
            detailed_issues.append(
                ReviewIssue(
                    severity="error",
                    category="missing_file",
                    message=f"Expected file was not created: {f}",
                    file=f,
                )
            )

        # 3. Run unit tests
        backend_tests = await self._run_backend_tests(wt_path, feature)
        if backend_tests:
            all_test_results["backend"] = {
                "passed": backend_tests.passed,
                "failed": backend_tests.failed,
                "errors": backend_tests.errors,
                "skipped": backend_tests.skipped,
                "total": backend_tests.total,
                "success": backend_tests.success,
            }
            if not backend_tests.success:
                issues.append(
                    f"Backend tests failed: {backend_tests.failed} failures, "
                    f"{backend_tests.errors} errors"
                )
                detailed_issues.append(
                    ReviewIssue(
                        severity="error",
                        category="test_failure",
                        message=f"Backend tests: {backend_tests.failed} failed, "
                        f"{backend_tests.errors} errors",
                    )
                )

        frontend_tests = await self._run_frontend_tests(wt_path, feature)
        if frontend_tests:
            all_test_results["frontend"] = {
                "passed": frontend_tests.passed,
                "failed": frontend_tests.failed,
                "errors": frontend_tests.errors,
                "skipped": frontend_tests.skipped,
                "total": frontend_tests.total,
                "success": frontend_tests.success,
            }
            if not frontend_tests.success:
                issues.append(
                    f"Frontend tests failed: {frontend_tests.failed} failures"
                )
                detailed_issues.append(
                    ReviewIssue(
                        severity="error",
                        category="test_failure",
                        message=f"Frontend tests: {frontend_tests.failed} failed",
                    )
                )

        # Aggregate test totals
        total_passed = sum(
            r.get("passed", 0) for r in all_test_results.values()
        )
        total_failed = sum(
            r.get("failed", 0) for r in all_test_results.values()
        )
        all_test_results["total"] = {
            "passed": total_passed,
            "failed": total_failed,
        }

        # 4. Run linting
        lint_output = await self._run_linting(wt_path)

        # 5. Scan for prohibited patterns
        pattern_issues = await self._scan_prohibited_patterns(wt_path, files_changed)
        for pi in pattern_issues:
            issues.append(pi.message)
            detailed_issues.append(pi)

        # Determine overall pass/fail
        has_errors = any(i.severity == "error" for i in detailed_issues)
        passed = not has_errors

        result = ReviewResult(
            passed=passed,
            files_changed=files_changed,
            test_results=all_test_results,
            issues=issues,
            warnings=warnings,
            detailed_issues=detailed_issues,
            lint_output=lint_output,
            diff_stats=diff_stats,
        )

        self._display_result(result, feature_name)

        return result

    async def _get_diff_stats(self, worktree_path: Path) -> str:
        """Get git diff --stat output for the worktree."""
        exit_code, stdout, _ = await _run_command(
            "git", "diff", "--stat", "HEAD~1",
            cwd=worktree_path,
            timeout=30.0,
        )
        if exit_code != 0:
            # Try diff against main instead
            exit_code, stdout, _ = await _run_command(
                "git", "diff", "--stat", "main",
                cwd=worktree_path,
                timeout=30.0,
            )
        return stdout

    async def _get_changed_files(self, worktree_path: Path) -> list[str]:
        """Get list of changed files in the worktree."""
        # Try diff against HEAD~1
        exit_code, stdout, _ = await _run_command(
            "git", "diff", "--name-only", "HEAD~1",
            cwd=worktree_path,
            timeout=30.0,
        )
        if exit_code != 0 or not stdout.strip():
            # Fall back to diff against main
            exit_code, stdout, _ = await _run_command(
                "git", "diff", "--name-only", "main",
                cwd=worktree_path,
                timeout=30.0,
            )
        if exit_code != 0 or not stdout.strip():
            # Last resort: show untracked + modified files
            exit_code, stdout, _ = await _run_command(
                "git", "status", "--porcelain",
                cwd=worktree_path,
                timeout=30.0,
            )
            if stdout:
                return [
                    line[3:].strip()
                    for line in stdout.split("\n")
                    if line.strip()
                ]
            return []

        return [f.strip() for f in stdout.split("\n") if f.strip()]

    async def _check_expected_files(
        self, worktree_path: Path, expected_files: list[str]
    ) -> list[str]:
        """Check that all expected files exist in the worktree.

        Returns list of missing file paths.
        """
        missing = []
        for expected in expected_files:
            full_path = worktree_path / expected
            if not full_path.exists():
                missing.append(expected)
        return missing

    async def _run_backend_tests(
        self, worktree_path: Path, feature: dict
    ) -> TestRunResult | None:
        """Run backend pytest tests in the worktree.

        Returns None if no backend test infrastructure is found.
        """
        backend_dir = worktree_path / "backend"
        tests_dir = backend_dir / "tests"

        if not tests_dir.exists():
            console.print("[dim]No backend tests directory found, skipping.[/dim]")
            return None

        custom_cmd = feature.get("test_command_backend")
        if custom_cmd:
            cmd_parts = custom_cmd.split()
        else:
            cmd_parts = [
                "python", "-m", "pytest",
                str(tests_dir),
                "-v", "--tb=short", "--no-header",
            ]

        console.print(f"[cyan]Running backend tests...[/cyan]")

        exit_code, stdout, stderr = await _run_command(
            *cmd_parts,
            cwd=backend_dir,
            timeout=self.test_timeout,
        )

        combined_output = f"{stdout}\n{stderr}".strip()
        result = _parse_pytest_output(combined_output)

        if exit_code == -1 and "Command not found" in stderr:
            console.print("[yellow]pytest not available, skipping backend tests.[/yellow]")
            return None

        console.print(
            f"  Backend tests: {result.passed} passed, "
            f"{result.failed} failed, {result.errors} errors"
        )

        return result

    async def _run_frontend_tests(
        self, worktree_path: Path, feature: dict
    ) -> TestRunResult | None:
        """Run frontend vitest tests in the worktree.

        Returns None if no frontend test infrastructure is found.
        """
        frontend_dir = worktree_path / "frontend"
        package_json = frontend_dir / "package.json"

        if not package_json.exists():
            console.print("[dim]No frontend package.json found, skipping.[/dim]")
            return None

        custom_cmd = feature.get("test_command_frontend")
        if custom_cmd:
            cmd_parts = custom_cmd.split()
        else:
            cmd_parts = ["npx", "vitest", "run", "--reporter=verbose"]

        console.print(f"[cyan]Running frontend tests...[/cyan]")

        exit_code, stdout, stderr = await _run_command(
            *cmd_parts,
            cwd=frontend_dir,
            timeout=self.test_timeout,
        )

        combined_output = f"{stdout}\n{stderr}".strip()
        result = _parse_vitest_output(combined_output)

        if exit_code == -1 and "Command not found" in stderr:
            console.print("[yellow]vitest not available, skipping frontend tests.[/yellow]")
            return None

        console.print(
            f"  Frontend tests: {result.passed} passed, "
            f"{result.failed} failed"
        )

        return result

    async def _run_linting(self, worktree_path: Path) -> str:
        """Run linting tools on the worktree.

        Runs ruff (Python) and eslint (TypeScript) if available.
        Returns combined lint output.
        """
        outputs: list[str] = []

        # Python linting with ruff
        backend_dir = worktree_path / "backend"
        if backend_dir.exists():
            exit_code, stdout, stderr = await _run_command(
                "ruff", "check", str(backend_dir),
                cwd=worktree_path,
                timeout=self.lint_timeout,
            )
            if exit_code == 0:
                outputs.append("[Python/ruff] Clean")
            elif exit_code != -1:
                outputs.append(f"[Python/ruff]\n{stdout}\n{stderr}".strip())

        # TypeScript linting with eslint
        frontend_dir = worktree_path / "frontend"
        if frontend_dir.exists() and (frontend_dir / "package.json").exists():
            exit_code, stdout, stderr = await _run_command(
                "npx", "eslint", "src/", "--max-warnings=0",
                cwd=frontend_dir,
                timeout=self.lint_timeout,
            )
            if exit_code == 0:
                outputs.append("[TypeScript/eslint] Clean")
            elif exit_code != -1:
                outputs.append(f"[TypeScript/eslint]\n{stdout}\n{stderr}".strip())

        return "\n\n".join(outputs)

    async def _scan_prohibited_patterns(
        self, worktree_path: Path, changed_files: list[str]
    ) -> list[ReviewIssue]:
        """Scan changed files for prohibited code patterns.

        Only scans files with recognized source code extensions.
        Returns a list of issues found.
        """
        issues: list[ReviewIssue] = []

        for rel_path in changed_files:
            full_path = worktree_path / rel_path
            if not full_path.exists() or not full_path.is_file():
                continue

            if full_path.suffix not in _SCANNABLE_EXTENSIONS:
                continue

            try:
                content = full_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            for pattern_name, regex in _PROHIBITED_PATTERNS:
                matches = list(regex.finditer(content))
                for match in matches:
                    # Calculate line number
                    line_num = content[: match.start()].count("\n") + 1
                    matched_text = match.group(0).strip()[:80]

                    issues.append(
                        ReviewIssue(
                            severity="error",
                            category="prohibited_pattern",
                            message=(
                                f"Prohibited pattern '{pattern_name}' found "
                                f"in {rel_path}:{line_num}: {matched_text}"
                            ),
                            file=rel_path,
                            line=line_num,
                        )
                    )

        return issues

    def _display_result(self, result: ReviewResult, feature_name: str) -> None:
        """Display a formatted review summary to the console."""
        if result.passed:
            style = "green"
            title = f"Review Passed: {feature_name}"
        else:
            style = "red"
            title = f"Review Failed: {feature_name}"

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Key", style="bold")
        table.add_column("Value")

        table.add_row("Status", "[green]PASSED[/green]" if result.passed else "[red]FAILED[/red]")
        table.add_row("Files Changed", str(len(result.files_changed)))
        table.add_row("Issues", str(len(result.issues)))
        table.add_row("Warnings", str(len(result.warnings)))

        if result.test_results and "total" in result.test_results:
            total = result.test_results["total"]
            table.add_row(
                "Tests",
                f"{total.get('passed', 0)} passed, {total.get('failed', 0)} failed",
            )

        console.print(Panel(table, title=title, border_style=style))

        if result.issues:
            console.print("[bold red]Issues:[/bold red]")
            for i, issue in enumerate(result.issues[:10], 1):
                console.print(f"  {i}. {issue}")
            if len(result.issues) > 10:
                console.print(
                    f"  [dim]... and {len(result.issues) - 10} more issues[/dim]"
                )

        if result.warnings:
            console.print("[bold yellow]Warnings:[/bold yellow]")
            for w in result.warnings[:5]:
                console.print(f"  - {w}")

    async def quick_check(self, worktree_path: str) -> bool:
        """Perform a quick pass/fail check without full review detail.

        Runs tests and checks for prohibited patterns, returning a simple
        boolean. Useful for fast feedback loops.

        Args:
            worktree_path: Path to the worktree to check.

        Returns:
            True if all basic checks pass.
        """
        wt_path = Path(worktree_path)
        changed = await self._get_changed_files(wt_path)

        if not changed:
            return False

        # Quick prohibited pattern scan
        pattern_issues = await self._scan_prohibited_patterns(wt_path, changed)
        if pattern_issues:
            return False

        # Quick backend test
        backend_result = await self._run_backend_tests(wt_path, {})
        if backend_result and not backend_result.success:
            return False

        # Quick frontend test
        frontend_result = await self._run_frontend_tests(wt_path, {})
        if frontend_result and not frontend_result.success:
            return False

        return True
