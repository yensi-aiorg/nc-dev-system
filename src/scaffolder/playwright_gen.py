"""Playwright configuration and base test generation.

Generates:
- ``playwright.config.ts`` at the project root (for running E2E from root)
- ``frontend/playwright.config.ts`` (for running from the frontend dir)
- ``frontend/e2e/smoke.spec.ts`` smoke tests covering every route
- Per-feature E2E test files under ``frontend/e2e/``
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from .templates import TemplateRenderer


class PlaywrightGenerator:
    """Generates Playwright configuration and base test files."""

    def __init__(self, renderer: TemplateRenderer) -> None:
        self.renderer = renderer

    async def generate(
        self,
        output_dir: Path,
        routes: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> list[Path]:
        """Generate Playwright config and smoke tests.

        Args:
            output_dir: Project root directory.
            routes: List of route dicts with ``path`` and ``name`` keys.
            context: Template rendering context (project_name, ports, features, etc.).

        Returns:
            List of all written file paths.
        """
        written: list[Path] = []

        # Root-level playwright config (runs from project root)
        root_config = await self.renderer.render_to_file(
            "playwright.config.ts.j2",
            output_dir / "playwright.config.ts",
            context,
        )
        written.append(root_config)

        # Frontend-level playwright config
        frontend_config = await self.renderer.render_to_file(
            "frontend/playwright.config.ts.j2",
            output_dir / "frontend" / "playwright.config.ts",
            context,
        )
        written.append(frontend_config)

        # Smoke test covering home page and navigation
        smoke_test = await self.renderer.render_to_file(
            "frontend/e2e/smoke.spec.ts.j2",
            output_dir / "frontend" / "e2e" / "smoke.spec.ts",
            context,
        )
        written.append(smoke_test)

        # Per-feature E2E tests
        for feature_ctx in context.get("features", []):
            feature_test = await self._generate_feature_e2e(
                output_dir, feature_ctx, context
            )
            written.append(feature_test)

        # Screenshots directory
        screenshots_dir = output_dir / "frontend" / "e2e" / "screenshots"
        await asyncio.to_thread(screenshots_dir.mkdir, parents=True, exist_ok=True)

        return written

    async def _generate_feature_e2e(
        self,
        output_dir: Path,
        feature: dict[str, Any],
        context: dict[str, Any],
    ) -> Path:
        """Generate an E2E test file for a single feature.

        The test navigates to the feature's page, verifies the title is
        visible, and captures desktop and mobile screenshots.
        """
        name_slug = feature.get("name_slug", feature.get("name", "unknown").lower().replace(" ", "-"))
        display_name = feature.get("display_name", feature.get("name", "Unknown"))
        entity_plural = feature.get("entity_plural", name_slug + "s")
        route_path = feature.get("route_path", f"/{name_slug}")

        content = _build_feature_e2e_test(
            name_slug=name_slug,
            display_name=display_name,
            entity_plural=entity_plural,
            route_path=route_path,
            project_name=context.get("project_name", ""),
            auth_required=context.get("auth_required", False),
        )

        out = output_dir / "frontend" / "e2e" / f"{name_slug}.spec.ts"
        await asyncio.to_thread(_write_file, out, content)
        return out


# ---------------------------------------------------------------------------
# E2E test content builders
# ---------------------------------------------------------------------------

def _build_feature_e2e_test(
    *,
    name_slug: str,
    display_name: str,
    entity_plural: str,
    route_path: str,
    project_name: str,
    auth_required: bool,
) -> str:
    """Build a Playwright E2E test file for a single feature."""
    lines = [
        "import { test, expect } from '@playwright/test';",
        "",
        f"test.describe('{display_name}', () => {{",
        f"  test('page loads successfully', async ({{ page }}) => {{",
        f"    await page.goto('{route_path}');",
        f"    await expect(page.locator('h1')).toBeVisible();",
        f"  }});",
        "",
        f"  test('displays {entity_plural} list or empty state', async ({{ page }}) => {{",
        f"    await page.goto('{route_path}');",
        f"    await page.waitForLoadState('networkidle');",
        f"    const hasItems = await page.locator('[class*=\"card\"], [class*=\"Card\"]').count();",
        f"    const hasEmpty = await page.getByText('No {entity_plural} found').count();",
        f"    expect(hasItems + hasEmpty).toBeGreaterThan(0);",
        f"  }});",
        "",
        f"  test('desktop screenshot', async ({{ page }}) => {{",
        f"    await page.setViewportSize({{ width: 1440, height: 900 }});",
        f"    await page.goto('{route_path}');",
        f"    await page.waitForLoadState('networkidle');",
        f"    await page.screenshot({{ path: 'screenshots/{name_slug}-desktop.png', fullPage: true }});",
        f"  }});",
        "",
        f"  test('mobile screenshot', async ({{ page }}) => {{",
        f"    await page.setViewportSize({{ width: 375, height: 812 }});",
        f"    await page.goto('{route_path}');",
        f"    await page.waitForLoadState('networkidle');",
        f"    await page.screenshot({{ path: 'screenshots/{name_slug}-mobile.png', fullPage: true }});",
        f"  }});",
        "});",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _write_file(path: Path, content: str) -> None:
    """Synchronous helper: create parent dirs and write content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
