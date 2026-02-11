"""Final screenshot capture and annotation for project delivery.

Uses Playwright (via subprocess) to capture screenshots at desktop and
mobile viewports for every route, and optionally annotates them with
labels using markdown-based annotation descriptions.
"""

from __future__ import annotations

import asyncio
import json
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
from rich.console import Console
from rich.table import Table

console = Console()


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

class ScreenshotInfo(BaseModel):
    """Metadata for a captured screenshot."""

    route: str = Field(..., description="Route path that was captured")
    viewport: str = Field(..., description="Viewport name: 'desktop' or 'mobile'")
    path: str = Field(..., description="File path where the screenshot is saved")
    width: int = Field(..., description="Viewport width in pixels")
    height: int = Field(..., description="Viewport height in pixels")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Capture timestamp (ISO-8601)",
    )


class AnnotationSpec(BaseModel):
    """Specification for a text annotation on a screenshot."""

    label: str = Field(..., description="Annotation text label")
    x: int = Field(..., description="X coordinate (pixels from left)")
    y: int = Field(..., description="Y coordinate (pixels from top)")
    color: str = Field(default="red", description="Annotation colour")


# ---------------------------------------------------------------------------
# Playwright Script Template
# ---------------------------------------------------------------------------

_CAPTURE_SCRIPT = textwrap.dedent("""\
    const {{ chromium }} = require('playwright');

    (async () => {{
        const browser = await chromium.launch({{ headless: true }});
        const results = [];
        const baseUrl = {base_url_json};
        const routes = {routes_json};
        const outputDir = {output_dir_json};

        const viewports = [
            {{ name: 'desktop', width: 1440, height: 900 }},
            {{ name: 'mobile', width: 375, height: 812 }},
        ];

        for (const route of routes) {{
            for (const vp of viewports) {{
                const context = await browser.newContext({{
                    viewport: {{ width: vp.width, height: vp.height }},
                    deviceScaleFactor: vp.name === 'mobile' ? 2 : 1,
                }});
                const page = await context.newPage();
                const routeSlug = (route.name || route.path || '/')
                    .replace(/\\//g, '_')
                    .replace(/^_/, '') || 'home';
                const filename = `${{routeSlug}}_${{vp.name}}.png`;
                const filepath = `${{outputDir}}/${{filename}}`;

                try {{
                    const fullUrl = baseUrl + (route.path || '/');
                    await page.goto(fullUrl, {{ waitUntil: 'networkidle', timeout: 15000 }});
                    await page.waitForTimeout(1500);

                    await page.screenshot({{
                        path: filepath,
                        fullPage: false,
                    }});

                    results.push({{
                        route: route.path || '/',
                        viewport: vp.name,
                        path: filepath,
                        width: vp.width,
                        height: vp.height,
                        success: true,
                    }});
                }} catch (err) {{
                    results.push({{
                        route: route.path || '/',
                        viewport: vp.name,
                        path: '',
                        width: vp.width,
                        height: vp.height,
                        success: false,
                        error: err.message,
                    }});
                }}

                await context.close();
            }}
        }}

        await browser.close();
        console.log(JSON.stringify(results));
    }})();
""")


# ---------------------------------------------------------------------------
# ScreenshotManager
# ---------------------------------------------------------------------------

class ScreenshotManager:
    """Captures and annotates final screenshots for delivery.

    Captures every route at desktop (1440x900) and mobile (375x812)
    viewports using Playwright, saving PNGs to the specified output
    directory.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def capture_all(
        self,
        base_url: str,
        routes: list[dict],
        output_dir: str | Path,
    ) -> list[ScreenshotInfo]:
        """Capture screenshots at all routes, desktop + mobile.

        Parameters
        ----------
        base_url:
            Base URL of the running application (e.g. ``http://localhost:23000``).
        routes:
            List of route dicts, each with at least ``{"path": "/...", "name": "..."}``.
        output_dir:
            Directory to save screenshots into.

        Returns
        -------
        list[ScreenshotInfo]
            Metadata for each captured screenshot.
        """
        output_path = Path(output_dir).resolve()
        screenshots_dir = output_path / "screenshots"
        screenshots_dir.mkdir(parents=True, exist_ok=True)

        raw_results = await self._run_capture_script(base_url, routes, screenshots_dir)
        screenshots: list[ScreenshotInfo] = []

        for entry in raw_results:
            if entry.get("success"):
                screenshots.append(
                    ScreenshotInfo(
                        route=entry["route"],
                        viewport=entry["viewport"],
                        path=entry["path"],
                        width=entry["width"],
                        height=entry["height"],
                    )
                )
            else:
                console.print(
                    f"[yellow]Failed to capture {entry.get('route', '?')} "
                    f"@ {entry.get('viewport', '?')}: "
                    f"{entry.get('error', 'unknown error')}[/yellow]"
                )

        console.print(f"[green]Captured {len(screenshots)} screenshots[/green]")
        return screenshots

    async def annotate(
        self,
        screenshot_path: Path,
        annotations: list[dict],
    ) -> Path:
        """Add text/arrow annotations to a screenshot.

        Because Pillow may not be available in all environments, this
        method generates a companion markdown file describing the
        annotations alongside the original image. When Pillow *is*
        available, it draws directly on the image.

        Parameters
        ----------
        screenshot_path:
            Path to the screenshot PNG file.
        annotations:
            List of annotation dicts with keys ``label``, ``x``, ``y``,
            and optionally ``color``.

        Returns
        -------
        Path
            Path to the annotated screenshot or annotation markdown file.
        """
        screenshot_path = Path(screenshot_path).resolve()

        if not screenshot_path.is_file():
            console.print(f"[red]Screenshot not found: {screenshot_path}[/red]")
            return screenshot_path

        specs = [AnnotationSpec(**a) for a in annotations]

        # Attempt Pillow-based annotation first
        annotated_path = await self._annotate_with_pillow(screenshot_path, specs)
        if annotated_path is not None:
            return annotated_path

        # Fallback: generate a markdown annotations file
        return await self._annotate_as_markdown(screenshot_path, specs)

    async def generate_index(
        self,
        screenshots: list[ScreenshotInfo],
        output_dir: str | Path,
        project_name: str = "Project",
    ) -> Path:
        """Generate a screenshots index markdown file.

        Parameters
        ----------
        screenshots:
            List of captured screenshot metadata.
        output_dir:
            Directory where the index file will be written.
        project_name:
            Name of the project for the heading.

        Returns
        -------
        Path
            Path to the generated index markdown file.
        """
        output_path = Path(output_dir).resolve()
        index_path = output_path / "screenshots" / "index.md"
        index_path.parent.mkdir(parents=True, exist_ok=True)

        lines: list[str] = [
            f"# {project_name} -- Screenshots",
            "",
            f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            "",
        ]

        # Group by route
        route_map: dict[str, list[ScreenshotInfo]] = {}
        for ss in screenshots:
            route_map.setdefault(ss.route, []).append(ss)

        for route, items in sorted(route_map.items()):
            route_label = route if route != "/" else "/ (Home)"
            lines.append(f"## Route: `{route_label}`")
            lines.append("")

            for item in sorted(items, key=lambda x: x.viewport):
                rel_path = Path(item.path).name
                lines.append(f"### {item.viewport.title()} ({item.width}x{item.height})")
                lines.append("")
                lines.append(f"![{route} - {item.viewport}](./{rel_path})")
                lines.append("")

        content = "\n".join(lines)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, index_path.write_text, content, "utf-8")

        console.print(f"[green]Screenshot index written to {index_path}[/green]")
        return index_path

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _run_capture_script(
        self,
        base_url: str,
        routes: list[dict],
        output_dir: Path,
    ) -> list[dict]:
        """Generate and execute a Playwright capture script."""
        script_content = _CAPTURE_SCRIPT.format(
            base_url_json=json.dumps(base_url.rstrip("/")),
            routes_json=json.dumps(routes),
            output_dir_json=json.dumps(str(output_dir).replace("\\", "/")),
        )

        script_path = output_dir / "_capture.js"
        script_path.write_text(script_content, encoding="utf-8")

        try:
            proc = await asyncio.create_subprocess_exec(
                "node",
                str(script_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=180)

            if proc.returncode != 0:
                console.print(
                    f"[yellow]Screenshot capture exited with code "
                    f"{proc.returncode}[/yellow]"
                )
                if stderr:
                    console.print(f"[dim]{stderr.decode(errors='replace')[:500]}[/dim]")
                return []

            output = stdout.decode("utf-8").strip()
            if not output:
                return []

            for candidate in reversed(output.split("\n")):
                candidate = candidate.strip()
                if candidate.startswith("["):
                    return json.loads(candidate)  # type: ignore[no-any-return]

            return []

        except FileNotFoundError:
            console.print(
                "[red]'node' not found. Screenshot capture requires Node.js.[/red]"
            )
            return []
        except asyncio.TimeoutError:
            console.print("[red]Screenshot capture timed out after 180 seconds.[/red]")
            return []
        except json.JSONDecodeError as exc:
            console.print(f"[red]Failed to parse capture output: {exc}[/red]")
            return []

    async def _annotate_with_pillow(
        self,
        screenshot_path: Path,
        annotations: list[AnnotationSpec],
    ) -> Path | None:
        """Attempt to annotate using Pillow. Returns None if Pillow unavailable."""
        try:
            from PIL import Image, ImageDraw, ImageFont  # type: ignore[import-untyped]
        except ImportError:
            return None

        loop = asyncio.get_running_loop()

        def _draw() -> Path:
            img = Image.open(screenshot_path)
            draw = ImageDraw.Draw(img)

            # Attempt to load a font, fall back to default
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
            except (IOError, OSError):
                font = ImageFont.load_default()

            color_map = {
                "red": (255, 0, 0, 200),
                "green": (0, 180, 0, 200),
                "blue": (0, 100, 255, 200),
                "yellow": (255, 200, 0, 200),
                "white": (255, 255, 255, 200),
            }

            for spec in annotations:
                fill = color_map.get(spec.color, (255, 0, 0, 200))
                # Draw background rectangle for readability
                text_bbox = draw.textbbox((spec.x, spec.y), spec.label, font=font)
                padding = 4
                bg_rect = (
                    text_bbox[0] - padding,
                    text_bbox[1] - padding,
                    text_bbox[2] + padding,
                    text_bbox[3] + padding,
                )
                draw.rectangle(bg_rect, fill=(0, 0, 0, 160))
                draw.text((spec.x, spec.y), spec.label, fill=fill[:3], font=font)

            stem = screenshot_path.stem
            annotated_path = screenshot_path.with_name(f"{stem}_annotated.png")
            img.save(annotated_path)
            return annotated_path

        return await loop.run_in_executor(None, _draw)

    async def _annotate_as_markdown(
        self,
        screenshot_path: Path,
        annotations: list[AnnotationSpec],
    ) -> Path:
        """Generate a markdown annotation companion file."""
        md_path = screenshot_path.with_suffix(".annotations.md")
        lines = [
            f"# Annotations for {screenshot_path.name}",
            "",
            f"![Screenshot](./{screenshot_path.name})",
            "",
            "| # | Label | Position (x, y) | Color |",
            "|---|-------|-----------------|-------|",
        ]
        for idx, spec in enumerate(annotations, start=1):
            lines.append(f"| {idx} | {spec.label} | ({spec.x}, {spec.y}) | {spec.color} |")

        lines.append("")

        content = "\n".join(lines)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, md_path.write_text, content, "utf-8")

        console.print(f"[dim]Annotation descriptions saved to {md_path}[/dim]")
        return md_path

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def print_summary(self, screenshots: list[ScreenshotInfo]) -> None:
        """Print a summary table of captured screenshots."""
        table = Table(title="Captured Screenshots", show_lines=True)
        table.add_column("Route", width=20)
        table.add_column("Viewport", width=12)
        table.add_column("Size", width=12)
        table.add_column("File", width=50)

        for ss in sorted(screenshots, key=lambda s: (s.route, s.viewport)):
            table.add_row(
                ss.route,
                ss.viewport,
                f"{ss.width}x{ss.height}",
                ss.path,
            )

        console.print(table)
