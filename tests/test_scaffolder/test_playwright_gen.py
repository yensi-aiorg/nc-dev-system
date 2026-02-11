"""Tests for Playwright configuration and E2E test generation.

Covers:
- Playwright config generation (root + frontend)
- Smoke test generation
- Per-feature E2E test generation
- Screenshot directory creation
- Feature E2E test content
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.scaffolder.playwright_gen import (
    PlaywrightGenerator,
    _build_feature_e2e_test,
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
def playwright_gen(mock_renderer) -> PlaywrightGenerator:
    """A PlaywrightGenerator with a mocked renderer."""
    return PlaywrightGenerator(mock_renderer)


@pytest.fixture
def basic_context() -> dict[str, Any]:
    """Basic template rendering context with features."""
    return {
        "project_name": "test-project",
        "project_name_slug": "test-project",
        "auth_required": False,
        "ports": {"frontend": 23000, "backend": 23001},
        "features": [
            {
                "name": "Task CRUD",
                "name_slug": "task_crud",
                "display_name": "Task CRUD",
                "entity_plural": "tasks",
                "route_path": "/task-crud",
            },
            {
                "name": "Dashboard",
                "name_slug": "dashboard",
                "display_name": "Dashboard",
                "entity_plural": "dashboards",
                "route_path": "/dashboard",
            },
        ],
    }


@pytest.fixture
def basic_routes() -> list[dict[str, Any]]:
    """Sample routes for E2E generation."""
    return [
        {"path": "/", "name": "Home"},
        {"path": "/tasks", "name": "Task CRUD"},
        {"path": "/dashboard", "name": "Dashboard"},
    ]


# ---------------------------------------------------------------------------
# PlaywrightGenerator.__init__
# ---------------------------------------------------------------------------


class TestPlaywrightGeneratorInit:
    def test_creates_with_renderer(self, mock_renderer):
        gen = PlaywrightGenerator(mock_renderer)
        assert gen.renderer is mock_renderer


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------


class TestGenerate:
    async def test_returns_list_of_paths(
        self, playwright_gen, tmp_path, basic_routes, basic_context
    ):
        result = await playwright_gen.generate(tmp_path, basic_routes, basic_context)
        assert isinstance(result, list)
        assert len(result) >= 3  # root config + frontend config + smoke test

    async def test_creates_root_playwright_config(
        self, playwright_gen, tmp_path, basic_routes, basic_context
    ):
        result = await playwright_gen.generate(tmp_path, basic_routes, basic_context)
        root_config = tmp_path / "playwright.config.ts"
        assert root_config.exists()

    async def test_creates_frontend_playwright_config(
        self, playwright_gen, tmp_path, basic_routes, basic_context
    ):
        result = await playwright_gen.generate(tmp_path, basic_routes, basic_context)
        frontend_config = tmp_path / "frontend" / "playwright.config.ts"
        assert frontend_config.exists()

    async def test_creates_smoke_test(
        self, playwright_gen, tmp_path, basic_routes, basic_context
    ):
        result = await playwright_gen.generate(tmp_path, basic_routes, basic_context)
        smoke_test = tmp_path / "frontend" / "e2e" / "smoke.spec.ts"
        assert smoke_test.exists()

    async def test_creates_per_feature_e2e_tests(
        self, playwright_gen, tmp_path, basic_routes, basic_context
    ):
        result = await playwright_gen.generate(tmp_path, basic_routes, basic_context)
        # 2 features in context
        task_test = tmp_path / "frontend" / "e2e" / "task_crud.spec.ts"
        dashboard_test = tmp_path / "frontend" / "e2e" / "dashboard.spec.ts"
        assert task_test.exists()
        assert dashboard_test.exists()

    async def test_creates_screenshots_directory(
        self, playwright_gen, tmp_path, basic_routes, basic_context
    ):
        await playwright_gen.generate(tmp_path, basic_routes, basic_context)
        screenshots_dir = tmp_path / "frontend" / "e2e" / "screenshots"
        assert screenshots_dir.is_dir()

    async def test_total_files_count(
        self, playwright_gen, tmp_path, basic_routes, basic_context
    ):
        result = await playwright_gen.generate(tmp_path, basic_routes, basic_context)
        # root config + frontend config + smoke test + 2 feature tests = 5
        assert len(result) == 5

    async def test_no_features_still_generates_configs(
        self, playwright_gen, tmp_path, basic_routes
    ):
        context = {
            "project_name": "test-project",
            "auth_required": False,
            "ports": {"frontend": 23000},
            "features": [],
        }
        result = await playwright_gen.generate(tmp_path, basic_routes, context)
        assert len(result) >= 3  # root + frontend config + smoke


# ---------------------------------------------------------------------------
# _build_feature_e2e_test
# ---------------------------------------------------------------------------


class TestBuildFeatureE2eTest:
    def test_generates_valid_typescript(self):
        content = _build_feature_e2e_test(
            name_slug="task_crud",
            display_name="Task CRUD",
            entity_plural="tasks",
            route_path="/task-crud",
            project_name="test-project",
            auth_required=False,
        )
        assert "import { test, expect }" in content
        assert "test.describe('Task CRUD'" in content

    def test_includes_page_load_test(self):
        content = _build_feature_e2e_test(
            name_slug="tasks",
            display_name="Tasks",
            entity_plural="tasks",
            route_path="/tasks",
            project_name="test",
            auth_required=False,
        )
        assert "page loads successfully" in content

    def test_includes_list_or_empty_state_test(self):
        content = _build_feature_e2e_test(
            name_slug="tasks",
            display_name="Tasks",
            entity_plural="tasks",
            route_path="/tasks",
            project_name="test",
            auth_required=False,
        )
        assert "displays tasks list or empty state" in content

    def test_includes_desktop_screenshot(self):
        content = _build_feature_e2e_test(
            name_slug="tasks",
            display_name="Tasks",
            entity_plural="tasks",
            route_path="/tasks",
            project_name="test",
            auth_required=False,
        )
        assert "desktop screenshot" in content
        assert "1440" in content
        assert "900" in content

    def test_includes_mobile_screenshot(self):
        content = _build_feature_e2e_test(
            name_slug="tasks",
            display_name="Tasks",
            entity_plural="tasks",
            route_path="/tasks",
            project_name="test",
            auth_required=False,
        )
        assert "mobile screenshot" in content
        assert "375" in content
        assert "812" in content

    def test_navigates_to_correct_route(self):
        content = _build_feature_e2e_test(
            name_slug="categories",
            display_name="Categories",
            entity_plural="categories",
            route_path="/categories",
            project_name="test",
            auth_required=False,
        )
        assert "page.goto('/categories')" in content

    def test_screenshot_paths_use_slug(self):
        content = _build_feature_e2e_test(
            name_slug="task_crud",
            display_name="Task CRUD",
            entity_plural="tasks",
            route_path="/task-crud",
            project_name="test",
            auth_required=False,
        )
        assert "task_crud-desktop.png" in content
        assert "task_crud-mobile.png" in content

    def test_uses_display_name_in_describe(self):
        content = _build_feature_e2e_test(
            name_slug="user_auth",
            display_name="User Authentication",
            entity_plural="users",
            route_path="/user-auth",
            project_name="test",
            auth_required=True,
        )
        assert "User Authentication" in content
