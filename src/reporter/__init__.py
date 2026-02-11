"""Delivery Engine for the NC Dev System.

Orchestrates the full delivery pipeline: screenshots, usage guide,
API documentation, build report, and mock documentation. Produces
a :class:`DeliveryPackage` describing every artefact generated.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.reporter.api_docs import APIDocGenerator
from src.reporter.build_report import BuildReportGenerator
from src.reporter.mock_docs import MockDocGenerator
from src.reporter.screenshots import ScreenshotInfo, ScreenshotManager
from src.reporter.usage_guide import UsageGuideGenerator

__all__ = [
    # Core engine
    "DeliveryEngine",
    "DeliveryPackage",
    "DeliveryArtefact",
    # Sub-modules
    "ScreenshotManager",
    "ScreenshotInfo",
    "UsageGuideGenerator",
    "APIDocGenerator",
    "BuildReportGenerator",
    "MockDocGenerator",
]

console = Console()


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

class DeliveryArtefact(BaseModel):
    """Metadata for a single delivery artefact (file)."""

    name: str = Field(..., description="Artefact name, e.g. 'usage-guide.md'")
    path: str = Field(..., description="Absolute file path")
    category: str = Field(
        ...,
        description=(
            "Artefact category: 'documentation', 'screenshot', 'report'"
        ),
    )
    description: str = Field(default="", description="What this artefact contains")


class DeliveryPackage(BaseModel):
    """Complete delivery package metadata."""

    project_name: str = Field(..., description="Name of the delivered project")
    project_path: str = Field(..., description="Root path of the project")
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )
    artefacts: list[DeliveryArtefact] = Field(default_factory=list)
    screenshots: list[ScreenshotInfo] = Field(default_factory=list)
    docs_dir: str = Field(default="", description="Path to docs/ directory")
    success: bool = Field(default=True)
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# DeliveryEngine
# ---------------------------------------------------------------------------

class DeliveryEngine:
    """Orchestrates the full delivery pipeline for a generated project.

    Generates:
    1. Screenshots (desktop + mobile for every route)
    2. Usage guide (``docs/usage-guide.md``)
    3. API documentation (``docs/api-documentation.md``)
    4. Build report (``docs/build-report.md``)
    5. Mock documentation (``docs/mock-documentation.md``)

    Usage::

        engine = DeliveryEngine()
        package = await engine.generate_delivery(
            project_path="/path/to/project",
            features=[...],
            architecture={...},
            test_results={...},
            build_metadata={...},
        )
        engine.print_summary(package)
    """

    def __init__(
        self,
        screenshot_manager: ScreenshotManager | None = None,
        usage_guide_generator: UsageGuideGenerator | None = None,
        api_doc_generator: APIDocGenerator | None = None,
        build_report_generator: BuildReportGenerator | None = None,
        mock_doc_generator: MockDocGenerator | None = None,
    ) -> None:
        self._screenshots = screenshot_manager or ScreenshotManager()
        self._usage_guide = usage_guide_generator or UsageGuideGenerator()
        self._api_docs = api_doc_generator or APIDocGenerator()
        self._build_report = build_report_generator or BuildReportGenerator()
        self._mock_docs = mock_doc_generator or MockDocGenerator()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_delivery(
        self,
        project_path: str,
        features: list[dict[str, Any]],
        architecture: dict[str, Any],
        test_results: dict[str, Any],
        build_metadata: dict[str, Any],
        project_url: str | None = None,
        mock_handlers: list[dict[str, Any]] | None = None,
    ) -> DeliveryPackage:
        """Generate the complete delivery package.

        Parameters
        ----------
        project_path:
            Root directory of the generated project.
        features:
            List of feature dicts (name, description, status, etc.).
        architecture:
            Architecture dict (project_name, api_contracts, etc.).
        test_results:
            Test results dict (total, passed, failed, coverage, etc.).
        build_metadata:
            Build metadata dict (project_name, duration, git info, etc.).
        project_url:
            Base URL of the running app for screenshot capture.
            If *None*, screenshot capture is skipped.
        mock_handlers:
            List of mock handler dicts for mock documentation.

        Returns
        -------
        DeliveryPackage
        """
        root = Path(project_path).resolve()
        project_name = architecture.get(
            "project_name", build_metadata.get("project_name", "Project")
        )
        docs_dir = root / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)

        console.print(
            Panel(
                f"[bold]Delivery Engine[/bold]\n"
                f"Project: {project_name}\n"
                f"Path: {root}\n"
                f"Docs: {docs_dir}",
                title="NC Dev System",
                border_style="green",
            )
        )

        artefacts: list[DeliveryArtefact] = []
        screenshots: list[ScreenshotInfo] = []
        errors: list[str] = []

        # Step 1: Capture screenshots (if URL provided)
        if project_url:
            console.print("  [dim]Capturing screenshots...[/dim]")
            try:
                routes = self._extract_routes(features, architecture)
                screenshots = await self._screenshots.capture_all(
                    base_url=project_url,
                    routes=routes,
                    output_dir=docs_dir,
                )
                if screenshots:
                    index_path = await self._screenshots.generate_index(
                        screenshots, docs_dir, project_name
                    )
                    artefacts.append(
                        DeliveryArtefact(
                            name="screenshots/index.md",
                            path=str(index_path),
                            category="screenshot",
                            description="Screenshot index with all captured views",
                        )
                    )
                    for ss in screenshots:
                        artefacts.append(
                            DeliveryArtefact(
                                name=Path(ss.path).name,
                                path=ss.path,
                                category="screenshot",
                                description=f"Screenshot of {ss.route} ({ss.viewport})",
                            )
                        )
                console.print(f"  [green]Captured {len(screenshots)} screenshots[/green]")
            except Exception as exc:
                errors.append(f"Screenshot capture failed: {exc}")
                console.print(f"  [red]Screenshot capture failed: {exc}[/red]")
        else:
            console.print("  [yellow]Skipping screenshots (no project URL)[/yellow]")

        # Steps 2-5: Generate documentation (all independent, run concurrently)
        screenshot_dicts = [ss.model_dump() for ss in screenshots]

        doc_tasks = {
            "usage_guide": self._generate_usage_guide(
                features, screenshot_dicts, project_name, docs_dir
            ),
            "api_docs": self._generate_api_docs(architecture, docs_dir),
            "build_report": self._generate_build_report(
                features, test_results, build_metadata, docs_dir
            ),
            "mock_docs": self._generate_mock_docs(
                architecture, mock_handlers or [], docs_dir
            ),
        }

        results = await asyncio.gather(
            *doc_tasks.values(), return_exceptions=True
        )

        task_names = list(doc_tasks.keys())
        doc_descriptions = {
            "usage_guide": "Usage guide with feature walkthroughs and screenshots",
            "api_docs": "API documentation with endpoint details and examples",
            "build_report": "Build report with features, test results, and stack info",
            "mock_docs": "Mock documentation with handler details and switching guide",
        }
        doc_filenames = {
            "usage_guide": "usage-guide.md",
            "api_docs": "api-documentation.md",
            "build_report": "build-report.md",
            "mock_docs": "mock-documentation.md",
        }

        for task_name, result in zip(task_names, results):
            if isinstance(result, Exception):
                errors.append(f"{task_name} generation failed: {result}")
                console.print(f"  [red]{task_name} generation failed: {result}[/red]")
            elif isinstance(result, Path):
                artefacts.append(
                    DeliveryArtefact(
                        name=doc_filenames[task_name],
                        path=str(result),
                        category="documentation",
                        description=doc_descriptions[task_name],
                    )
                )

        success = len(errors) == 0

        package = DeliveryPackage(
            project_name=project_name,
            project_path=str(root),
            artefacts=artefacts,
            screenshots=screenshots,
            docs_dir=str(docs_dir),
            success=success,
            errors=errors,
        )

        self.print_summary(package)
        return package

    # ------------------------------------------------------------------
    # Document generators (with error isolation)
    # ------------------------------------------------------------------

    async def _generate_usage_guide(
        self,
        features: list[dict[str, Any]],
        screenshots: list[dict[str, Any]],
        project_name: str,
        docs_dir: Path,
    ) -> Path:
        """Generate the usage guide."""
        console.print("  [dim]Generating usage guide...[/dim]")
        path = await self._usage_guide.generate(
            features=features,
            screenshots=screenshots,
            project_name=project_name,
            output_path=docs_dir / "usage-guide.md",
        )
        console.print("  [green]Usage guide generated[/green]")
        return path

    async def _generate_api_docs(
        self,
        architecture: dict[str, Any],
        docs_dir: Path,
    ) -> Path:
        """Generate API documentation."""
        console.print("  [dim]Generating API documentation...[/dim]")
        path = await self._api_docs.generate(
            architecture=architecture,
            output_path=docs_dir / "api-documentation.md",
        )
        console.print("  [green]API documentation generated[/green]")
        return path

    async def _generate_build_report(
        self,
        features: list[dict[str, Any]],
        test_results: dict[str, Any],
        build_metadata: dict[str, Any],
        docs_dir: Path,
    ) -> Path:
        """Generate the build report."""
        console.print("  [dim]Generating build report...[/dim]")
        path = await self._build_report.generate(
            features=features,
            test_results=test_results,
            build_metadata=build_metadata,
            output_path=docs_dir / "build-report.md",
        )
        console.print("  [green]Build report generated[/green]")
        return path

    async def _generate_mock_docs(
        self,
        architecture: dict[str, Any],
        mock_handlers: list[dict[str, Any]],
        docs_dir: Path,
    ) -> Path:
        """Generate mock documentation."""
        console.print("  [dim]Generating mock documentation...[/dim]")
        path = await self._mock_docs.generate(
            architecture=architecture,
            mock_handlers=mock_handlers,
            output_path=docs_dir / "mock-documentation.md",
        )
        console.print("  [green]Mock documentation generated[/green]")
        return path

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_routes(
        self,
        features: list[dict[str, Any]],
        architecture: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Extract route dicts from features and architecture for screenshots."""
        routes: list[dict[str, Any]] = []
        seen_paths: set[str] = set()

        # Always include the home route
        routes.append({"path": "/", "name": "Home"})
        seen_paths.add("/")

        # Extract from features
        for feat in features:
            for route in feat.get("ui_routes", feat.get("routes", [])):
                if isinstance(route, dict):
                    path = route.get("path", "/")
                    name = route.get("name", path)
                elif isinstance(route, str):
                    path = route
                    name = route
                else:
                    continue
                if path not in seen_paths:
                    routes.append({"path": path, "name": name})
                    seen_paths.add(path)

        # Extract from architecture features
        for feat in architecture.get("features", []):
            for route in feat.get("ui_routes", []):
                if isinstance(route, dict):
                    path = route.get("path", "/")
                    name = route.get("name", path)
                elif isinstance(route, str):
                    path = route
                    name = route
                else:
                    continue
                if path not in seen_paths:
                    routes.append({"path": path, "name": name})
                    seen_paths.add(path)

        return routes

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def print_summary(self, package: DeliveryPackage) -> None:
        """Pretty-print a delivery package summary."""
        console.print("\n")
        status = "[green bold]SUCCESS[/green bold]" if package.success else "[red bold]PARTIAL[/red bold]"
        console.print(
            Panel(
                f"[bold]Delivery Package[/bold]\n"
                f"Project: {package.project_name}\n"
                f"Status: {status}\n"
                f"Artefacts: {len(package.artefacts)}\n"
                f"Screenshots: {len(package.screenshots)}\n"
                f"Docs: {package.docs_dir}",
                title="NC Dev System",
                border_style="green" if package.success else "yellow",
            )
        )

        if package.artefacts:
            table = Table(title="Delivery Artefacts", show_lines=True)
            table.add_column("Name", width=30)
            table.add_column("Category", width=16)
            table.add_column("Description", width=50)

            for art in package.artefacts:
                cat_style = {
                    "documentation": "blue",
                    "screenshot": "magenta",
                    "report": "cyan",
                }.get(art.category, "white")
                table.add_row(
                    art.name,
                    f"[{cat_style}]{art.category}[/{cat_style}]",
                    art.description,
                )
            console.print(table)

        if package.errors:
            console.print("\n[red bold]Errors:[/red bold]")
            for err in package.errors:
                console.print(f"  [red]- {err}[/red]")

        console.print("")
