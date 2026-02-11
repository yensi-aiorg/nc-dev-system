"""Tests for Docker Compose file generation.

Covers:
- Production docker-compose.yml generation
- Development docker-compose.dev.yml generation
- Test docker-compose.test.yml generation
- Port correctness (23000+)
- Service existence verification
- Backend/frontend Dockerfile generation
- KeyCloak generation with auth
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.scaffolder.docker_gen import DockerGenerator
from src.scaffolder.templates import TemplateRenderer


# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_renderer() -> MagicMock:
    """A mock TemplateRenderer that tracks render_to_file calls."""
    renderer = MagicMock(spec=TemplateRenderer)

    async def mock_render_to_file(template_path: str, output_path, context):
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(f"# Rendered from {template_path}\n", encoding="utf-8")
        return out

    renderer.render_to_file = AsyncMock(side_effect=mock_render_to_file)
    return renderer


@pytest.fixture
def docker_gen(mock_renderer) -> DockerGenerator:
    """A DockerGenerator with a mocked renderer."""
    return DockerGenerator(mock_renderer)


@pytest.fixture
def basic_context() -> dict[str, Any]:
    """Basic template rendering context."""
    return {
        "project_name": "test-project",
        "project_name_slug": "test-project",
        "description": "A test project.",
        "auth_required": False,
        "ports": {
            "frontend": 23000,
            "backend": 23001,
            "mongodb": 23002,
            "redis": 23003,
        },
        "features": [],
        "db_collections": [],
        "api_contracts": [],
        "external_apis": [],
    }


@pytest.fixture
def auth_context(basic_context) -> dict[str, Any]:
    """Context with auth_required=True and keycloak ports."""
    return {
        **basic_context,
        "auth_required": True,
        "ports": {
            **basic_context["ports"],
            "keycloak": 23004,
            "keycloak_postgres": 23005,
        },
    }


# ---------------------------------------------------------------------------
# DockerGenerator.__init__
# ---------------------------------------------------------------------------


class TestDockerGeneratorInit:
    def test_creates_with_renderer(self, mock_renderer):
        gen = DockerGenerator(mock_renderer)
        assert gen.renderer is mock_renderer


# ---------------------------------------------------------------------------
# generate_all
# ---------------------------------------------------------------------------


class TestGenerateAll:
    async def test_generates_three_compose_files(self, docker_gen, tmp_path, basic_context):
        result = await docker_gen.generate_all(tmp_path, basic_context)
        assert "production" in result
        assert "development" in result
        assert "test" in result

    async def test_production_file_path(self, docker_gen, tmp_path, basic_context):
        result = await docker_gen.generate_all(tmp_path, basic_context)
        assert result["production"] == tmp_path / "docker-compose.yml"

    async def test_development_file_path(self, docker_gen, tmp_path, basic_context):
        result = await docker_gen.generate_all(tmp_path, basic_context)
        assert result["development"] == tmp_path / "docker-compose.dev.yml"

    async def test_test_file_path(self, docker_gen, tmp_path, basic_context):
        result = await docker_gen.generate_all(tmp_path, basic_context)
        assert result["test"] == tmp_path / "docker-compose.test.yml"

    async def test_files_are_created(self, docker_gen, tmp_path, basic_context):
        await docker_gen.generate_all(tmp_path, basic_context)
        assert (tmp_path / "docker-compose.yml").exists()
        assert (tmp_path / "docker-compose.dev.yml").exists()
        assert (tmp_path / "docker-compose.test.yml").exists()

    async def test_renderer_called_three_times(self, docker_gen, tmp_path, basic_context):
        await docker_gen.generate_all(tmp_path, basic_context)
        assert docker_gen.renderer.render_to_file.call_count == 3

    async def test_correct_templates_used(self, docker_gen, tmp_path, basic_context):
        await docker_gen.generate_all(tmp_path, basic_context)
        templates_used = [
            call.args[0]
            for call in docker_gen.renderer.render_to_file.call_args_list
        ]
        assert "docker-compose.yml.j2" in templates_used
        assert "docker-compose.dev.yml.j2" in templates_used
        assert "docker-compose.test.yml.j2" in templates_used

    async def test_context_passed_to_renderer(self, docker_gen, tmp_path, basic_context):
        await docker_gen.generate_all(tmp_path, basic_context)
        for call in docker_gen.renderer.render_to_file.call_args_list:
            passed_context = call.args[2]
            assert passed_context["project_name"] == "test-project"


# ---------------------------------------------------------------------------
# generate_backend_dockerfiles
# ---------------------------------------------------------------------------


class TestGenerateBackendDockerfiles:
    async def test_generates_two_dockerfiles(self, docker_gen, tmp_path, basic_context):
        backend_dir = tmp_path / "backend"
        backend_dir.mkdir()
        result = await docker_gen.generate_backend_dockerfiles(backend_dir, basic_context)
        assert len(result) == 2

    async def test_creates_dockerfile(self, docker_gen, tmp_path, basic_context):
        backend_dir = tmp_path / "backend"
        backend_dir.mkdir()
        result = await docker_gen.generate_backend_dockerfiles(backend_dir, basic_context)
        assert any("Dockerfile" == p.name for p in result)

    async def test_creates_dockerfile_dev(self, docker_gen, tmp_path, basic_context):
        backend_dir = tmp_path / "backend"
        backend_dir.mkdir()
        result = await docker_gen.generate_backend_dockerfiles(backend_dir, basic_context)
        assert any("Dockerfile.dev" == p.name for p in result)

    async def test_correct_templates(self, docker_gen, tmp_path, basic_context):
        backend_dir = tmp_path / "backend"
        backend_dir.mkdir()
        await docker_gen.generate_backend_dockerfiles(backend_dir, basic_context)
        templates = [
            call.args[0]
            for call in docker_gen.renderer.render_to_file.call_args_list
        ]
        assert "backend/Dockerfile.j2" in templates
        assert "backend/Dockerfile.dev.j2" in templates


# ---------------------------------------------------------------------------
# generate_frontend_dockerfiles
# ---------------------------------------------------------------------------


class TestGenerateFrontendDockerfiles:
    async def test_generates_three_files(self, docker_gen, tmp_path, basic_context):
        frontend_dir = tmp_path / "frontend"
        frontend_dir.mkdir()
        result = await docker_gen.generate_frontend_dockerfiles(frontend_dir, basic_context)
        assert len(result) == 3

    async def test_creates_dockerfile(self, docker_gen, tmp_path, basic_context):
        frontend_dir = tmp_path / "frontend"
        frontend_dir.mkdir()
        result = await docker_gen.generate_frontend_dockerfiles(frontend_dir, basic_context)
        names = [p.name for p in result]
        assert "Dockerfile" in names

    async def test_creates_dockerfile_dev(self, docker_gen, tmp_path, basic_context):
        frontend_dir = tmp_path / "frontend"
        frontend_dir.mkdir()
        result = await docker_gen.generate_frontend_dockerfiles(frontend_dir, basic_context)
        names = [p.name for p in result]
        assert "Dockerfile.dev" in names

    async def test_creates_nginx_conf(self, docker_gen, tmp_path, basic_context):
        frontend_dir = tmp_path / "frontend"
        frontend_dir.mkdir()
        result = await docker_gen.generate_frontend_dockerfiles(frontend_dir, basic_context)
        names = [p.name for p in result]
        assert "nginx.conf" in names

    async def test_correct_templates(self, docker_gen, tmp_path, basic_context):
        frontend_dir = tmp_path / "frontend"
        frontend_dir.mkdir()
        await docker_gen.generate_frontend_dockerfiles(frontend_dir, basic_context)
        templates = [
            call.args[0]
            for call in docker_gen.renderer.render_to_file.call_args_list
        ]
        assert "frontend/Dockerfile.j2" in templates
        assert "frontend/Dockerfile.dev.j2" in templates
        assert "frontend/nginx.conf.j2" in templates


# ---------------------------------------------------------------------------
# generate_keycloak
# ---------------------------------------------------------------------------


class TestGenerateKeycloak:
    async def test_generates_files_when_auth_required(
        self, docker_gen, tmp_path, auth_context
    ):
        kc_dir = tmp_path / "keycloak"
        kc_dir.mkdir()
        result = await docker_gen.generate_keycloak(kc_dir, auth_context)
        assert len(result) == 2

    async def test_creates_dockerfile(self, docker_gen, tmp_path, auth_context):
        kc_dir = tmp_path / "keycloak"
        kc_dir.mkdir()
        result = await docker_gen.generate_keycloak(kc_dir, auth_context)
        names = [p.name for p in result]
        assert "Dockerfile" in names

    async def test_creates_realm_export(self, docker_gen, tmp_path, auth_context):
        kc_dir = tmp_path / "keycloak"
        kc_dir.mkdir()
        result = await docker_gen.generate_keycloak(kc_dir, auth_context)
        names = [p.name for p in result]
        assert "realm-export.json" in names

    async def test_skips_when_auth_not_required(
        self, docker_gen, tmp_path, basic_context
    ):
        kc_dir = tmp_path / "keycloak"
        kc_dir.mkdir()
        result = await docker_gen.generate_keycloak(kc_dir, basic_context)
        assert result == []

    async def test_correct_templates_for_keycloak(
        self, docker_gen, tmp_path, auth_context
    ):
        kc_dir = tmp_path / "keycloak"
        kc_dir.mkdir()
        await docker_gen.generate_keycloak(kc_dir, auth_context)
        templates = [
            call.args[0]
            for call in docker_gen.renderer.render_to_file.call_args_list
        ]
        assert "keycloak/Dockerfile.j2" in templates
        assert "keycloak/realm-export.json.j2" in templates


# ---------------------------------------------------------------------------
# Port validation
# ---------------------------------------------------------------------------


class TestPortAllocation:
    def test_default_ports_start_at_23000(self):
        from src.scaffolder.generator import DEFAULT_PORTS

        for service, port in DEFAULT_PORTS.items():
            assert port >= 23000, f"{service} port {port} is below 23000"

    def test_no_standard_ports_used(self):
        from src.scaffolder.generator import DEFAULT_PORTS

        forbidden = {3000, 5000, 8000, 8080, 27017, 5432}
        for service, port in DEFAULT_PORTS.items():
            assert port not in forbidden, (
                f"{service} uses forbidden port {port}"
            )

    def test_all_ports_unique(self):
        from src.scaffolder.generator import DEFAULT_PORTS

        ports = list(DEFAULT_PORTS.values())
        assert len(ports) == len(set(ports)), "Duplicate ports found"

    def test_ports_are_sequential(self):
        from src.scaffolder.generator import DEFAULT_PORTS

        ports = sorted(DEFAULT_PORTS.values())
        for i in range(len(ports) - 1):
            assert ports[i + 1] - ports[i] == 1, (
                f"Gap between ports {ports[i]} and {ports[i+1]}"
            )


# ---------------------------------------------------------------------------
# _COMPOSE_FILES mapping
# ---------------------------------------------------------------------------


class TestComposeFilesMapping:
    def test_has_three_entries(self):
        assert len(DockerGenerator._COMPOSE_FILES) == 3

    def test_templates_end_with_j2(self):
        for template in DockerGenerator._COMPOSE_FILES.keys():
            assert template.endswith(".j2")

    def test_outputs_are_yml(self):
        for output in DockerGenerator._COMPOSE_FILES.values():
            assert output.endswith(".yml")
