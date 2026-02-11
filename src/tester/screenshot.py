"""Screenshot capture for visual testing.

Uses Playwright (via subprocess) to capture full-page screenshots of every
route at multiple viewports.  Produces a deterministic directory tree:

    <output_dir>/<route_slug>/<viewport_name>.png
"""

from __future__ import annotations

import asyncio
import re
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()

# ---------------------------------------------------------------------------
# Viewport definitions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Viewport:
    """Named viewport dimensions."""

    name: str
    width: int
    height: int


DESKTOP = Viewport("desktop", 1440, 900)
MOBILE = Viewport("mobile", 375, 812)

DEFAULT_VIEWPORTS: list[Viewport] = [DESKTOP, MOBILE]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(route: str) -> str:
    """Turn a URL route path into a safe directory name.

    Examples:
        "/" -> "root"
        "/tasks"  -> "tasks"
        "/tasks/123/edit" -> "tasks-123-edit"
    """
    cleaned = route.strip("/")
    if not cleaned:
        return "root"
    return re.sub(r"[^a-zA-Z0-9]+", "-", cleaned).strip("-").lower()


def _build_playwright_script(url: str, viewport: Viewport, output_path: Path) -> str:
    """Return a self-contained Playwright script for capturing a screenshot."""
    return textwrap.dedent(f"""\
        const {{ chromium }} = require('playwright');

        (async () => {{
            const browser = await chromium.launch({{ headless: true }});
            const context = await browser.newContext({{
                viewport: {{ width: {viewport.width}, height: {viewport.height} }},
                deviceScaleFactor: 1,
            }});
            const page = await context.newPage();
            try {{
                await page.goto('{url}', {{ waitUntil: 'networkidle', timeout: 30000 }});
                await page.waitForTimeout(1000);
                await page.screenshot({{ path: '{output_path}', fullPage: true }});
            }} catch (err) {{
                console.error('Screenshot capture failed:', err.message);
                process.exit(1);
            }} finally {{
                await browser.close();
            }}
        }})();
    """)


# ---------------------------------------------------------------------------
# ScreenshotCapture
# ---------------------------------------------------------------------------

class ScreenshotCapture:
    """Captures screenshots of web application routes at specified viewports."""

    def __init__(
        self,
        base_url: str,
        output_dir: str | Path,
        *,
        viewports: Optional[list[Viewport]] = None,
        timeout_seconds: int = 60,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.output_dir = Path(output_dir)
        self.viewports = viewports or list(DEFAULT_VIEWPORTS)
        self.timeout_seconds = timeout_seconds

    # -- Public API ----------------------------------------------------------

    async def capture_route(self, route: str, viewport: Viewport) -> Path:
        """Capture a single screenshot of *route* at *viewport*.

        Returns the path to the saved PNG file.

        Raises ``RuntimeError`` if the Playwright subprocess exits with a
        non-zero return code.
        """
        url = f"{self.base_url}{route}" if route.startswith("/") else f"{self.base_url}/{route}"
        slug = _slugify(route)
        output_path = self.output_dir / slug / f"{viewport.name}.png"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        await self._run_playwright_capture(url, viewport, output_path)
        return output_path

    async def capture_all_routes(
        self,
        routes: list[str],
        *,
        concurrency: int = 3,
    ) -> dict[str, dict[str, Path]]:
        """Capture every *route* at every configured viewport.

        Returns a mapping of ``{route: {viewport_name: screenshot_path}}``.
        Screenshots are taken with bounded concurrency to avoid overloading
        the machine.
        """
        results: dict[str, dict[str, Path]] = {}
        semaphore = asyncio.Semaphore(concurrency)

        async def _capture(route: str, vp: Viewport) -> tuple[str, str, Path]:
            async with semaphore:
                path = await self.capture_route(route, vp)
                return route, vp.name, path

        tasks: list[asyncio.Task[tuple[str, str, Path]]] = []
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            tid = progress.add_task("Capturing screenshots...", total=len(routes) * len(self.viewports))
            for route in routes:
                for vp in self.viewports:
                    tasks.append(asyncio.create_task(_capture(route, vp)))

            for coro in asyncio.as_completed(tasks):
                route_key, vp_name, screenshot_path = await coro
                results.setdefault(route_key, {})[vp_name] = screenshot_path
                progress.advance(tid)

        console.print(
            f"[green]Captured {sum(len(v) for v in results.values())} "
            f"screenshots across {len(results)} routes.[/green]"
        )
        return results

    # -- Internal ------------------------------------------------------------

    async def _run_playwright_capture(
        self,
        url: str,
        viewport: Viewport,
        output: Path,
    ) -> Path:
        """Execute a Playwright capture script in a subprocess.

        The method first tries the fast ``npx playwright screenshot`` CLI.  If
        that is unavailable or fails, it falls back to running a generated
        Node.js script via ``node -e``.
        """
        # Strategy 1: npx playwright screenshot (simpler, but may not support
        # all options on every Playwright version).
        cli_result = await self._try_npx_screenshot(url, viewport, output)
        if cli_result is not None:
            return cli_result

        # Strategy 2: inline Node script (always works if playwright is installed).
        script = _build_playwright_script(url, viewport, output)
        proc = await asyncio.create_subprocess_exec(
            "node",
            "-e",
            script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=self.timeout_seconds,
        )

        if proc.returncode != 0:
            error_msg = stderr.decode().strip() or stdout.decode().strip()
            raise RuntimeError(
                f"Playwright screenshot failed for {url} "
                f"({viewport.name} {viewport.width}x{viewport.height}): {error_msg}"
            )

        if not output.exists():
            raise RuntimeError(
                f"Playwright exited successfully but screenshot file not found: {output}"
            )

        return output

    async def _try_npx_screenshot(
        self,
        url: str,
        viewport: Viewport,
        output: Path,
    ) -> Optional[Path]:
        """Attempt a capture using ``npx playwright screenshot``.

        Returns the output path on success, or ``None`` if the command is
        unavailable or fails.
        """
        cmd = [
            "npx",
            "playwright",
            "screenshot",
            "--viewport-size",
            f"{viewport.width},{viewport.height}",
            "--full-page",
            url,
            str(output),
        ]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.timeout_seconds,
            )
            if proc.returncode == 0 and output.exists():
                return output
        except (FileNotFoundError, asyncio.TimeoutError):
            pass
        return None
