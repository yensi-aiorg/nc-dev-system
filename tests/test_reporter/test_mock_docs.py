"""Unit tests for the MockDocGenerator module.

Tests mock documentation generation from architecture dicts and mock handler
lists, including endpoint behaviour documentation, success/error/empty
response examples, and switching instructions.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.reporter.mock_docs import MockDocGenerator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def generator() -> MockDocGenerator:
    """Fresh MockDocGenerator instance."""
    return MockDocGenerator()


@pytest.fixture
def sample_architecture() -> dict:
    """A minimal architecture dict."""
    return {
        "project_name": "Task App",
        "api_contracts": [
            {
                "base_path": "/api/v1/tasks",
                "endpoints": [
                    {"method": "GET", "path": "/api/v1/tasks", "description": "List tasks"},
                    {"method": "POST", "path": "/api/v1/tasks", "description": "Create task"},
                ],
            }
        ],
        "external_apis": [],
        "port_allocation": {"backend": 23001},
    }


@pytest.fixture
def sample_frontend_handlers() -> list[dict]:
    """Sample MSW frontend mock handlers."""
    return [
        {
            "name": "list-tasks",
            "type": "frontend",
            "method": "GET",
            "path": "/api/v1/tasks",
            "description": "List all tasks",
            "success_response": {"items": [{"id": "1", "title": "Task 1"}], "total": 1},
            "error_response": {"detail": "Server error"},
            "error_status": 500,
            "empty_response": {"items": [], "total": 0},
        },
        {
            "name": "create-task",
            "type": "frontend",
            "method": "POST",
            "path": "/api/v1/tasks",
            "description": "Create a new task",
            "success_response": {"id": "2", "title": "New Task"},
            "error_response": {"detail": "Validation failed"},
            "error_status": 422,
            "empty_response": None,
        },
    ]


@pytest.fixture
def sample_backend_handlers() -> list[dict]:
    """Sample pytest backend mock handlers."""
    return [
        {
            "name": "get-task-by-id",
            "type": "backend",
            "method": "GET",
            "path": "/api/v1/tasks/:id",
            "description": "Get task by ID",
            "success_response": {"id": "abc123", "title": "Test Task"},
            "error_response": {"detail": "Not found"},
            "error_status": 404,
            "empty_response": None,
        },
    ]


@pytest.fixture
def architecture_with_external_apis() -> dict:
    """Architecture with external API definitions."""
    return {
        "project_name": "Integration App",
        "api_contracts": [],
        "external_apis": [
            {
                "name": "Stripe",
                "base_url": "https://api.stripe.com",
                "auth_type": "Bearer token",
            },
            {
                "name": "SendGrid",
                "base_url": "https://api.sendgrid.com",
                "auth_type": "API key",
            },
        ],
        "port_allocation": {"backend": 23001},
    }


# ---------------------------------------------------------------------------
# Basic Rendering Tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestBasicRendering:
    """Test basic markdown rendering from architecture and handlers."""

    def test_render_includes_project_name(self, generator, sample_architecture):
        content = generator._render(sample_architecture, [])
        assert "# Task App -- Mock Documentation" in content

    def test_render_includes_toc(self, generator, sample_architecture):
        content = generator._render(sample_architecture, [])
        assert "## Table of Contents" in content
        assert "[Overview](#overview)" in content
        assert "[Mocking Strategy](#mocking-strategy)" in content

    def test_render_includes_overview(self, generator, sample_architecture):
        content = generator._render(sample_architecture, [])
        assert "## Overview" in content
        assert "comprehensive mocking strategy" in content

    def test_render_includes_strategy(self, generator, sample_architecture):
        content = generator._render(sample_architecture, [])
        assert "## Mocking Strategy" in content
        assert "MSW (Mock Service Worker)" in content
        assert "pytest fixtures" in content

    def test_render_includes_switching_instructions(self, generator, sample_architecture):
        content = generator._render(sample_architecture, [])
        assert "## Switching Between Mock and Real APIs" in content
        assert "MOCK_APIS" in content
        assert "VITE_MOCK_APIS" in content

    def test_render_includes_docker_compose_table(self, generator, sample_architecture):
        content = generator._render(sample_architecture, [])
        assert "docker-compose.dev.yml" in content
        assert "docker-compose.test.yml" in content
        assert "docker-compose.yml" in content

    def test_render_includes_footer(self, generator, sample_architecture):
        content = generator._render(sample_architecture, [])
        assert "auto-generated by the NC Dev System" in content
        assert "api-documentation.md" in content


# ---------------------------------------------------------------------------
# Frontend Handler Documentation Tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFrontendHandlerDocs:
    """Test frontend MSW handler documentation rendering."""

    def test_render_frontend_handlers_section(self, generator, sample_architecture, sample_frontend_handlers):
        content = generator._render(sample_architecture, sample_frontend_handlers)
        assert "## Frontend Mocks (MSW)" in content
        assert "2 MSW handlers" in content

    def test_render_frontend_summary_table(self, generator, sample_architecture, sample_frontend_handlers):
        content = generator._render(sample_architecture, sample_frontend_handlers)
        assert "| `GET` | `/api/v1/tasks` | List all tasks |" in content
        assert "| `POST` | `/api/v1/tasks` | Create a new task |" in content

    def test_render_frontend_handler_detail(self, generator, sample_architecture, sample_frontend_handlers):
        content = generator._render(sample_architecture, sample_frontend_handlers)
        assert "### `GET /api/v1/tasks`" in content
        assert "### `POST /api/v1/tasks`" in content

    def test_render_frontend_success_response(self, generator, sample_architecture, sample_frontend_handlers):
        content = generator._render(sample_architecture, sample_frontend_handlers)
        assert "**Success Response** (200):" in content
        assert '"title": "Task 1"' in content

    def test_render_frontend_error_response(self, generator, sample_architecture, sample_frontend_handlers):
        content = generator._render(sample_architecture, sample_frontend_handlers)
        assert "**Error Response** (500):" in content
        assert '"detail": "Server error"' in content

    def test_render_frontend_empty_response(self, generator, sample_architecture, sample_frontend_handlers):
        content = generator._render(sample_architecture, sample_frontend_handlers)
        assert "**Empty Response** (200):" in content
        assert '"items": []' in content

    def test_render_msw_handler_code(self, generator, sample_architecture, sample_frontend_handlers):
        content = generator._render(sample_architecture, sample_frontend_handlers)
        assert "**MSW Handler**" in content
        assert "http.get('/api/v1" in content
        assert "HttpResponse.json" in content

    def test_no_frontend_handlers_message(self, generator, sample_architecture):
        content = generator._render(sample_architecture, [])
        assert "No frontend mock handlers registered" in content


# ---------------------------------------------------------------------------
# Backend Handler Documentation Tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestBackendHandlerDocs:
    """Test backend pytest fixture documentation rendering."""

    def test_render_backend_handlers_section(self, generator, sample_architecture, sample_backend_handlers):
        content = generator._render(sample_architecture, sample_backend_handlers)
        assert "## Backend Mocks (pytest)" in content
        assert "1 pytest fixtures" in content

    def test_render_backend_handler_detail(self, generator, sample_architecture, sample_backend_handlers):
        content = generator._render(sample_architecture, sample_backend_handlers)
        assert "### `GET /api/v1/tasks/:id`" in content

    def test_render_backend_success_response(self, generator, sample_architecture, sample_backend_handlers):
        content = generator._render(sample_architecture, sample_backend_handlers)
        assert '"title": "Test Task"' in content

    def test_render_backend_error_response(self, generator, sample_architecture, sample_backend_handlers):
        content = generator._render(sample_architecture, sample_backend_handlers)
        assert "**Error Response** (404):" in content
        assert '"detail": "Not found"' in content

    def test_render_pytest_fixture_code(self, generator, sample_architecture, sample_backend_handlers):
        content = generator._render(sample_architecture, sample_backend_handlers)
        assert "**pytest Fixture**" in content
        assert "@pytest.fixture" in content
        assert "def mock_" in content

    def test_no_backend_handlers_message(self, generator, sample_architecture):
        content = generator._render(sample_architecture, [])
        assert "No backend mock fixtures registered" in content


# ---------------------------------------------------------------------------
# External API Mocks Tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestExternalAPIMocks:
    """Test external API mocks documentation."""

    def test_external_apis_section(self, generator, architecture_with_external_apis):
        content = generator._render(architecture_with_external_apis, [])
        assert "## External API Mocks" in content
        assert "### Stripe" in content
        assert "### SendGrid" in content

    def test_external_api_base_url(self, generator, architecture_with_external_apis):
        content = generator._render(architecture_with_external_apis, [])
        assert "https://api.stripe.com" in content
        assert "https://api.sendgrid.com" in content

    def test_external_api_with_handlers(self, generator, architecture_with_external_apis):
        handlers = [
            {
                "name": "stripe-charge",
                "type": "backend",
                "method": "POST",
                "path": "/v1/charges",
                "description": "Create a charge",
                "external_api": "Stripe",
                "success_response": {"id": "ch_123", "status": "succeeded"},
                "error_response": {"error": {"message": "Card declined"}},
                "error_status": 402,
                "empty_response": None,
            },
        ]
        content = generator._render(architecture_with_external_apis, handlers)
        assert "### `POST /v1/charges`" in content
        assert '"status": "succeeded"' in content

    def test_external_api_no_handlers_message(self, generator, architecture_with_external_apis):
        content = generator._render(architecture_with_external_apis, [])
        assert "will be generated during the build phase" in content

    def test_external_api_string_format(self, generator):
        arch = {
            "project_name": "Test",
            "api_contracts": [],
            "external_apis": ["Stripe", "Twilio"],
            "port_allocation": {"backend": 23001},
        }
        content = generator._render(arch, [])
        assert "### Stripe" in content
        assert "### Twilio" in content

    def test_no_external_apis_no_section(self, generator, sample_architecture):
        content = generator._render(sample_architecture, [])
        assert "## External API Mocks" not in content

    def test_toc_includes_external_apis(self, generator, architecture_with_external_apis):
        content = generator._render(architecture_with_external_apis, [])
        assert "[External API Mocks](#external-api-mocks)" in content


# ---------------------------------------------------------------------------
# Handler Overview Table Tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestOverviewTable:
    """Test the overview table in the rendering."""

    def test_overview_table_counts(self, generator, sample_architecture, sample_frontend_handlers, sample_backend_handlers):
        all_handlers = sample_frontend_handlers + sample_backend_handlers
        content = generator._render(sample_architecture, all_handlers)
        assert "| Frontend | MSW (Mock Service Worker) | 2 handlers |" in content
        assert "| Backend | pytest fixtures + httpx MockTransport | 1 fixtures |" in content

    def test_overview_table_zero_handlers(self, generator, sample_architecture):
        content = generator._render(sample_architecture, [])
        assert "| Frontend | MSW (Mock Service Worker) | 0 handlers |" in content
        assert "| Backend | pytest fixtures + httpx MockTransport | 0 fixtures |" in content


# ---------------------------------------------------------------------------
# File Output Tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFileOutput:
    """Test file creation and content writing."""

    @pytest.mark.asyncio
    async def test_generate_creates_file(self, generator, sample_architecture, tmp_path):
        output_path = tmp_path / "docs" / "mock-documentation.md"
        result = await generator.generate(
            architecture=sample_architecture,
            mock_handlers=[],
            output_path=output_path,
        )
        assert result.exists()
        assert result.is_file()

    @pytest.mark.asyncio
    async def test_generate_creates_parent_dirs(self, generator, sample_architecture, tmp_path):
        output_path = tmp_path / "deep" / "nested" / "mock.md"
        result = await generator.generate(
            architecture=sample_architecture,
            mock_handlers=[],
            output_path=output_path,
        )
        assert result.exists()

    @pytest.mark.asyncio
    async def test_generate_returns_absolute_path(self, generator, sample_architecture, tmp_path):
        output_path = tmp_path / "mock.md"
        result = await generator.generate(
            architecture=sample_architecture,
            mock_handlers=[],
            output_path=output_path,
        )
        assert result.is_absolute()

    @pytest.mark.asyncio
    async def test_generate_writes_correct_content(
        self, generator, sample_architecture, sample_frontend_handlers, tmp_path
    ):
        output_path = tmp_path / "mock-docs.md"
        await generator.generate(
            architecture=sample_architecture,
            mock_handlers=sample_frontend_handlers,
            output_path=output_path,
        )

        content = output_path.read_text(encoding="utf-8")
        assert "# Task App -- Mock Documentation" in content
        assert "## Frontend Mocks (MSW)" in content
        assert "2 MSW handlers" in content


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_empty_architecture(self, generator, tmp_path):
        """Minimal architecture with no contracts, no external APIs."""
        arch = {
            "project_name": "Empty",
            "api_contracts": [],
            "external_apis": [],
            "port_allocation": {},
        }
        output_path = tmp_path / "mock.md"
        await generator.generate(
            architecture=arch,
            mock_handlers=[],
            output_path=output_path,
        )

        content = output_path.read_text(encoding="utf-8")
        assert "# Empty -- Mock Documentation" in content

    def test_handler_without_responses(self, generator, sample_architecture):
        """Handler with no success/error/empty response should still render."""
        handlers = [
            {
                "name": "minimal",
                "type": "frontend",
                "method": "GET",
                "path": "/api/v1/health",
                "description": "Health check",
            },
        ]
        content = generator._render(sample_architecture, handlers)
        assert "### `GET /api/v1/health`" in content
        # Should NOT crash even without response keys

    def test_handler_with_string_responses(self, generator, sample_architecture):
        """Handlers with string (non-dict) responses should render."""
        handlers = [
            {
                "name": "plain-text",
                "type": "frontend",
                "method": "GET",
                "path": "/api/v1/status",
                "description": "Get status",
                "success_response": "OK",
                "error_response": "ERROR",
                "empty_response": "",
            },
        ]
        content = generator._render(sample_architecture, handlers)
        assert "OK" in content
        assert "ERROR" in content

    def test_handler_without_description(self, generator, sample_architecture):
        """Handler with no description should still render cleanly."""
        handlers = [
            {
                "name": "no-desc",
                "type": "frontend",
                "method": "DELETE",
                "path": "/api/v1/cache",
                "success_response": {"cleared": True},
            },
        ]
        content = generator._render(sample_architecture, handlers)
        assert "### `DELETE /api/v1/cache`" in content
