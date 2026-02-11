"""Tests for MSW handler and pytest fixture generation.

Covers:
- MSW handler generation from API contracts
- Pytest fixture generation for backend tests
- External API mock fixture generation
- Combined generation (generate_all)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.scaffolder.mock_gen import (
    MockGenerator,
    _build_external_api_fixtures,
    _to_fixture_name,
)
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
    """A mock TemplateRenderer that writes marker files."""
    renderer = MagicMock(spec=TemplateRenderer)

    async def mock_render_to_file(template_path: str, output_path, context):
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(f"// Rendered from {template_path}\n", encoding="utf-8")
        return out

    renderer.render_to_file = AsyncMock(side_effect=mock_render_to_file)
    return renderer


@pytest.fixture
def mock_gen(mock_renderer) -> MockGenerator:
    """A MockGenerator with a mocked renderer."""
    return MockGenerator(mock_renderer)


@pytest.fixture
def basic_context() -> dict[str, Any]:
    """Basic template rendering context."""
    return {
        "project_name": "test-project",
        "project_name_slug": "test-project",
        "auth_required": False,
        "ports": {"frontend": 23000, "backend": 23001},
        "features": [],
        "db_collections": [],
        "api_contracts": [],
        "external_apis": [],
    }


@pytest.fixture
def sample_api_contracts() -> list[dict[str, Any]]:
    """Sample API contracts for mock generation."""
    return [
        {
            "base_path": "/api/v1/tasks",
            "name": "tasks",
            "endpoints": [
                {"method": "GET", "path": "/api/v1/tasks", "description": "List tasks"},
                {"method": "POST", "path": "/api/v1/tasks", "description": "Create task"},
                {"method": "GET", "path": "/api/v1/tasks/:id", "description": "Get task"},
                {"method": "PUT", "path": "/api/v1/tasks/:id", "description": "Update task"},
                {"method": "DELETE", "path": "/api/v1/tasks/:id", "description": "Delete task"},
            ],
        },
        {
            "base_path": "/api/v1/categories",
            "name": "categories",
            "endpoints": [
                {"method": "GET", "path": "/api/v1/categories", "description": "List categories"},
                {"method": "POST", "path": "/api/v1/categories", "description": "Create category"},
            ],
        },
    ]


@pytest.fixture
def sample_external_apis() -> list[dict[str, Any]]:
    """Sample external API definitions for mock generation."""
    return [
        {
            "name": "Stripe",
            "base_url": "https://api.stripe.com/v1",
            "auth_type": "bearer",
            "endpoints": [
                {"method": "POST", "path": "/charges", "description": "Create charge"},
                {"method": "GET", "path": "/charges/{id}", "description": "Get charge"},
            ],
        },
        {
            "name": "SendGrid",
            "base_url": "https://api.sendgrid.com/v3",
            "auth_type": "bearer",
            "endpoints": [
                {"method": "POST", "path": "/mail/send", "description": "Send email"},
            ],
        },
    ]


# ---------------------------------------------------------------------------
# _to_fixture_name
# ---------------------------------------------------------------------------


class TestToFixtureName:
    def test_simple_name(self):
        assert _to_fixture_name("Stripe") == "stripe"

    def test_multi_word(self):
        assert _to_fixture_name("Google Maps") == "google_maps"

    def test_special_chars(self):
        assert _to_fixture_name("AWS S3") == "aws_s3"

    def test_leading_trailing(self):
        assert _to_fixture_name("  Stripe  ") == "stripe"


# ---------------------------------------------------------------------------
# _build_external_api_fixtures
# ---------------------------------------------------------------------------


class TestBuildExternalApiFixtures:
    def test_generates_python_code(self, sample_external_apis):
        content = _build_external_api_fixtures(sample_external_apis)
        assert "import pytest" in content
        assert "import httpx" in content

    def test_creates_fixture_per_api(self, sample_external_apis):
        content = _build_external_api_fixtures(sample_external_apis)
        assert "mock_stripe" in content
        assert "mock_sendgrid" in content
        assert "@pytest.fixture" in content

    def test_includes_docstrings(self, sample_external_apis):
        content = _build_external_api_fixtures(sample_external_apis)
        assert "Stripe API" in content
        assert "SendGrid API" in content

    def test_includes_endpoint_responses(self, sample_external_apis):
        content = _build_external_api_fixtures(sample_external_apis)
        assert '"/charges"' in content
        assert '"/mail/send"' in content

    def test_includes_mock_methods(self, sample_external_apis):
        content = _build_external_api_fixtures(sample_external_apis)
        assert "mock_client.get" in content
        assert "mock_client.post" in content
        assert "mock_client.put" in content
        assert "mock_client.delete" in content

    def test_handles_empty_endpoints(self):
        apis = [{"name": "Custom", "base_url": "https://api.custom.com", "endpoints": []}]
        content = _build_external_api_fixtures(apis)
        assert "mock_custom" in content
        assert '("GET", "/")' in content  # fallback endpoint

    def test_handles_empty_list(self):
        content = _build_external_api_fixtures([])
        assert "import pytest" in content  # header still present
        assert "@pytest.fixture" not in content


# ---------------------------------------------------------------------------
# MockGenerator.generate_msw_handlers
# ---------------------------------------------------------------------------


class TestGenerateMswHandlers:
    async def test_generates_three_files(
        self, mock_gen, tmp_path, sample_api_contracts, basic_context
    ):
        result = await mock_gen.generate_msw_handlers(
            tmp_path, sample_api_contracts, basic_context
        )
        assert len(result) == 3

    async def test_creates_handlers_ts(
        self, mock_gen, tmp_path, sample_api_contracts, basic_context
    ):
        await mock_gen.generate_msw_handlers(
            tmp_path, sample_api_contracts, basic_context
        )
        handlers = tmp_path / "frontend" / "src" / "mocks" / "handlers.ts"
        assert handlers.exists()

    async def test_creates_browser_ts(
        self, mock_gen, tmp_path, sample_api_contracts, basic_context
    ):
        await mock_gen.generate_msw_handlers(
            tmp_path, sample_api_contracts, basic_context
        )
        browser = tmp_path / "frontend" / "src" / "mocks" / "browser.ts"
        assert browser.exists()

    async def test_creates_server_ts(
        self, mock_gen, tmp_path, sample_api_contracts, basic_context
    ):
        await mock_gen.generate_msw_handlers(
            tmp_path, sample_api_contracts, basic_context
        )
        server = tmp_path / "frontend" / "src" / "mocks" / "server.ts"
        assert server.exists()

    async def test_correct_templates_used(
        self, mock_gen, tmp_path, sample_api_contracts, basic_context
    ):
        await mock_gen.generate_msw_handlers(
            tmp_path, sample_api_contracts, basic_context
        )
        templates = [
            call.args[0]
            for call in mock_gen.renderer.render_to_file.call_args_list
        ]
        assert "frontend/src/mocks/handlers.ts.j2" in templates
        assert "frontend/src/mocks/browser.ts.j2" in templates
        assert "frontend/src/mocks/server.ts.j2" in templates

    async def test_context_includes_api_contracts(
        self, mock_gen, tmp_path, sample_api_contracts, basic_context
    ):
        await mock_gen.generate_msw_handlers(
            tmp_path, sample_api_contracts, basic_context
        )
        # Check that the context passed to the renderer includes api_contracts
        for call in mock_gen.renderer.render_to_file.call_args_list:
            ctx = call.args[2]
            assert "api_contracts" in ctx
            assert len(ctx["api_contracts"]) == 2

    async def test_empty_contracts(self, mock_gen, tmp_path, basic_context):
        result = await mock_gen.generate_msw_handlers(tmp_path, [], basic_context)
        assert len(result) == 3  # Still generates the 3 files


# ---------------------------------------------------------------------------
# MockGenerator.generate_pytest_fixtures
# ---------------------------------------------------------------------------


class TestGeneratePytestFixtures:
    async def test_generates_conftest(
        self, mock_gen, tmp_path, sample_api_contracts, basic_context
    ):
        result = await mock_gen.generate_pytest_fixtures(
            tmp_path, sample_api_contracts, [], basic_context
        )
        assert len(result) >= 1
        conftest = tmp_path / "backend" / "tests" / "conftest.py"
        assert conftest.exists()

    async def test_generates_external_mocks_file(
        self, mock_gen, tmp_path, sample_api_contracts, sample_external_apis, basic_context
    ):
        result = await mock_gen.generate_pytest_fixtures(
            tmp_path, sample_api_contracts, sample_external_apis, basic_context
        )
        ext_mocks = tmp_path / "backend" / "tests" / "external_mocks.py"
        assert ext_mocks.exists()
        assert len(result) == 2  # conftest + external_mocks

    async def test_no_external_mocks_when_empty(
        self, mock_gen, tmp_path, sample_api_contracts, basic_context
    ):
        result = await mock_gen.generate_pytest_fixtures(
            tmp_path, sample_api_contracts, [], basic_context
        )
        ext_mocks = tmp_path / "backend" / "tests" / "external_mocks.py"
        assert not ext_mocks.exists()
        assert len(result) == 1  # only conftest

    async def test_external_mocks_content(
        self, mock_gen, tmp_path, sample_api_contracts, sample_external_apis, basic_context
    ):
        await mock_gen.generate_pytest_fixtures(
            tmp_path, sample_api_contracts, sample_external_apis, basic_context
        )
        ext_mocks = tmp_path / "backend" / "tests" / "external_mocks.py"
        content = ext_mocks.read_text(encoding="utf-8")
        assert "mock_stripe" in content
        assert "mock_sendgrid" in content


# ---------------------------------------------------------------------------
# MockGenerator.generate_all
# ---------------------------------------------------------------------------


class TestGenerateAll:
    async def test_generates_msw_and_pytest(
        self, mock_gen, tmp_path, sample_api_contracts, sample_external_apis, basic_context
    ):
        result = await mock_gen.generate_all(
            tmp_path, sample_api_contracts, sample_external_apis, basic_context
        )
        # 3 MSW files + 2 pytest files (conftest + external_mocks) = 5
        assert len(result) == 5

    async def test_all_files_exist(
        self, mock_gen, tmp_path, sample_api_contracts, sample_external_apis, basic_context
    ):
        await mock_gen.generate_all(
            tmp_path, sample_api_contracts, sample_external_apis, basic_context
        )
        # MSW files
        assert (tmp_path / "frontend" / "src" / "mocks" / "handlers.ts").exists()
        assert (tmp_path / "frontend" / "src" / "mocks" / "browser.ts").exists()
        assert (tmp_path / "frontend" / "src" / "mocks" / "server.ts").exists()
        # Pytest files
        assert (tmp_path / "backend" / "tests" / "conftest.py").exists()
        assert (tmp_path / "backend" / "tests" / "external_mocks.py").exists()

    async def test_without_external_apis(
        self, mock_gen, tmp_path, sample_api_contracts, basic_context
    ):
        result = await mock_gen.generate_all(
            tmp_path, sample_api_contracts, [], basic_context
        )
        # 3 MSW + 1 conftest = 4
        assert len(result) == 4

    async def test_empty_everything(self, mock_gen, tmp_path, basic_context):
        result = await mock_gen.generate_all(tmp_path, [], [], basic_context)
        # 3 MSW + 1 conftest = 4
        assert len(result) == 4
