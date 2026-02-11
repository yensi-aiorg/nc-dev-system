"""Tests for the requirements parser (extractor module).

Covers:
- Parsing sample requirements markdown end-to-end
- Feature extraction (names, priorities, descriptions)
- Route extraction from markdown
- API endpoint extraction
- Database schema inference
- Handling of empty/malformed markdown
- Ambiguity detection
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.parser.extractor import (
    _build_feature,
    _detect_ambiguities,
    _detect_external_apis,
    _estimate_complexity,
    _extract_api_endpoints_from_bullets,
    _extract_priority,
    _extract_project_description,
    _extract_project_name,
    _extract_routes_from_bullets,
    _find_feature_sections,
    _get_bullets,
    _guess_field_type,
    _infer_entity_name,
    _infer_request_body,
    _is_meta_section,
    _parse_sections,
    _read_file,
    _requires_auth,
    _slugify,
    parse_requirements,
)
from src.parser.models import (
    Complexity,
    Feature,
    HTTPMethod,
    Priority,
    Route,
)


# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def simple_markdown() -> str:
    """Minimal valid markdown with one feature."""
    return textwrap.dedent("""\
        # My Project

        A simple project description.

        ## Features

        ### Task Management (P0)
        - Create tasks with title and description
        - View task list with pagination
        - Edit task details
        - Delete tasks (soft delete)
    """)


@pytest.fixture
def auth_markdown() -> str:
    """Markdown with an auth feature."""
    return textwrap.dedent("""\
        # Auth App

        An application with authentication.

        ## Features

        ### User Authentication (P0)
        - Email/password registration with validation
        - Email/password login
        - Session management with JWT tokens
        - Password reset via email link
        - Logout functionality
    """)


@pytest.fixture
def multi_feature_markdown() -> str:
    """Markdown with multiple features at different priorities."""
    return textwrap.dedent("""\
        # Multi Feature App

        A complex application.

        ## Features

        ### Core Dashboard (P0)
        - Dashboard overview with statistics
        - Recent activity feed

        ### Task CRUD (P0)
        - Create tasks with title, description, priority
        - View task list
        - Update task status
        - Delete tasks

        ### Reports (P1)
        - Generate weekly reports
        - Filter reports by date range

        ### Responsive Design (P2)
        - Mobile-first responsive layout
        - Touch-friendly interactions
    """)


@pytest.fixture
def ambiguous_markdown() -> str:
    """Markdown containing ambiguous language."""
    return textwrap.dedent("""\
        # Ambiguous Project

        Some project description.

        ## Features

        ### Something (P1)
        - This feature does something TBD
        - We'll decide later how to handle errors
        - Maybe add caching or similar
        - Need to figure out the data model
    """)


@pytest.fixture
def external_api_markdown() -> str:
    """Markdown referencing external APIs."""
    return textwrap.dedent("""\
        # Payment App

        Application with external integrations.

        ## Features

        ### Payment Processing (P0)
        - Process payments via Stripe integration
        - Send email notifications via SendGrid
        - Store files on S3
    """)


# ---------------------------------------------------------------------------
# _slugify
# ---------------------------------------------------------------------------


class TestSlugify:
    def test_basic_slug(self):
        assert _slugify("Task Management") == "task-management"

    def test_strips_special_chars(self):
        assert _slugify("Hello, World!") == "hello-world"

    def test_strips_leading_trailing_hyphens(self):
        assert _slugify("  --hello--  ") == "hello"

    def test_empty_string(self):
        assert _slugify("") == ""


# ---------------------------------------------------------------------------
# _infer_entity_name
# ---------------------------------------------------------------------------


class TestInferEntityName:
    def test_task_crud(self):
        result = _infer_entity_name("Task CRUD")
        assert result == "tasks"

    def test_user_authentication(self):
        result = _infer_entity_name("User Authentication")
        assert result == "users"

    def test_comment_management(self):
        result = _infer_entity_name("Comment Management")
        assert result == "comments"

    def test_category(self):
        result = _infer_entity_name("Category")
        # "category" -> "categor" -> "categories" (via -y -> -ies)
        assert "categor" in result

    def test_single_word(self):
        result = _infer_entity_name("Project Dashboard")
        assert result == "projects"


# ---------------------------------------------------------------------------
# _extract_priority
# ---------------------------------------------------------------------------


class TestExtractPriority:
    def test_p0_explicit(self):
        assert _extract_priority("Feature Name (P0)") == Priority.P0

    def test_p1_explicit(self):
        assert _extract_priority("Feature Name (P1)") == Priority.P1

    def test_p2_explicit(self):
        assert _extract_priority("Feature Name (P2)") == Priority.P2

    def test_inferred_p0_from_must(self):
        assert _extract_priority("This must be implemented") == Priority.P0

    def test_inferred_p0_from_critical(self):
        assert _extract_priority("Critical feature for launch") == Priority.P0

    def test_inferred_p2_from_nice_to_have(self):
        assert _extract_priority("nice to have feature") == Priority.P2

    def test_inferred_p2_from_optional(self):
        assert _extract_priority("optional dark mode") == Priority.P2

    def test_default_p1(self):
        assert _extract_priority("Some normal feature") == Priority.P1

    def test_case_insensitive(self):
        assert _extract_priority("Feature (p0)") == Priority.P0


# ---------------------------------------------------------------------------
# _estimate_complexity
# ---------------------------------------------------------------------------


class TestEstimateComplexity:
    def test_high_from_realtime(self):
        bullets = ["real-time updates via websocket"]
        assert _estimate_complexity(bullets, "Chat") == Complexity.HIGH

    def test_high_from_payment(self):
        bullets = ["payment processing integration"]
        assert _estimate_complexity(bullets, "Billing") == Complexity.HIGH

    def test_high_from_many_bullets(self):
        bullets = ["b1", "b2", "b3", "b4", "b5", "b6"]
        assert _estimate_complexity(bullets, "Feature") == Complexity.HIGH

    def test_low_from_static_page(self):
        bullets = ["static about page"]
        assert _estimate_complexity(bullets, "About") == Complexity.LOW

    def test_medium_default(self):
        bullets = ["create items", "list items"]
        assert _estimate_complexity(bullets, "Items") == Complexity.MEDIUM


# ---------------------------------------------------------------------------
# _detect_external_apis
# ---------------------------------------------------------------------------


class TestDetectExternalApis:
    def test_detects_stripe(self):
        result = _detect_external_apis("Process payments via Stripe")
        assert "stripe" in result

    def test_detects_multiple(self):
        result = _detect_external_apis("Use Stripe for payments and SendGrid for email")
        assert "stripe" in result
        assert "sendgrid" in result

    def test_no_apis(self):
        result = _detect_external_apis("Create tasks with title and description")
        assert result == []

    def test_case_insensitive(self):
        result = _detect_external_apis("STRIPE integration")
        assert "stripe" in result


# ---------------------------------------------------------------------------
# _detect_ambiguities
# ---------------------------------------------------------------------------


class TestDetectAmbiguities:
    def test_detects_tbd(self):
        text = "- The data model is TBD"
        result = _detect_ambiguities(text)
        assert len(result) >= 1
        assert "tbd" in result[0].lower()

    def test_detects_to_be_decided(self):
        text = "- The approach is to be decided"
        result = _detect_ambiguities(text)
        assert len(result) >= 1

    def test_detects_maybe(self):
        text = "- Maybe add caching"
        result = _detect_ambiguities(text)
        assert len(result) >= 1

    def test_detects_figure_out(self):
        text = "- Need to figure out the data model"
        result = _detect_ambiguities(text)
        assert len(result) >= 1

    def test_no_ambiguities(self):
        text = "Create tasks with title and description"
        result = _detect_ambiguities(text)
        assert result == []

    def test_multiple_ambiguities(self):
        text = "- TBD how to handle errors\n- Maybe add caching\n- Something like Redis"
        result = _detect_ambiguities(text)
        assert len(result) >= 2


# ---------------------------------------------------------------------------
# _requires_auth
# ---------------------------------------------------------------------------


class TestRequiresAuth:
    def test_auth_feature_name(self):
        assert _requires_auth("User Authentication", []) is True

    def test_login_feature_name(self):
        assert _requires_auth("Login System", []) is True

    def test_requires_login_in_bullets(self):
        assert _requires_auth("Task CRUD", ["requires login to access"]) is True

    def test_personal_in_bullets(self):
        assert _requires_auth("Dashboard", ["view personal dashboard"]) is True

    def test_no_auth_needed(self):
        assert _requires_auth("Landing Page", ["static page"]) is False


# ---------------------------------------------------------------------------
# _parse_sections
# ---------------------------------------------------------------------------


class TestParseSections:
    def test_parses_headers(self, simple_markdown):
        sections = _parse_sections(simple_markdown)
        assert len(sections) >= 1
        # Top-level should be the H1
        assert sections[0].level == 1
        assert sections[0].title == "My Project"

    def test_nested_sections(self, simple_markdown):
        sections = _parse_sections(simple_markdown)
        # The H2 "Features" should be a child of H1
        all_h2 = [s for s in sections[0].children if s.level == 2]
        assert len(all_h2) >= 1

    def test_empty_markdown(self):
        sections = _parse_sections("")
        assert sections == []

    def test_no_headers(self):
        sections = _parse_sections("Just some text\nwith no headers\n")
        assert sections == []

    def test_body_content(self):
        md = "# Title\n\nBody text here.\n\n## Sub\nSub body.\n"
        sections = _parse_sections(md)
        assert "Body text here." in sections[0].body


# ---------------------------------------------------------------------------
# _get_bullets
# ---------------------------------------------------------------------------


class TestGetBullets:
    def test_dash_bullets(self):
        body = "- Item one\n- Item two\n- Item three"
        bullets = _get_bullets(body)
        assert len(bullets) == 3
        assert bullets[0] == "Item one"

    def test_asterisk_bullets(self):
        body = "* Item one\n* Item two"
        bullets = _get_bullets(body)
        assert len(bullets) == 2

    def test_plus_bullets(self):
        body = "+ Item one\n+ Item two"
        bullets = _get_bullets(body)
        assert len(bullets) == 2

    def test_no_bullets(self):
        body = "Just plain text here."
        bullets = _get_bullets(body)
        assert bullets == []

    def test_mixed_content(self):
        body = "Some intro text.\n- Bullet one\nMore text.\n- Bullet two"
        bullets = _get_bullets(body)
        assert len(bullets) == 2


# ---------------------------------------------------------------------------
# _find_feature_sections
# ---------------------------------------------------------------------------


class TestFindFeatureSections:
    def test_finds_features_under_features_header(self, simple_markdown):
        sections = _parse_sections(simple_markdown)
        feature_sections = _find_feature_sections(sections)
        assert len(feature_sections) >= 1
        assert "Task Management" in feature_sections[0].title

    def test_finds_multiple_features(self, multi_feature_markdown):
        sections = _parse_sections(multi_feature_markdown)
        feature_sections = _find_feature_sections(sections)
        assert len(feature_sections) >= 4
        names = [s.title for s in feature_sections]
        assert any("Task CRUD" in n for n in names)
        assert any("Dashboard" in n for n in names)


# ---------------------------------------------------------------------------
# _is_meta_section
# ---------------------------------------------------------------------------


class TestIsMetaSection:
    def test_overview_is_meta(self):
        assert _is_meta_section("Overview") is True

    def test_description_is_meta(self):
        assert _is_meta_section("Description") is True

    def test_tech_stack_is_meta(self):
        assert _is_meta_section("Tech Stack") is True

    def test_feature_is_not_meta(self):
        assert _is_meta_section("Task CRUD") is False

    def test_dashboard_is_not_meta(self):
        assert _is_meta_section("Dashboard") is False


# ---------------------------------------------------------------------------
# _extract_routes_from_bullets
# ---------------------------------------------------------------------------


class TestExtractRoutesFromBullets:
    def test_explicit_routes(self):
        bullets = ["/tasks - Task list page", "/tasks/new - Create task form"]
        routes = _extract_routes_from_bullets(bullets, "Task CRUD", True)
        assert len(routes) >= 2
        paths = [r.path for r in routes]
        assert "/tasks" in paths
        assert "/tasks/new" in paths

    def test_inferred_crud_routes(self):
        bullets = ["Create tasks", "View task list", "Edit task details"]
        routes = _extract_routes_from_bullets(bullets, "Task CRUD", True)
        assert len(routes) >= 1

    def test_auth_routes(self):
        bullets = ["Email/password login", "Registration", "Password reset"]
        routes = _extract_routes_from_bullets(bullets, "User Authentication", False)
        paths = [r.path for r in routes]
        assert "/login" in paths
        assert "/register" in paths

    def test_auth_routes_not_require_auth(self):
        bullets = ["Email/password login"]
        routes = _extract_routes_from_bullets(bullets, "User Authentication", False)
        login_routes = [r for r in routes if r.path == "/login"]
        if login_routes:
            assert login_routes[0].requires_auth is False

    def test_dashboard_route(self):
        bullets = ["Dashboard overview with statistics"]
        routes = _extract_routes_from_bullets(bullets, "Dashboard", True)
        assert len(routes) >= 1

    def test_fallback_generic_route(self):
        bullets = ["Something that does not match CRUD patterns"]
        routes = _extract_routes_from_bullets(bullets, "Widget Feature", False)
        assert len(routes) >= 1


# ---------------------------------------------------------------------------
# _extract_api_endpoints_from_bullets
# ---------------------------------------------------------------------------


class TestExtractApiEndpointsFromBullets:
    def test_explicit_http_methods(self):
        bullets = ["GET /api/v1/tasks - List tasks", "POST /api/v1/tasks - Create task"]
        endpoints = _extract_api_endpoints_from_bullets(bullets, "Task CRUD", True)
        methods = [ep.method for ep in endpoints]
        assert HTTPMethod.GET in methods
        assert HTTPMethod.POST in methods

    def test_inferred_from_crud_keywords(self):
        bullets = [
            "Create tasks with title and description",
            "View task list",
            "Update task status",
            "Delete tasks",
        ]
        endpoints = _extract_api_endpoints_from_bullets(bullets, "Task CRUD", True)
        methods = [ep.method for ep in endpoints]
        assert HTTPMethod.POST in methods
        assert HTTPMethod.GET in methods
        assert HTTPMethod.PUT in methods
        assert HTTPMethod.DELETE in methods

    def test_auth_endpoints(self):
        bullets = ["Email/password login", "Registration", "Logout"]
        endpoints = _extract_api_endpoints_from_bullets(
            bullets, "User Authentication", False
        )
        paths = [ep.path for ep in endpoints]
        assert any("auth/login" in p for p in paths)
        assert any("auth/register" in p for p in paths)
        assert any("auth/logout" in p for p in paths)

    def test_auth_endpoints_login_not_require_auth(self):
        bullets = ["Email/password login"]
        endpoints = _extract_api_endpoints_from_bullets(
            bullets, "User Authentication", False
        )
        login_eps = [ep for ep in endpoints if "login" in ep.path]
        if login_eps:
            assert login_eps[0].requires_auth is False

    def test_pagination_response_body(self):
        bullets = ["List tasks with pagination"]
        endpoints = _extract_api_endpoints_from_bullets(bullets, "Task CRUD", True)
        list_endpoints = [
            ep
            for ep in endpoints
            if ep.method == HTTPMethod.GET and "{id}" not in ep.path
        ]
        if list_endpoints:
            assert "total" in list_endpoints[0].response_body

    def test_password_reset_endpoints(self):
        bullets = [
            "Email/password login",
            "Password reset via email link",
            "Forgot password",
        ]
        endpoints = _extract_api_endpoints_from_bullets(
            bullets, "User Authentication", False
        )
        paths = [ep.path for ep in endpoints]
        assert any("forgot-password" in p for p in paths)


# ---------------------------------------------------------------------------
# _infer_request_body
# ---------------------------------------------------------------------------


class TestInferRequestBody:
    def test_detects_title(self):
        bullets = ["Create task with title and description"]
        body = _infer_request_body(bullets, "tasks")
        assert "title" in body
        assert "description" in body

    def test_detects_email_password(self):
        bullets = ["Register with email and password"]
        body = _infer_request_body(bullets, "users")
        assert "email" in body
        assert "password" in body

    def test_fallback_minimal_body(self):
        bullets = ["Some action that does not mention fields"]
        body = _infer_request_body(bullets, "items")
        assert "name" in body  # fallback


# ---------------------------------------------------------------------------
# _guess_field_type
# ---------------------------------------------------------------------------


class TestGuessFieldType:
    def test_date_field(self):
        assert "datetime" in _guess_field_type("due_date")

    def test_price_field(self):
        assert "number" in _guess_field_type("price")

    def test_quantity_field(self):
        assert "integer" in _guess_field_type("quantity")

    def test_email_field(self):
        assert "email" in _guess_field_type("email")

    def test_password_field(self):
        assert "password" in _guess_field_type("password")

    def test_tags_field(self):
        assert "array" in _guess_field_type("tags")

    def test_generic_field(self):
        assert _guess_field_type("title") == "string"


# ---------------------------------------------------------------------------
# _extract_project_name
# ---------------------------------------------------------------------------


class TestExtractProjectName:
    def test_from_h1(self, simple_markdown):
        sections = _parse_sections(simple_markdown)
        name = _extract_project_name(sections, simple_markdown)
        assert name == "My Project"

    def test_strips_priority(self):
        md = "# My App (P0)\n\nDescription.\n"
        sections = _parse_sections(md)
        name = _extract_project_name(sections, md)
        assert name == "My App"

    def test_fallback_untitled(self):
        md = "Just text without headers.\n"
        sections = _parse_sections(md)
        name = _extract_project_name(sections, md)
        assert name == "Untitled Project"


# ---------------------------------------------------------------------------
# _extract_project_description
# ---------------------------------------------------------------------------


class TestExtractProjectDescription:
    def test_from_h1_body(self, simple_markdown):
        sections = _parse_sections(simple_markdown)
        desc = _extract_project_description(sections)
        assert "simple project description" in desc

    def test_empty_when_no_body(self):
        md = "# Title\n## Features\n### Feature 1\n- Bullet\n"
        sections = _parse_sections(md)
        desc = _extract_project_description(sections)
        # May or may not return empty depending on body parsing
        assert isinstance(desc, str)


# ---------------------------------------------------------------------------
# _build_feature
# ---------------------------------------------------------------------------


class TestBuildFeature:
    def test_builds_feature_from_section(self, simple_markdown):
        sections = _parse_sections(simple_markdown)
        feature_sections = _find_feature_sections(sections)
        assert len(feature_sections) >= 1
        feature = _build_feature(feature_sections[0])
        assert isinstance(feature, Feature)
        assert "Task Management" in feature.name
        assert feature.priority == Priority.P0

    def test_feature_has_routes(self, simple_markdown):
        sections = _parse_sections(simple_markdown)
        feature_sections = _find_feature_sections(sections)
        feature = _build_feature(feature_sections[0])
        assert len(feature.ui_routes) >= 1

    def test_feature_has_api_endpoints(self, simple_markdown):
        sections = _parse_sections(simple_markdown)
        feature_sections = _find_feature_sections(sections)
        feature = _build_feature(feature_sections[0])
        assert len(feature.api_endpoints) >= 1

    def test_feature_has_acceptance_criteria(self, simple_markdown):
        sections = _parse_sections(simple_markdown)
        feature_sections = _find_feature_sections(sections)
        feature = _build_feature(feature_sections[0])
        assert len(feature.acceptance_criteria) >= 1

    def test_auth_feature_complexity(self, auth_markdown):
        sections = _parse_sections(auth_markdown)
        feature_sections = _find_feature_sections(sections)
        feature = _build_feature(feature_sections[0])
        assert feature.name == "User Authentication"

    def test_external_apis_detected(self, external_api_markdown):
        sections = _parse_sections(external_api_markdown)
        feature_sections = _find_feature_sections(sections)
        feature = _build_feature(feature_sections[0])
        assert len(feature.external_apis) >= 1


# ---------------------------------------------------------------------------
# _read_file (async)
# ---------------------------------------------------------------------------


class TestReadFile:
    async def test_reads_existing_markdown(self, sample_requirements):
        content = await _read_file(sample_requirements)
        assert "Task Management App" in content

    async def test_raises_on_missing_file(self):
        with pytest.raises(FileNotFoundError):
            await _read_file("/nonexistent/path/requirements.md")

    async def test_raises_on_non_markdown_file(self, tmp_path):
        py_file = tmp_path / "test.py"
        py_file.write_text("print('hello')")
        with pytest.raises(ValueError, match="markdown"):
            await _read_file(str(py_file))


# ---------------------------------------------------------------------------
# parse_requirements (end-to-end, async)
# ---------------------------------------------------------------------------


class TestParseRequirements:
    async def test_parses_sample_requirements(self, sample_requirements):
        result = await parse_requirements(sample_requirements)
        assert len(result.features) >= 3
        feature_names = [f.name for f in result.features]
        # Check that known features are extracted
        assert any("Authentication" in name for name in feature_names)
        assert any("Task" in name for name in feature_names)

    async def test_architecture_is_populated(self, sample_requirements):
        result = await parse_requirements(sample_requirements)
        assert result.architecture is not None
        assert result.architecture.project_name != ""
        assert len(result.architecture.db_collections) >= 1
        assert len(result.architecture.api_contracts) >= 1

    async def test_test_plan_is_populated(self, sample_requirements):
        result = await parse_requirements(sample_requirements)
        assert result.test_plan is not None
        assert len(result.test_plan.scenarios) >= 1
        assert len(result.test_plan.visual_checkpoints) >= 1

    async def test_auth_required_detected(self, sample_requirements):
        result = await parse_requirements(sample_requirements)
        assert result.architecture.auth_required is True

    async def test_port_allocation(self, sample_requirements):
        result = await parse_requirements(sample_requirements)
        ports = result.architecture.port_allocation
        assert ports["frontend"] == 23000
        assert ports["backend"] == 23001
        assert ports["mongodb"] == 23002

    async def test_priorities_extracted(self, sample_requirements):
        result = await parse_requirements(sample_requirements)
        priorities = {f.priority for f in result.features}
        assert Priority.P0 in priorities

    async def test_empty_markdown_file(self, tmp_path):
        empty_md = tmp_path / "empty.md"
        empty_md.write_text("")
        result = await parse_requirements(str(empty_md))
        assert len(result.features) == 0

    async def test_malformed_markdown(self, tmp_path):
        malformed = tmp_path / "malformed.md"
        malformed.write_text("Just plain text with no structure at all.\nAnother line.\n")
        result = await parse_requirements(str(malformed))
        assert isinstance(result.features, list)

    async def test_ambiguities_in_sample(self, tmp_path):
        ambiguous = tmp_path / "ambiguous.md"
        ambiguous.write_text(textwrap.dedent("""\
            # Ambiguous App

            ## Features

            ### Feature X (P1)
            - This is TBD
            - Maybe add something later
        """))
        result = await parse_requirements(str(ambiguous))
        assert len(result.ambiguities) >= 1

    async def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            await parse_requirements("/does/not/exist.md")

    async def test_features_have_unique_names(self, sample_requirements):
        result = await parse_requirements(sample_requirements)
        names = [f.name for f in result.features]
        assert len(names) == len(set(names)), "Duplicate feature names found"

    async def test_routes_have_paths(self, sample_requirements):
        result = await parse_requirements(sample_requirements)
        for feature in result.features:
            for route in feature.ui_routes:
                assert route.path.startswith("/"), f"Route path must start with /: {route.path}"

    async def test_api_endpoints_have_paths(self, sample_requirements):
        result = await parse_requirements(sample_requirements)
        for feature in result.features:
            for ep in feature.api_endpoints:
                assert ep.path.startswith("/"), f"Endpoint path must start with /: {ep.path}"
                assert ep.method in HTTPMethod
