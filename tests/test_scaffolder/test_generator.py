"""Tests for the project scaffolding generator.

Covers:
- Full project generation with mock architecture
- Directory structure creation
- All expected files are created
- auth_required=True and auth_required=False variants
- ProjectConfig model validation
- Architecture-to-config extraction
- Feature/collection enrichment helpers
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.scaffolder.generator import (
    DEFAULT_PORTS,
    ProjectConfig,
    ProjectGenerator,
    _enrich_api_contract,
    _enrich_collection,
    _enrich_feature,
    _extract_config_from_architecture,
    _infer_entity_plural,
    _python_default_literal,
    _python_slugify,
    _sample_value_for_type,
    _slugify,
    _to_pascal,
)


# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def minimal_config() -> ProjectConfig:
    """A minimal valid ProjectConfig with no features."""
    return ProjectConfig(
        name="test-project",
        description="A test project.",
        auth_required=False,
        features=[],
        db_collections=[],
        api_contracts=[],
    )


@pytest.fixture
def feature_config() -> ProjectConfig:
    """A ProjectConfig with one feature."""
    return ProjectConfig(
        name="task-app",
        description="A task management app.",
        auth_required=False,
        features=[
            {
                "name": "Task CRUD",
                "description": "Manage tasks.",
                "priority": "P0",
                "fields": [
                    {"name": "title", "type": "string", "required": True},
                    {"name": "description", "type": "string", "required": False},
                    {"name": "priority", "type": "string", "required": True},
                    {"name": "due_date", "type": "datetime", "required": False},
                ],
            },
        ],
        db_collections=[
            {
                "name": "tasks",
                "fields": [
                    {"name": "_id", "type": "ObjectId", "required": True},
                    {"name": "title", "type": "string", "required": True},
                    {"name": "description", "type": "string", "required": False},
                    {"name": "created_at", "type": "datetime", "required": True},
                    {"name": "updated_at", "type": "datetime", "required": True},
                ],
                "indexes": [
                    {"fields": ["title"], "unique": False},
                ],
            },
        ],
        api_contracts=[
            {
                "base_path": "/api/v1/tasks",
                "endpoints": [
                    {"method": "GET", "path": "/api/v1/tasks", "description": "List tasks"},
                    {"method": "POST", "path": "/api/v1/tasks", "description": "Create task"},
                ],
            },
        ],
    )


@pytest.fixture
def auth_config() -> ProjectConfig:
    """A ProjectConfig with auth_required=True."""
    return ProjectConfig(
        name="auth-app",
        description="An app with authentication.",
        auth_required=True,
        features=[
            {
                "name": "User Authentication",
                "description": "Login and registration.",
                "priority": "P0",
                "fields": [],
            },
        ],
        db_collections=[
            {
                "name": "users",
                "fields": [
                    {"name": "_id", "type": "ObjectId", "required": True},
                    {"name": "email", "type": "string", "required": True},
                    {"name": "password_hash", "type": "string", "required": True},
                    {"name": "name", "type": "string", "required": True},
                ],
                "indexes": [{"fields": ["email"], "unique": True}],
            },
        ],
        api_contracts=[],
    )


@pytest.fixture
def sample_architecture_dict(parsed_architecture, parsed_features) -> dict[str, Any]:
    """Architecture dict as returned from the parser."""
    return {**parsed_architecture, "features": parsed_features}


# ---------------------------------------------------------------------------
# ProjectConfig model tests
# ---------------------------------------------------------------------------


class TestProjectConfig:
    def test_minimal_config(self, minimal_config):
        assert minimal_config.name == "test-project"
        assert minimal_config.auth_required is False
        assert minimal_config.features == []

    def test_default_ports(self, minimal_config):
        assert minimal_config.ports == DEFAULT_PORTS

    def test_custom_ports(self):
        config = ProjectConfig(
            name="test",
            ports={"frontend": 24000, "backend": 24001},
        )
        assert config.ports["frontend"] == 24000
        assert config.ports["backend"] == 24001


# ---------------------------------------------------------------------------
# _slugify helpers
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_hyphen_slug(self):
        assert _slugify("Task Management") == "task-management"

    def test_strips_special(self):
        assert _slugify("Hello, World!") == "hello-world"

    def test_empty(self):
        assert _slugify("") == ""


class TestPythonSlugify:
    def test_underscore_slug(self):
        assert _python_slugify("Task Management") == "task_management"

    def test_strips_special(self):
        assert _python_slugify("Hello, World!") == "hello_world"


class TestToPascal:
    def test_from_hyphen(self):
        assert _to_pascal("task-management") == "TaskManagement"

    def test_from_underscore(self):
        assert _to_pascal("task_management") == "TaskManagement"

    def test_from_spaces(self):
        assert _to_pascal("Task Management") == "TaskManagement"

    def test_single_word(self):
        assert _to_pascal("task") == "Task"


class TestInferEntityPlural:
    def test_task_crud(self):
        assert _infer_entity_plural("Task CRUD") == "tasks"

    def test_user_management(self):
        assert _infer_entity_plural("User Management") == "users"

    def test_category(self):
        result = _infer_entity_plural("Category")
        assert "categor" in result


# ---------------------------------------------------------------------------
# _python_default_literal
# ---------------------------------------------------------------------------


class TestPythonDefaultLiteral:
    def test_with_default(self):
        assert _python_default_literal("str", "hello") == "'hello'"

    def test_without_default(self):
        assert _python_default_literal("str") == "None"

    def test_boolean_default(self):
        assert _python_default_literal("bool", True) == "True"

    def test_list_default(self):
        assert _python_default_literal("list", []) == "[]"


# ---------------------------------------------------------------------------
# _sample_value_for_type
# ---------------------------------------------------------------------------


class TestSampleValueForType:
    def test_email_field(self):
        val = _sample_value_for_type("string", "email")
        assert "@" in val

    def test_password_field(self):
        val = _sample_value_for_type("string", "password")
        assert "Password" in val or "password" in val.lower()

    def test_url_field(self):
        val = _sample_value_for_type("string", "url")
        assert "http" in val

    def test_integer_type(self):
        val = _sample_value_for_type("int", "count")
        assert isinstance(val, int)

    def test_float_type(self):
        val = _sample_value_for_type("float", "amount")
        assert isinstance(val, float)

    def test_boolean_type(self):
        val = _sample_value_for_type("bool", "is_active")
        assert isinstance(val, bool)

    def test_datetime_type(self):
        val = _sample_value_for_type("datetime", "created_at")
        assert "2025" in str(val) or "T" in str(val)

    def test_array_type(self):
        val = _sample_value_for_type("array", "tags")
        assert isinstance(val, list)

    def test_string_fallback(self):
        val = _sample_value_for_type("string", "custom_field")
        assert isinstance(val, str)
        assert "custom_field" in val


# ---------------------------------------------------------------------------
# _enrich_feature
# ---------------------------------------------------------------------------


class TestEnrichFeature:
    def test_adds_name_slug(self):
        feature = {"name": "Task CRUD", "fields": []}
        enriched = _enrich_feature(feature, False)
        assert enriched["name_slug"] == "task_crud"

    def test_adds_url_slug(self):
        feature = {"name": "Task CRUD", "fields": []}
        enriched = _enrich_feature(feature, False)
        assert enriched["url_slug"] == "task-crud"

    def test_adds_model_name(self):
        feature = {"name": "Task CRUD", "fields": []}
        enriched = _enrich_feature(feature, False)
        assert enriched["model_name"] == "TaskCrud"

    def test_adds_ts_type_name(self):
        feature = {"name": "Task Management", "fields": []}
        enriched = _enrich_feature(feature, False)
        assert enriched["ts_type_name"] == "TaskManagement"

    def test_adds_route_path(self):
        feature = {"name": "Task CRUD", "fields": []}
        enriched = _enrich_feature(feature, False)
        assert enriched["route_path"] == "/task-crud"

    def test_enriches_field_types(self):
        feature = {
            "name": "Tasks",
            "fields": [
                {"name": "title", "type": "string", "required": True},
                {"name": "count", "type": "int", "required": True},
            ],
        }
        enriched = _enrich_feature(feature, False)
        fields = enriched["fields"]
        assert fields[0]["python_type"] == "str"
        assert fields[0]["ts_type"] == "string"
        assert fields[1]["python_type"] == "int"
        assert fields[1]["ts_type"] == "number"

    def test_sample_create_payload(self):
        feature = {
            "name": "Tasks",
            "fields": [
                {"name": "title", "type": "string", "required": True},
            ],
        }
        enriched = _enrich_feature(feature, False)
        assert "sample_create_payload" in enriched
        assert "sample_create_keys" in enriched
        assert "title" in enriched["sample_create_keys"]

    def test_auth_required_flag(self):
        feature = {"name": "Tasks", "fields": []}
        enriched = _enrich_feature(feature, True)
        assert enriched["auth_required"] is True


# ---------------------------------------------------------------------------
# _enrich_collection
# ---------------------------------------------------------------------------


class TestEnrichCollection:
    def test_enriches_field_types(self):
        collection = {
            "name": "tasks",
            "fields": [
                {"name": "title", "type": "string", "required": True},
                {"name": "count", "type": "int", "required": True},
            ],
            "indexes": [],
        }
        enriched = _enrich_collection(collection)
        fields = enriched["fields"]
        assert fields[0]["python_type"] == "str"
        assert fields[1]["python_type"] == "int"

    def test_preserves_indexes(self):
        collection = {
            "name": "tasks",
            "fields": [],
            "indexes": [{"fields": ["title"], "unique": False}],
        }
        enriched = _enrich_collection(collection)
        assert len(enriched["indexes"]) == 1

    def test_adds_seed_values(self):
        collection = {
            "name": "tasks",
            "fields": [
                {"name": "title", "type": "string", "required": True},
            ],
            "indexes": [],
        }
        enriched = _enrich_collection(collection)
        assert "seed_value" in enriched["fields"][0]
        assert "seed_value_alt" in enriched["fields"][0]


# ---------------------------------------------------------------------------
# _enrich_api_contract
# ---------------------------------------------------------------------------


class TestEnrichApiContract:
    def test_extracts_name_from_base_path(self):
        contract = {
            "base_path": "/api/v1/tasks",
            "endpoints": [],
        }
        enriched = _enrich_api_contract(contract)
        assert enriched["name"] == "tasks"

    def test_preserves_endpoints(self):
        contract = {
            "base_path": "/api/v1/tasks",
            "endpoints": [{"method": "GET", "path": "/api/v1/tasks"}],
        }
        enriched = _enrich_api_contract(contract)
        assert len(enriched["endpoints"]) == 1


# ---------------------------------------------------------------------------
# _extract_config_from_architecture
# ---------------------------------------------------------------------------


class TestExtractConfigFromArchitecture:
    def test_extracts_basic_fields(self):
        arch = {
            "project_name": "My App",
            "description": "A cool app.",
            "auth_required": True,
            "features": [],
            "db_collections": [],
            "api_contracts": [],
            "external_apis": [],
        }
        config = _extract_config_from_architecture(arch)
        assert config.name == "My App"
        assert config.description == "A cool app."
        assert config.auth_required is True

    def test_extracts_ports(self):
        arch = {
            "project_name": "Test",
            "port_allocation": {"frontend": 24000, "backend": 24001},
            "features": [],
            "db_collections": [],
            "api_contracts": [],
            "external_apis": [],
        }
        config = _extract_config_from_architecture(arch)
        assert config.ports["frontend"] == 24000
        assert config.ports["backend"] == 24001

    def test_default_ports_when_missing(self):
        arch = {
            "project_name": "Test",
            "features": [],
            "db_collections": [],
            "api_contracts": [],
            "external_apis": [],
        }
        config = _extract_config_from_architecture(arch)
        assert config.ports == DEFAULT_PORTS

    def test_handles_pydantic_model_features(self):
        """Test that features with model_dump() are handled."""

        class FakeModel:
            def model_dump(self):
                return {"name": "Feature 1"}

        arch = {
            "project_name": "Test",
            "features": [FakeModel()],
            "db_collections": [],
            "api_contracts": [],
            "external_apis": [],
        }
        config = _extract_config_from_architecture(arch)
        assert len(config.features) == 1
        assert config.features[0]["name"] == "Feature 1"

    def test_handles_dict_features(self):
        arch = {
            "project_name": "Test",
            "features": [{"name": "Feature 1"}],
            "db_collections": [],
            "api_contracts": [],
            "external_apis": [],
        }
        config = _extract_config_from_architecture(arch)
        assert len(config.features) == 1

    def test_extracts_external_apis(self):
        arch = {
            "project_name": "Test",
            "features": [],
            "db_collections": [],
            "api_contracts": [],
            "external_apis": [{"name": "Stripe", "base_url": "https://api.stripe.com"}],
        }
        config = _extract_config_from_architecture(arch)
        assert len(config.external_apis) == 1


# ---------------------------------------------------------------------------
# ProjectGenerator (integration: directory structure + mock rendering)
# ---------------------------------------------------------------------------


class TestProjectGenerator:
    def test_init(self, minimal_config):
        gen = ProjectGenerator(minimal_config)
        assert gen.config == minimal_config
        assert gen.renderer is not None
        assert gen.docker_gen is not None
        assert gen.playwright_gen is not None
        assert gen.mock_gen is not None
        assert gen.factory_gen is not None

    def test_build_context(self, feature_config):
        gen = ProjectGenerator(feature_config)
        ctx = gen._build_context()
        assert ctx["project_name"] == "task-app"
        assert ctx["description"] == "A task management app."
        assert ctx["auth_required"] is False
        assert ctx["ports"] == DEFAULT_PORTS
        assert len(ctx["features"]) == 1
        assert ctx["features"][0]["name_slug"] == "task_crud"

    def test_collect_routes_basic(self, feature_config):
        gen = ProjectGenerator(feature_config)
        routes = gen._collect_routes()
        # Home route + 1 feature route
        assert len(routes) >= 2
        assert routes[0]["path"] == "/"

    def test_collect_routes_with_auth(self, auth_config):
        gen = ProjectGenerator(auth_config)
        routes = gen._collect_routes()
        paths = [r["path"] for r in routes]
        assert "/login" in paths

    def test_collect_routes_no_auth(self, minimal_config):
        gen = ProjectGenerator(minimal_config)
        routes = gen._collect_routes()
        paths = [r["path"] for r in routes]
        assert "/login" not in paths

    async def test_create_directory_structure(self, minimal_config, tmp_path):
        gen = ProjectGenerator(minimal_config)
        root = tmp_path / "project"
        root.mkdir()
        await gen._create_directory_structure(root)

        # Check critical directories exist
        assert (root / "backend" / "app" / "api" / "v1" / "endpoints").is_dir()
        assert (root / "backend" / "app" / "core").is_dir()
        assert (root / "backend" / "app" / "models").is_dir()
        assert (root / "backend" / "app" / "schemas").is_dir()
        assert (root / "backend" / "app" / "services").is_dir()
        assert (root / "backend" / "app" / "db" / "migrations").is_dir()
        assert (root / "backend" / "tests" / "unit" / "test_services").is_dir()
        assert (root / "backend" / "tests" / "integration" / "test_api").is_dir()
        assert (root / "backend" / "tests" / "e2e" / "test_workflows").is_dir()
        assert (root / "frontend" / "src" / "api").is_dir()
        assert (root / "frontend" / "src" / "components" / "ui").is_dir()
        assert (root / "frontend" / "src" / "components" / "layout").is_dir()
        assert (root / "frontend" / "src" / "components" / "features").is_dir()
        assert (root / "frontend" / "src" / "stores").is_dir()
        assert (root / "frontend" / "src" / "pages").is_dir()
        assert (root / "frontend" / "src" / "hooks").is_dir()
        assert (root / "frontend" / "src" / "mocks").is_dir()
        assert (root / "frontend" / "src" / "types").is_dir()
        assert (root / "frontend" / "src" / "utils").is_dir()
        assert (root / "frontend" / "src" / "styles").is_dir()
        assert (root / "frontend" / "e2e").is_dir()
        assert (root / "frontend" / "tests" / "unit").is_dir()
        assert (root / "frontend" / "tests" / "integration").is_dir()
        assert (root / "frontend" / "tests" / "e2e").is_dir()
        assert (root / "scripts").is_dir()
        assert (root / "docs" / "screenshots").is_dir()
        assert (root / ".github" / "workflows").is_dir()

    async def test_create_directory_structure_with_auth(self, auth_config, tmp_path):
        gen = ProjectGenerator(auth_config)
        root = tmp_path / "auth-project"
        root.mkdir()
        await gen._create_directory_structure(root)
        assert (root / "keycloak" / "themes").is_dir()

    async def test_create_directory_structure_no_keycloak_without_auth(
        self, minimal_config, tmp_path
    ):
        gen = ProjectGenerator(minimal_config)
        root = tmp_path / "no-auth-project"
        root.mkdir()
        await gen._create_directory_structure(root)
        assert not (root / "keycloak").exists()

    async def test_generate_from_architecture(self, tmp_path):
        """Test generate_from_architecture extracts config and delegates."""
        arch = {
            "project_name": "test-from-arch",
            "description": "Generated from architecture.",
            "auth_required": False,
            "features": [{"name": "Widget", "fields": []}],
            "db_collections": [{"name": "widgets", "fields": [], "indexes": []}],
            "api_contracts": [],
            "external_apis": [],
            "port_allocation": DEFAULT_PORTS,
        }

        # Use a minimal config to create the generator, then call generate_from_architecture
        config = ProjectConfig(name="placeholder")
        gen = ProjectGenerator(config)

        # Mock the generate method to avoid template rendering
        gen.generate = AsyncMock(return_value=tmp_path / "test-from-arch")

        result = await gen.generate_from_architecture(arch, str(tmp_path))
        assert gen.config.name == "test-from-arch"
        assert gen.config.description == "Generated from architecture."
