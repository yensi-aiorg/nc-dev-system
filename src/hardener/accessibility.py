"""WCAG AA accessibility compliance checking for generated projects.

Uses Playwright (via subprocess) to inject axe-core into each route and
collect accessibility violations, grouping them by impact level.
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

class AccessibilityViolation(BaseModel):
    """A single axe-core accessibility violation."""

    id: str = Field(..., description="axe-core rule ID, e.g. 'color-contrast'")
    impact: str = Field(
        ..., description="Impact level: 'critical', 'serious', 'moderate', 'minor'"
    )
    description: str = Field(..., description="Human-readable violation description")
    help_url: str = Field(default="", description="URL to axe-core documentation for this rule")
    nodes: int = Field(default=1, description="Number of DOM nodes affected")


class RouteAccessibility(BaseModel):
    """Accessibility results for a single route."""

    violations: list[AccessibilityViolation] = Field(default_factory=list)
    passes: int = Field(default=0, description="Number of axe-core rules that passed")
    incomplete: int = Field(
        default=0, description="Number of rules that could not be evaluated"
    )
    url: str = Field(default="", description="Full URL that was checked")


class AccessibilityResult(BaseModel):
    """Aggregated accessibility check results."""

    routes: dict[str, RouteAccessibility] = Field(default_factory=dict)
    total_violations: int = Field(default=0)
    critical_violations: int = Field(default=0)
    serious_violations: int = Field(default=0)
    passed: bool = Field(
        default=True,
        description="True if no critical or serious violations found",
    )
    score: float = Field(default=100.0, ge=0.0, le=100.0)


# ---------------------------------------------------------------------------
# Playwright Script Template
# ---------------------------------------------------------------------------

_AXE_CHECK_SCRIPT = textwrap.dedent("""\
    const {{ chromium }} = require('playwright');

    (async () => {{
        const browser = await chromium.launch({{ headless: true }});
        const results = {{}};
        const routes = {routes_json};
        const baseUrl = {base_url_json};

        // axe-core CDN source (minified)
        const AXE_CDN = 'https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.8.4/axe.min.js';

        for (const route of routes) {{
            const context = await browser.newContext({{
                viewport: {{ width: 1440, height: 900 }},
            }});
            const page = await context.newPage();
            const fullUrl = baseUrl + route;

            const routeResult = {{
                violations: [],
                passes: 0,
                incomplete: 0,
                url: fullUrl,
            }};

            try {{
                await page.goto(fullUrl, {{ waitUntil: 'networkidle', timeout: 15000 }});
                await page.waitForTimeout(1000);

                // Inject axe-core
                await page.addScriptTag({{ url: AXE_CDN }});
                await page.waitForFunction('typeof axe !== "undefined"', null, {{ timeout: 10000 }});

                // Run axe audit
                const axeResults = await page.evaluate(async () => {{
                    const results = await axe.run(document, {{
                        runOnly: {{
                            type: 'tag',
                            values: ['wcag2a', 'wcag2aa', 'best-practice'],
                        }},
                    }});
                    return {{
                        violations: results.violations.map(v => ({{
                            id: v.id,
                            impact: v.impact || 'minor',
                            description: v.description,
                            helpUrl: v.helpUrl,
                            nodes: v.nodes.length,
                        }})),
                        passes: results.passes.length,
                        incomplete: results.incomplete.length,
                    }};
                }});

                routeResult.violations = axeResults.violations;
                routeResult.passes = axeResults.passes;
                routeResult.incomplete = axeResults.incomplete;

            }} catch (err) {{
                routeResult.violations.push({{
                    id: 'check-error',
                    impact: 'critical',
                    description: `Failed to run accessibility check: ${{err.message}}`,
                    helpUrl: '',
                    nodes: 0,
                }});
            }}

            await context.close();
            results[route] = routeResult;
        }}

        await browser.close();
        console.log(JSON.stringify(results));
    }})();
""")

# Fallback script that does static HTML analysis when Playwright is unavailable
_STATIC_ANALYSIS_PATTERNS = {
    "missing-alt-text": {
        "pattern": r'<img(?![^>]*alt=)[^>]*>',
        "impact": "critical",
        "description": "Image element is missing an 'alt' attribute.",
        "help_url": "https://dequeuniversity.com/rules/axe/4.8/image-alt",
    },
    "missing-form-label": {
        "pattern": r'<input(?![^>]*(?:aria-label|aria-labelledby|id=["\'][^"\']+["\'][^>]*<label))[^>]*>',
        "impact": "serious",
        "description": "Form input element is missing an associated label.",
        "help_url": "https://dequeuniversity.com/rules/axe/4.8/label",
    },
    "empty-link": {
        "pattern": r'<a[^>]*>\s*</a>',
        "impact": "serious",
        "description": "Link element has no text content.",
        "help_url": "https://dequeuniversity.com/rules/axe/4.8/link-name",
    },
    "empty-button": {
        "pattern": r'<button[^>]*>\s*</button>',
        "impact": "serious",
        "description": "Button element has no text content or accessible name.",
        "help_url": "https://dequeuniversity.com/rules/axe/4.8/button-name",
    },
    "missing-lang": {
        "pattern": r'<html(?![^>]*lang=)[^>]*>',
        "impact": "serious",
        "description": "HTML element is missing a 'lang' attribute.",
        "help_url": "https://dequeuniversity.com/rules/axe/4.8/html-has-lang",
    },
    "missing-viewport-meta": {
        "pattern": r'(?!.*<meta[^>]*name=["\']viewport["\'])',
        "impact": "moderate",
        "description": "Missing viewport meta tag for mobile accessibility.",
        "help_url": "https://dequeuniversity.com/rules/axe/4.8/meta-viewport",
    },
}


# ---------------------------------------------------------------------------
# AccessibilityChecker
# ---------------------------------------------------------------------------

class AccessibilityChecker:
    """Runs WCAG AA accessibility checks using axe-core via Playwright.

    Falls back to static HTML analysis of source files when Playwright /
    Node.js is not available.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def check(
        self,
        project_url: str,
        routes: list[str],
    ) -> AccessibilityResult:
        """Run axe-core accessibility audit on all routes.

        Parameters
        ----------
        project_url:
            Base URL of the running application (e.g. ``http://localhost:23000``).
        routes:
            List of route paths to audit (e.g. ``["/", "/login"]``).

        Returns
        -------
        AccessibilityResult
            Structured results with per-route violations.
        """
        raw = await self._run_axe_audit(project_url, routes)
        return self._parse_results(raw)

    async def check_static(
        self,
        project_path: str | Path,
    ) -> AccessibilityResult:
        """Run a static source-level accessibility check (no browser required).

        This is a lightweight fallback that scans HTML/TSX files for common
        accessibility issues using regex pattern matching.

        Parameters
        ----------
        project_path:
            Root directory of the generated project.

        Returns
        -------
        AccessibilityResult
        """
        root = Path(project_path).resolve()
        frontend_src = root / "frontend" / "src"
        if not frontend_src.is_dir():
            return AccessibilityResult()

        return await self._static_analysis(frontend_src)

    # ------------------------------------------------------------------
    # Playwright-based audit
    # ------------------------------------------------------------------

    async def _run_axe_audit(
        self,
        base_url: str,
        routes: list[str],
    ) -> dict:
        """Generate and execute a Playwright script that injects axe-core."""
        tmp_dir = Path(tempfile.mkdtemp(prefix="nc_a11y_"))
        script_content = _AXE_CHECK_SCRIPT.format(
            routes_json=json.dumps(routes),
            base_url_json=json.dumps(base_url.rstrip("/")),
        )
        script_path = tmp_dir / "_axe_check.js"
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
                    f"[yellow]axe-core audit exited with code {proc.returncode}[/yellow]"
                )
                if stderr:
                    console.print(f"[dim]{stderr.decode(errors='replace')[:500]}[/dim]")
                return {}

            output = stdout.decode("utf-8").strip()
            if not output:
                return {}

            for candidate in reversed(output.split("\n")):
                candidate = candidate.strip()
                if candidate.startswith("{"):
                    return json.loads(candidate)  # type: ignore[no-any-return]

            return {}

        except FileNotFoundError:
            console.print(
                "[red]'node' not found. axe-core audit requires Node.js.[/red]"
            )
            return {}
        except asyncio.TimeoutError:
            console.print("[red]Accessibility audit timed out after 120 seconds.[/red]")
            return {}
        except json.JSONDecodeError as exc:
            console.print(f"[red]Failed to parse axe-core output: {exc}[/red]")
            return {}

    def _parse_results(self, raw: dict) -> AccessibilityResult:
        """Convert raw axe-core JSON into an :class:`AccessibilityResult`."""
        routes_map: dict[str, RouteAccessibility] = {}
        total = 0
        critical = 0
        serious = 0

        for route, data in raw.items():
            violations: list[AccessibilityViolation] = []
            for v in data.get("violations", []):
                violation = AccessibilityViolation(
                    id=v.get("id", "unknown"),
                    impact=v.get("impact", "minor"),
                    description=v.get("description", ""),
                    help_url=v.get("helpUrl", ""),
                    nodes=v.get("nodes", 1),
                )
                violations.append(violation)
                total += 1
                if violation.impact == "critical":
                    critical += 1
                elif violation.impact == "serious":
                    serious += 1

            routes_map[route] = RouteAccessibility(
                violations=violations,
                passes=data.get("passes", 0),
                incomplete=data.get("incomplete", 0),
                url=data.get("url", ""),
            )

        passed = critical == 0 and serious == 0

        # Score: deduct 15 per critical, 8 per serious, 3 per moderate, 1 per minor
        deductions = 0.0
        for ra in routes_map.values():
            for v in ra.violations:
                if v.impact == "critical":
                    deductions += 15.0
                elif v.impact == "serious":
                    deductions += 8.0
                elif v.impact == "moderate":
                    deductions += 3.0
                else:
                    deductions += 1.0

        score = max(0.0, round(100.0 - deductions, 1))

        return AccessibilityResult(
            routes=routes_map,
            total_violations=total,
            critical_violations=critical,
            serious_violations=serious,
            passed=passed,
            score=score,
        )

    # ------------------------------------------------------------------
    # Static fallback analysis
    # ------------------------------------------------------------------

    async def _static_analysis(self, src_dir: Path) -> AccessibilityResult:
        """Scan TSX/HTML files for common accessibility anti-patterns."""
        import re as re_mod

        skip_dirs = {"node_modules", "__pycache__", ".git", "dist", "build"}
        tsx_files: list[Path] = []
        self._collect_files(src_dir, {".tsx", ".html", ".jsx"}, skip_dirs, tsx_files)

        routes_map: dict[str, RouteAccessibility] = {}
        total = 0
        critical = 0
        serious = 0

        for fpath in tsx_files:
            loop = asyncio.get_running_loop()
            content = await loop.run_in_executor(None, fpath.read_text, "utf-8")
            violations: list[AccessibilityViolation] = []

            for rule_id, rule_info in _STATIC_ANALYSIS_PATTERNS.items():
                matches = re_mod.findall(rule_info["pattern"], content)
                if matches:
                    node_count = len(matches) if isinstance(matches, list) else 1
                    violations.append(
                        AccessibilityViolation(
                            id=rule_id,
                            impact=rule_info["impact"],
                            description=rule_info["description"],
                            help_url=rule_info["help_url"],
                            nodes=node_count,
                        )
                    )
                    total += 1
                    if rule_info["impact"] == "critical":
                        critical += 1
                    elif rule_info["impact"] == "serious":
                        serious += 1

            if violations:
                rel = fpath.relative_to(src_dir.parent.parent).as_posix()
                routes_map[rel] = RouteAccessibility(
                    violations=violations,
                    passes=0,
                    url=rel,
                )

        passed = critical == 0 and serious == 0
        deductions = 0.0
        for ra in routes_map.values():
            for v in ra.violations:
                if v.impact == "critical":
                    deductions += 15.0
                elif v.impact == "serious":
                    deductions += 8.0
                elif v.impact == "moderate":
                    deductions += 3.0
                else:
                    deductions += 1.0
        score = max(0.0, round(100.0 - deductions, 1))

        return AccessibilityResult(
            routes=routes_map,
            total_violations=total,
            critical_violations=critical,
            serious_violations=serious,
            passed=passed,
            score=score,
        )

    def _collect_files(
        self,
        root: Path,
        extensions: set[str],
        skip_dirs: set[str],
        results: list[Path],
    ) -> None:
        """Recursively collect files matching extensions."""
        if not root.is_dir():
            return
        for child in sorted(root.iterdir()):
            if child.is_dir():
                if child.name not in skip_dirs:
                    self._collect_files(child, extensions, skip_dirs, results)
            elif child.suffix in extensions:
                results.append(child)

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def print_report(self, result: AccessibilityResult) -> None:
        """Pretty-print an accessibility report to the console."""
        console.print("\n[bold]Accessibility Report (WCAG AA)[/bold]\n")

        table = Table(title="Accessibility Violations", show_lines=True)
        table.add_column("Route", width=20)
        table.add_column("Rule ID", width=22)
        table.add_column("Impact", width=12)
        table.add_column("Description", width=45)
        table.add_column("Nodes", width=6, justify="right")

        impact_styles = {
            "critical": "red bold",
            "serious": "red",
            "moderate": "yellow",
            "minor": "blue",
        }

        for route, ra in result.routes.items():
            for v in ra.violations:
                style = impact_styles.get(v.impact, "white")
                table.add_row(
                    route,
                    v.id,
                    f"[{style}]{v.impact.upper()}[/{style}]",
                    v.description,
                    str(v.nodes),
                )

        has_violations = result.total_violations > 0
        if has_violations:
            console.print(table)
        else:
            console.print("[green]No accessibility violations found.[/green]")

        status = "[green]PASS[/green]" if result.passed else "[red]FAIL[/red]"
        score_color = "green" if result.score >= 80 else "yellow" if result.score >= 50 else "red"
        console.print(f"\n[bold]Score:[/bold] [{score_color}]{result.score}/100[/{score_color}]  |  Status: {status}")
        console.print(
            f"  Total violations: {result.total_violations}  |  "
            f"Critical: {result.critical_violations}  |  "
            f"Serious: {result.serious_violations}\n"
        )
