"""Unit tests for Codex prompt generation (src.builder.prompt_gen).

Tests cover:
- PromptGenerator.generate() with full and partial feature specs
- Prompt includes required sections (conventions, patterns, tests)
- PromptGenerator.save_prompt() writes to correct location
- PromptGenerator.generate_and_save() convenience method
- Helper formatters (_format_file_list, _format_api_contracts, etc.)
- Different feature types (backend-only, frontend-only, full-stack)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.builder.prompt_gen import (
    PromptGenerator,
    _format_acceptance_criteria,
    _format_api_contracts,
    _format_db_models,
    _format_file_list,
    _format_test_requirements,
)


# ---------------------------------------------------------------------------
# Helper formatters
# ---------------------------------------------------------------------------

class TestFormatFileList:
    @pytest.mark.unit
    def test_empty_list(self):
        result = _format_file_list([])
        assert "No specific files" in result

    @pytest.mark.unit
    def test_creates_and_modifies(self):
        files = [
            {"path": "backend/app/main.py", "action": "create", "description": "Entry point"},
            {"path": "frontend/src/App.tsx", "action": "modify", "description": "Route update"},
        ]
        result = _format_file_list(files)
        assert "+ `backend/app/main.py`" in result
        assert "~ `frontend/src/App.tsx`" in result
        assert "Entry point" in result

    @pytest.mark.unit
    def test_defaults_to_create(self):
        files = [{"path": "some/file.py"}]
        result = _format_file_list(files)
        assert "+ `some/file.py`" in result


class TestFormatApiContracts:
    @pytest.mark.unit
    def test_empty_contracts(self):
        result = _format_api_contracts([])
        assert "No API contracts" in result

    @pytest.mark.unit
    def test_contract_with_all_fields(self):
        contracts = [{
            "method": "POST",
            "path": "/api/v1/tasks",
            "description": "Create a task",
            "request_body": {"title": "string"},
            "response": {"id": "string"},
            "status_codes": {"201": "Created", "400": "Bad Request"},
        }]
        result = _format_api_contracts(contracts)
        assert "### POST /api/v1/tasks" in result
        assert "Create a task" in result
        assert "Request Body" in result
        assert "Response" in result
        assert "Status Codes" in result
        assert "201" in result

    @pytest.mark.unit
    def test_contract_minimal(self):
        contracts = [{"method": "get", "path": "/health"}]
        result = _format_api_contracts(contracts)
        assert "### GET /health" in result


class TestFormatDbModels:
    @pytest.mark.unit
    def test_empty_models(self):
        result = _format_db_models([])
        assert "No DB models" in result

    @pytest.mark.unit
    def test_model_with_fields_and_indexes(self):
        models = [{
            "name": "Task",
            "collection": "tasks",
            "fields": [
                {"name": "title", "type": "str", "required": True, "description": "Task title"},
            ],
            "indexes": [
                {"fields": ["title"], "unique": False},
            ],
        }]
        result = _format_db_models(models)
        assert "### Task (collection: `tasks`)" in result
        assert "title" in result
        assert "Indexes" in result


class TestFormatAcceptanceCriteria:
    @pytest.mark.unit
    def test_empty_criteria(self):
        result = _format_acceptance_criteria([])
        assert "No specific acceptance criteria" in result

    @pytest.mark.unit
    def test_numbered_list(self):
        criteria = ["User can log in", "JWT returned"]
        result = _format_acceptance_criteria(criteria)
        assert "1. User can log in" in result
        assert "2. JWT returned" in result


class TestFormatTestRequirements:
    @pytest.mark.unit
    def test_empty_tests(self):
        result = _format_test_requirements({})
        assert "comprehensive unit tests" in result

    @pytest.mark.unit
    def test_all_sections(self):
        tests = {
            "unit": ["Test service layer"],
            "integration": ["Test API routes"],
            "e2e": ["Test login flow"],
        }
        result = _format_test_requirements(tests)
        assert "Unit Tests" in result
        assert "Integration Tests" in result
        assert "E2E Tests" in result
        assert "Test service layer" in result


# ---------------------------------------------------------------------------
# PromptGenerator.generate
# ---------------------------------------------------------------------------

class TestPromptGeneratorGenerate:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_contains_feature_name(self):
        gen = PromptGenerator(project_name="test-project")
        feature = {"name": "Task CRUD", "description": "CRUD for tasks"}
        architecture = {"overview": "Standard stack"}

        prompt = await gen.generate(feature, architecture, "/tmp/proj")

        assert "Task CRUD" in prompt
        assert "CRUD for tasks" in prompt

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_includes_conventions(self):
        gen = PromptGenerator()
        feature = {"name": "auth"}
        architecture = {}

        prompt = await gen.generate(feature, architecture, "/tmp")

        assert "Python 3.12+" in prompt
        assert "FastAPI" in prompt
        assert "React 19" in prompt
        assert "Zustand" in prompt
        assert "Axios" in prompt

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_includes_prohibited_patterns(self):
        gen = PromptGenerator()
        feature = {"name": "feat"}
        architecture = {}

        prompt = await gen.generate(feature, architecture, "/tmp")

        assert "NO TODO comments" in prompt
        assert "NO placeholder" in prompt
        assert "NO console.log" in prompt

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_includes_zustand_pattern(self):
        gen = PromptGenerator()
        prompt = await gen.generate({"name": "x"}, {}, "/tmp")

        assert "useFeatureStore" in prompt
        assert "devtools" in prompt

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_includes_backend_service_pattern(self):
        gen = PromptGenerator()
        prompt = await gen.generate({"name": "x"}, {}, "/tmp")

        assert "BaseService" in prompt
        assert "AsyncIOMotorCollection" in prompt

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_with_dependencies(self):
        gen = PromptGenerator()
        feature = {"name": "categories", "dependencies": ["auth", "tasks"]}

        prompt = await gen.generate(feature, {}, "/tmp")

        assert "`auth`" in prompt
        assert "`tasks`" in prompt
        assert "depends on" in prompt

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_with_architecture_ports(self):
        gen = PromptGenerator()
        architecture = {
            "ports": {"Frontend": 23000, "Backend": 23001},
            "services": ["Frontend", "Backend"],
        }
        prompt = await gen.generate({"name": "x"}, architecture, "/tmp")

        assert "23000" in prompt
        assert "23001" in prompt

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_default_ports_when_empty(self):
        gen = PromptGenerator()
        prompt = await gen.generate({"name": "x"}, {"ports": {}}, "/tmp")

        # Should fall back to default port table
        assert "23000" in prompt

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_with_api_contracts(self):
        gen = PromptGenerator()
        feature = {
            "name": "tasks",
            "api_contracts": [
                {"method": "GET", "path": "/api/v1/tasks", "description": "List tasks"}
            ],
        }
        prompt = await gen.generate(feature, {}, "/tmp")
        assert "GET /api/v1/tasks" in prompt

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_with_db_models(self):
        gen = PromptGenerator()
        feature = {
            "name": "tasks",
            "db_models": [{"name": "Task", "collection": "tasks", "fields": []}],
        }
        prompt = await gen.generate(feature, {}, "/tmp")
        assert "Task" in prompt
        assert "tasks" in prompt


# ---------------------------------------------------------------------------
# PromptGenerator.save_prompt
# ---------------------------------------------------------------------------

class TestPromptGeneratorSavePrompt:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_save_creates_file(self, tmp_path: Path):
        gen = PromptGenerator()
        content = "# Test Prompt\nBuild something."

        path = await gen.save_prompt("User Auth", content, str(tmp_path))

        assert path.exists()
        assert path.name == "build-user-auth.md"
        assert path.read_text() == content

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_save_creates_prompts_directory(self, tmp_path: Path):
        gen = PromptGenerator()

        path = await gen.save_prompt("feat", "content", str(tmp_path))

        assert (tmp_path / ".nc-dev" / "prompts").is_dir()
        assert path.parent == tmp_path / ".nc-dev" / "prompts"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_save_sanitizes_filename(self, tmp_path: Path):
        gen = PromptGenerator()

        path = await gen.save_prompt("Complex Feature Name!!", "content", str(tmp_path))

        assert "!" not in path.name
        assert path.name.startswith("build-")
        assert path.name.endswith(".md")


# ---------------------------------------------------------------------------
# PromptGenerator.generate_and_save
# ---------------------------------------------------------------------------

class TestPromptGeneratorGenerateAndSave:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_and_save_returns_tuple(self, tmp_path: Path):
        gen = PromptGenerator()
        feature = {"name": "auth", "description": "Authentication"}
        architecture = {}

        prompt_content, path = await gen.generate_and_save(
            feature, architecture, str(tmp_path)
        )

        assert isinstance(prompt_content, str)
        assert "auth" in prompt_content
        assert path.exists()
        assert path.read_text() == prompt_content
