"""Shared utility functions for the NC Dev System.

Provides async command execution, JSON I/O, file-system helpers, Rich-based
progress reporting, port validation, and health-check polling.  Every public
function is designed to be safe and side-effect-free where possible, with
clear error messages when something goes wrong.
"""

from __future__ import annotations

import asyncio
import json
import re
import socket
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.rule import Rule
from rich.table import Table

console = Console()

# ---------------------------------------------------------------------------
# Async command execution
# ---------------------------------------------------------------------------


async def run_command(
    cmd: str | list[str],
    cwd: str | Path | None = None,
    timeout: int = 120,
    capture: bool = True,
    env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    """Run a shell command asynchronously.

    Args:
        cmd: Shell command string or list of arguments.
        cwd: Working directory for the child process.
        timeout: Maximum wall-clock seconds before the process is killed.
        capture: Whether to capture stdout/stderr (if ``False`` they inherit
            the parent's streams).
        env: Optional extra environment variables merged on top of ``os.environ``.

    Returns:
        A ``(returncode, stdout, stderr)`` tuple.  If *capture* is ``False``
        the stdout/stderr strings will be empty.
    """
    import os

    merged_env: dict[str, str] | None = None
    if env:
        merged_env = {**os.environ, **env}

    stdout_pipe = asyncio.subprocess.PIPE if capture else None
    stderr_pipe = asyncio.subprocess.PIPE if capture else None

    if isinstance(cmd, list):
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=stdout_pipe,
            stderr=stderr_pipe,
            cwd=str(cwd) if cwd else None,
            env=merged_env,
        )
    else:
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=stdout_pipe,
            stderr=stderr_pipe,
            cwd=str(cwd) if cwd else None,
            env=merged_env,
        )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        return (
            -1,
            "",
            f"Command timed out after {timeout}s: {cmd if isinstance(cmd, str) else ' '.join(cmd)}",
        )

    stdout_str = (stdout_bytes or b"").decode("utf-8", errors="replace").strip()
    stderr_str = (stderr_bytes or b"").decode("utf-8", errors="replace").strip()
    return (process.returncode or 0, stdout_str, stderr_str)


async def run_command_streaming(
    cmd: str,
    cwd: str | Path | None = None,
    timeout: int = 600,
    env: dict[str, str] | None = None,
) -> AsyncIterator[str]:
    """Run a command and yield stdout lines as they arrive.

    The generator stops when the process exits or the *timeout* is exceeded.
    Stderr is collected internally and can be retrieved after iteration via
    the generator's ``athrow`` protocol, but in typical usage it is simply
    logged.

    Args:
        cmd: Shell command string.
        cwd: Working directory.
        timeout: Maximum wall-clock seconds.
        env: Optional extra environment variables.

    Yields:
        Individual lines of stdout (without trailing newlines).
    """
    import os
    import time

    merged_env: dict[str, str] | None = None
    if env:
        merged_env = {**os.environ, **env}

    process = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(cwd) if cwd else None,
        env=merged_env,
    )

    assert process.stdout is not None  # guaranteed by PIPE
    deadline = time.monotonic() + timeout

    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process.kill()
                await process.wait()
                yield f"[timeout] Command exceeded {timeout}s limit"
                return

            try:
                line_bytes = await asyncio.wait_for(
                    process.stdout.readline(), timeout=min(remaining, 30)
                )
            except asyncio.TimeoutError:
                # No output for 30s, but overall deadline not yet reached — keep waiting.
                if process.returncode is not None:
                    return
                continue

            if not line_bytes:
                # EOF — process has closed stdout.
                break

            yield line_bytes.decode("utf-8", errors="replace").rstrip("\n")
    finally:
        if process.returncode is None:
            process.kill()
        await process.wait()


# ---------------------------------------------------------------------------
# String / name helpers
# ---------------------------------------------------------------------------


def sanitize_name(name: str) -> str:
    """Convert an arbitrary feature name to a safe directory/branch name.

    * Lowercases the input.
    * Replaces spaces and non-alphanumeric characters (except hyphens and
      underscores) with hyphens.
    * Collapses consecutive hyphens and strips leading/trailing hyphens.

    Examples::

        sanitize_name("User Authentication") -> "user-authentication"
        sanitize_name("  2FA (TOTP)  ") -> "2fa-totp"
    """
    result = re.sub(r"[^a-zA-Z0-9_-]", "-", name.strip().lower())
    result = re.sub(r"-+", "-", result)
    return result.strip("-")


# ---------------------------------------------------------------------------
# JSON I/O
# ---------------------------------------------------------------------------


def load_json(path: str | Path) -> dict[str, Any]:
    """Load and parse a JSON file.

    Args:
        path: Path to the JSON file.

    Returns:
        Parsed dictionary.

    Raises:
        FileNotFoundError: If the file does not exist.
        json.JSONDecodeError: If the file is not valid JSON.
    """
    file_path = Path(path)
    raw = file_path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        return {"_root": data}
    return data


def load_json_list(path: str | Path) -> list[Any]:
    """Load a JSON file that contains a top-level array.

    Returns an empty list if the file does not exist.
    """
    file_path = Path(path)
    if not file_path.exists():
        return []
    raw = file_path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if isinstance(data, list):
        return data
    return [data]


async def save_json(data: dict[str, Any] | list[Any], path: str | Path) -> None:
    """Save data as pretty-printed JSON.

    Parent directories are created automatically.  The write itself is
    performed in a thread-pool executor to avoid blocking the event loop on
    large files.

    Args:
        data: Serialisable data (dict or list).
        path: Destination file path.
    """
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(data, indent=2, ensure_ascii=False, default=str)

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, file_path.write_text, content, "utf-8")


# ---------------------------------------------------------------------------
# File-system helpers
# ---------------------------------------------------------------------------


def ensure_dir(path: str | Path) -> Path:
    """Create a directory (and parents) if it does not exist.

    Args:
        path: Directory path.

    Returns:
        The resolved ``Path`` object.
    """
    dir_path = Path(path)
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path.resolve()


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def format_duration(seconds: float) -> str:
    """Format a duration in seconds to a human-readable string.

    Examples::

        format_duration(3.7)    -> "3.7s"
        format_duration(65.2)   -> "1m 5s"
        format_duration(3661.0) -> "1h 1m 1s"
    """
    if seconds < 0:
        return "0.0s"

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60

    parts: list[str] = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")

    if hours > 0 or minutes > 0:
        parts.append(f"{int(secs)}s")
    else:
        parts.append(f"{secs:.1f}s")

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Rich output helpers
# ---------------------------------------------------------------------------


PHASE_NAMES: dict[int, str] = {
    1: "UNDERSTAND",
    2: "SCAFFOLD",
    3: "BUILD",
    4: "VERIFY",
    5: "HARDEN",
    6: "DELIVER",
}

PHASE_COLORS: dict[int, str] = {
    1: "bright_cyan",
    2: "bright_green",
    3: "bright_yellow",
    4: "bright_magenta",
    5: "bright_red",
    6: "bright_blue",
}


def print_phase_header(phase: int, name: str) -> None:
    """Print a prominent phase header using Rich.

    Renders a full-width rule with the phase number and name, coloured
    according to the phase.

    Args:
        phase: Phase number (1-6).
        name: Phase display name.
    """
    color = PHASE_COLORS.get(phase, "white")
    console.print()
    console.print(
        Rule(
            f"[bold {color}] Phase {phase}: {name.upper()} [/bold {color}]",
            style=color,
        )
    )
    console.print()


def print_summary_table(data: dict[str, str], title: str = "Summary") -> None:
    """Print a two-column key/value summary table.

    Args:
        data: Mapping of label -> value.
        title: Table title.
    """
    table = Table(title=title, show_header=True, header_style="bold cyan")
    table.add_column("Item", style="dim", no_wrap=True)
    table.add_column("Value")

    for key, value in data.items():
        table.add_row(key, str(value))

    console.print(table)
    console.print()


def print_success(message: str) -> None:
    """Print a green success message."""
    console.print(f"[bold green]{message}[/bold green]")


def print_error(message: str) -> None:
    """Print a red error message."""
    console.print(f"[bold red]{message}[/bold red]")


def print_warning(message: str) -> None:
    """Print a yellow warning message."""
    console.print(f"[bold yellow]{message}[/bold yellow]")


def create_progress() -> Progress:
    """Create a Rich progress bar configured for pipeline tasks.

    Returns:
        A ``Progress`` instance suitable for use as a context manager.
    """
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    )


# ---------------------------------------------------------------------------
# Port helpers
# ---------------------------------------------------------------------------


def validate_port(port: int) -> bool:
    """Return ``True`` if the port is in the allowed NC Dev range (>=23000).

    Ports below 23000 are rejected to prevent conflicts with common
    development servers.
    """
    return port >= 23000


async def check_port_available(port: int) -> bool:
    """Check whether a TCP port is available for binding.

    Attempts a non-blocking ``connect`` to localhost:port. If the connection
    is *refused* the port is available; if it *succeeds* something is
    already listening.

    Args:
        port: Port number to probe.

    Returns:
        ``True`` if no service is listening on the port.
    """
    loop = asyncio.get_running_loop()

    def _probe() -> bool:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        try:
            result = sock.connect_ex(("127.0.0.1", port))
            # connect_ex returns 0 on success (port in use), nonzero on failure (port free)
            return result != 0
        finally:
            sock.close()

    return await loop.run_in_executor(None, _probe)


async def check_ports_available(ports: list[int]) -> dict[int, bool]:
    """Check multiple ports concurrently.

    Returns:
        Mapping of ``{port: is_available}``.
    """
    results = await asyncio.gather(*(check_port_available(p) for p in ports))
    return dict(zip(ports, results))


# ---------------------------------------------------------------------------
# Health-check polling
# ---------------------------------------------------------------------------


async def wait_for_health(
    url: str,
    timeout: int = 60,
    interval: int = 2,
) -> bool:
    """Poll a health endpoint until it responds with HTTP 200 or timeout.

    Useful for waiting until a Docker container's health endpoint is ready.

    Args:
        url: Fully-qualified URL (e.g. ``http://localhost:23001/health``).
        timeout: Maximum seconds to wait.
        interval: Seconds between probes.

    Returns:
        ``True`` if a 200 response was received within the timeout window,
        ``False`` otherwise.
    """
    import time

    deadline = time.monotonic() + timeout

    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=3.0)) as client:
        while time.monotonic() < deadline:
            try:
                response = await client.get(url)
                if response.status_code == 200:
                    return True
            except (httpx.ConnectError, httpx.TimeoutException, Exception):
                pass

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            await asyncio.sleep(min(interval, remaining))

    return False
