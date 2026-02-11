"""Responsive design verification for generated projects.

Uses Playwright (via subprocess) to render each route at multiple viewport
sizes and detect common responsive issues such as horizontal overflow,
overlapping elements, and text truncation.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import textwrap
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
from rich.console import Console
from rich.table import Table

console = Console()


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

class ViewportConfig(BaseModel):
    """Viewport dimensions used for responsive testing."""

    name: str = Field(..., description="Human label, e.g. 'desktop'")
    width: int = Field(..., ge=1)
    height: int = Field(..., ge=1)


class ResponsiveIssue(BaseModel):
    """A single responsive design problem detected at a specific viewport."""

    severity: str = Field(..., description="'error', 'warning', or 'info'")
    category: str = Field(
        ...,
        description=(
            "Issue category: 'horizontal-overflow', 'overlapping-elements', "
            "'text-truncation', 'viewport-error'"
        ),
    )
    route: str = Field(..., description="Route path where the issue was found")
    viewport: str = Field(..., description="Viewport name, e.g. 'mobile'")
    description: str = Field(...)
    suggestion: str = Field(...)
    screenshot_path: Optional[str] = Field(
        default=None, description="Path to screenshot capturing the issue"
    )


class RouteResponsiveResult(BaseModel):
    """Results for a single route across all viewports."""

    route: str
    viewports_checked: list[str] = Field(default_factory=list)
    issues: list[ResponsiveIssue] = Field(default_factory=list)
    screenshots: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of viewport name to screenshot file path",
    )


class ResponsiveResult(BaseModel):
    """Aggregated responsive check results."""

    routes: list[RouteResponsiveResult] = Field(default_factory=list)
    total_issues: int = Field(default=0)
    passed: bool = Field(default=True)
    score: float = Field(default=100.0, ge=0.0, le=100.0)


# ---------------------------------------------------------------------------
# Playwright Script Templates
# ---------------------------------------------------------------------------

_RESPONSIVE_CHECK_SCRIPT = textwrap.dedent("""\
    const {{ chromium }} = require('playwright');

    (async () => {{
        const browser = await chromium.launch({{ headless: true }});
        const results = [];

        const viewports = {viewports_json};
        const routes = {routes_json};
        const baseUrl = {base_url_json};

        for (const route of routes) {{
            for (const vp of viewports) {{
                const context = await browser.newContext({{
                    viewport: {{ width: vp.width, height: vp.height }},
                }});
                const page = await context.newPage();
                const routeResult = {{
                    route: route,
                    viewport: vp.name,
                    width: vp.width,
                    height: vp.height,
                    issues: [],
                    screenshot: null,
                }};

                try {{
                    await page.goto(baseUrl + route, {{ waitUntil: 'networkidle', timeout: 15000 }});
                    await page.waitForTimeout(1000);

                    // Capture screenshot
                    const screenshotName = `${{route.replace(/\\//g, '_') || 'home'}}_${{vp.name}}.png`;
                    const screenshotPath = `{output_dir}/${{screenshotName}}`;
                    await page.screenshot({{ path: screenshotPath, fullPage: false }});
                    routeResult.screenshot = screenshotPath;

                    // Check horizontal overflow
                    const overflow = await page.evaluate(() => {{
                        return document.documentElement.scrollWidth > document.documentElement.clientWidth;
                    }});
                    if (overflow) {{
                        const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
                        const clientWidth = await page.evaluate(() => document.documentElement.clientWidth);
                        routeResult.issues.push({{
                            severity: 'error',
                            category: 'horizontal-overflow',
                            description: `Page has horizontal overflow: scrollWidth=${{scrollWidth}}px > clientWidth=${{clientWidth}}px`,
                            suggestion: 'Check for fixed-width elements or missing overflow-x:hidden. Use max-width:100% on images and containers.',
                        }});
                    }}

                    // Check for elements extending beyond viewport
                    const overflowingElements = await page.evaluate((vpWidth) => {{
                        const elements = document.querySelectorAll('*');
                        const overflowing = [];
                        for (const el of elements) {{
                            const rect = el.getBoundingClientRect();
                            if (rect.right > vpWidth + 5 && rect.width > 0) {{
                                const tag = el.tagName.toLowerCase();
                                const cls = el.className ? `.${{}}{el.className.toString().split(' ')[0]}` : '';
                                overflowing.push(`${{tag}}${{cls}} (right=${{Math.round(rect.right)}}px)`);
                            }}
                        }}
                        return overflowing.slice(0, 5);
                    }}, vp.width);

                    if (overflowingElements.length > 0) {{
                        routeResult.issues.push({{
                            severity: 'warning',
                            category: 'overlapping-elements',
                            description: `Elements extend beyond viewport: ${{overflowingElements.join(', ')}}`,
                            suggestion: 'Use responsive classes (e.g., Tailwind w-full, max-w-screen) to constrain elements within the viewport.',
                        }});
                    }}

                    // Check for text truncation (elements with overflow:hidden and text-overflow:ellipsis)
                    const truncatedCount = await page.evaluate(() => {{
                        const els = document.querySelectorAll('*');
                        let count = 0;
                        for (const el of els) {{
                            const style = window.getComputedStyle(el);
                            if (
                                style.textOverflow === 'ellipsis' &&
                                style.overflow === 'hidden' &&
                                el.scrollWidth > el.clientWidth
                            ) {{
                                count++;
                            }}
                        }}
                        return count;
                    }});

                    if (truncatedCount > 3) {{
                        routeResult.issues.push({{
                            severity: 'info',
                            category: 'text-truncation',
                            description: `${{truncatedCount}} elements have truncated text at this viewport.`,
                            suggestion: 'Consider making text wrap or using responsive font sizes for important content.',
                        }});
                    }}

                }} catch (err) {{
                    routeResult.issues.push({{
                        severity: 'error',
                        category: 'viewport-error',
                        description: `Failed to load route at ${{vp.name}} viewport: ${{err.message}}`,
                        suggestion: 'Ensure the development server is running and the route is accessible.',
                    }});
                }}

                await context.close();
                results.push(routeResult);
            }}
        }}

        await browser.close();
        console.log(JSON.stringify(results));
    }})();
""")


# ---------------------------------------------------------------------------
# ResponsiveChecker
# ---------------------------------------------------------------------------

class ResponsiveChecker:
    """Verifies responsive design at multiple viewports using Playwright.

    For each route at each viewport the checker:
    - Captures a screenshot
    - Detects horizontal overflow
    - Detects elements overflowing the viewport
    - Counts excessive text truncation
    """

    VIEWPORTS: list[ViewportConfig] = [
        ViewportConfig(name="desktop", width=1440, height=900),
        ViewportConfig(name="tablet", width=768, height=1024),
        ViewportConfig(name="mobile", width=375, height=812),
    ]

    def __init__(self, viewports: list[ViewportConfig] | None = None) -> None:
        if viewports is not None:
            self.VIEWPORTS = viewports

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def check(
        self,
        project_url: str,
        routes: list[str],
        output_dir: str | Path | None = None,
    ) -> ResponsiveResult:
        """Run responsive checks at all viewports for all routes.

        Parameters
        ----------
        project_url:
            Base URL of the running application (e.g. ``http://localhost:23000``).
        routes:
            List of route paths to check (e.g. ``["/", "/login", "/dashboard"]``).
        output_dir:
            Directory to save screenshots. A temp directory is used if *None*.

        Returns
        -------
        ResponsiveResult
            Structured results for every route+viewport combination.
        """
        if output_dir is None:
            output_dir = Path(tempfile.mkdtemp(prefix="nc_responsive_"))
        else:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

        raw_results = await self._run_playwright_checks(project_url, routes, output_dir)
        return self._parse_results(raw_results)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _run_playwright_checks(
        self,
        base_url: str,
        routes: list[str],
        output_dir: Path,
    ) -> list[dict]:
        """Generate and execute a Playwright script to perform responsive checks."""
        viewports_data = [vp.model_dump() for vp in self.VIEWPORTS]
        script_content = _RESPONSIVE_CHECK_SCRIPT.format(
            viewports_json=json.dumps(viewports_data),
            routes_json=json.dumps(routes),
            base_url_json=json.dumps(base_url.rstrip("/")),
            output_dir=str(output_dir).replace("\\", "/"),
        )

        script_path = output_dir / "_responsive_check.js"
        script_path.write_text(script_content, encoding="utf-8")

        try:
            proc = await asyncio.create_subprocess_exec(
                "node",
                str(script_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

            if proc.returncode != 0:
                console.print(
                    f"[yellow]Playwright responsive check exited with code "
                    f"{proc.returncode}[/yellow]"
                )
                if stderr:
                    console.print(f"[dim]{stderr.decode(errors='replace')[:500]}[/dim]")
                return []

            output = stdout.decode("utf-8").strip()
            if not output:
                return []

            # The script may emit non-JSON logging before the final JSON line.
            # Take the last line that looks like JSON.
            for candidate in reversed(output.split("\n")):
                candidate = candidate.strip()
                if candidate.startswith("["):
                    return json.loads(candidate)  # type: ignore[no-any-return]

            return []

        except FileNotFoundError:
            console.print(
                "[red]'node' not found. Playwright responsive checks require "
                "Node.js.[/red]"
            )
            return []
        except asyncio.TimeoutError:
            console.print("[red]Responsive check timed out after 120 seconds.[/red]")
            return []
        except json.JSONDecodeError as exc:
            console.print(f"[red]Failed to parse Playwright output: {exc}[/red]")
            return []

    def _parse_results(self, raw: list[dict]) -> ResponsiveResult:
        """Convert raw Playwright JSON output into a :class:`ResponsiveResult`."""
        route_map: dict[str, RouteResponsiveResult] = {}

        for entry in raw:
            route = entry.get("route", "/")
            viewport_name = entry.get("viewport", "unknown")

            if route not in route_map:
                route_map[route] = RouteResponsiveResult(route=route)

            rr = route_map[route]
            rr.viewports_checked.append(viewport_name)

            screenshot = entry.get("screenshot")
            if screenshot:
                rr.screenshots[viewport_name] = screenshot

            for raw_issue in entry.get("issues", []):
                rr.issues.append(
                    ResponsiveIssue(
                        severity=raw_issue.get("severity", "warning"),
                        category=raw_issue.get("category", "unknown"),
                        route=route,
                        viewport=viewport_name,
                        description=raw_issue.get("description", ""),
                        suggestion=raw_issue.get("suggestion", ""),
                        screenshot_path=screenshot,
                    )
                )

        route_results = list(route_map.values())
        total_issues = sum(len(r.issues) for r in route_results)

        # Score: deduct 10 per error, 3 per warning, 1 per info
        deductions = 0.0
        for rr in route_results:
            for issue in rr.issues:
                if issue.severity == "error":
                    deductions += 10.0
                elif issue.severity == "warning":
                    deductions += 3.0
                else:
                    deductions += 1.0

        score = max(0.0, round(100.0 - deductions, 1))
        passed = all(
            issue.severity != "error"
            for rr in route_results
            for issue in rr.issues
        )

        return ResponsiveResult(
            routes=route_results,
            total_issues=total_issues,
            passed=passed,
            score=score,
        )

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def print_report(self, result: ResponsiveResult) -> None:
        """Pretty-print a responsive check report to the console."""
        console.print("\n[bold]Responsive Design Report[/bold]\n")

        table = Table(title="Responsive Issues", show_lines=True)
        table.add_column("Route", width=20)
        table.add_column("Viewport", width=12)
        table.add_column("Severity", width=10)
        table.add_column("Category", width=22)
        table.add_column("Description", width=50)

        severity_styles = {"error": "red", "warning": "yellow", "info": "blue"}

        for route_result in result.routes:
            for issue in route_result.issues:
                style = severity_styles.get(issue.severity, "white")
                table.add_row(
                    issue.route,
                    issue.viewport,
                    f"[{style}]{issue.severity.upper()}[/{style}]",
                    issue.category,
                    issue.description,
                )

        if any(rr.issues for rr in result.routes):
            console.print(table)
        else:
            console.print("[green]No responsive issues found.[/green]")

        score_color = "green" if result.score >= 80 else "yellow" if result.score >= 50 else "red"
        status = "[green]PASS[/green]" if result.passed else "[red]FAIL[/red]"
        console.print(f"\n[bold]Score:[/bold] [{score_color}]{result.score}/100[/{score_color}]  |  Status: {status}")
        console.print(f"  Routes checked: {len(result.routes)}  |  Total issues: {result.total_issues}\n")
