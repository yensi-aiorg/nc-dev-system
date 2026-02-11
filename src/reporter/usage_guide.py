"""Usage guide documentation generator.

Produces a ``usage-guide.md`` file with feature walkthroughs,
step-by-step instructions, inline screenshot references, and
API endpoint summaries for each feature.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from rich.console import Console

console = Console()


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

class FeatureGuide(BaseModel):
    """Structured description of a single feature for the usage guide."""

    name: str = Field(..., description="Feature name")
    description: str = Field(default="", description="What the feature does")
    steps: list[str] = Field(
        default_factory=list, description="Step-by-step usage instructions"
    )
    api_endpoints: list[str] = Field(
        default_factory=list,
        description="Related API endpoint paths (e.g. 'POST /api/v1/tasks')",
    )
    routes: list[str] = Field(
        default_factory=list,
        description="Frontend route paths for this feature",
    )
    screenshots: list[str] = Field(
        default_factory=list,
        description="Relative paths to related screenshots",
    )
    tips: list[str] = Field(
        default_factory=list,
        description="Helpful tips or notes for using the feature",
    )


# ---------------------------------------------------------------------------
# UsageGuideGenerator
# ---------------------------------------------------------------------------

class UsageGuideGenerator:
    """Generates ``usage-guide.md`` with feature walkthrough and screenshots.

    The generated document is designed to be read by end users and
    includes:

    - Project overview
    - Prerequisites and setup instructions
    - Feature-by-feature walkthrough with screenshots
    - API endpoint reference per feature
    - Tips and troubleshooting
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate(
        self,
        features: list[dict[str, Any]],
        screenshots: list[dict[str, Any]],
        project_name: str,
        output_path: str | Path,
    ) -> Path:
        """Generate the usage guide markdown.

        Parameters
        ----------
        features:
            List of feature dicts. Each should have at least ``name`` and
            ``description``; optional keys include ``steps``,
            ``api_endpoints``, ``routes``, ``tips``.
        screenshots:
            List of screenshot dicts with ``route``, ``viewport``, and
            ``path`` keys.
        project_name:
            Human-readable project name for headings.
        output_path:
            File path where the markdown will be written.

        Returns
        -------
        Path
            Absolute path to the written file.
        """
        output = Path(output_path).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)

        feature_guides = self._normalise_features(features)
        screenshot_map = self._build_screenshot_map(screenshots)

        content = self._render(project_name, feature_guides, screenshot_map)

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, output.write_text, content, "utf-8")

        console.print(f"[green]Usage guide written to {output}[/green]")
        return output

    # ------------------------------------------------------------------
    # Normalisation
    # ------------------------------------------------------------------

    def _normalise_features(self, raw: list[dict[str, Any]]) -> list[FeatureGuide]:
        """Convert raw feature dicts into validated FeatureGuide models."""
        guides: list[FeatureGuide] = []
        for item in raw:
            guide = FeatureGuide(
                name=item.get("name", "Unnamed Feature"),
                description=item.get("description", ""),
                steps=item.get("steps", []),
                api_endpoints=self._extract_endpoint_labels(item),
                routes=self._extract_route_paths(item),
                screenshots=item.get("screenshots", []),
                tips=item.get("tips", []),
            )
            # Auto-generate steps if none provided
            if not guide.steps:
                guide.steps = self._auto_steps(guide)
            guides.append(guide)
        return guides

    def _extract_endpoint_labels(self, feature: dict[str, Any]) -> list[str]:
        """Extract human-readable endpoint labels from a feature dict."""
        labels: list[str] = []
        endpoints = feature.get("api_endpoints", [])
        for ep in endpoints:
            if isinstance(ep, str):
                labels.append(ep)
            elif isinstance(ep, dict):
                method = ep.get("method", "GET")
                path = ep.get("path", "/")
                labels.append(f"{method} {path}")
        return labels

    def _extract_route_paths(self, feature: dict[str, Any]) -> list[str]:
        """Extract route path strings from a feature dict."""
        paths: list[str] = []
        routes = feature.get("ui_routes", feature.get("routes", []))
        for r in routes:
            if isinstance(r, str):
                paths.append(r)
            elif isinstance(r, dict):
                paths.append(r.get("path", "/"))
        return paths

    def _auto_steps(self, guide: FeatureGuide) -> list[str]:
        """Auto-generate basic usage steps from feature metadata."""
        steps: list[str] = []
        if guide.routes:
            steps.append(f"Navigate to **{guide.routes[0]}** in your browser.")
        if guide.description:
            steps.append(guide.description)
        if guide.api_endpoints:
            steps.append(
                f"This feature uses the following API endpoints: "
                f"{', '.join(f'`{ep}`' for ep in guide.api_endpoints)}."
            )
        if not steps:
            steps.append(f"Use the {guide.name} feature as described above.")
        return steps

    def _build_screenshot_map(
        self, screenshots: list[dict[str, Any]]
    ) -> dict[str, list[dict[str, Any]]]:
        """Build a mapping of route path to screenshot info dicts."""
        mapping: dict[str, list[dict[str, Any]]] = {}
        for ss in screenshots:
            route = ss.get("route", "/")
            mapping.setdefault(route, []).append(ss)
        return mapping

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render(
        self,
        project_name: str,
        features: list[FeatureGuide],
        screenshot_map: dict[str, list[dict[str, Any]]],
    ) -> str:
        """Render the complete usage guide markdown."""
        sections: list[str] = []

        # Title & overview
        sections.append(f"# {project_name} -- Usage Guide")
        sections.append("")
        sections.append(
            f"> Generated by NC Dev System on "
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
        )
        sections.append("")

        # Table of contents
        sections.append("## Table of Contents")
        sections.append("")
        sections.append("1. [Prerequisites](#prerequisites)")
        sections.append("2. [Getting Started](#getting-started)")
        for idx, f in enumerate(features, start=3):
            anchor = f.name.lower().replace(" ", "-").replace("/", "")
            sections.append(f"{idx}. [{f.name}](#{anchor})")
        sections.append(f"{len(features) + 3}. [Troubleshooting](#troubleshooting)")
        sections.append("")

        # Prerequisites
        sections.append("## Prerequisites")
        sections.append("")
        sections.append("Before using this application, ensure you have:")
        sections.append("")
        sections.append("- Docker and Docker Compose installed")
        sections.append("- A modern web browser (Chrome, Firefox, Safari, or Edge)")
        sections.append("- At least 2 GB of free disk space")
        sections.append("")

        # Getting Started
        sections.append("## Getting Started")
        sections.append("")
        sections.append("1. Clone the repository:")
        sections.append("   ```bash")
        sections.append(f"   git clone <repository-url>")
        sections.append(f"   cd {project_name.lower().replace(' ', '-')}")
        sections.append("   ```")
        sections.append("")
        sections.append("2. Start the development environment:")
        sections.append("   ```bash")
        sections.append("   make dev")
        sections.append("   ```")
        sections.append("")
        sections.append("3. Open the application in your browser:")
        sections.append("   ```")
        sections.append("   http://localhost:23000")
        sections.append("   ```")
        sections.append("")

        # Feature sections
        for feature in features:
            sections.append(f"## {feature.name}")
            sections.append("")

            if feature.description:
                sections.append(feature.description)
                sections.append("")

            # Screenshots (desktop first, then mobile)
            feature_screenshots = self._find_feature_screenshots(
                feature.routes, screenshot_map
            )
            if feature_screenshots:
                sections.append("### Screenshots")
                sections.append("")
                for ss in feature_screenshots:
                    viewport = ss.get("viewport", "desktop")
                    path = ss.get("path", "")
                    rel_path = Path(path).name if path else "screenshot.png"
                    sections.append(
                        f"**{viewport.title()} View:**"
                    )
                    sections.append("")
                    sections.append(
                        f"![{feature.name} - {viewport}](./screenshots/{rel_path})"
                    )
                    sections.append("")

            # Step-by-step instructions
            if feature.steps:
                sections.append("### How to Use")
                sections.append("")
                for step_idx, step in enumerate(feature.steps, start=1):
                    sections.append(f"{step_idx}. {step}")
                sections.append("")

            # API endpoints
            if feature.api_endpoints:
                sections.append("### API Endpoints")
                sections.append("")
                sections.append("| Method & Path | Description |")
                sections.append("|--------------|-------------|")
                for ep in feature.api_endpoints:
                    sections.append(f"| `{ep}` | See API documentation for details |")
                sections.append("")

            # Tips
            if feature.tips:
                sections.append("### Tips")
                sections.append("")
                for tip in feature.tips:
                    sections.append(f"- {tip}")
                sections.append("")

        # Troubleshooting
        sections.append("## Troubleshooting")
        sections.append("")
        sections.append("### Application won't start")
        sections.append("")
        sections.append(
            "Ensure Docker is running and ports 23000-23005 are not in use by "
            "other applications. Run `docker compose -f docker-compose.dev.yml down` "
            "and try again."
        )
        sections.append("")
        sections.append("### Pages are blank or show errors")
        sections.append("")
        sections.append(
            "Check the browser developer console (F12) for error messages. "
            "Ensure the backend API is running on port 23001. Try clearing "
            "your browser cache and refreshing."
        )
        sections.append("")
        sections.append("### API calls fail")
        sections.append("")
        sections.append(
            "Verify the backend is healthy by visiting "
            "`http://localhost:23001/health`. Check that MongoDB is running "
            "on port 23002. Review the backend logs with "
            "`docker compose -f docker-compose.dev.yml logs backend`."
        )
        sections.append("")
        sections.append("---")
        sections.append("")
        sections.append(
            f"*This guide was auto-generated by the NC Dev System. "
            f"For API details, see `api-documentation.md`.*"
        )
        sections.append("")

        return "\n".join(sections)

    def _find_feature_screenshots(
        self,
        routes: list[str],
        screenshot_map: dict[str, list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        """Find screenshots that match a feature's routes."""
        results: list[dict[str, Any]] = []
        for route in routes:
            if route in screenshot_map:
                # Sort: desktop before mobile
                sorted_ss = sorted(
                    screenshot_map[route],
                    key=lambda s: 0 if s.get("viewport") == "desktop" else 1,
                )
                results.extend(sorted_ss)
        return results
