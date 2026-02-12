"""Codex CLI process management for builder agents.

Spawns and monitors OpenAI Codex CLI processes that implement features
in isolated worktrees. Handles timeouts, process crashes, output parsing,
and structured result reporting.
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table

console = Console()


@dataclass
class CodexResult:
    """Structured result from a Codex CLI execution."""

    success: bool
    files_created: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    test_results: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1
    raw_output: dict | None = None

    def summary(self) -> str:
        """Return a human-readable summary of the result."""
        status = "[green]SUCCESS[/green]" if self.success else "[red]FAILED[/red]"
        lines = [
            f"Status: {status}",
            f"Duration: {self.duration_seconds:.1f}s",
            f"Files created: {len(self.files_created)}",
            f"Files modified: {len(self.files_modified)}",
        ]
        if self.errors:
            lines.append(f"Errors: {len(self.errors)}")
            for err in self.errors[:5]:
                lines.append(f"  - {err[:200]}")
        if self.test_results:
            passed = self.test_results.get("passed", 0)
            failed = self.test_results.get("failed", 0)
            lines.append(f"Tests: {passed} passed, {failed} failed")
        return "\n".join(lines)


class CodexRunnerError(Exception):
    """Raised when the Codex runner encounters an unrecoverable error."""

    def __init__(self, message: str, result: CodexResult | None = None):
        self.result = result
        super().__init__(message)


def _parse_codex_output(raw_json: str) -> dict:
    """Parse the JSON output from Codex CLI.

    Codex may produce multiple JSON objects or wrap output differently.
    This tries several strategies to extract valid JSON.
    """
    raw_json = raw_json.strip()
    if not raw_json:
        return {}

    # Strategy 1: direct JSON parse
    try:
        return json.loads(raw_json)
    except json.JSONDecodeError:
        pass

    # Strategy 2: last valid JSON object in output (Codex may emit progress before JSON)
    last_brace = raw_json.rfind("}")
    if last_brace != -1:
        first_brace = raw_json.rfind("{", 0, last_brace)
        if first_brace != -1:
            try:
                return json.loads(raw_json[first_brace : last_brace + 1])
            except json.JSONDecodeError:
                pass

    # Strategy 3: try JSONL (multiple JSON objects, take last one)
    lines = raw_json.split("\n")
    for line in reversed(lines):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue

    return {}


def _extract_files_from_output(
    output: dict,
) -> tuple[list[str], list[str]]:
    """Extract lists of created and modified files from Codex output.

    Codex output format may vary; this handles common structures.
    """
    created: list[str] = []
    modified: list[str] = []

    # Check for direct fields
    if "files_created" in output:
        created = output["files_created"]
    if "files_modified" in output:
        modified = output["files_modified"]

    # Check for a 'files' list with action metadata
    if "files" in output and isinstance(output["files"], list):
        for f in output["files"]:
            if isinstance(f, dict):
                path = f.get("path", "")
                action = f.get("action", "create")
                if action == "create":
                    created.append(path)
                else:
                    modified.append(path)
            elif isinstance(f, str):
                created.append(f)

    # Check for 'changes' structure
    if "changes" in output and isinstance(output["changes"], list):
        for change in output["changes"]:
            if isinstance(change, dict):
                path = change.get("file", change.get("path", ""))
                if path:
                    change_type = change.get("type", "create")
                    if change_type in ("create", "add", "new"):
                        created.append(path)
                    else:
                        modified.append(path)

    return created, modified


def _extract_test_results(output: dict) -> dict:
    """Extract test result summary from Codex output."""
    if "test_results" in output:
        return output["test_results"]

    if "tests" in output and isinstance(output["tests"], dict):
        return output["tests"]

    return {}


def _extract_errors(output: dict, stderr: str) -> list[str]:
    """Extract error messages from Codex output and stderr."""
    errors: list[str] = []

    if "errors" in output and isinstance(output["errors"], list):
        errors.extend(str(e) for e in output["errors"])

    if "error" in output:
        errors.append(str(output["error"]))

    # Parse meaningful lines from stderr
    if stderr:
        for line in stderr.split("\n"):
            line = line.strip()
            if line and any(
                keyword in line.lower()
                for keyword in ["error", "failed", "exception", "traceback", "fatal"]
            ):
                errors.append(line)

    return errors


class CodexRunner:
    """Manages Codex CLI process execution for feature building.

    Spawns Codex CLI processes with --full-auto --json flags, monitors their
    execution, parses output, and returns structured results. Handles timeouts
    and process crashes gracefully.
    """

    def __init__(
        self,
        timeout_seconds: float = 600.0,
        codex_binary: str = "codex",
    ):
        """Initialize the Codex runner.

        Args:
            timeout_seconds: Maximum time to wait for a Codex process (default: 600s).
            codex_binary: Path to the codex CLI binary (default: "codex").

        Authentication is handled by the Codex CLI itself (via ``codex login``).
        No API keys are needed here.
        """
        self.timeout_seconds = timeout_seconds
        self.codex_binary = codex_binary

    async def run(
        self,
        prompt_path: str,
        worktree_path: str,
        output_path: str,
    ) -> CodexResult:
        """Execute Codex CLI to implement a feature.

        Spawns: codex exec --full-auto --json --cd {worktree_path}
                "$(cat {prompt_path})" -o {output_path}

        Monitors stdout/stderr for progress, parses JSON output,
        and returns a structured result.

        Args:
            prompt_path: Path to the prompt markdown file.
            worktree_path: Path to the git worktree for the feature.
            output_path: Path to write the JSON result output.

        Returns:
            CodexResult with execution details.

        Raises:
            CodexRunnerError: If the process cannot be started at all.
        """
        prompt_file = Path(prompt_path)
        worktree = Path(worktree_path)
        output_file = Path(output_path)

        if not prompt_file.exists():
            raise CodexRunnerError(f"Prompt file not found: {prompt_path}")
        if not worktree.exists():
            raise CodexRunnerError(f"Worktree path not found: {worktree_path}")

        # Ensure output directory exists
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Read the prompt content
        prompt_content = prompt_file.read_text(encoding="utf-8")

        console.print(
            Panel(
                f"[cyan]Starting Codex builder[/cyan]\n"
                f"  Prompt: {prompt_path}\n"
                f"  Worktree: {worktree_path}\n"
                f"  Output: {output_path}\n"
                f"  Timeout: {self.timeout_seconds}s",
                title="Codex Runner",
                border_style="cyan",
            )
        )

        # Build the command
        cmd = [
            self.codex_binary,
            "exec",
            "--full-auto",
            "--json",
            "--cd", str(worktree),
            prompt_content,
            "-o", str(output_file),
        ]

        start_time = time.monotonic()
        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            raise CodexRunnerError(
                f"Codex binary not found: '{self.codex_binary}'. "
                "Ensure the Codex CLI is installed and in PATH."
            )
        except PermissionError:
            raise CodexRunnerError(
                f"Permission denied executing: '{self.codex_binary}'. "
                "Check file permissions."
            )

        # Monitor the process with timeout
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout_seconds,
            )
            stdout_text = stdout_bytes.decode("utf-8", errors="replace")
            stderr_text = stderr_bytes.decode("utf-8", errors="replace")
        except asyncio.TimeoutError:
            elapsed = time.monotonic() - start_time
            console.print(
                f"[red]Codex process timed out after {elapsed:.1f}s. Killing...[/red]"
            )
            process.kill()
            try:
                await asyncio.wait_for(process.communicate(), timeout=10.0)
            except asyncio.TimeoutError:
                pass

            return CodexResult(
                success=False,
                errors=[f"Process timed out after {self.timeout_seconds}s"],
                duration_seconds=elapsed,
                exit_code=-1,
            )

        elapsed = time.monotonic() - start_time
        exit_code = process.returncode if process.returncode is not None else -1

        # Log progress
        if stderr_text.strip():
            for line in stderr_text.strip().split("\n")[:10]:
                console.print(f"  [dim]{line.strip()}[/dim]")

        # Try to read the output file (Codex writes JSON result here)
        raw_output: dict = {}
        if output_file.exists():
            try:
                raw_output = json.loads(
                    output_file.read_text(encoding="utf-8")
                )
            except (json.JSONDecodeError, OSError):
                # Fall back to parsing stdout
                raw_output = _parse_codex_output(stdout_text)
        else:
            # No output file; parse from stdout
            raw_output = _parse_codex_output(stdout_text)

        # Extract structured data
        files_created, files_modified = _extract_files_from_output(raw_output)
        test_results = _extract_test_results(raw_output)
        errors = _extract_errors(raw_output, stderr_text)

        success = exit_code == 0 and len(errors) == 0

        result = CodexResult(
            success=success,
            files_created=files_created,
            files_modified=files_modified,
            test_results=test_results,
            errors=errors,
            duration_seconds=elapsed,
            stdout=stdout_text,
            stderr=stderr_text,
            exit_code=exit_code,
            raw_output=raw_output,
        )

        # Display result summary
        self._display_result(result)

        return result

    async def run_with_progress(
        self,
        prompt_path: str,
        worktree_path: str,
        output_path: str,
        feature_name: str = "feature",
    ) -> CodexResult:
        """Execute Codex CLI with a live progress spinner.

        Same as run() but displays a Rich live spinner while the process executes.

        Args:
            prompt_path: Path to the prompt markdown file.
            worktree_path: Path to the git worktree.
            output_path: Path to write the JSON result.
            feature_name: Display name for the progress indicator.

        Returns:
            CodexResult with execution details.
        """
        spinner = Spinner("dots", text=f"Building {feature_name}...")

        with Live(spinner, console=console, refresh_per_second=4):
            result = await self.run(prompt_path, worktree_path, output_path)

        return result

    def _display_result(self, result: CodexResult) -> None:
        """Display a formatted result summary to the console."""
        if result.success:
            style = "green"
            title = "Codex Build Succeeded"
        else:
            style = "red"
            title = "Codex Build Failed"

        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Key", style="bold")
        table.add_column("Value")

        table.add_row("Exit Code", str(result.exit_code))
        table.add_row("Duration", f"{result.duration_seconds:.1f}s")
        table.add_row("Files Created", str(len(result.files_created)))
        table.add_row("Files Modified", str(len(result.files_modified)))

        if result.test_results:
            passed = result.test_results.get("passed", 0)
            failed = result.test_results.get("failed", 0)
            table.add_row("Tests Passed", str(passed))
            table.add_row("Tests Failed", str(failed))

        if result.errors:
            table.add_row("Errors", str(len(result.errors)))

        console.print(Panel(table, title=title, border_style=style))

        if result.errors:
            for i, err in enumerate(result.errors[:5], 1):
                console.print(f"  [red]{i}. {err[:300]}[/red]")
            if len(result.errors) > 5:
                console.print(
                    f"  [dim]... and {len(result.errors) - 5} more errors[/dim]"
                )

    async def check_available(self) -> bool:
        """Check if the Codex CLI is available in PATH.

        Returns:
            True if the codex binary can be found and executed.
        """
        try:
            process = await asyncio.create_subprocess_exec(
                self.codex_binary, "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, _ = await asyncio.wait_for(
                process.communicate(), timeout=10.0
            )
            version = stdout_bytes.decode("utf-8", errors="replace").strip()
            console.print(f"[green]Codex CLI available:[/green] {version}")
            return True
        except (FileNotFoundError, asyncio.TimeoutError):
            console.print(
                f"[red]Codex CLI not available:[/red] '{self.codex_binary}' "
                "not found in PATH."
            )
            return False

    async def check_authenticated(self) -> bool:
        """Check if the Codex CLI is authenticated (via ``codex login``).

        Returns:
            True if ``codex login status`` exits successfully.
        """
        try:
            process = await asyncio.create_subprocess_exec(
                self.codex_binary, "login", "status",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, _ = await asyncio.wait_for(
                process.communicate(), timeout=10.0
            )
            if process.returncode == 0:
                console.print("[green]Codex CLI authenticated.[/green]")
                return True
            console.print(
                "[red]Codex CLI not authenticated. Run: codex login[/red]"
            )
            return False
        except (FileNotFoundError, asyncio.TimeoutError):
            console.print(
                "[red]Could not verify Codex authentication.[/red]"
            )
            return False
