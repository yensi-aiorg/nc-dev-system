"""Unit tests for the APIDocGenerator module.

Tests API documentation generation from architecture dicts, including
endpoint formatting, request/response body rendering, output file creation,
and edge cases.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.reporter.api_docs import APIDocGenerator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def generator() -> APIDocGenerator:
    """Fresh APIDocGenerator instance."""
    return APIDocGenerator()


@pytest.fixture
def sample_architecture() -> dict:
    """A minimal architecture dict with API contracts."""
    return {
        "project_name": "Test App",
        "api_contracts": [
            {
                "base_path": "/api/v1/tasks",
                "endpoints": [
                    {
                        "method": "GET",
                        "path": "/api/v1/tasks",
                        "description": "List all tasks",
                    },
                    {
                        "method": "POST",
                        "path": "/api/v1/tasks",
                        "description": "Create a new task",
                        "request_body": {
                            "title": "str",
                            "description": "str",
                            "priority": "str",
                        },
                        "response_body": {
                            "id": "objectid",
                            "title": "str",
                            "description": "str",
                        },
                    },
                    {
                        "method": "GET",
                        "path": "/api/v1/tasks/:id",
                        "description": "Get task details",
                        "response_body": {
                            "id": "objectid",
                            "title": "str",
                        },
                    },
                    {
                        "method": "PUT",
                        "path": "/api/v1/tasks/:id",
                        "description": "Update a task",
                        "request_body": {
                            "title": "str",
                            "description": "str",
                        },
                        "response_body": {
                            "id": "objectid",
                            "title": "str",
                        },
                    },
                    {
                        "method": "DELETE",
                        "path": "/api/v1/tasks/:id",
                        "description": "Delete a task",
                    },
                ],
            },
        ],
        "auth_required": True,
        "port_allocation": {
            "frontend": 23000,
            "backend": 23001,
        },
        "external_apis": [],
    }


@pytest.fixture
def architecture_with_auth_endpoint() -> dict:
    """Architecture with a POST login endpoint for rate-limiting tests."""
    return {
        "project_name": "Auth App",
        "api_contracts": [
            {
                "base_path": "/api/v1/auth",
                "endpoints": [
                    {
                        "method": "POST",
                        "path": "/api/v1/auth/login",
                        "description": "Authenticate user",
                        "request_body": {
                            "email": "email",
                            "password": "str",
                        },
                        "response_body": {
                            "access_token": "str",
                            "token_type": "str",
                        },
                    },
                    {
                        "method": "POST",
                        "path": "/api/v1/auth/register",
                        "description": "Register user",
                        "request_body": {
                            "email": "email",
                            "name": "str",
                            "password": "str",
                        },
                    },
                ],
            },
        ],
        "auth_required": True,
        "port_allocation": {"backend": 23001},
        "external_apis": [],
    }


# ---------------------------------------------------------------------------
# Rendering Tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestRendering:
    """Test markdown content rendering from architecture dicts."""

    def test_render_includes_project_name(self, generator, sample_architecture):
        content = generator._render(sample_architecture)
        assert "# Test App -- API Documentation" in content

    def test_render_includes_base_url(self, generator, sample_architecture):
        content = generator._render(sample_architecture)
        assert "http://localhost:23001/api/v1" in content

    def test_render_includes_health_endpoints(self, generator, sample_architecture):
        content = generator._render(sample_architecture)
        assert "/health" in content
        assert "/ready" in content

    def test_render_includes_authentication_section(self, generator, sample_architecture):
        content = generator._render(sample_architecture)
        assert "## Authentication" in content
        assert "Bearer token" in content

    def test_render_no_auth_required(self, generator):
        arch = {
            "project_name": "Public API",
            "api_contracts": [],
            "auth_required": False,
            "port_allocation": {"backend": 23001},
            "external_apis": [],
        }
        content = generator._render(arch)
        assert "does **not** require authentication" in content

    def test_render_includes_table_of_contents(self, generator, sample_architecture):
        content = generator._render(sample_architecture)
        assert "## Table of Contents" in content
        assert "[Overview](#overview)" in content
        assert "[Authentication](#authentication)" in content

    def test_render_includes_error_responses_section(self, generator, sample_architecture):
        content = generator._render(sample_architecture)
        assert "## Error Responses" in content
        assert "NOT_FOUND" in content
        assert "VALIDATION_ERROR" in content
        assert "UNAUTHORIZED" in content

    def test_render_includes_status_codes_section(self, generator, sample_architecture):
        content = generator._render(sample_architecture)
        assert "## Status Codes" in content
        assert "200" in content
        assert "404" in content
        assert "500" in content


# ---------------------------------------------------------------------------
# Endpoint Formatting Tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestEndpointFormatting:
    """Test individual endpoint rendering."""

    def test_render_get_endpoint(self, generator, sample_architecture):
        content = generator._render(sample_architecture)
        assert "### `GET /api/v1/tasks`" in content
        assert "List all tasks" in content

    def test_render_post_endpoint_with_request_body(self, generator, sample_architecture):
        content = generator._render(sample_architecture)
        assert "### `POST /api/v1/tasks`" in content
        assert "**Request Body:**" in content

    def test_render_put_endpoint(self, generator, sample_architecture):
        content = generator._render(sample_architecture)
        assert "### `PUT /api/v1/tasks/:id`" in content

    def test_render_delete_endpoint(self, generator, sample_architecture):
        content = generator._render(sample_architecture)
        assert "### `DELETE /api/v1/tasks/:id`" in content

    def test_render_summary_table(self, generator, sample_architecture):
        content = generator._render(sample_architecture)
        assert "| Method | Path | Description | Auth |" in content
        assert "| `GET` | `/api/v1/tasks` |" in content
        assert "| `POST` | `/api/v1/tasks` |" in content

    def test_render_rate_limiting_for_login(self, generator, architecture_with_auth_endpoint):
        content = generator._render(architecture_with_auth_endpoint)
        assert "Rate Limiting" in content


# ---------------------------------------------------------------------------
# Request/Response Body Formatting Tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestBodyFormatting:
    """Test request and response body example generation."""

    def test_generate_example_string(self, generator):
        result = generator._generate_example("str")
        assert result == "string_value"

    def test_generate_example_int(self, generator):
        result = generator._generate_example("int")
        assert result == 42

    def test_generate_example_bool(self, generator):
        result = generator._generate_example("bool")
        assert result is True

    def test_generate_example_datetime(self, generator):
        result = generator._generate_example("datetime")
        assert result == "2025-01-15T12:00:00Z"

    def test_generate_example_email(self, generator):
        result = generator._generate_example("email")
        assert result == "user@example.com"

    def test_generate_example_objectid(self, generator):
        result = generator._generate_example("objectid")
        assert isinstance(result, str)
        assert len(result) == 24  # MongoDB ObjectID format

    def test_generate_example_uuid(self, generator):
        result = generator._generate_example("uuid")
        assert isinstance(result, str)
        assert "-" in result

    def test_generate_example_dict(self, generator):
        schema = {"name": "str", "age": "int", "active": "bool"}
        result = generator._generate_example(schema)
        assert isinstance(result, dict)
        assert result["name"] == "string_value"
        assert result["age"] == 42
        assert result["active"] is True

    def test_generate_example_nested_dict(self, generator):
        schema = {"user": {"name": "str", "email": "email"}}
        result = generator._generate_example(schema)
        assert isinstance(result, dict)
        assert isinstance(result["user"], dict)
        assert result["user"]["email"] == "user@example.com"

    def test_generate_example_list(self, generator):
        schema = [{"id": "str"}]
        result = generator._generate_example(schema)
        assert isinstance(result, list)
        assert len(result) == 1

    def test_generate_example_empty_list(self, generator):
        result = generator._generate_example([])
        assert result == []

    def test_generate_example_list_type_string(self, generator):
        result = generator._generate_example("list[str]")
        assert isinstance(result, list)

    def test_generate_example_unknown_type(self, generator):
        result = generator._generate_example("custom_type")
        assert result == "custom_type"

    def test_generate_example_passthrough_non_string(self, generator):
        result = generator._generate_example(42)
        assert result == 42

    def test_extract_field_descriptions_simple(self, generator):
        schema = {
            "name": "str",
            "age": "int",
        }
        rows = generator._extract_field_descriptions(schema)
        assert len(rows) == 2
        assert rows[0]["name"] == "name"
        assert rows[0]["type"] == "str"
        assert rows[0]["required"] == "Yes"

    def test_extract_field_descriptions_with_metadata(self, generator):
        schema = {
            "email": {
                "type": "string",
                "description": "User email address",
                "required": True,
            },
            "nickname": {
                "type": "string",
                "description": "Optional nickname",
                "default": None,
            },
        }
        rows = generator._extract_field_descriptions(schema)
        assert len(rows) == 2

        email_row = next(r for r in rows if r["name"] == "email")
        assert email_row["description"] == "User email address"
        assert email_row["required"] == "Yes"

        nick_row = next(r for r in rows if r["name"] == "nickname")
        assert nick_row["required"] == "No"  # has default

    def test_extract_field_descriptions_array(self, generator):
        schema = {"tags": ["str"]}
        rows = generator._extract_field_descriptions(schema)
        assert len(rows) == 1
        assert rows[0]["type"] == "array"


# ---------------------------------------------------------------------------
# Contract Label Tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestContractLabel:
    """Test the contract label extraction helper."""

    def test_label_from_base_path(self, generator):
        label = generator._contract_label({"base_path": "/api/v1/tasks"})
        assert label == "Tasks"

    def test_label_from_nested_path(self, generator):
        label = generator._contract_label({"base_path": "/api/v1/dashboard"})
        assert label == "Dashboard"

    def test_label_from_hyphenated_path(self, generator):
        label = generator._contract_label({"base_path": "/api/v1/user-profiles"})
        assert label == "User Profiles"

    def test_label_fallback(self, generator):
        label = generator._contract_label({"base_path": "/api/v1"})
        assert label == "API"

    def test_label_no_base_path(self, generator):
        label = generator._contract_label({})
        assert label == "API"


# ---------------------------------------------------------------------------
# File Output Tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFileOutput:
    """Test file creation and content writing."""

    @pytest.mark.asyncio
    async def test_generate_creates_file(self, generator, sample_architecture, tmp_path):
        output_path = tmp_path / "docs" / "api-documentation.md"
        result = await generator.generate(
            architecture=sample_architecture,
            output_path=output_path,
        )
        assert result.exists()
        assert result.is_file()

    @pytest.mark.asyncio
    async def test_generate_creates_parent_dirs(self, generator, sample_architecture, tmp_path):
        output_path = tmp_path / "deep" / "nested" / "docs" / "api.md"
        result = await generator.generate(
            architecture=sample_architecture,
            output_path=output_path,
        )
        assert result.exists()

    @pytest.mark.asyncio
    async def test_generate_returns_absolute_path(self, generator, sample_architecture, tmp_path):
        output_path = tmp_path / "api-docs.md"
        result = await generator.generate(
            architecture=sample_architecture,
            output_path=output_path,
        )
        assert result.is_absolute()

    @pytest.mark.asyncio
    async def test_generate_writes_markdown_content(self, generator, sample_architecture, tmp_path):
        output_path = tmp_path / "api-docs.md"
        await generator.generate(
            architecture=sample_architecture,
            output_path=output_path,
        )

        content = output_path.read_text(encoding="utf-8")
        assert "# Test App -- API Documentation" in content
        assert "## Table of Contents" in content
        assert "## Status Codes" in content


# ---------------------------------------------------------------------------
# Empty / Edge Cases
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestEdgeCases:
    """Test edge cases and empty data handling."""

    @pytest.mark.asyncio
    async def test_empty_endpoints(self, generator, tmp_path):
        """Architecture with no endpoints should produce valid markdown."""
        arch = {
            "project_name": "Empty API",
            "api_contracts": [
                {
                    "base_path": "/api/v1/things",
                    "endpoints": [],
                }
            ],
            "auth_required": False,
            "port_allocation": {"backend": 23001},
            "external_apis": [],
        }
        output_path = tmp_path / "api-docs.md"
        await generator.generate(architecture=arch, output_path=output_path)

        content = output_path.read_text(encoding="utf-8")
        assert "No endpoints defined for this contract" in content

    @pytest.mark.asyncio
    async def test_no_api_contracts(self, generator, tmp_path):
        """Architecture with no contracts should produce valid markdown."""
        arch = {
            "project_name": "No APIs",
            "api_contracts": [],
            "auth_required": False,
            "port_allocation": {"backend": 23001},
            "external_apis": [],
        }
        output_path = tmp_path / "api-docs.md"
        await generator.generate(architecture=arch, output_path=output_path)

        content = output_path.read_text(encoding="utf-8")
        assert "# No APIs -- API Documentation" in content
        assert "## Status Codes" in content

    @pytest.mark.asyncio
    async def test_external_apis_section(self, generator, tmp_path):
        """Architecture with external APIs should include External APIs section."""
        arch = {
            "project_name": "Integration App",
            "api_contracts": [],
            "auth_required": False,
            "port_allocation": {"backend": 23001},
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
        }
        output_path = tmp_path / "api-docs.md"
        await generator.generate(architecture=arch, output_path=output_path)

        content = output_path.read_text(encoding="utf-8")
        assert "## External APIs" in content
        assert "### Stripe" in content
        assert "### SendGrid" in content
        assert "https://api.stripe.com" in content

    @pytest.mark.asyncio
    async def test_external_api_string_format(self, generator, tmp_path):
        """External APIs provided as strings should be handled."""
        arch = {
            "project_name": "Test",
            "api_contracts": [],
            "auth_required": False,
            "port_allocation": {"backend": 23001},
            "external_apis": ["Stripe", "PayPal"],
        }
        output_path = tmp_path / "api-docs.md"
        await generator.generate(architecture=arch, output_path=output_path)

        content = output_path.read_text(encoding="utf-8")
        assert "### Stripe" in content
        assert "### PayPal" in content

    @pytest.mark.asyncio
    async def test_endpoint_without_request_body(self, generator, tmp_path):
        """GET endpoint with no request body should not show Request Body section."""
        arch = {
            "project_name": "Test",
            "api_contracts": [
                {
                    "base_path": "/api/v1/items",
                    "endpoints": [
                        {
                            "method": "GET",
                            "path": "/api/v1/items",
                            "description": "List items",
                        }
                    ],
                }
            ],
            "auth_required": False,
            "port_allocation": {"backend": 23001},
            "external_apis": [],
        }
        output_path = tmp_path / "api-docs.md"
        await generator.generate(architecture=arch, output_path=output_path)

        content = output_path.read_text(encoding="utf-8")
        # The GET endpoint section should NOT have "Request Body:"
        # Split at the endpoint heading
        sections = content.split("### `GET /api/v1/items`")
        if len(sections) > 1:
            endpoint_section = sections[1].split("##")[0]  # Only up to the next section
            assert "**Request Body:**" not in endpoint_section

    @pytest.mark.asyncio
    async def test_default_port_when_not_specified(self, generator, tmp_path):
        """Missing port_allocation should use default 23001."""
        arch = {
            "project_name": "Test",
            "api_contracts": [],
            "auth_required": False,
            "port_allocation": {},
            "external_apis": [],
        }
        output_path = tmp_path / "api-docs.md"
        await generator.generate(architecture=arch, output_path=output_path)

        content = output_path.read_text(encoding="utf-8")
        assert "http://localhost:23001/api/v1" in content
