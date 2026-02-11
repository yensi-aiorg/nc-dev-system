"""Fallback strategy management for builder agents.

Implements the Codex -> Codex retry -> Sonnet -> escalate chain:
1. Attempt feature build with Codex CLI
2. If Codex fails, retry once with Codex
3. If Codex fails again, fall back to Claude Code Sonnet (via `claude` CLI)
4. If Sonnet also fails, escalate to the user for manual intervention

Tracks attempt history for debugging and reporting.
"""

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .codex_runner import CodexResult, CodexRunner, CodexRunnerError
from .prompt_gen import PromptGenerator
from .reviewer import BuildReviewer, ReviewResult
from .worktree import WorktreeManager

console = Console()


class BuildMethod(str, Enum):
    """Method used to build a feature."""

    CODEX = "codex"
    SONNET = "sonnet"
    MANUAL = "manual"


@dataclass
class BuildAttempt:
    """Record of a single build attempt."""

    method: BuildMethod
    attempt_number: int
    success: bool
    started_at: str
    duration_seconds: float
    errors: list[str] = field(default_factory=list)
    review_passed: bool = False
    files_created: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)


@dataclass
class BuildResult:
    """Final result from the fallback-aware build pipeline."""

    success: bool
    feature_name: str
    method: str  # "codex", "sonnet", or "manual"
    attempts: int
    result: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    attempt_history: list[BuildAttempt] = field(default_factory=list)
    review: ReviewResult | None = None
    total_duration_seconds: float = 0.0

    def summary(self) -> str:
        """Return a human-readable summary of the build result."""
        status = "SUCCESS" if self.success else "FAILED"
        lines = [
            f"Feature: {self.feature_name}",
            f"Status: {status}",
            f"Method: {self.method}",
            f"Attempts: {self.attempts}",
            f"Total Duration: {self.total_duration_seconds:.1f}s",
        ]
        if self.errors:
            lines.append(f"Errors: {len(self.errors)}")
            for err in self.errors[:3]:
                lines.append(f"  - {err[:200]}")
        return "\n".join(lines)


class SonnetRunner:
    """Runs feature builds using Claude Code Sonnet CLI as a fallback.

    Invokes the `claude` CLI with a prompt to implement the feature, as a
    subprocess. This is used when Codex fails repeatedly.
    """

    def __init__(
        self,
        timeout_seconds: float = 900.0,
        claude_binary: str = "claude",
    ):
        self.timeout_seconds = timeout_seconds
        self.claude_binary = claude_binary

    async def run(
        self,
        prompt: str,
        worktree_path: str,
    ) -> CodexResult:
        """Execute Claude Code Sonnet to implement a feature.

        Uses: claude -p "{prompt}" --allowedTools ... --cd {worktree_path}

        Args:
            prompt: The full builder prompt.
            worktree_path: Path to the git worktree.

        Returns:
            CodexResult (reused structure) with execution details.
        """
        wt_path = Path(worktree_path)

        if not wt_path.exists():
            return CodexResult(
                success=False,
                errors=[f"Worktree path not found: {worktree_path}"],
            )

        console.print(
            Panel(
                f"[magenta]Starting Sonnet fallback builder[/magenta]\n"
                f"  Worktree: {worktree_path}\n"
                f"  Timeout: {self.timeout_seconds}s",
                title="Sonnet Fallback",
                border_style="magenta",
            )
        )

        # Build the claude CLI command
        cmd = [
            self.claude_binary,
            "-p", prompt,
            "--output-format", "json",
            "--model", "claude-sonnet-4-5-20250514",
            "--allowedTools",
            "Edit,Write,Bash,Read,Glob,Grep",
            "--cd", str(wt_path),
        ]

        start_time = time.monotonic()

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=os.environ.copy(),
            )
        except FileNotFoundError:
            return CodexResult(
                success=False,
                errors=[
                    f"Claude CLI not found: '{self.claude_binary}'. "
                    "Install Claude Code CLI to use Sonnet fallback."
                ],
                duration_seconds=time.monotonic() - start_time,
            )
        except PermissionError:
            return CodexResult(
                success=False,
                errors=[
                    f"Permission denied executing: '{self.claude_binary}'."
                ],
                duration_seconds=time.monotonic() - start_time,
            )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError:
            elapsed = time.monotonic() - start_time
            process.kill()
            try:
                await asyncio.wait_for(process.communicate(), timeout=10.0)
            except asyncio.TimeoutError:
                pass
            return CodexResult(
                success=False,
                errors=[f"Sonnet process timed out after {self.timeout_seconds}s"],
                duration_seconds=elapsed,
                exit_code=-1,
            )

        elapsed = time.monotonic() - start_time
        stdout_text = stdout_bytes.decode("utf-8", errors="replace").strip()
        stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()
        exit_code = process.returncode if process.returncode is not None else -1

        # Parse JSON output from claude CLI
        raw_output: dict = {}
        try:
            raw_output = json.loads(stdout_text)
        except (json.JSONDecodeError, ValueError):
            pass

        errors: list[str] = []
        if exit_code != 0:
            errors.append(f"Sonnet CLI exited with code {exit_code}")
        if stderr_text:
            for line in stderr_text.split("\n"):
                line = line.strip()
                if line and any(
                    kw in line.lower()
                    for kw in ["error", "failed", "exception", "fatal"]
                ):
                    errors.append(line)

        success = exit_code == 0 and len(errors) == 0

        result = CodexResult(
            success=success,
            errors=errors,
            duration_seconds=elapsed,
            stdout=stdout_text,
            stderr=stderr_text,
            exit_code=exit_code,
            raw_output=raw_output,
        )

        if success:
            console.print("[green]Sonnet fallback build succeeded.[/green]")
        else:
            console.print(f"[red]Sonnet fallback build failed:[/red] {errors}")

        return result

    async def check_available(self) -> bool:
        """Check if the Claude CLI is available."""
        try:
            process = await asyncio.create_subprocess_exec(
                self.claude_binary, "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, _ = await asyncio.wait_for(
                process.communicate(), timeout=10.0
            )
            version = stdout_bytes.decode("utf-8", errors="replace").strip()
            console.print(f"[green]Claude CLI available:[/green] {version}")
            return True
        except (FileNotFoundError, asyncio.TimeoutError):
            console.print(
                f"[red]Claude CLI not available:[/red] '{self.claude_binary}' "
                "not found in PATH."
            )
            return False


class FallbackStrategy:
    """Manages the Codex -> Codex retry -> Sonnet -> escalate fallback chain.

    Orchestrates the full build pipeline for a single feature:
    1. Generate a prompt from the feature spec
    2. Create a worktree for isolation
    3. Attempt builds with fallback
    4. Review each attempt
    5. Report structured results
    """

    def __init__(
        self,
        worktree_manager: WorktreeManager,
        prompt_generator: PromptGenerator,
        codex_runner: CodexRunner,
        reviewer: BuildReviewer,
        sonnet_runner: SonnetRunner | None = None,
        codex_timeout: float = 600.0,
        sonnet_timeout: float = 900.0,
    ):
        """Initialize the fallback strategy.

        Args:
            worktree_manager: Manager for git worktrees.
            prompt_generator: Generator for builder prompts.
            codex_runner: Runner for Codex CLI.
            reviewer: Reviewer for build output.
            sonnet_runner: Optional Sonnet runner (created with defaults if None).
            codex_timeout: Timeout for each Codex attempt.
            sonnet_timeout: Timeout for the Sonnet fallback attempt.
        """
        self.worktree_manager = worktree_manager
        self.prompt_generator = prompt_generator
        self.codex_runner = codex_runner
        self.reviewer = reviewer
        self.sonnet_runner = sonnet_runner or SonnetRunner(timeout_seconds=sonnet_timeout)
        self.codex_timeout = codex_timeout
        self.sonnet_timeout = sonnet_timeout

    async def execute_with_fallback(
        self,
        feature: dict,
        architecture: dict,
        project_path: str,
        max_codex_attempts: int = 2,
    ) -> BuildResult:
        """Execute the full fallback chain for a feature build.

        Attempts:
        1. Codex attempt 1
        2. Codex attempt 2 (retry)
        3. Claude Code Sonnet (fallback)
        4. Escalate to user (manual)

        Each successful build is reviewed. If the review fails, the attempt
        is considered failed and the next attempt proceeds.

        Args:
            feature: Feature specification dict.
            architecture: Architecture context dict.
            project_path: Absolute path to the project.
            max_codex_attempts: Maximum Codex attempts before falling back (default: 2).

        Returns:
            BuildResult with the final outcome and full attempt history.
        """
        feature_name = feature.get("name", "unnamed-feature")
        pipeline_start = time.monotonic()
        attempt_history: list[BuildAttempt] = []
        all_errors: list[str] = []

        console.print(
            Panel(
                f"[bold cyan]Starting build pipeline for:[/bold cyan] {feature_name}\n"
                f"  Max Codex attempts: {max_codex_attempts}\n"
                f"  Fallback: Sonnet CLI\n"
                f"  Escalation: Manual",
                title="Build Pipeline",
                border_style="cyan",
            )
        )

        # Generate the prompt
        prompt_content, prompt_path = await self.prompt_generator.generate_and_save(
            feature, architecture, project_path
        )

        # Create the worktree
        worktree_info = await self.worktree_manager.create(
            feature_name, base_branch=feature.get("base_branch", "main")
        )
        worktree_path_str = str(worktree_info.path)

        # Set up output path for Codex results
        results_dir = Path(project_path) / ".nc-dev" / "codex-results"
        results_dir.mkdir(parents=True, exist_ok=True)

        # ---- Codex attempts ----
        for attempt_num in range(1, max_codex_attempts + 1):
            console.print(
                f"\n[cyan]Codex attempt {attempt_num}/{max_codex_attempts}[/cyan]"
            )

            attempt_start = time.monotonic()
            output_path = str(
                results_dir / f"{worktree_info.name}-attempt{attempt_num}.json"
            )

            attempt = BuildAttempt(
                method=BuildMethod.CODEX,
                attempt_number=attempt_num,
                success=False,
                started_at=datetime.now(timezone.utc).isoformat(),
                duration_seconds=0.0,
            )

            try:
                codex_result = await self.codex_runner.run(
                    prompt_path=str(prompt_path),
                    worktree_path=worktree_path_str,
                    output_path=output_path,
                )
            except CodexRunnerError as exc:
                attempt.errors.append(str(exc))
                attempt.duration_seconds = time.monotonic() - attempt_start
                attempt_history.append(attempt)
                all_errors.append(f"Codex attempt {attempt_num}: {exc}")
                console.print(f"[red]Codex attempt {attempt_num} crashed:[/red] {exc}")
                continue

            attempt.duration_seconds = time.monotonic() - attempt_start
            attempt.files_created = codex_result.files_created
            attempt.files_modified = codex_result.files_modified
            attempt.errors = codex_result.errors

            if not codex_result.success:
                all_errors.extend(codex_result.errors)
                attempt_history.append(attempt)
                console.print(
                    f"[red]Codex attempt {attempt_num} failed:[/red] "
                    f"{len(codex_result.errors)} errors"
                )
                continue

            # Run review
            console.print(f"[cyan]Reviewing Codex attempt {attempt_num}...[/cyan]")
            review = await self.reviewer.review(worktree_path_str, feature)
            attempt.review_passed = review.passed

            if review.passed:
                attempt.success = True
                attempt_history.append(attempt)
                total_duration = time.monotonic() - pipeline_start

                result = BuildResult(
                    success=True,
                    feature_name=feature_name,
                    method=BuildMethod.CODEX.value,
                    attempts=attempt_num,
                    result={
                        "files_created": codex_result.files_created,
                        "files_modified": codex_result.files_modified,
                        "test_results": codex_result.test_results,
                    },
                    errors=[],
                    attempt_history=attempt_history,
                    review=review,
                    total_duration_seconds=total_duration,
                )

                self._display_final_result(result)
                return result

            # Review failed -- record and continue to next attempt
            review_issues = "; ".join(review.issues[:3])
            all_errors.append(
                f"Codex attempt {attempt_num} review failed: {review_issues}"
            )
            attempt_history.append(attempt)
            console.print(
                f"[yellow]Codex attempt {attempt_num} review failed:[/yellow] "
                f"{len(review.issues)} issues"
            )

        # ---- Sonnet fallback ----
        console.print(
            "\n[magenta]All Codex attempts failed. "
            "Falling back to Claude Code Sonnet...[/magenta]"
        )

        sonnet_attempt_num = max_codex_attempts + 1
        sonnet_start = time.monotonic()
        sonnet_attempt = BuildAttempt(
            method=BuildMethod.SONNET,
            attempt_number=sonnet_attempt_num,
            success=False,
            started_at=datetime.now(timezone.utc).isoformat(),
            duration_seconds=0.0,
        )

        sonnet_result = await self.sonnet_runner.run(
            prompt=prompt_content,
            worktree_path=worktree_path_str,
        )

        sonnet_attempt.duration_seconds = time.monotonic() - sonnet_start
        sonnet_attempt.files_created = sonnet_result.files_created
        sonnet_attempt.files_modified = sonnet_result.files_modified
        sonnet_attempt.errors = sonnet_result.errors

        if sonnet_result.success:
            # Run review on Sonnet output
            console.print("[cyan]Reviewing Sonnet output...[/cyan]")
            review = await self.reviewer.review(worktree_path_str, feature)
            sonnet_attempt.review_passed = review.passed

            if review.passed:
                sonnet_attempt.success = True
                attempt_history.append(sonnet_attempt)
                total_duration = time.monotonic() - pipeline_start

                result = BuildResult(
                    success=True,
                    feature_name=feature_name,
                    method=BuildMethod.SONNET.value,
                    attempts=sonnet_attempt_num,
                    result={
                        "files_created": sonnet_result.files_created,
                        "files_modified": sonnet_result.files_modified,
                    },
                    errors=[],
                    attempt_history=attempt_history,
                    review=review,
                    total_duration_seconds=total_duration,
                )

                self._display_final_result(result)
                return result

            # Sonnet review failed
            review_issues = "; ".join(review.issues[:3])
            all_errors.append(f"Sonnet review failed: {review_issues}")
        else:
            all_errors.extend(sonnet_result.errors)

        attempt_history.append(sonnet_attempt)

        # ---- Escalation to user ----
        console.print(
            Panel(
                f"[bold red]All automated build attempts failed for:[/bold red] "
                f"{feature_name}\n\n"
                f"Total attempts: {sonnet_attempt_num}\n"
                f"Errors: {len(all_errors)}\n\n"
                "Manual intervention required. The worktree is preserved at:\n"
                f"  {worktree_path_str}\n\n"
                "You can:\n"
                "  1. Implement the feature manually in the worktree\n"
                "  2. Fix the issues and re-run the pipeline\n"
                "  3. Remove the feature from scope",
                title="Escalation Required",
                border_style="red",
            )
        )

        total_duration = time.monotonic() - pipeline_start
        return BuildResult(
            success=False,
            feature_name=feature_name,
            method=BuildMethod.MANUAL.value,
            attempts=sonnet_attempt_num,
            result={},
            errors=all_errors,
            attempt_history=attempt_history,
            review=None,
            total_duration_seconds=total_duration,
        )

    async def execute_parallel(
        self,
        features: list[dict],
        architecture: dict,
        project_path: str,
        max_parallel: int = 3,
        max_codex_attempts: int = 2,
    ) -> list[BuildResult]:
        """Execute multiple feature builds in parallel with fallback.

        Limits concurrency to max_parallel simultaneous builds.

        Args:
            features: List of feature specification dicts.
            architecture: Architecture context dict.
            project_path: Absolute path to the project.
            max_parallel: Maximum concurrent builds (default: 3).
            max_codex_attempts: Maximum Codex attempts per feature.

        Returns:
            List of BuildResult, one per feature.
        """
        console.print(
            Panel(
                f"[bold cyan]Parallel build pipeline[/bold cyan]\n"
                f"  Features: {len(features)}\n"
                f"  Max parallel: {max_parallel}\n"
                f"  Max Codex attempts per feature: {max_codex_attempts}",
                title="Parallel Builds",
                border_style="cyan",
            )
        )

        semaphore = asyncio.Semaphore(max_parallel)

        async def _build_with_semaphore(feat: dict) -> BuildResult:
            async with semaphore:
                return await self.execute_with_fallback(
                    feature=feat,
                    architecture=architecture,
                    project_path=project_path,
                    max_codex_attempts=max_codex_attempts,
                )

        tasks = [_build_with_semaphore(f) for f in features]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to failed BuildResults
        final_results: list[BuildResult] = []
        for i, res in enumerate(results):
            if isinstance(res, Exception):
                feat_name = features[i].get("name", f"feature-{i}")
                final_results.append(
                    BuildResult(
                        success=False,
                        feature_name=feat_name,
                        method=BuildMethod.MANUAL.value,
                        attempts=0,
                        errors=[f"Unhandled exception: {res}"],
                    )
                )
            else:
                final_results.append(res)

        # Display summary
        self._display_parallel_summary(final_results)

        return final_results

    def _display_final_result(self, result: BuildResult) -> None:
        """Display the final build result."""
        if result.success:
            style = "green"
            title = f"Build Succeeded: {result.feature_name}"
        else:
            style = "red"
            title = f"Build Failed: {result.feature_name}"

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Key", style="bold")
        table.add_column("Value")

        table.add_row(
            "Status",
            "[green]SUCCESS[/green]" if result.success else "[red]FAILED[/red]",
        )
        table.add_row("Method", result.method.upper())
        table.add_row("Attempts", str(result.attempts))
        table.add_row("Duration", f"{result.total_duration_seconds:.1f}s")

        if result.errors:
            table.add_row("Errors", str(len(result.errors)))

        console.print(Panel(table, title=title, border_style=style))

        # Show attempt timeline
        if result.attempt_history:
            console.print("[bold]Attempt History:[/bold]")
            for att in result.attempt_history:
                status = "[green]OK[/green]" if att.success else "[red]FAIL[/red]"
                review = (
                    "[green]passed[/green]" if att.review_passed else "[red]failed[/red]"
                )
                console.print(
                    f"  {att.attempt_number}. [{att.method.value}] "
                    f"{status} ({att.duration_seconds:.1f}s, review: {review})"
                )

    def _display_parallel_summary(self, results: list[BuildResult]) -> None:
        """Display a summary of parallel build results."""
        succeeded = sum(1 for r in results if r.success)
        failed = sum(1 for r in results if not r.success)
        total_time = max((r.total_duration_seconds for r in results), default=0.0)

        table = Table(title="Parallel Build Summary")
        table.add_column("Feature", style="bold")
        table.add_column("Status")
        table.add_column("Method")
        table.add_column("Attempts")
        table.add_column("Duration")
        table.add_column("Issues")

        for r in results:
            status = "[green]PASS[/green]" if r.success else "[red]FAIL[/red]"
            table.add_row(
                r.feature_name,
                status,
                r.method.upper(),
                str(r.attempts),
                f"{r.total_duration_seconds:.1f}s",
                str(len(r.errors)),
            )

        console.print(table)
        console.print(
            f"\n[bold]Total:[/bold] {succeeded} succeeded, {failed} failed "
            f"({total_time:.1f}s wall time)"
        )
