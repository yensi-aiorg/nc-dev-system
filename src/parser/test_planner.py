"""Test plan generator for the NC Dev System.

Takes parsed features and architecture to produce a comprehensive TestPlan
containing unit test scenarios, integration tests, E2E scenarios, visual
checkpoints, and mock requirements.
"""

from __future__ import annotations

from .models import (
    APIEndpoint,
    Architecture,
    Feature,
    HTTPMethod,
    TestPlan,
    TestScenario,
    TestType,
    Viewport,
    VisualCheckpoint,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    """Convert text to a test-friendly slug."""
    import re
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower().strip())
    return slug.strip("_")


def _singular(word: str) -> str:
    """Naive singularization for test naming."""
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("ses") or word.endswith("xes") or word.endswith("zes"):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


# ---------------------------------------------------------------------------
# Unit test scenario generators
# ---------------------------------------------------------------------------

def _generate_service_unit_tests(feature: Feature) -> list[TestScenario]:
    """Generate unit test scenarios for the service layer of a feature."""
    scenarios: list[TestScenario] = []
    slug = _slugify(feature.name)

    for endpoint in feature.api_endpoints:
        method = endpoint.method
        path = endpoint.path

        if method == HTTPMethod.POST:
            scenarios.append(TestScenario(
                name=f"test_{slug}_service_create_success",
                description=f"Service creates a new record via {method.value} {path}",
                steps=[
                    "Prepare valid input data with all required fields",
                    "Call service.create() with the input data",
                    "Assert the returned object has an 'id' field",
                    "Assert all input fields are present in the returned object",
                    "Assert 'created_at' timestamp is set",
                ],
                expected_result="A new record is created and returned with an assigned ID",
                feature=feature.name,
                type=TestType.UNIT,
            ))
            scenarios.append(TestScenario(
                name=f"test_{slug}_service_create_validation_error",
                description=f"Service rejects invalid data for {method.value} {path}",
                steps=[
                    "Prepare input data with missing required fields",
                    "Call service.create() with the invalid data",
                    "Assert a validation error is raised",
                ],
                expected_result="A validation error is raised with descriptive message",
                feature=feature.name,
                type=TestType.UNIT,
            ))

        elif method == HTTPMethod.GET and "{id}" in path:
            scenarios.append(TestScenario(
                name=f"test_{slug}_service_get_by_id_success",
                description=f"Service retrieves a record by ID via {method.value} {path}",
                steps=[
                    "Create a test record in the mock database",
                    "Call service.get_by_id() with the record's ID",
                    "Assert the returned object matches the inserted record",
                ],
                expected_result="The correct record is returned",
                feature=feature.name,
                type=TestType.UNIT,
            ))
            scenarios.append(TestScenario(
                name=f"test_{slug}_service_get_by_id_not_found",
                description=f"Service returns None for non-existent ID via {method.value} {path}",
                steps=[
                    "Call service.get_by_id() with a non-existent ID",
                    "Assert the result is None or a NotFoundException is raised",
                ],
                expected_result="None is returned or NotFoundException is raised",
                feature=feature.name,
                type=TestType.UNIT,
            ))

        elif method == HTTPMethod.GET and "{id}" not in path:
            scenarios.append(TestScenario(
                name=f"test_{slug}_service_list_success",
                description=f"Service lists records via {method.value} {path}",
                steps=[
                    "Insert multiple test records into the mock database",
                    "Call service.get_all() with default pagination",
                    "Assert the returned list contains the expected records",
                    "Assert total count matches",
                ],
                expected_result="All matching records are returned with correct pagination",
                feature=feature.name,
                type=TestType.UNIT,
            ))
            scenarios.append(TestScenario(
                name=f"test_{slug}_service_list_empty",
                description=f"Service returns empty list when no records exist",
                steps=[
                    "Ensure the mock database collection is empty",
                    "Call service.get_all()",
                    "Assert the returned list is empty",
                    "Assert total count is 0",
                ],
                expected_result="An empty list is returned with total count of 0",
                feature=feature.name,
                type=TestType.UNIT,
            ))
            scenarios.append(TestScenario(
                name=f"test_{slug}_service_list_pagination",
                description=f"Service correctly paginates results",
                steps=[
                    "Insert 15 test records into the mock database",
                    "Call service.get_all(skip=0, limit=5)",
                    "Assert exactly 5 records are returned",
                    "Call service.get_all(skip=10, limit=5)",
                    "Assert exactly 5 records are returned",
                    "Assert no overlap between the two pages",
                ],
                expected_result="Records are correctly paginated",
                feature=feature.name,
                type=TestType.UNIT,
            ))

        elif method == HTTPMethod.PUT:
            scenarios.append(TestScenario(
                name=f"test_{slug}_service_update_success",
                description=f"Service updates a record via {method.value} {path}",
                steps=[
                    "Create a test record in the mock database",
                    "Prepare update data with modified fields",
                    "Call service.update() with the record's ID and update data",
                    "Assert the returned object reflects the changes",
                    "Assert 'updated_at' timestamp changed",
                ],
                expected_result="The record is updated and the new state is returned",
                feature=feature.name,
                type=TestType.UNIT,
            ))
            scenarios.append(TestScenario(
                name=f"test_{slug}_service_update_not_found",
                description=f"Service handles update of non-existent record",
                steps=[
                    "Call service.update() with a non-existent ID",
                    "Assert None is returned or NotFoundException is raised",
                ],
                expected_result="None is returned or NotFoundException is raised",
                feature=feature.name,
                type=TestType.UNIT,
            ))

        elif method == HTTPMethod.DELETE:
            scenarios.append(TestScenario(
                name=f"test_{slug}_service_delete_success",
                description=f"Service deletes a record via {method.value} {path}",
                steps=[
                    "Create a test record in the mock database",
                    "Call service.delete() with the record's ID",
                    "Assert the operation returns True",
                    "Verify the record is no longer retrievable (or is soft-deleted)",
                ],
                expected_result="The record is deleted (or soft-deleted) successfully",
                feature=feature.name,
                type=TestType.UNIT,
            ))
            scenarios.append(TestScenario(
                name=f"test_{slug}_service_delete_not_found",
                description=f"Service handles deletion of non-existent record",
                steps=[
                    "Call service.delete() with a non-existent ID",
                    "Assert the operation returns False or NotFoundException is raised",
                ],
                expected_result="False is returned or NotFoundException is raised",
                feature=feature.name,
                type=TestType.UNIT,
            ))

        elif method == HTTPMethod.PATCH:
            scenarios.append(TestScenario(
                name=f"test_{slug}_service_patch_success",
                description=f"Service partially updates a record via {method.value} {path}",
                steps=[
                    "Create a test record in the mock database",
                    "Prepare partial update data",
                    "Call service.update() with only the changed fields",
                    "Assert only the specified fields are changed",
                    "Assert other fields remain unchanged",
                ],
                expected_result="Only the specified fields are updated",
                feature=feature.name,
                type=TestType.UNIT,
            ))

    return scenarios


# ---------------------------------------------------------------------------
# Integration test scenario generators
# ---------------------------------------------------------------------------

def _generate_api_integration_tests(feature: Feature) -> list[TestScenario]:
    """Generate integration test scenarios for API endpoints."""
    scenarios: list[TestScenario] = []
    slug = _slugify(feature.name)

    for endpoint in feature.api_endpoints:
        method = endpoint.method
        path = endpoint.path

        # Happy path test
        scenarios.append(TestScenario(
            name=f"test_{slug}_api_{method.value.lower()}_{_slugify(path)}_success",
            description=f"API endpoint {method.value} {path} returns expected response",
            steps=[
                f"Send {method.value} request to {path}" + (
                    " with valid request body" if endpoint.request_body else ""
                ),
                *(["Include valid auth token in request headers"] if endpoint.requires_auth else []),
                f"Assert response status is {_expected_status_code(method)}",
                "Assert response body matches expected schema",
                "Assert Content-Type is application/json",
            ],
            expected_result=f"{method.value} {path} returns {_expected_status_code(method)} with correct body",
            feature=feature.name,
            type=TestType.INTEGRATION,
        ))

        # Auth failure test (if endpoint requires auth)
        if endpoint.requires_auth:
            scenarios.append(TestScenario(
                name=f"test_{slug}_api_{method.value.lower()}_{_slugify(path)}_unauthorized",
                description=f"API endpoint {method.value} {path} rejects unauthenticated requests",
                steps=[
                    f"Send {method.value} request to {path} without auth token",
                    "Assert response status is 401",
                    "Assert response body contains error message",
                ],
                expected_result="Request is rejected with 401 Unauthorized",
                feature=feature.name,
                type=TestType.INTEGRATION,
            ))

        # Validation failure test (if endpoint has a request body)
        if endpoint.request_body and method in (HTTPMethod.POST, HTTPMethod.PUT, HTTPMethod.PATCH):
            scenarios.append(TestScenario(
                name=f"test_{slug}_api_{method.value.lower()}_{_slugify(path)}_validation",
                description=f"API endpoint {method.value} {path} validates request body",
                steps=[
                    f"Send {method.value} request to {path} with invalid/empty body",
                    *(["Include valid auth token in request headers"] if endpoint.requires_auth else []),
                    "Assert response status is 422",
                    "Assert response body contains validation error details",
                ],
                expected_result="Request is rejected with 422 Unprocessable Entity and validation errors",
                feature=feature.name,
                type=TestType.INTEGRATION,
            ))

    return scenarios


def _expected_status_code(method: HTTPMethod) -> int:
    """Return the expected HTTP status code for a successful operation."""
    return {
        HTTPMethod.GET: 200,
        HTTPMethod.POST: 201,
        HTTPMethod.PUT: 200,
        HTTPMethod.DELETE: 200,
        HTTPMethod.PATCH: 200,
    }.get(method, 200)


# ---------------------------------------------------------------------------
# E2E test scenario generators
# ---------------------------------------------------------------------------

def _generate_e2e_scenarios(feature: Feature) -> list[TestScenario]:
    """Generate Playwright E2E test scenarios for each UI route."""
    scenarios: list[TestScenario] = []
    slug = _slugify(feature.name)

    for route in feature.ui_routes:
        route_slug = _slugify(route.path)

        # Navigation test
        scenarios.append(TestScenario(
            name=f"test_e2e_{slug}_navigate_to_{route_slug}",
            description=f"User can navigate to {route.path} ({route.name})",
            steps=[
                *(
                    ["Log in with valid test credentials"]
                    if route.requires_auth
                    else []
                ),
                f"Navigate to {route.path}",
                "Wait for page to fully load",
                f"Assert page title or heading contains '{route.name}'",
                "Assert no console errors are present",
                "Assert page is accessible (no critical a11y violations)",
            ],
            expected_result=f"Page at {route.path} loads successfully with correct content",
            feature=feature.name,
            type=TestType.E2E,
        ))

    # Feature-specific workflow tests based on acceptance criteria
    if feature.acceptance_criteria:
        workflow_steps: list[str] = []
        for criterion in feature.acceptance_criteria[:5]:  # Limit to avoid overly large tests
            workflow_steps.append(f"Verify: {criterion}")

        scenarios.append(TestScenario(
            name=f"test_e2e_{slug}_complete_workflow",
            description=f"Complete user workflow for {feature.name}",
            steps=[
                *(
                    ["Log in with valid test credentials"]
                    if any(r.requires_auth for r in feature.ui_routes)
                    else []
                ),
                f"Navigate to the primary {feature.name} page",
                *workflow_steps,
                "Assert all operations completed successfully",
                "Verify data persistence by refreshing the page",
            ],
            expected_result=f"Complete {feature.name} workflow executes without errors",
            feature=feature.name,
            type=TestType.E2E,
        ))

    # CRUD workflow test if applicable
    has_create = any(ep.method == HTTPMethod.POST for ep in feature.api_endpoints)
    has_read = any(ep.method == HTTPMethod.GET for ep in feature.api_endpoints)
    has_update = any(ep.method in (HTTPMethod.PUT, HTTPMethod.PATCH) for ep in feature.api_endpoints)
    has_delete = any(ep.method == HTTPMethod.DELETE for ep in feature.api_endpoints)

    if has_create and has_read:
        crud_steps = [
            *(
                ["Log in with valid test credentials"]
                if any(r.requires_auth for r in feature.ui_routes)
                else []
            ),
        ]
        if has_create:
            crud_steps.extend([
                "Navigate to the create form",
                "Fill in all required fields with valid test data",
                "Submit the form",
                "Assert success notification is shown",
            ])
        if has_read:
            crud_steps.extend([
                "Navigate to the list view",
                "Assert the newly created item appears in the list",
                "Click on the item to view details",
                "Assert all fields are displayed correctly",
            ])
        if has_update:
            crud_steps.extend([
                "Click the edit button",
                "Modify one or more fields",
                "Save changes",
                "Assert the updated values are displayed",
            ])
        if has_delete:
            crud_steps.extend([
                "Click the delete button",
                "Confirm deletion in the confirmation dialog",
                "Assert the item is removed from the list",
            ])

        scenarios.append(TestScenario(
            name=f"test_e2e_{slug}_crud_workflow",
            description=f"Full CRUD lifecycle for {feature.name}",
            steps=crud_steps,
            expected_result=f"All CRUD operations for {feature.name} work correctly end-to-end",
            feature=feature.name,
            type=TestType.E2E,
        ))

    return scenarios


# ---------------------------------------------------------------------------
# Visual checkpoint generators
# ---------------------------------------------------------------------------

def _generate_visual_checkpoints(feature: Feature) -> list[VisualCheckpoint]:
    """Generate visual checkpoints for each route at both desktop and mobile viewports."""
    checkpoints: list[VisualCheckpoint] = []

    for route in feature.ui_routes:
        # Desktop checkpoint (1440x900)
        checkpoints.append(VisualCheckpoint(
            route=route.path,
            viewport=Viewport.DESKTOP,
            description=f"Desktop view of {route.name} at {route.path}",
            elements_to_check=_infer_elements_to_check(route.name, route.description, feature),
        ))
        # Mobile checkpoint (375x812)
        checkpoints.append(VisualCheckpoint(
            route=route.path,
            viewport=Viewport.MOBILE,
            description=f"Mobile view of {route.name} at {route.path}",
            elements_to_check=[
                "Mobile navigation menu/hamburger icon",
                "Content fits within mobile viewport",
                "Touch-friendly interactive elements (min 44px tap targets)",
                *_infer_elements_to_check(route.name, route.description, feature)[:3],
            ],
        ))

    return checkpoints


def _infer_elements_to_check(route_name: str, description: str, feature: Feature) -> list[str]:
    """Infer visual elements to verify on a page."""
    elements: list[str] = []
    lower_name = route_name.lower()
    lower_desc = description.lower()
    combined = lower_name + " " + lower_desc

    # Page header/title
    elements.append(f"Page heading: '{route_name}'")

    # Navigation
    elements.append("Navigation bar/header is visible")

    # Form elements
    if any(kw in combined for kw in ["create", "new", "edit", "register", "login", "form"]):
        elements.append("Form fields are properly labeled and visible")
        elements.append("Submit button is visible and styled correctly")
        if "login" in combined or "register" in combined:
            elements.append("Email/username input field")
            elements.append("Password input field")
        if "register" in combined or "signup" in combined:
            elements.append("Registration form with all required fields")

    # List/table elements
    if any(kw in combined for kw in ["list", "all", "browse", "dashboard"]):
        elements.append("Data table or list container is visible")
        elements.append("Pagination controls are present")

    # Detail elements
    if any(kw in combined for kw in ["detail", "view", "{id}"]):
        elements.append("Detail content area is populated")
        elements.append("Action buttons (edit, delete) are visible")

    # Auth-specific
    if any(kw in combined for kw in ["forgot", "reset", "password"]):
        elements.append("Password reset form is visible")

    # Empty state
    elements.append("Loading state is handled (no infinite spinners)")

    return elements


# ---------------------------------------------------------------------------
# Mock requirement generators
# ---------------------------------------------------------------------------

def _generate_mock_requirements(
    features: list[Feature], architecture: Architecture
) -> list[str]:
    """Identify all APIs and services that need to be mocked for testing."""
    mocks: list[str] = []
    seen: set[str] = set()

    # External APIs need MSW handlers (frontend) and pytest fixtures (backend)
    for api in architecture.external_apis:
        key = api.name.lower()
        if key not in seen:
            mocks.append(
                f"Mock {api.name} API ({api.base_url}) - "
                f"success, error, and empty response variants"
            )
            seen.add(key)

    # Feature external APIs that may not be in architecture yet
    for feature in features:
        for api_name in feature.external_apis:
            key = api_name.lower()
            if key not in seen:
                mocks.append(
                    f"Mock {api_name} API - success, error, and empty response variants"
                )
                seen.add(key)

    # Auth mocking if auth is required
    if architecture.auth_required:
        if "auth" not in seen:
            mocks.append("Mock authentication service (KeyCloak) - valid tokens, expired tokens, invalid tokens")
            mocks.append("Mock user session management - active session, expired session")
            seen.add("auth")

    # Database mocking
    mocks.append("Mock MongoDB collections via pytest fixtures with in-memory data")

    # Frontend API mocking
    mocks.append("MSW (Mock Service Worker) handlers for all backend API endpoints")

    # Feature-specific mocks
    for feature in features:
        criteria_text = " ".join(feature.acceptance_criteria).lower()
        if "email" in criteria_text or "notification" in criteria_text:
            if "email" not in seen:
                mocks.append("Mock email/notification service - delivery success and failure scenarios")
                seen.add("email")
        if "upload" in criteria_text or "file" in criteria_text:
            if "file_upload" not in seen:
                mocks.append("Mock file upload service - successful uploads, size limit errors, type validation errors")
                seen.add("file_upload")
        if "payment" in criteria_text or "billing" in criteria_text:
            if "payment" not in seen:
                mocks.append("Mock payment processing - successful charges, declined cards, refunds")
                seen.add("payment")
        if "search" in criteria_text:
            if "search" not in seen:
                mocks.append("Mock search service - results, no results, search error scenarios")
                seen.add("search")
        if "websocket" in criteria_text or "real-time" in criteria_text or "realtime" in criteria_text:
            if "websocket" not in seen:
                mocks.append("Mock WebSocket connections - connection, message, disconnect, error scenarios")
                seen.add("websocket")

    return mocks


# ---------------------------------------------------------------------------
# Health endpoint tests
# ---------------------------------------------------------------------------

def _generate_health_tests() -> list[TestScenario]:
    """Generate test scenarios for the mandatory health endpoints."""
    return [
        TestScenario(
            name="test_health_endpoint_returns_ok",
            description="Health endpoint returns status ok",
            steps=[
                "Send GET request to /api/v1/health",
                "Assert response status is 200",
                "Assert response body contains 'status': 'ok'",
            ],
            expected_result="Health endpoint returns 200 with status ok",
            feature="Health Check",
            type=TestType.INTEGRATION,
        ),
        TestScenario(
            name="test_readiness_endpoint_returns_ok",
            description="Readiness endpoint verifies database connectivity",
            steps=[
                "Ensure test database is running",
                "Send GET request to /api/v1/health/ready",
                "Assert response status is 200",
                "Assert response body contains 'database': 'connected'",
            ],
            expected_result="Readiness endpoint returns 200 with database connected",
            feature="Health Check",
            type=TestType.INTEGRATION,
        ),
        TestScenario(
            name="test_readiness_endpoint_fails_when_db_down",
            description="Readiness endpoint reports failure when database is unreachable",
            steps=[
                "Configure test to use an unreachable database connection string",
                "Send GET request to /api/v1/health/ready",
                "Assert response status is 503",
                "Assert response body indicates database is disconnected",
            ],
            expected_result="Readiness endpoint returns 503 when database is down",
            feature="Health Check",
            type=TestType.INTEGRATION,
        ),
    ]


# ---------------------------------------------------------------------------
# Auth tests
# ---------------------------------------------------------------------------

def _generate_auth_tests() -> list[TestScenario]:
    """Generate test scenarios specific to authentication flows."""
    return [
        TestScenario(
            name="test_e2e_login_valid_credentials",
            description="User can log in with valid credentials",
            steps=[
                "Navigate to /login",
                "Enter valid email address",
                "Enter valid password",
                "Click the login button",
                "Assert redirect to dashboard/home",
                "Assert user name is displayed in the header",
            ],
            expected_result="User is logged in and redirected to the home page",
            feature="User Authentication",
            type=TestType.E2E,
        ),
        TestScenario(
            name="test_e2e_login_invalid_credentials",
            description="Login fails with invalid credentials",
            steps=[
                "Navigate to /login",
                "Enter invalid email or password",
                "Click the login button",
                "Assert an error message is displayed",
                "Assert user remains on the login page",
            ],
            expected_result="Login fails with clear error message",
            feature="User Authentication",
            type=TestType.E2E,
        ),
        TestScenario(
            name="test_e2e_registration_flow",
            description="New user can register an account",
            steps=[
                "Navigate to /register",
                "Fill in name, email, and password fields",
                "Submit the registration form",
                "Assert success message or redirect to login/home",
            ],
            expected_result="New account is created successfully",
            feature="User Authentication",
            type=TestType.E2E,
        ),
        TestScenario(
            name="test_e2e_logout_flow",
            description="Logged-in user can log out",
            steps=[
                "Log in with valid credentials",
                "Click the logout button/link",
                "Assert redirect to the login page",
                "Attempt to access a protected route",
                "Assert redirect back to login",
            ],
            expected_result="User is logged out and cannot access protected routes",
            feature="User Authentication",
            type=TestType.E2E,
        ),
        TestScenario(
            name="test_api_auth_token_refresh",
            description="Expired token triggers automatic refresh",
            steps=[
                "Authenticate and obtain access token",
                "Wait for token to approach expiry (or mock expiry)",
                "Send a request to a protected endpoint",
                "Assert the token is refreshed transparently",
                "Assert the original request succeeds",
            ],
            expected_result="Expired tokens are automatically refreshed without user intervention",
            feature="User Authentication",
            type=TestType.INTEGRATION,
        ),
    ]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def generate_test_plan(
    features: list[Feature],
    architecture: Architecture,
) -> TestPlan:
    """Generate a comprehensive test plan from features and architecture.

    This function produces:
    - Unit test scenarios for each service/feature
    - Integration test scenarios for API endpoints
    - E2E test scenarios for user workflows
    - Visual checkpoints for all routes (desktop + mobile)
    - Mock requirements for external dependencies

    Args:
        features: List of parsed Feature models.
        architecture: The generated Architecture model.

    Returns:
        A TestPlan with all scenarios, checkpoints, and mock requirements.
    """
    all_scenarios: list[TestScenario] = []
    all_checkpoints: list[VisualCheckpoint] = []

    # Health endpoint tests (always included)
    all_scenarios.extend(_generate_health_tests())

    # Auth-specific tests
    if architecture.auth_required:
        all_scenarios.extend(_generate_auth_tests())

    # Per-feature tests
    for feature in features:
        # Unit tests for service layer
        unit_scenarios = _generate_service_unit_tests(feature)
        all_scenarios.extend(unit_scenarios)

        # Integration tests for API endpoints
        integration_scenarios = _generate_api_integration_tests(feature)
        all_scenarios.extend(integration_scenarios)

        # E2E tests for user workflows
        e2e_scenarios = _generate_e2e_scenarios(feature)
        all_scenarios.extend(e2e_scenarios)

        # Visual checkpoints for routes
        checkpoints = _generate_visual_checkpoints(feature)
        all_checkpoints.extend(checkpoints)

    # Mock requirements
    mock_requirements = _generate_mock_requirements(features, architecture)

    # Add visual checkpoint for the home page if not already covered
    home_routes = {cp.route for cp in all_checkpoints}
    if "/" not in home_routes and "/home" not in home_routes:
        all_checkpoints.insert(0, VisualCheckpoint(
            route="/",
            viewport=Viewport.DESKTOP,
            description="Home page desktop view",
            elements_to_check=["Navigation bar", "Main content area", "Footer"],
        ))
        all_checkpoints.insert(1, VisualCheckpoint(
            route="/",
            viewport=Viewport.MOBILE,
            description="Home page mobile view",
            elements_to_check=[
                "Mobile navigation menu/hamburger icon",
                "Content fits within mobile viewport",
                "Touch-friendly interactive elements",
            ],
        ))

    return TestPlan(
        scenarios=all_scenarios,
        visual_checkpoints=all_checkpoints,
        mock_requirements=mock_requirements,
    )
