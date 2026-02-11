"""Unit tests for usage guide generator (src.reporter.usage_guide).

Tests cover:
- FeatureGuide Pydantic model
- UsageGuideGenerator.generate() with full features and screenshots
- UsageGuideGenerator._normalise_features with various input formats
- UsageGuideGenerator._extract_endpoint_labels (str and dict endpoints)
- UsageGuideGenerator._extract_route_paths (str and dict routes)
- UsageGuideGenerator._auto_steps generation
- UsageGuideGenerator._build_screenshot_map grouping
- Rendered markdown structure (title, TOC, prerequisites, features, troubleshooting)
- Output file creation and path resolution
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.reporter.usage_guide import FeatureGuide, UsageGuideGenerator


# ---------------------------------------------------------------------------
# FeatureGuide model
# ---------------------------------------------------------------------------

class TestFeatureGuide:
    @pytest.mark.unit
    def test_minimal_creation(self):
        guide = FeatureGuide(name="Auth")
        assert guide.name == "Auth"
        assert guide.description == ""
        assert guide.steps == []
        assert guide.api_endpoints == []
        assert guide.routes == []
        assert guide.screenshots == []
        assert guide.tips == []

    @pytest.mark.unit
    def test_full_creation(self):
        guide = FeatureGuide(
            name="Task CRUD",
            description="Manage tasks",
            steps=["Create task", "View tasks"],
            api_endpoints=["POST /api/v1/tasks"],
            routes=["/tasks"],
            screenshots=["ss1.png"],
            tips=["Use keyboard shortcuts"],
        )
        assert guide.name == "Task CRUD"
        assert len(guide.steps) == 2
        assert len(guide.api_endpoints) == 1


# ---------------------------------------------------------------------------
# UsageGuideGenerator._normalise_features
# ---------------------------------------------------------------------------

class TestNormaliseFeatures:
    @pytest.mark.unit
    def test_basic_feature(self):
        gen = UsageGuideGenerator()
        raw = [{"name": "Auth", "description": "Login/Logout"}]
        guides = gen._normalise_features(raw)

        assert len(guides) == 1
        assert guides[0].name == "Auth"
        assert guides[0].description == "Login/Logout"

    @pytest.mark.unit
    def test_missing_name_defaults(self):
        gen = UsageGuideGenerator()
        raw = [{"description": "Something"}]
        guides = gen._normalise_features(raw)
        assert guides[0].name == "Unnamed Feature"

    @pytest.mark.unit
    def test_auto_steps_generated_when_empty(self):
        gen = UsageGuideGenerator()
        raw = [{"name": "Tasks", "description": "Manage tasks", "routes": ["/tasks"]}]
        guides = gen._normalise_features(raw)

        assert len(guides[0].steps) > 0
        assert any("/tasks" in s for s in guides[0].steps)

    @pytest.mark.unit
    def test_explicit_steps_preserved(self):
        gen = UsageGuideGenerator()
        raw = [{"name": "Auth", "steps": ["Step 1", "Step 2"]}]
        guides = gen._normalise_features(raw)

        assert guides[0].steps == ["Step 1", "Step 2"]


# ---------------------------------------------------------------------------
# UsageGuideGenerator._extract_endpoint_labels
# ---------------------------------------------------------------------------

class TestExtractEndpointLabels:
    @pytest.mark.unit
    def test_string_endpoints(self):
        gen = UsageGuideGenerator()
        feature = {"api_endpoints": ["GET /tasks", "POST /tasks"]}
        labels = gen._extract_endpoint_labels(feature)
        assert labels == ["GET /tasks", "POST /tasks"]

    @pytest.mark.unit
    def test_dict_endpoints(self):
        gen = UsageGuideGenerator()
        feature = {
            "api_endpoints": [
                {"method": "GET", "path": "/api/v1/tasks"},
                {"method": "POST", "path": "/api/v1/tasks"},
            ]
        }
        labels = gen._extract_endpoint_labels(feature)
        assert labels == ["GET /api/v1/tasks", "POST /api/v1/tasks"]

    @pytest.mark.unit
    def test_mixed_endpoints(self):
        gen = UsageGuideGenerator()
        feature = {
            "api_endpoints": [
                "DELETE /api/v1/tasks/:id",
                {"method": "PUT", "path": "/api/v1/tasks/:id"},
            ]
        }
        labels = gen._extract_endpoint_labels(feature)
        assert len(labels) == 2

    @pytest.mark.unit
    def test_empty_endpoints(self):
        gen = UsageGuideGenerator()
        labels = gen._extract_endpoint_labels({})
        assert labels == []


# ---------------------------------------------------------------------------
# UsageGuideGenerator._extract_route_paths
# ---------------------------------------------------------------------------

class TestExtractRoutePaths:
    @pytest.mark.unit
    def test_string_routes(self):
        gen = UsageGuideGenerator()
        feature = {"routes": ["/tasks", "/tasks/new"]}
        paths = gen._extract_route_paths(feature)
        assert paths == ["/tasks", "/tasks/new"]

    @pytest.mark.unit
    def test_dict_routes(self):
        gen = UsageGuideGenerator()
        feature = {"routes": [{"path": "/tasks"}, {"path": "/login"}]}
        paths = gen._extract_route_paths(feature)
        assert paths == ["/tasks", "/login"]

    @pytest.mark.unit
    def test_ui_routes_key(self):
        gen = UsageGuideGenerator()
        feature = {"ui_routes": ["/dashboard"]}
        paths = gen._extract_route_paths(feature)
        assert paths == ["/dashboard"]

    @pytest.mark.unit
    def test_ui_routes_takes_priority(self):
        gen = UsageGuideGenerator()
        feature = {"ui_routes": ["/a"], "routes": ["/b"]}
        paths = gen._extract_route_paths(feature)
        assert paths == ["/a"]


# ---------------------------------------------------------------------------
# UsageGuideGenerator._auto_steps
# ---------------------------------------------------------------------------

class TestAutoSteps:
    @pytest.mark.unit
    def test_with_route_and_description(self):
        gen = UsageGuideGenerator()
        guide = FeatureGuide(
            name="Tasks",
            description="Manage tasks",
            routes=["/tasks"],
            api_endpoints=["GET /api/v1/tasks"],
        )
        steps = gen._auto_steps(guide)

        assert len(steps) >= 2
        assert any("/tasks" in s for s in steps)
        assert any("Manage tasks" in s for s in steps)

    @pytest.mark.unit
    def test_no_metadata_fallback(self):
        gen = UsageGuideGenerator()
        guide = FeatureGuide(name="Mystery Feature")
        steps = gen._auto_steps(guide)

        assert len(steps) == 1
        assert "Mystery Feature" in steps[0]


# ---------------------------------------------------------------------------
# UsageGuideGenerator._build_screenshot_map
# ---------------------------------------------------------------------------

class TestBuildScreenshotMap:
    @pytest.mark.unit
    def test_groups_by_route(self):
        gen = UsageGuideGenerator()
        screenshots = [
            {"route": "/", "viewport": "desktop", "path": "ss/root-desktop.png"},
            {"route": "/", "viewport": "mobile", "path": "ss/root-mobile.png"},
            {"route": "/tasks", "viewport": "desktop", "path": "ss/tasks-desktop.png"},
        ]
        mapping = gen._build_screenshot_map(screenshots)

        assert "/" in mapping
        assert len(mapping["/"]) == 2
        assert "/tasks" in mapping
        assert len(mapping["/tasks"]) == 1

    @pytest.mark.unit
    def test_empty_screenshots(self):
        gen = UsageGuideGenerator()
        mapping = gen._build_screenshot_map([])
        assert mapping == {}


# ---------------------------------------------------------------------------
# UsageGuideGenerator._find_feature_screenshots
# ---------------------------------------------------------------------------

class TestFindFeatureScreenshots:
    @pytest.mark.unit
    def test_finds_matching_screenshots(self):
        gen = UsageGuideGenerator()
        screenshot_map = {
            "/tasks": [
                {"route": "/tasks", "viewport": "mobile", "path": "m.png"},
                {"route": "/tasks", "viewport": "desktop", "path": "d.png"},
            ],
        }
        results = gen._find_feature_screenshots(["/tasks"], screenshot_map)

        assert len(results) == 2
        # Desktop should come first
        assert results[0]["viewport"] == "desktop"
        assert results[1]["viewport"] == "mobile"

    @pytest.mark.unit
    def test_no_matching_screenshots(self):
        gen = UsageGuideGenerator()
        screenshot_map = {"/login": [{"viewport": "desktop", "path": "x.png"}]}
        results = gen._find_feature_screenshots(["/tasks"], screenshot_map)
        assert results == []


# ---------------------------------------------------------------------------
# UsageGuideGenerator.generate (full integration)
# ---------------------------------------------------------------------------

class TestUsageGuideGeneratorGenerate:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_creates_file(self, tmp_path: Path):
        gen = UsageGuideGenerator()
        features = [
            {"name": "Auth", "description": "User authentication", "routes": ["/login"]},
            {"name": "Tasks", "description": "Task management", "routes": ["/tasks"]},
        ]
        screenshots = [
            {"route": "/login", "viewport": "desktop", "path": "login-desktop.png"},
        ]

        result = await gen.generate(features, screenshots, "My App", tmp_path / "usage-guide.md")

        assert result.exists()
        content = result.read_text()
        assert "My App" in content
        assert "Usage Guide" in content

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_includes_toc(self, tmp_path: Path):
        gen = UsageGuideGenerator()
        features = [{"name": "Auth"}, {"name": "Tasks"}]

        result = await gen.generate(features, [], "My App", tmp_path / "guide.md")
        content = result.read_text()

        assert "Table of Contents" in content
        assert "Prerequisites" in content
        assert "Getting Started" in content
        assert "Auth" in content
        assert "Tasks" in content
        assert "Troubleshooting" in content

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_includes_screenshots(self, tmp_path: Path):
        gen = UsageGuideGenerator()
        features = [{"name": "Auth", "routes": ["/login"]}]
        screenshots = [
            {"route": "/login", "viewport": "desktop", "path": "/ss/login-desktop.png"},
        ]

        result = await gen.generate(features, screenshots, "App", tmp_path / "guide.md")
        content = result.read_text()

        assert "Screenshots" in content
        assert "Desktop View" in content

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_includes_api_endpoints(self, tmp_path: Path):
        gen = UsageGuideGenerator()
        features = [{
            "name": "Tasks",
            "api_endpoints": ["GET /api/v1/tasks", "POST /api/v1/tasks"],
        }]

        result = await gen.generate(features, [], "App", tmp_path / "guide.md")
        content = result.read_text()

        assert "API Endpoints" in content
        assert "GET /api/v1/tasks" in content

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_includes_tips(self, tmp_path: Path):
        gen = UsageGuideGenerator()
        features = [{"name": "Auth", "tips": ["Use a strong password"]}]

        result = await gen.generate(features, [], "App", tmp_path / "guide.md")
        content = result.read_text()

        assert "Tips" in content
        assert "Use a strong password" in content

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_creates_parent_dirs(self, tmp_path: Path):
        gen = UsageGuideGenerator()
        output = tmp_path / "deep" / "nested" / "guide.md"

        result = await gen.generate([], [], "App", output)
        assert result.exists()
        assert result.parent.exists()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_includes_troubleshooting(self, tmp_path: Path):
        gen = UsageGuideGenerator()
        result = await gen.generate([], [], "App", tmp_path / "guide.md")
        content = result.read_text()

        assert "Troubleshooting" in content
        assert "Application won't start" in content
        assert "Pages are blank" in content
        assert "API calls fail" in content

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_includes_port_23000(self, tmp_path: Path):
        gen = UsageGuideGenerator()
        result = await gen.generate([], [], "App", tmp_path / "guide.md")
        content = result.read_text()
        assert "23000" in content

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_generate_returns_absolute_path(self, tmp_path: Path):
        gen = UsageGuideGenerator()
        result = await gen.generate([], [], "App", tmp_path / "guide.md")
        assert result.is_absolute()
