"""CLI builder process management for builder agents.

Spawns and monitors CLI builder processes (Claude Code or OpenAI Codex) that
implement features in isolated worktrees. Handles timeouts, process crashes,
output parsing, and structured result reporting.

Supports two CLI modes:
- "claude" (default): Uses the Claude Code CLI
- "codex": Uses the OpenAI Codex CLI
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
    """Structured result from a CLI builder execution."""

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
    """Raised when the builder runner encounters an unrecoverable error."""

    def __init__(self, message: str, result: CodexResult | None = None):
        self.result = result
        super().__init__(message)


def _parse_codex_output(raw_json: str) -> dict:
    """Parse the JSON output from a CLI builder.

    The builder may produce multiple JSON objects or wrap output differently.
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

    # Strategy 2: last valid JSON object in output (builder may emit progress before JSON)
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
    """Extract lists of created and modified files from builder output.

    Builder output format may vary; this handles common structures.
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
    """Extract test result summary from builder output."""
    if "test_results" in output:
        return output["test_results"]

    if "tests" in output and isinstance(output["tests"], dict):
        return output["tests"]

    return {}


def _extract_errors(output: dict, stderr: str) -> list[str]:
    """Extract error messages from builder output and stderr."""
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
    """Manages CLI builder process execution for feature building.

    Supports two CLI modes:
    - "claude" (default): Spawns Claude Code CLI processes with -p and --output-format json
    - "codex": Spawns Codex CLI processes with --full-auto --json flags

    Monitors execution, parses output, and returns structured results.
    Handles timeouts and process crashes gracefully.

    The class name is kept as CodexRunner for backward compatibility.
    """

    def __init__(
        self,
        timeout_seconds: float = 600.0,
        codex_binary: str = "codex",
        cli_binary: str | None = None,
        cli_mode: str = "claude",
        cli_model: str = "claude-sonnet-4-6",
    ):
        """Initialize the builder runner.

        Args:
            timeout_seconds: Maximum time to wait for a builder process (default: 600s).
            codex_binary: Path to the codex CLI binary (backward-compat alias for cli_binary).
            cli_binary: Path to the CLI binary. Defaults based on cli_mode if not set.
            cli_mode: CLI mode to use - "claude" or "codex" (default: "claude").
            cli_model: Model to use for claude mode (default: "claude-sonnet-4-6").

        When cli_mode is "codex", authentication is handled by the Codex CLI itself
        (via ``codex login``). When cli_mode is "claude", no separate auth is needed.
        """
        self.timeout_seconds = timeout_seconds
        self.cli_mode = cli_mode
        self.cli_model = cli_model

        # Resolve cli_binary: explicit cli_binary > backward-compat codex_binary > mode default
        if cli_binary is not None:
            self.cli_binary = cli_binary
        elif codex_binary != "codex":
            # User explicitly set codex_binary to a custom path
            self.cli_binary = codex_binary
        else:
            # Use default based on mode
            self.cli_binary = "claude" if cli_mode == "claude" else "codex"

    @property
    def codex_binary(self) -> str:
        """Backward-compatible property returning the CLI binary path."""
        return self.cli_binary

    async def run(
        self,
        prompt_path: str,
        worktree_path: str,
        output_path: str,
        stdout_log_path: str | None = None,
        stderr_log_path: str | None = None,
    ) -> CodexResult:
        """Execute the CLI builder to implement a feature.

        For codex mode, spawns:
            codex exec --full-auto --json --cd {worktree_path}
                    "$(cat {prompt_path})" -o {output_path}

        For claude mode, spawns:
            claude -p {prompt_content} --output-format json --model {cli_model}
                   --allowedTools "Edit,Write,Bash,Read,Glob,Grep" --cd {worktree_path}

        Monitors stdout/stderr for progress, parses JSON output,
        and returns a structured result.

        Args:
            prompt_path: Path to the prompt markdown file.
            worktree_path: Path to the git worktree for the feature.
            output_path: Path to write the JSON result output (used by codex mode).

        Returns:
            CodexResult with execution details.

        Raises:
            CodexRunnerError: If the process cannot be started at all.
        """
        prompt_file = Path(prompt_path)
        worktree = Path(worktree_path)
        output_file = Path(output_path)
        stdout_log_file = Path(stdout_log_path).resolve() if stdout_log_path else None
        stderr_log_file = Path(stderr_log_path).resolve() if stderr_log_path else None

        if not prompt_file.exists():
            raise CodexRunnerError(f"Prompt file not found: {prompt_path}")
        if not worktree.exists():
            raise CodexRunnerError(f"Worktree path not found: {worktree_path}")

        # Ensure output directory exists
        output_file.parent.mkdir(parents=True, exist_ok=True)
        if stdout_log_file:
            stdout_log_file.parent.mkdir(parents=True, exist_ok=True)
            stdout_log_file.write_text("", encoding="utf-8")
        if stderr_log_file:
            stderr_log_file.parent.mkdir(parents=True, exist_ok=True)
            stderr_log_file.write_text("", encoding="utf-8")

        # Read the prompt content
        prompt_content = prompt_file.read_text(encoding="utf-8")

        mode_label = self.cli_mode.capitalize()
        console.print(
            Panel(
                f"[cyan]Starting {mode_label} builder[/cyan]\n"
                f"  CLI: {self.cli_binary} ({self.cli_mode} mode)\n"
                f"  Prompt: {prompt_path}\n"
                f"  Worktree: {worktree_path}\n"
                f"  Output: {output_path}\n"
                f"  Timeout: {self.timeout_seconds}s",
                title="Builder Runner",
                border_style="cyan",
            )
        )

        # Build the command based on cli_mode.
        # For large prompts (>100KB), pass via a temp file to avoid ARG_MAX limits.
        _use_prompt_file = len(prompt_content.encode("utf-8")) > 100_000
        if _use_prompt_file:
            _prompt_tmp = worktree / ".nc-dev-prompt.md"
            _prompt_tmp.parent.mkdir(parents=True, exist_ok=True)
            _prompt_tmp.write_text(prompt_content, encoding="utf-8")

        if self.cli_mode == "codex":
            if _use_prompt_file:
                cmd = [
                    self.cli_binary,
                    "exec",
                    "--full-auto",
                    "--sandbox", "danger-full-access",
                    "--json",
                    "--cd", str(worktree),
                    f"$(cat {_prompt_tmp})",
                    "-o", str(output_file),
                ]
            else:
                cmd = [
                    self.cli_binary,
                    "exec",
                    "--full-auto",
                    "--sandbox", "danger-full-access",
                    "--json",
                    "--cd", str(worktree),
                    prompt_content,
                    "-o", str(output_file),
                ]
        else:
            # claude mode
            if _use_prompt_file:
                cmd = [
                    self.cli_binary,
                    "-p", f"Read the file .nc-dev-prompt.md in the current directory for your full instructions, then follow them.",
                    "--output-format", "json",
                    "--model", self.cli_model,
                    "--allowedTools",
                    "Edit,Write,Bash,Read,Glob,Grep",
                    "--cd", str(worktree),
                ]
            else:
                cmd = [
                    self.cli_binary,
                    "-p", prompt_content,
                    "--output-format", "json",
                    "--model", self.cli_model,
                    "--allowedTools",
                    "Edit,Write,Bash,Read,Glob,Grep",
                    "--cd", str(worktree),
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
                f"Builder CLI not found: '{self.cli_binary}'. "
                f"Ensure the {mode_label} CLI is installed and in PATH."
            )
        except PermissionError:
            raise CodexRunnerError(
                f"Permission denied executing: '{self.cli_binary}'. "
                "Check file permissions."
            )

        # Monitor the process with timeout
        async def _read_stream(stream, chunks: list[str], log_file: Path | None) -> None:
            while True:
                chunk = await stream.read(4096)
                if not chunk:
                    return
                text = chunk.decode("utf-8", errors="replace")
                chunks.append(text)
                if log_file:
                    with log_file.open("a", encoding="utf-8") as handle:
                        handle.write(text)

        use_streaming = bool(stdout_log_file or stderr_log_file) and all(
            hasattr(obj, attr)
            for obj, attr in (
                (process, "wait"),
                (process, "stdout"),
                (process, "stderr"),
                (getattr(process, "stdout", None), "read"),
                (getattr(process, "stderr", None), "read"),
            )
        )

        try:
            if use_streaming:
                await asyncio.wait_for(
                    asyncio.gather(
                        _read_stream(process.stdout, stdout_chunks, stdout_log_file),
                        _read_stream(process.stderr, stderr_chunks, stderr_log_file),
                        process.wait(),
                    ),
                    timeout=self.timeout_seconds,
                )
                stdout_text = "".join(stdout_chunks)
                stderr_text = "".join(stderr_chunks)
            else:  # pragma: no cover - compatibility path for older mocks
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.timeout_seconds,
                )
                stdout_text = stdout_bytes.decode("utf-8", errors="replace")
                stderr_text = stderr_bytes.decode("utf-8", errors="replace")
                if stdout_log_file:
                    stdout_log_file.write_text(stdout_text, encoding="utf-8")
                if stderr_log_file:
                    stderr_log_file.write_text(stderr_text, encoding="utf-8")
        except asyncio.TimeoutError:
            elapsed = time.monotonic() - start_time
            console.print(
                f"[red]Builder process timed out after {elapsed:.1f}s. Killing...[/red]"
            )
            process.kill()
            try:
                await asyncio.wait_for(process.communicate(), timeout=10.0)
            except asyncio.TimeoutError:
                pass
            stdout_text = "".join(stdout_chunks)
            stderr_text = "".join(stderr_chunks)

            return CodexResult(
                success=False,
                errors=[f"Process timed out after {self.timeout_seconds}s"],
                duration_seconds=elapsed,
                stdout=stdout_text,
                stderr=stderr_text,
                exit_code=-1,
            )

        elapsed = time.monotonic() - start_time
        exit_code = process.returncode if process.returncode is not None else -1

        # Log progress
        if stderr_text.strip():
            for line in stderr_text.strip().split("\n")[:10]:
                console.print(f"  [dim]{line.strip()}[/dim]")

        # Parse output based on mode
        raw_output: dict = {}
        if self.cli_mode == "codex":
            # Codex writes JSON result to the output file
            if output_file.exists():
                try:
                    raw_output = json.loads(
                        output_file.read_text(encoding="utf-8")
                    )
                except (json.JSONDecodeError, OSError):
                    raw_output = _parse_codex_output(stdout_text)
            else:
                raw_output = _parse_codex_output(stdout_text)
        else:
            # Claude mode: parse result from stdout only (no -o support)
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
        """Execute CLI builder with a live progress spinner.

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
            title = "Builder Succeeded"
        else:
            style = "red"
            title = "Builder Failed"

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
        """Check if the CLI builder is available in PATH.

        Uses ``claude --version`` for claude mode, ``codex --version`` for codex mode.

        Returns:
            True if the CLI binary can be found and executed.
        """
        try:
            process = await asyncio.create_subprocess_exec(
                self.cli_binary, "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, _ = await asyncio.wait_for(
                process.communicate(), timeout=10.0
            )
            version = stdout_bytes.decode("utf-8", errors="replace").strip()
            mode_label = self.cli_mode.capitalize()
            console.print(f"[green]{mode_label} CLI available:[/green] {version}")
            return True
        except (FileNotFoundError, asyncio.TimeoutError):
            mode_label = self.cli_mode.capitalize()
            console.print(
                f"[red]{mode_label} CLI not available:[/red] '{self.cli_binary}' "
                "not found in PATH."
            )
            return False

    async def check_authenticated(self) -> bool:
        """Check if the CLI builder is authenticated.

        For codex mode, checks via ``codex login status``.
        For claude mode, this is a no-op that always returns True (no separate auth needed).

        Returns:
            True if authentication is confirmed or not required.
        """
        if self.cli_mode == "claude":
            # Claude CLI does not need separate authentication
            console.print("[green]Builder CLI (claude) does not require separate auth.[/green]")
            return True

        # Codex mode: check via codex login status
        try:
            process = await asyncio.create_subprocess_exec(
                self.cli_binary, "login", "status",
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
