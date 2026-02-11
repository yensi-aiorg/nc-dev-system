"""Docker Compose file generation for dev, prod, and test environments.

Uses the existing Jinja2 templates (``docker-compose.yml.j2``,
``docker-compose.dev.yml.j2``, ``docker-compose.test.yml.j2``) to produce
fully configured Docker Compose files for the generated project.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .templates import TemplateRenderer


class DockerGenerator:
    """Generates Docker Compose files for dev, prod, and test environments."""

    # Template name -> output file name
    _COMPOSE_FILES: dict[str, str] = {
        "docker-compose.yml.j2": "docker-compose.yml",
        "docker-compose.dev.yml.j2": "docker-compose.dev.yml",
        "docker-compose.test.yml.j2": "docker-compose.test.yml",
    }

    def __init__(self, renderer: TemplateRenderer) -> None:
        self.renderer = renderer

    async def generate_all(
        self,
        output_dir: Path,
        context: dict[str, Any],
    ) -> dict[str, Path]:
        """Generate all Docker Compose files to *output_dir*.

        Args:
            output_dir: Project root directory where the Compose files go.
            context: Template rendering context (project_name, ports, etc.).

        Returns:
            Mapping of descriptive name to written file path, e.g.
            ``{"production": Path(".../docker-compose.yml"), ...}``.
        """
        result: dict[str, Path] = {}

        label_map = {
            "docker-compose.yml.j2": "production",
            "docker-compose.dev.yml.j2": "development",
            "docker-compose.test.yml.j2": "test",
        }

        for template_name, output_name in self._COMPOSE_FILES.items():
            output_path = output_dir / output_name
            label = label_map[template_name]
            path = await self.renderer.render_to_file(
                template_name, output_path, context
            )
            result[label] = path

        return result

    async def generate_backend_dockerfiles(
        self,
        output_dir: Path,
        context: dict[str, Any],
    ) -> list[Path]:
        """Generate backend Dockerfile and Dockerfile.dev.

        Args:
            output_dir: The ``backend/`` directory inside the project root.
            context: Template rendering context.

        Returns:
            List of written Dockerfile paths.
        """
        written: list[Path] = []
        for template_name in ("backend/Dockerfile.j2", "backend/Dockerfile.dev.j2"):
            filename = template_name.split("/")[-1].replace(".j2", "")
            out = output_dir / filename
            path = await self.renderer.render_to_file(template_name, out, context)
            written.append(path)
        return written

    async def generate_frontend_dockerfiles(
        self,
        output_dir: Path,
        context: dict[str, Any],
    ) -> list[Path]:
        """Generate frontend Dockerfile, Dockerfile.dev, and nginx.conf.

        Args:
            output_dir: The ``frontend/`` directory inside the project root.
            context: Template rendering context.

        Returns:
            List of written file paths.
        """
        written: list[Path] = []
        for template_name in (
            "frontend/Dockerfile.j2",
            "frontend/Dockerfile.dev.j2",
            "frontend/nginx.conf.j2",
        ):
            filename = template_name.split("/")[-1].replace(".j2", "")
            out = output_dir / filename
            path = await self.renderer.render_to_file(template_name, out, context)
            written.append(path)
        return written

    async def generate_keycloak(
        self,
        output_dir: Path,
        context: dict[str, Any],
    ) -> list[Path]:
        """Generate KeyCloak Dockerfile and realm export (when auth is required).

        Args:
            output_dir: The ``keycloak/`` directory inside the project root.
            context: Template rendering context. Must include ``auth_required``.

        Returns:
            List of written file paths (empty if auth not required).
        """
        if not context.get("auth_required", False):
            return []

        written: list[Path] = []
        for template_name in (
            "keycloak/Dockerfile.j2",
            "keycloak/realm-export.json.j2",
        ):
            filename = template_name.split("/")[-1].replace(".j2", "")
            out = output_dir / filename
            path = await self.renderer.render_to_file(template_name, out, context)
            written.append(path)
        return written
