"""Tests for the test plan generator module.

Covers:
- E2E scenario creation from features
- Visual checkpoint creation for routes (desktop + mobile)
- Mock requirement identification
- Unit/integration test scenario generation
- Health endpoint test generation
- Auth test generation
"""

from __future__ import annotations

from typing import Any

import pytest

from src.parser.models import (
    APIEndpoint,
    Architecture,
    Feature,
    HTTPMethod,
    Priority,
    Route,
    TestPlan,
    TestScenario,
    TestType,
    Viewport,
    VisualCheckpoint,
)
from src.parser.test_planner import (
    _expected_status_code,
    _generate_api_integration_tests,
    _generate_auth_tests,
    _generate_e2e_scenarios,
    _generate_health_tests,
    _generate_mock_requirements,
    _generate_service_unit_tests,
    _generate_visual_checkpoints,
    generate_test_plan,
)


# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def task_feature() -> Feature:
    """A Task CRUD feature with endpoints and routes."""
    return Feature(
        name="Task CRUD",
        description="Manage tasks.",
        priority=Priority.P0,
        ui_routes=[
            Route(path="/tasks", name="Task List", requires_auth=True),
            Route(path="/tasks/new", name="Create Task", requires_auth=True),
            Route(path="/tasks/{id}", name="Task Detail", requires_auth=True),
        ],
        api_endpoints=[
            APIEndpoint(
                method=HTTPMethod.GET,
                path="/api/v1/tasks",
                description="List tasks",
                response_body={"items": [], "total": "int"},
                requires_auth=True,
            ),
            APIEndpoint(
                method=HTTPMethod.POST,
                path="/api/v1/tasks",
                description="Create task",
                request_body={"title": "string", "description": "string"},
                response_body={"id": "string"},
                requires_auth=True,
            ),
            APIEndpoint(
                method=HTTPMethod.GET,
                path="/api/v1/tasks/{id}",
                description="Get task",
                response_body={"id": "string"},
                requires_auth=True,
            ),
            APIEndpoint(
                method=HTTPMethod.PUT,
                path="/api/v1/tasks/{id}",
                description="Update task",
                request_body={"title": "string"},
                response_body={"id": "string"},
                requires_auth=True,
            ),
            APIEndpoint(
                method=HTTPMethod.DELETE,
                path="/api/v1/tasks/{id}",
                description="Delete task",
                response_body={"deleted": "bool"},
                requires_auth=True,
            ),
        ],
        acceptance_criteria=[
            "Create tasks with title and description",
            "View task list with pagination",
            "Delete tasks",
        ],
    )


@pytest.fixture
def auth_feature() -> Feature:
    """An authentication feature."""
    return Feature(
        name="User Authentication",
        description="Login and registration.",
        priority=Priority.P0,
        ui_routes=[
            Route(path="/login", name="Login", requires_auth=False),
            Route(path="/register", name="Register", requires_auth=False),
        ],
        api_endpoints=[
            APIEndpoint(
                method=HTTPMethod.POST,
                path="/api/v1/auth/login",
                description="Login",
                request_body={"email": "string", "password": "string"},
                response_body={"access_token": "string"},
                requires_auth=False,
            ),
            APIEndpoint(
                method=HTTPMethod.POST,
                path="/api/v1/auth/register",
                description="Register",
                request_body={"email": "string", "password": "string", "name": "string"},
                response_body={"id": "string"},
                requires_auth=False,
            ),
        ],
        acceptance_criteria=["Email/password login", "Registration"],
    )


@pytest.fixture
def stripe_feature() -> Feature:
    """Feature with external API dependency."""
    return Feature(
        name="Payments",
        description="Process payments.",
        priority=Priority.P0,
        external_apis=["stripe"],
        api_endpoints=[
            APIEndpoint(
                method=HTTPMethod.POST,
                path="/api/v1/payments",
                description="Create payment",
                request_body={"amount": "number"},
                response_body={"id": "string"},
                requires_auth=True,
            ),
        ],
        ui_routes=[Route(path="/payments", name="Payments", requires_auth=True)],
        acceptance_criteria=["Process payments via Stripe"],
    )


@pytest.fixture
def patch_feature() -> Feature:
    """Feature with a PATCH endpoint."""
    return Feature(
        name="Task Archival",
        description="Archive tasks.",
        priority=Priority.P1,
        api_endpoints=[
            APIEndpoint(
                method=HTTPMethod.PATCH,
                path="/api/v1/tasks/{id}",
                description="Patch task",
                request_body={"archived": "bool"},
                response_body={"id": "string"},
                requires_auth=True,
            ),
        ],
        ui_routes=[],
        acceptance_criteria=["Archive completed tasks"],
    )


@pytest.fixture
def basic_architecture(task_feature, auth_feature) -> Architecture:
    """Minimal architecture for test plan generation."""
    from src.parser.models import ExternalAPI

    return Architecture(
        project_name="Test App",
        features=[task_feature, auth_feature],
        db_collections=[],
        api_contracts=[],
        external_apis=[],
        auth_required=True,
    )


@pytest.fixture
def architecture_with_external(stripe_feature) -> Architecture:
    """Architecture with external API dependencies."""
    from src.parser.models import ExternalAPI

    return Architecture(
        project_name="Payment App",
        features=[stripe_feature],
        db_collections=[],
        api_contracts=[],
        external_apis=[
            ExternalAPI(
                name="Stripe",
                base_url="https://api.stripe.com/v1",
                auth_type="bearer",
            ),
        ],
        auth_required=True,
    )


# ---------------------------------------------------------------------------
# _expected_status_code
# ---------------------------------------------------------------------------


class TestExpectedStatusCode:
    def test_get(self):
        assert _expected_status_code(HTTPMethod.GET) == 200

    def test_post(self):
        assert _expected_status_code(HTTPMethod.POST) == 201

    def test_put(self):
        assert _expected_status_code(HTTPMethod.PUT) == 200

    def test_delete(self):
        assert _expected_status_code(HTTPMethod.DELETE) == 200

    def test_patch(self):
        assert _expected_status_code(HTTPMethod.PATCH) == 200


# ---------------------------------------------------------------------------
# _generate_service_unit_tests
# ---------------------------------------------------------------------------


class TestGenerateServiceUnitTests:
    def test_generates_create_tests(self, task_feature):
        scenarios = _generate_service_unit_tests(task_feature)
        create_tests = [s for s in scenarios if "create" in s.name.lower()]
        assert len(create_tests) >= 2  # success + validation error

    def test_generates_get_by_id_tests(self, task_feature):
        scenarios = _generate_service_unit_tests(task_feature)
        get_tests = [s for s in scenarios if "get_by_id" in s.name.lower()]
        assert len(get_tests) >= 2  # success + not found

    def test_generates_list_tests(self, task_feature):
        scenarios = _generate_service_unit_tests(task_feature)
        list_tests = [s for s in scenarios if "list" in s.name.lower()]
        assert len(list_tests) >= 2  # success + empty + pagination

    def test_generates_update_tests(self, task_feature):
        scenarios = _generate_service_unit_tests(task_feature)
        update_tests = [s for s in scenarios if "update" in s.name.lower()]
        assert len(update_tests) >= 2  # success + not found

    def test_generates_delete_tests(self, task_feature):
        scenarios = _generate_service_unit_tests(task_feature)
        delete_tests = [s for s in scenarios if "delete" in s.name.lower()]
        assert len(delete_tests) >= 2  # success + not found

    def test_generates_patch_tests(self, patch_feature):
        scenarios = _generate_service_unit_tests(patch_feature)
        patch_tests = [s for s in scenarios if "patch" in s.name.lower()]
        assert len(patch_tests) >= 1

    def test_all_are_unit_type(self, task_feature):
        scenarios = _generate_service_unit_tests(task_feature)
        for s in scenarios:
            assert s.type == TestType.UNIT

    def test_all_have_feature_name(self, task_feature):
        scenarios = _generate_service_unit_tests(task_feature)
        for s in scenarios:
            assert s.feature == "Task CRUD"

    def test_all_have_steps(self, task_feature):
        scenarios = _generate_service_unit_tests(task_feature)
        for s in scenarios:
            assert len(s.steps) >= 1

    def test_empty_endpoints(self):
        feature = Feature(name="Empty", description="No endpoints.")
        scenarios = _generate_service_unit_tests(feature)
        assert scenarios == []


# ---------------------------------------------------------------------------
# _generate_api_integration_tests
# ---------------------------------------------------------------------------


class TestGenerateApiIntegrationTests:
    def test_happy_path_for_each_endpoint(self, task_feature):
        scenarios = _generate_api_integration_tests(task_feature)
        success_tests = [s for s in scenarios if "success" in s.name.lower()]
        assert len(success_tests) >= len(task_feature.api_endpoints)

    def test_auth_failure_tests(self, task_feature):
        scenarios = _generate_api_integration_tests(task_feature)
        auth_tests = [s for s in scenarios if "unauthorized" in s.name.lower()]
        # All endpoints in task_feature require auth
        assert len(auth_tests) >= 1

    def test_validation_failure_tests(self, task_feature):
        scenarios = _generate_api_integration_tests(task_feature)
        validation_tests = [s for s in scenarios if "validation" in s.name.lower()]
        # POST and PUT have request bodies
        assert len(validation_tests) >= 1

    def test_all_are_integration_type(self, task_feature):
        scenarios = _generate_api_integration_tests(task_feature)
        for s in scenarios:
            assert s.type == TestType.INTEGRATION

    def test_no_auth_failure_for_public_endpoints(self, auth_feature):
        scenarios = _generate_api_integration_tests(auth_feature)
        # Login and register are public
        auth_tests = [s for s in scenarios if "unauthorized" in s.name.lower()]
        # Logout requires auth, so at least 1 auth test
        auth_ep_count = sum(1 for ep in auth_feature.api_endpoints if ep.requires_auth)
        assert len(auth_tests) == auth_ep_count


# ---------------------------------------------------------------------------
# _generate_e2e_scenarios
# ---------------------------------------------------------------------------


class TestGenerateE2eScenarios:
    def test_navigation_tests_per_route(self, task_feature):
        scenarios = _generate_e2e_scenarios(task_feature)
        nav_tests = [s for s in scenarios if "navigate" in s.name.lower()]
        assert len(nav_tests) >= len(task_feature.ui_routes)

    def test_all_are_e2e_type(self, task_feature):
        scenarios = _generate_e2e_scenarios(task_feature)
        for s in scenarios:
            assert s.type == TestType.E2E

    def test_workflow_test_created(self, task_feature):
        scenarios = _generate_e2e_scenarios(task_feature)
        workflow_tests = [s for s in scenarios if "workflow" in s.name.lower()]
        assert len(workflow_tests) >= 1

    def test_crud_workflow_test(self, task_feature):
        scenarios = _generate_e2e_scenarios(task_feature)
        crud_tests = [s for s in scenarios if "crud" in s.name.lower()]
        assert len(crud_tests) >= 1

    def test_login_step_for_auth_required_routes(self, task_feature):
        scenarios = _generate_e2e_scenarios(task_feature)
        for s in scenarios:
            if "navigate" in s.name.lower():
                # All task_feature routes require auth
                assert any("log in" in step.lower() or "login" in step.lower() for step in s.steps)

    def test_no_login_step_for_public_routes(self, auth_feature):
        scenarios = _generate_e2e_scenarios(auth_feature)
        nav_tests = [s for s in scenarios if "navigate" in s.name.lower()]
        for s in nav_tests:
            # Auth feature routes (/login, /register) don't require auth
            if "login" in s.name.lower() or "register" in s.name.lower():
                # Should NOT have a "log in" prerequisite step
                login_steps = [step for step in s.steps if "log in with valid" in step.lower()]
                assert len(login_steps) == 0

    def test_empty_routes(self):
        feature = Feature(name="No Routes", description="", acceptance_criteria=["Something"])
        scenarios = _generate_e2e_scenarios(feature)
        # Should still generate workflow from acceptance criteria
        assert len(scenarios) >= 1


# ---------------------------------------------------------------------------
# _generate_visual_checkpoints
# ---------------------------------------------------------------------------


class TestGenerateVisualCheckpoints:
    def test_desktop_and_mobile_per_route(self, task_feature):
        checkpoints = _generate_visual_checkpoints(task_feature)
        # Each route should have both desktop and mobile
        route_count = len(task_feature.ui_routes)
        assert len(checkpoints) == route_count * 2

    def test_viewport_types(self, task_feature):
        checkpoints = _generate_visual_checkpoints(task_feature)
        viewports = {cp.viewport for cp in checkpoints}
        assert Viewport.DESKTOP in viewports
        assert Viewport.MOBILE in viewports

    def test_mobile_has_touch_elements(self, task_feature):
        checkpoints = _generate_visual_checkpoints(task_feature)
        mobile_cps = [cp for cp in checkpoints if cp.viewport == Viewport.MOBILE]
        for cp in mobile_cps:
            combined = " ".join(cp.elements_to_check).lower()
            assert "mobile" in combined or "touch" in combined or "tap" in combined

    def test_correct_routes(self, task_feature):
        checkpoints = _generate_visual_checkpoints(task_feature)
        routes = {cp.route for cp in checkpoints}
        assert "/tasks" in routes
        assert "/tasks/new" in routes

    def test_empty_routes_no_checkpoints(self):
        feature = Feature(name="No Routes", description="")
        checkpoints = _generate_visual_checkpoints(feature)
        assert checkpoints == []


# ---------------------------------------------------------------------------
# _generate_mock_requirements
# ---------------------------------------------------------------------------


class TestGenerateMockRequirements:
    def test_includes_mongodb_mock(self, task_feature, basic_architecture):
        mocks = _generate_mock_requirements([task_feature], basic_architecture)
        assert any("mongodb" in m.lower() or "mongo" in m.lower() for m in mocks)

    def test_includes_msw_mock(self, task_feature, basic_architecture):
        mocks = _generate_mock_requirements([task_feature], basic_architecture)
        assert any("msw" in m.lower() for m in mocks)

    def test_includes_auth_mock_when_auth_required(self, task_feature, basic_architecture):
        mocks = _generate_mock_requirements([task_feature], basic_architecture)
        assert any("auth" in m.lower() or "keycloak" in m.lower() for m in mocks)

    def test_includes_external_api_mock(self, stripe_feature, architecture_with_external):
        mocks = _generate_mock_requirements([stripe_feature], architecture_with_external)
        assert any("stripe" in m.lower() for m in mocks)

    def test_email_mock(self):
        feature = Feature(
            name="Notifications",
            description="",
            acceptance_criteria=["Send email notification"],
        )
        arch = Architecture(project_name="Test", auth_required=False)
        mocks = _generate_mock_requirements([feature], arch)
        assert any("email" in m.lower() for m in mocks)

    def test_payment_mock(self):
        feature = Feature(
            name="Billing",
            description="",
            acceptance_criteria=["Process payment via Stripe"],
        )
        arch = Architecture(project_name="Test", auth_required=False)
        mocks = _generate_mock_requirements([feature], arch)
        assert any("payment" in m.lower() for m in mocks)

    def test_search_mock(self):
        feature = Feature(
            name="Search",
            description="",
            acceptance_criteria=["Full-text search across tasks"],
        )
        arch = Architecture(project_name="Test", auth_required=False)
        mocks = _generate_mock_requirements([feature], arch)
        assert any("search" in m.lower() for m in mocks)

    def test_websocket_mock(self):
        feature = Feature(
            name="Realtime",
            description="",
            acceptance_criteria=["Real-time updates via websocket"],
        )
        arch = Architecture(project_name="Test", auth_required=False)
        mocks = _generate_mock_requirements([feature], arch)
        assert any("websocket" in m.lower() for m in mocks)


# ---------------------------------------------------------------------------
# _generate_health_tests
# ---------------------------------------------------------------------------


class TestGenerateHealthTests:
    def test_generates_health_tests(self):
        scenarios = _generate_health_tests()
        assert len(scenarios) == 3

    def test_includes_basic_health(self):
        scenarios = _generate_health_tests()
        names = [s.name for s in scenarios]
        assert "test_health_endpoint_returns_ok" in names

    def test_includes_readiness(self):
        scenarios = _generate_health_tests()
        names = [s.name for s in scenarios]
        assert "test_readiness_endpoint_returns_ok" in names

    def test_includes_db_down(self):
        scenarios = _generate_health_tests()
        names = [s.name for s in scenarios]
        assert "test_readiness_endpoint_fails_when_db_down" in names

    def test_all_integration_type(self):
        scenarios = _generate_health_tests()
        for s in scenarios:
            assert s.type == TestType.INTEGRATION


# ---------------------------------------------------------------------------
# _generate_auth_tests
# ---------------------------------------------------------------------------


class TestGenerateAuthTests:
    def test_generates_auth_tests(self):
        scenarios = _generate_auth_tests()
        assert len(scenarios) >= 4

    def test_includes_login_valid(self):
        scenarios = _generate_auth_tests()
        names = [s.name for s in scenarios]
        assert "test_e2e_login_valid_credentials" in names

    def test_includes_login_invalid(self):
        scenarios = _generate_auth_tests()
        names = [s.name for s in scenarios]
        assert "test_e2e_login_invalid_credentials" in names

    def test_includes_registration(self):
        scenarios = _generate_auth_tests()
        names = [s.name for s in scenarios]
        assert "test_e2e_registration_flow" in names

    def test_includes_logout(self):
        scenarios = _generate_auth_tests()
        names = [s.name for s in scenarios]
        assert "test_e2e_logout_flow" in names


# ---------------------------------------------------------------------------
# generate_test_plan (async, end-to-end)
# ---------------------------------------------------------------------------


class TestGenerateTestPlan:
    async def test_generates_test_plan(self, task_feature, basic_architecture):
        plan = await generate_test_plan(
            features=[task_feature],
            architecture=basic_architecture,
        )
        assert isinstance(plan, TestPlan)

    async def test_includes_health_tests(self, task_feature, basic_architecture):
        plan = await generate_test_plan(
            features=[task_feature],
            architecture=basic_architecture,
        )
        health_tests = [s for s in plan.scenarios if s.feature == "Health Check"]
        assert len(health_tests) >= 3

    async def test_includes_auth_tests_when_auth_required(self, task_feature, basic_architecture):
        plan = await generate_test_plan(
            features=[task_feature],
            architecture=basic_architecture,
        )
        auth_tests = [s for s in plan.scenarios if s.feature == "User Authentication"]
        assert len(auth_tests) >= 4

    async def test_no_auth_tests_when_not_required(self, task_feature):
        arch = Architecture(
            project_name="No Auth",
            features=[task_feature],
            auth_required=False,
        )
        plan = await generate_test_plan(
            features=[task_feature],
            architecture=arch,
        )
        auth_tests = [s for s in plan.scenarios if s.feature == "User Authentication"]
        assert len(auth_tests) == 0

    async def test_includes_unit_tests(self, task_feature, basic_architecture):
        plan = await generate_test_plan(
            features=[task_feature],
            architecture=basic_architecture,
        )
        unit_tests = [s for s in plan.scenarios if s.type == TestType.UNIT]
        assert len(unit_tests) >= 1

    async def test_includes_integration_tests(self, task_feature, basic_architecture):
        plan = await generate_test_plan(
            features=[task_feature],
            architecture=basic_architecture,
        )
        integration_tests = [s for s in plan.scenarios if s.type == TestType.INTEGRATION]
        assert len(integration_tests) >= 1

    async def test_includes_e2e_tests(self, task_feature, basic_architecture):
        plan = await generate_test_plan(
            features=[task_feature],
            architecture=basic_architecture,
        )
        e2e_tests = [s for s in plan.scenarios if s.type == TestType.E2E]
        assert len(e2e_tests) >= 1

    async def test_visual_checkpoints_created(self, task_feature, basic_architecture):
        plan = await generate_test_plan(
            features=[task_feature],
            architecture=basic_architecture,
        )
        assert len(plan.visual_checkpoints) >= 1

    async def test_home_page_checkpoint_added(self, auth_feature):
        arch = Architecture(
            project_name="Auth App",
            features=[auth_feature],
            auth_required=True,
        )
        plan = await generate_test_plan(
            features=[auth_feature],
            architecture=arch,
        )
        # /login and /register don't cover "/" or "/home",
        # so home page checkpoint should be added
        home_cps = [cp for cp in plan.visual_checkpoints if cp.route == "/"]
        assert len(home_cps) >= 1

    async def test_mock_requirements_populated(self, task_feature, basic_architecture):
        plan = await generate_test_plan(
            features=[task_feature],
            architecture=basic_architecture,
        )
        assert len(plan.mock_requirements) >= 1

    async def test_empty_features(self):
        arch = Architecture(project_name="Empty", auth_required=False)
        plan = await generate_test_plan(features=[], architecture=arch)
        # Health tests should still be present
        assert len(plan.scenarios) >= 3

    async def test_all_scenarios_have_names(self, task_feature, basic_architecture):
        plan = await generate_test_plan(
            features=[task_feature],
            architecture=basic_architecture,
        )
        for s in plan.scenarios:
            assert s.name, "Scenario must have a name"
            assert s.feature, "Scenario must have a feature"

    async def test_all_checkpoints_have_routes(self, task_feature, basic_architecture):
        plan = await generate_test_plan(
            features=[task_feature],
            architecture=basic_architecture,
        )
        for cp in plan.visual_checkpoints:
            assert cp.route.startswith("/"), f"Checkpoint route must start with /: {cp.route}"
            assert cp.viewport in (Viewport.DESKTOP, Viewport.MOBILE)
