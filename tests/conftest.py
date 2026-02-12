"""Shared pytest fixtures for the NC Dev System test suite.

Provides reusable fixtures for:
- Temporary project directories
- Sample requirements documents
- Mocked Ollama and Codex responses
- Pre-parsed features, architecture, and test plans
- Mock subprocess helpers
"""

from __future__ import annotations

import asyncio
import json
import shutil
import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Paths & Directories
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_project_dir(tmp_path: Path) -> Path:
    """Temporary directory for generated projects (auto-cleanup)."""
    project_dir = tmp_path / "test-project"
    project_dir.mkdir()
    yield project_dir


@pytest.fixture
def tmp_git_repo(tmp_path: Path) -> Path:
    """Temporary git repository with an initial commit.

    Creates a real git repo in a temp directory so that tests depending on
    git operations (worktrees, branches, etc.) have a valid repo to work in.
    """
    import subprocess

    repo_dir = tmp_path / "test-repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init"], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@nc-dev.local"],
        cwd=repo_dir, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "NC Dev Test"],
        cwd=repo_dir, check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "commit.gpgsign", "false"],
        cwd=repo_dir, check=True, capture_output=True,
    )
    # Create an initial commit so branches can be created
    readme = repo_dir / "README.md"
    readme.write_text("# Test Project\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo_dir, check=True, capture_output=True,
    )
    yield repo_dir


@pytest.fixture
def sample_requirements() -> str:
    """Path to sample requirements.md fixture file."""
    path = Path(__file__).parent / "fixtures" / "sample-requirements.md"
    assert path.exists(), f"Sample requirements fixture not found at {path}"
    return str(path)


@pytest.fixture
def sample_requirements_text() -> str:
    """Raw text content of the sample requirements.md."""
    path = Path(__file__).parent / "fixtures" / "sample-requirements.md"
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Mock Ollama
# ---------------------------------------------------------------------------

def _make_ollama_generate_response(model: str, prompt: str) -> dict[str, Any]:
    """Build a realistic Ollama /api/generate response."""
    return {
        "model": model,
        "created_at": "2026-01-15T10:30:00.000Z",
        "response": json.dumps({
            "summary": "Generated mock response for testing.",
            "items": [
                {"name": "item-1", "description": "First mock item"},
                {"name": "item-2", "description": "Second mock item"},
            ],
        }),
        "done": True,
        "total_duration": 1234567890,
        "load_duration": 123456789,
        "prompt_eval_count": 42,
        "eval_count": 128,
    }


def _make_ollama_vision_response() -> dict[str, Any]:
    """Build a realistic Ollama vision model response."""
    return {
        "model": "qwen2.5vl:7b",
        "created_at": "2026-01-15T10:31:00.000Z",
        "response": json.dumps({
            "description": "The screenshot shows a task management dashboard with a sidebar navigation, a main content area displaying task cards, and a header with user avatar.",
            "issues": [],
            "layout_score": 0.92,
            "accessibility_notes": "Good contrast ratios observed. Navigation elements are clearly labelled.",
        }),
        "done": True,
        "total_duration": 2345678901,
    }


@pytest.fixture
def mock_ollama():
    """Mocked Ollama API responses.

    Patches httpx.AsyncClient to intercept calls to the Ollama API and return
    realistic mock responses for both generate and vision endpoints.

    Usage:
        def test_something(mock_ollama):
            with mock_ollama:
                # Code that calls Ollama will receive mock responses
                ...
    """
    mock_response_generate = MagicMock()
    mock_response_generate.status_code = 200
    mock_response_generate.json.return_value = _make_ollama_generate_response(
        "qwen3-coder:30b", "test prompt"
    )
    mock_response_generate.raise_for_status = MagicMock()

    mock_response_vision = MagicMock()
    mock_response_vision.status_code = 200
    mock_response_vision.json.return_value = _make_ollama_vision_response()
    mock_response_vision.raise_for_status = MagicMock()

    async def mock_post(url: str, **kwargs: Any) -> MagicMock:
        if "generate" in url:
            return mock_response_generate
        if "chat" in url or "vision" in url:
            return mock_response_vision
        return mock_response_generate

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=mock_post)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    return patch("httpx.AsyncClient", return_value=mock_client)


# ---------------------------------------------------------------------------
# Mock Codex CLI
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_codex():
    """Mocked Codex CLI responses.

    Patches asyncio.create_subprocess_exec to intercept codex CLI invocations
    and return realistic success responses.

    Usage:
        def test_builder(mock_codex):
            with mock_codex:
                # Code that spawns codex processes will receive mock results
                ...
    """
    codex_result = json.dumps({
        "status": "success",
        "feature": "test-feature",
        "files_created": [
            "backend/app/api/v1/endpoints/tasks.py",
            "backend/app/services/task_service.py",
            "backend/app/models/task.py",
            "backend/app/schemas/task.py",
            "backend/tests/unit/test_task_service.py",
            "frontend/src/pages/TasksPage.tsx",
            "frontend/src/stores/useTaskStore.ts",
            "frontend/src/components/features/TaskCard.tsx",
        ],
        "files_modified": [
            "backend/app/api/v1/router.py",
            "frontend/src/App.tsx",
        ],
        "tests_run": 24,
        "tests_passed": 24,
        "tests_failed": 0,
        "duration_seconds": 45.2,
    })

    mock_process = AsyncMock()
    mock_process.communicate = AsyncMock(
        return_value=(codex_result.encode("utf-8"), b"")
    )
    mock_process.returncode = 0
    mock_process.pid = 12345
    mock_process.kill = MagicMock()

    async def mock_create_subprocess(*args: Any, **kwargs: Any) -> AsyncMock:
        return mock_process

    return patch(
        "asyncio.create_subprocess_exec",
        side_effect=mock_create_subprocess,
    )


# ---------------------------------------------------------------------------
# Mock Subprocess (generic)
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_subprocess():
    """Mock asyncio subprocess for testing command execution.

    Returns a factory that creates mock subprocess instances with configurable
    stdout, stderr, and return codes.

    Usage:
        def test_command(mock_subprocess):
            proc = mock_subprocess(stdout="output", returncode=0)
            with patch("asyncio.create_subprocess_exec", return_value=proc):
                ...
    """
    def factory(
        stdout: str = "",
        stderr: str = "",
        returncode: int = 0,
    ) -> AsyncMock:
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(
            return_value=(stdout.encode("utf-8"), stderr.encode("utf-8"))
        )
        mock_proc.returncode = returncode
        mock_proc.pid = 99999
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock(return_value=returncode)
        return mock_proc

    return factory


# ---------------------------------------------------------------------------
# Pre-parsed Features
# ---------------------------------------------------------------------------

@pytest.fixture
def parsed_features() -> list[dict[str, Any]]:
    """Pre-parsed features list matching the sample-requirements.md.

    Returns a list of feature dicts as the parser would produce from the
    sample Task Management App requirements. Each feature includes name,
    priority, routes, endpoints, and acceptance criteria.
    """
    return [
        {
            "name": "User Authentication",
            "description": "Email/password registration with validation. Email/password login. Session management with JWT tokens.",
            "priority": "P0",
            "dependencies": [],
            "complexity": "medium",
            "ui_routes": [
                {
                    "path": "/login",
                    "name": "Login page",
                    "description": "/login - Login page",
                    "requires_auth": False,
                },
                {
                    "path": "/register",
                    "name": "Registration page",
                    "description": "/register - Registration page",
                    "requires_auth": False,
                },
                {
                    "path": "/forgot-password",
                    "name": "Password reset request",
                    "description": "/forgot-password - Password reset request",
                    "requires_auth": False,
                },
            ],
            "api_endpoints": [
                {
                    "method": "POST",
                    "path": "/api/v1/auth/register",
                    "description": "Create new account",
                    "request_body": {"email": "string", "password": "string", "name": "string"},
                    "response_body": {"id": "string", "email": "string"},
                    "requires_auth": False,
                },
                {
                    "method": "POST",
                    "path": "/api/v1/auth/login",
                    "description": "Authenticate user",
                    "request_body": {"email": "string", "password": "string"},
                    "response_body": {"access_token": "string", "token_type": "bearer"},
                    "requires_auth": False,
                },
                {
                    "method": "POST",
                    "path": "/api/v1/auth/logout",
                    "description": "End session",
                    "request_body": None,
                    "response_body": {"status": "ok"},
                    "requires_auth": True,
                },
                {
                    "method": "POST",
                    "path": "/api/v1/auth/forgot-password",
                    "description": "Request password reset",
                    "request_body": {"email": "string"},
                    "response_body": {"status": "ok"},
                    "requires_auth": False,
                },
                {
                    "method": "POST",
                    "path": "/api/v1/auth/reset-password",
                    "description": "Reset password with token",
                    "request_body": {"token": "string", "new_password": "string"},
                    "response_body": {"status": "ok"},
                    "requires_auth": False,
                },
            ],
            "external_apis": [],
            "acceptance_criteria": [
                "Email/password registration with validation",
                "Email/password login",
                "Session management with JWT tokens",
                "Password reset via email link",
                "Logout functionality",
            ],
        },
        {
            "name": "Task CRUD",
            "description": "Create tasks with title, description, priority (low/medium/high/urgent), due date. View task list with pagination. View single task details.",
            "priority": "P0",
            "dependencies": [],
            "complexity": "medium",
            "ui_routes": [
                {
                    "path": "/tasks",
                    "name": "Task list page",
                    "description": "/tasks - Task list page",
                    "requires_auth": True,
                },
                {
                    "path": "/tasks/new",
                    "name": "Create task form",
                    "description": "/tasks/new - Create task form",
                    "requires_auth": True,
                },
                {
                    "path": "/tasks/:id",
                    "name": "Task detail/edit page",
                    "description": "/tasks/:id - Task detail/edit page",
                    "requires_auth": True,
                },
            ],
            "api_endpoints": [
                {
                    "method": "GET",
                    "path": "/api/v1/tasks",
                    "description": "List tasks (paginated, filterable)",
                    "request_body": None,
                    "response_body": {"items": [{"id": "string"}], "total": "int", "page": "int", "page_size": "int"},
                    "requires_auth": True,
                },
                {
                    "method": "POST",
                    "path": "/api/v1/tasks",
                    "description": "Create task",
                    "request_body": {"title": "string", "description": "string", "priority": "string", "due_date": "datetime", "status": "string"},
                    "response_body": {"id": "string", "title": "string", "description": "string", "priority": "string", "due_date": "datetime", "status": "string"},
                    "requires_auth": True,
                },
                {
                    "method": "GET",
                    "path": "/api/v1/tasks/:id",
                    "description": "Get task details",
                    "request_body": None,
                    "response_body": {"id": "string"},
                    "requires_auth": True,
                },
                {
                    "method": "PUT",
                    "path": "/api/v1/tasks/:id",
                    "description": "Update task",
                    "request_body": {"title": "string", "description": "string", "priority": "string", "due_date": "datetime", "status": "string"},
                    "response_body": {"id": "string", "title": "string", "description": "string", "priority": "string", "due_date": "datetime", "status": "string"},
                    "requires_auth": True,
                },
                {
                    "method": "DELETE",
                    "path": "/api/v1/tasks/:id",
                    "description": "Soft delete task",
                    "request_body": None,
                    "response_body": {"deleted": "bool"},
                    "requires_auth": True,
                },
            ],
            "external_apis": [],
            "acceptance_criteria": [
                "Create tasks with title, description, priority (low/medium/high/urgent), due date",
                "View task list with pagination",
                "View single task details",
                "Update task properties (title, description, priority, due date, status)",
                "Delete tasks (soft delete - mark as deleted, don't remove from DB)",
                "Task status workflow: todo \u2192 in_progress \u2192 done",
            ],
        },
        {
            "name": "Task Categories",
            "description": "Create and manage categories (name, color, icon). Assign categories to tasks (many-to-many). Filter tasks by category.",
            "priority": "P1",
            "dependencies": [],
            "complexity": "medium",
            "ui_routes": [
                {
                    "path": "/categories",
                    "name": "Category management page",
                    "description": "/categories - Category management page",
                    "requires_auth": True,
                },
            ],
            "api_endpoints": [
                {
                    "method": "GET",
                    "path": "/api/v1/categories",
                    "description": "List categories",
                    "request_body": None,
                    "response_body": {"items": [{"id": "string"}], "total": "int", "page": "int", "page_size": "int"},
                    "requires_auth": True,
                },
                {
                    "method": "POST",
                    "path": "/api/v1/categories",
                    "description": "Create category",
                    "request_body": {"name": "string", "color": "string", "icon": "string"},
                    "response_body": {"id": "string", "name": "string", "color": "string", "icon": "string"},
                    "requires_auth": True,
                },
                {
                    "method": "PUT",
                    "path": "/api/v1/categories/:id",
                    "description": "Update category",
                    "request_body": {"name": "string", "color": "string", "icon": "string"},
                    "response_body": {"id": "string", "name": "string", "color": "string", "icon": "string"},
                    "requires_auth": True,
                },
                {
                    "method": "DELETE",
                    "path": "/api/v1/categories/:id",
                    "description": "Delete category",
                    "request_body": None,
                    "response_body": {"deleted": "bool"},
                    "requires_auth": True,
                },
            ],
            "external_apis": [],
            "acceptance_criteria": [
                "Create and manage categories (name, color, icon)",
                "Assign categories to tasks (many-to-many)",
                "Filter tasks by category",
                "Category management page",
            ],
        },
        {
            "name": "Dashboard",
            "description": "Task statistics overview (total, completed, overdue, by priority). Tasks due today/this week widget. Recent activity feed.",
            "priority": "P1",
            "dependencies": [],
            "complexity": "medium",
            "ui_routes": [
                {
                    "path": "/",
                    "name": "Dashboard (home page)",
                    "description": "/ - Dashboard (home page)",
                    "requires_auth": True,
                },
            ],
            "api_endpoints": [
                {
                    "method": "GET",
                    "path": "/api/v1/dashboard/stats",
                    "description": "Get task statistics",
                    "request_body": None,
                    "response_body": {
                        "total": "int",
                        "completed": "int",
                        "overdue": "int",
                        "by_priority": {"low": "int", "medium": "int", "high": "int", "urgent": "int"},
                    },
                    "requires_auth": True,
                },
                {
                    "method": "GET",
                    "path": "/api/v1/dashboard/recent",
                    "description": "Get recent activity",
                    "request_body": None,
                    "response_body": {"items": [{"action": "string", "task_id": "string", "timestamp": "datetime"}]},
                    "requires_auth": True,
                },
            ],
            "external_apis": [],
            "acceptance_criteria": [
                "Task statistics overview (total, completed, overdue, by priority)",
                "Tasks due today/this week widget",
                "Recent activity feed",
                "Category distribution chart",
            ],
        },
        {
            "name": "Search & Filter",
            "description": "Full-text search across task titles and descriptions. Filter by status (todo, in_progress, done). Filter by priority (low, medium, high, urgent).",
            "priority": "P1",
            "dependencies": [],
            "complexity": "medium",
            "ui_routes": [],
            "api_endpoints": [
                {
                    "method": "GET",
                    "path": "/api/v1/tasks/search",
                    "description": "Search tasks",
                    "request_body": None,
                    "response_body": {"items": [{"id": "string"}], "total": "int", "page": "int", "page_size": "int"},
                    "requires_auth": True,
                },
            ],
            "external_apis": [],
            "acceptance_criteria": [
                "Full-text search across task titles and descriptions",
                "Filter by status (todo, in_progress, done)",
                "Filter by priority (low, medium, high, urgent)",
                "Filter by category",
                "Filter by due date range",
                "Sort by created date, due date, priority",
            ],
        },
        {
            "name": "Responsive Design",
            "description": "Mobile-first responsive layout. Touch-friendly task interactions. Collapsible sidebar on mobile.",
            "priority": "P2",
            "dependencies": [],
            "complexity": "medium",
            "ui_routes": [],
            "api_endpoints": [],
            "external_apis": [],
            "acceptance_criteria": [
                "Mobile-first responsive layout",
                "Touch-friendly task interactions",
                "Collapsible sidebar on mobile",
                "Bottom navigation on mobile",
            ],
        },
    ]


# ---------------------------------------------------------------------------
# Pre-parsed Architecture
# ---------------------------------------------------------------------------

@pytest.fixture
def parsed_architecture() -> dict[str, Any]:
    """Pre-parsed architecture dict matching the sample-requirements.md.

    Returns an Architecture-like dict as generate_architecture() would produce
    for the Task Management App. Includes project metadata, DB collections,
    API contracts, port allocations, and auth requirements.
    """
    return {
        "project_name": "Task Management App",
        "description": (
            "A web application for managing personal and team tasks with "
            "priorities, categories, and due dates. Users can create, organize, "
            "and track their tasks through an intuitive dashboard."
        ),
        "features": [],  # Populated separately via parsed_features
        "db_collections": [
            {
                "name": "users",
                "fields": [
                    {"name": "_id", "type": "ObjectId", "required": True, "description": "Primary key"},
                    {"name": "email", "type": "string", "required": True, "description": "User email (unique)"},
                    {"name": "password_hash", "type": "string", "required": True, "description": "Bcrypt hashed password"},
                    {"name": "name", "type": "string", "required": True, "description": "Display name"},
                    {"name": "created_at", "type": "datetime", "required": True, "description": "Account creation timestamp"},
                    {"name": "updated_at", "type": "datetime", "required": True, "description": "Last update timestamp"},
                ],
                "indexes": [
                    {"fields": ["email"], "unique": True},
                ],
            },
            {
                "name": "tasks",
                "fields": [
                    {"name": "_id", "type": "ObjectId", "required": True, "description": "Primary key"},
                    {"name": "title", "type": "string", "required": True, "description": "Task title"},
                    {"name": "description", "type": "string", "required": False, "description": "Task description"},
                    {"name": "status", "type": "string", "required": True, "description": "Enum: todo, in_progress, done"},
                    {"name": "priority", "type": "string", "required": True, "description": "Enum: low, medium, high, urgent"},
                    {"name": "due_date", "type": "datetime", "required": False, "description": "Task due date"},
                    {"name": "category_ids", "type": "ObjectId[]", "required": False, "description": "References to categories"},
                    {"name": "user_id", "type": "ObjectId", "required": True, "description": "Owner user reference"},
                    {"name": "is_deleted", "type": "boolean", "required": True, "description": "Soft delete flag", "default": False},
                    {"name": "created_at", "type": "datetime", "required": True, "description": "Creation timestamp"},
                    {"name": "updated_at", "type": "datetime", "required": True, "description": "Last update timestamp"},
                ],
                "indexes": [
                    {"fields": ["title"], "unique": False},
                    {"fields": ["due_date"], "unique": False},
                    {"fields": ["user_id"], "unique": False},
                    {"fields": ["user_id", "is_deleted"], "unique": False},
                    {"fields": ["user_id", "status"], "unique": False},
                ],
            },
            {
                "name": "categories",
                "fields": [
                    {"name": "_id", "type": "ObjectId", "required": True, "description": "Primary key"},
                    {"name": "name", "type": "string", "required": True, "description": "Category name"},
                    {"name": "color", "type": "string", "required": True, "description": "Hex color code"},
                    {"name": "icon", "type": "string", "required": False, "description": "Icon identifier"},
                    {"name": "user_id", "type": "ObjectId", "required": True, "description": "Owner user reference"},
                    {"name": "created_at", "type": "datetime", "required": True, "description": "Creation timestamp"},
                    {"name": "updated_at", "type": "datetime", "required": True, "description": "Last update timestamp"},
                ],
                "indexes": [
                    {"fields": ["user_id"], "unique": False},
                    {"fields": ["user_id", "name"], "unique": True},
                ],
            },
        ],
        "api_contracts": [
            {
                "base_path": "/api/v1/auth",
                "endpoints": [
                    {"method": "POST", "path": "/api/v1/auth/register", "description": "Create new account"},
                    {"method": "POST", "path": "/api/v1/auth/login", "description": "Authenticate user"},
                    {"method": "POST", "path": "/api/v1/auth/logout", "description": "End session"},
                    {"method": "POST", "path": "/api/v1/auth/forgot-password", "description": "Request password reset"},
                    {"method": "POST", "path": "/api/v1/auth/reset-password", "description": "Reset password with token"},
                ],
            },
            {
                "base_path": "/api/v1/tasks",
                "endpoints": [
                    {"method": "GET", "path": "/api/v1/tasks", "description": "List tasks (paginated, filterable)"},
                    {"method": "POST", "path": "/api/v1/tasks", "description": "Create task"},
                    {"method": "GET", "path": "/api/v1/tasks/:id", "description": "Get task details"},
                    {"method": "PUT", "path": "/api/v1/tasks/:id", "description": "Update task"},
                    {"method": "DELETE", "path": "/api/v1/tasks/:id", "description": "Soft delete task"},
                    {"method": "GET", "path": "/api/v1/tasks/search", "description": "Search tasks"},
                ],
            },
            {
                "base_path": "/api/v1/categories",
                "endpoints": [
                    {"method": "GET", "path": "/api/v1/categories", "description": "List categories"},
                    {"method": "POST", "path": "/api/v1/categories", "description": "Create category"},
                    {"method": "PUT", "path": "/api/v1/categories/:id", "description": "Update category"},
                    {"method": "DELETE", "path": "/api/v1/categories/:id", "description": "Delete category"},
                ],
            },
            {
                "base_path": "/api/v1/dashboard",
                "endpoints": [
                    {"method": "GET", "path": "/api/v1/dashboard/stats", "description": "Get task statistics"},
                    {"method": "GET", "path": "/api/v1/dashboard/recent", "description": "Get recent activity"},
                ],
            },
        ],
        "external_apis": [],
        "auth_required": True,
        "port_allocation": {
            "frontend": 23000,
            "backend": 23001,
            "mongodb": 23002,
            "redis": 23003,
            "keycloak": 23004,
            "keycloak_postgres": 23005,
        },
    }


# ---------------------------------------------------------------------------
# Pre-parsed Test Plan
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_test_plan() -> dict[str, Any]:
    """Pre-generated test plan for the Task Management App.

    Provides a complete test plan dict with scenarios, visual checkpoints,
    and mock requirements that match the sample requirements document.
    """
    return {
        "scenarios": [
            # Unit tests
            {
                "name": "test_user_registration_valid_input",
                "description": "Verify user registration with valid email and password succeeds",
                "steps": [
                    "POST /api/v1/auth/register with valid email, password, name",
                    "Assert 201 status code returned",
                    "Assert response contains user id and email",
                    "Assert password is not returned in response",
                ],
                "expected_result": "User account created and returned without password hash",
                "feature": "User Authentication",
                "type": "unit",
            },
            {
                "name": "test_user_registration_duplicate_email",
                "description": "Verify duplicate email registration is rejected",
                "steps": [
                    "Create a user with test@example.com",
                    "POST /api/v1/auth/register with same email",
                    "Assert 409 status code returned",
                ],
                "expected_result": "Conflict error with descriptive message",
                "feature": "User Authentication",
                "type": "unit",
            },
            {
                "name": "test_user_login_valid_credentials",
                "description": "Verify login with correct credentials returns JWT",
                "steps": [
                    "Create a test user",
                    "POST /api/v1/auth/login with correct email and password",
                    "Assert 200 status code",
                    "Assert response contains access_token and token_type",
                ],
                "expected_result": "JWT access token returned",
                "feature": "User Authentication",
                "type": "unit",
            },
            {
                "name": "test_user_login_invalid_password",
                "description": "Verify login with wrong password is rejected",
                "steps": [
                    "Create a test user",
                    "POST /api/v1/auth/login with wrong password",
                    "Assert 401 status code",
                ],
                "expected_result": "Unauthorized error response",
                "feature": "User Authentication",
                "type": "unit",
            },
            {
                "name": "test_create_task",
                "description": "Verify task creation with all required fields",
                "steps": [
                    "Authenticate as test user",
                    "POST /api/v1/tasks with title, description, priority, due_date",
                    "Assert 201 status code",
                    "Assert returned task has generated id and timestamps",
                ],
                "expected_result": "Task created with auto-generated id and timestamps",
                "feature": "Task CRUD",
                "type": "unit",
            },
            {
                "name": "test_list_tasks_paginated",
                "description": "Verify task listing supports pagination parameters",
                "steps": [
                    "Create 15 tasks for test user",
                    "GET /api/v1/tasks?page=1&page_size=10",
                    "Assert 200 status code",
                    "Assert 10 items returned with total=15",
                    "GET /api/v1/tasks?page=2&page_size=10",
                    "Assert 5 items returned",
                ],
                "expected_result": "Paginated response with correct counts",
                "feature": "Task CRUD",
                "type": "integration",
            },
            {
                "name": "test_update_task_status",
                "description": "Verify task status can be updated through workflow",
                "steps": [
                    "Create a task with status=todo",
                    "PUT /api/v1/tasks/:id with status=in_progress",
                    "Assert status updated to in_progress",
                    "PUT /api/v1/tasks/:id with status=done",
                    "Assert status updated to done",
                ],
                "expected_result": "Task status transitions through workflow correctly",
                "feature": "Task CRUD",
                "type": "unit",
            },
            {
                "name": "test_soft_delete_task",
                "description": "Verify soft delete marks task as deleted without removing",
                "steps": [
                    "Create a task",
                    "DELETE /api/v1/tasks/:id",
                    "Assert 200 with deleted=true",
                    "Verify task still exists in DB with is_deleted=true",
                    "GET /api/v1/tasks should not include deleted task",
                ],
                "expected_result": "Task marked as deleted but not removed from database",
                "feature": "Task CRUD",
                "type": "integration",
            },
            {
                "name": "test_create_category",
                "description": "Verify category creation with name, color, icon",
                "steps": [
                    "Authenticate as test user",
                    "POST /api/v1/categories with name, color, icon",
                    "Assert 201 status code",
                    "Assert returned category has generated id",
                ],
                "expected_result": "Category created successfully",
                "feature": "Task Categories",
                "type": "unit",
            },
            {
                "name": "test_assign_category_to_task",
                "description": "Verify categories can be assigned to tasks",
                "steps": [
                    "Create a category",
                    "Create a task",
                    "PUT /api/v1/tasks/:id with category_ids including the new category",
                    "GET /api/v1/tasks/:id",
                    "Assert category_ids contains the assigned category",
                ],
                "expected_result": "Task updated with category assignment",
                "feature": "Task Categories",
                "type": "integration",
            },
            {
                "name": "test_dashboard_stats",
                "description": "Verify dashboard statistics calculation",
                "steps": [
                    "Create tasks with various statuses and priorities",
                    "GET /api/v1/dashboard/stats",
                    "Assert total count matches",
                    "Assert completed count matches done tasks",
                    "Assert overdue count matches past-due tasks",
                    "Assert by_priority breakdown is correct",
                ],
                "expected_result": "Accurate task statistics returned",
                "feature": "Dashboard",
                "type": "integration",
            },
            {
                "name": "test_search_tasks_by_title",
                "description": "Verify full-text search matches task titles",
                "steps": [
                    "Create tasks with distinct titles",
                    "GET /api/v1/tasks/search?q=specific-keyword",
                    "Assert only matching tasks returned",
                ],
                "expected_result": "Search returns tasks matching the query",
                "feature": "Search & Filter",
                "type": "unit",
            },
            {
                "name": "test_filter_tasks_by_status",
                "description": "Verify filtering tasks by status",
                "steps": [
                    "Create tasks with various statuses",
                    "GET /api/v1/tasks?status=todo",
                    "Assert only todo tasks returned",
                ],
                "expected_result": "Filtered results contain only matching status",
                "feature": "Search & Filter",
                "type": "unit",
            },
            # E2E tests
            {
                "name": "test_e2e_login_flow",
                "description": "End-to-end test of the complete login flow",
                "steps": [
                    "Navigate to /login",
                    "Fill in email and password fields",
                    "Click login button",
                    "Assert redirect to dashboard (/)",
                    "Assert user name visible in header",
                ],
                "expected_result": "User is logged in and sees the dashboard",
                "feature": "User Authentication",
                "type": "e2e",
            },
            {
                "name": "test_e2e_create_task_flow",
                "description": "End-to-end test of creating a new task",
                "steps": [
                    "Login as test user",
                    "Navigate to /tasks/new",
                    "Fill in task title, description, priority, due date",
                    "Click create button",
                    "Assert redirect to /tasks",
                    "Assert new task appears in task list",
                ],
                "expected_result": "Task created and visible in the task list",
                "feature": "Task CRUD",
                "type": "e2e",
            },
            {
                "name": "test_e2e_dashboard_overview",
                "description": "End-to-end test of dashboard statistics display",
                "steps": [
                    "Login as test user with pre-seeded tasks",
                    "Navigate to /",
                    "Assert statistics cards are visible",
                    "Assert tasks due today widget shows tasks",
                    "Assert recent activity feed is populated",
                ],
                "expected_result": "Dashboard displays accurate statistics and widgets",
                "feature": "Dashboard",
                "type": "e2e",
            },
        ],
        "visual_checkpoints": [
            {
                "route": "/login",
                "viewport": "desktop",
                "description": "Login page with centered form, logo, and footer",
                "elements_to_check": ["login form", "email input", "password input", "submit button"],
            },
            {
                "route": "/login",
                "viewport": "mobile",
                "description": "Login page responsive layout on mobile",
                "elements_to_check": ["login form", "email input", "password input"],
            },
            {
                "route": "/",
                "viewport": "desktop",
                "description": "Dashboard with sidebar, statistics cards, and widgets",
                "elements_to_check": ["sidebar", "stats cards", "due today widget", "activity feed"],
            },
            {
                "route": "/",
                "viewport": "mobile",
                "description": "Dashboard mobile layout with collapsed sidebar",
                "elements_to_check": ["stats cards", "bottom nav", "hamburger menu"],
            },
            {
                "route": "/tasks",
                "viewport": "desktop",
                "description": "Task list with table/card view, filters, and pagination",
                "elements_to_check": ["task list", "filter bar", "pagination", "create button"],
            },
            {
                "route": "/tasks",
                "viewport": "mobile",
                "description": "Task list responsive card view on mobile",
                "elements_to_check": ["task cards", "filter toggle", "floating action button"],
            },
            {
                "route": "/tasks/new",
                "viewport": "desktop",
                "description": "Create task form with all fields",
                "elements_to_check": ["title input", "description textarea", "priority select", "due date picker", "submit button"],
            },
            {
                "route": "/categories",
                "viewport": "desktop",
                "description": "Category management page with list and create form",
                "elements_to_check": ["category list", "color picker", "create form"],
            },
        ],
        "mock_requirements": [],
    }


# ---------------------------------------------------------------------------
# Full ParseResult fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def parsed_result(
    parsed_features: list[dict[str, Any]],
    parsed_architecture: dict[str, Any],
    sample_test_plan: dict[str, Any],
) -> dict[str, Any]:
    """Complete ParseResult-like dict combining features, architecture, and test plan."""
    arch_with_features = {**parsed_architecture, "features": parsed_features}
    return {
        "features": parsed_features,
        "architecture": arch_with_features,
        "test_plan": sample_test_plan,
        "ambiguities": [],
    }


# ---------------------------------------------------------------------------
# Builder / Prompt fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_build_prompt() -> str:
    """A realistic Codex builder prompt for the Task CRUD feature."""
    return textwrap.dedent("""\
        # Builder Task: Task CRUD

        You are a Codex builder for the NC Dev System. Implement the following
        feature completely with production-quality code and comprehensive tests.

        ## Feature Specification

        **Feature:** Task CRUD

        **Description:**
        Create tasks with title, description, priority, due date. View task list
        with pagination. View single task details. Update and soft-delete tasks.

        ## Acceptance Criteria

        1. Create tasks with title, description, priority (low/medium/high/urgent), due date
        2. View task list with pagination
        3. View single task details
        4. Update task properties (title, description, priority, due date, status)
        5. Delete tasks (soft delete - mark as deleted, don't remove from DB)
        6. Task status workflow: todo -> in_progress -> done

        ## Architecture Context

        Standard NC Dev System stack: FastAPI backend, React 19 frontend, MongoDB.

        **Port Allocations:**
        | Service | Port |
        |---------|------|
        | Frontend | 23000 |
        | Backend | 23001 |
        | MongoDB | 23002 |
        | Redis | 23003 |
    """)


@pytest.fixture
def sample_codex_result() -> dict[str, Any]:
    """A realistic Codex builder result dict."""
    return {
        "status": "success",
        "feature": "task-crud",
        "files_created": [
            "backend/app/api/v1/endpoints/tasks.py",
            "backend/app/services/task_service.py",
            "backend/app/models/task.py",
            "backend/app/schemas/task.py",
            "backend/tests/unit/test_task_service.py",
            "backend/tests/integration/test_api/test_tasks.py",
            "frontend/src/pages/TasksPage.tsx",
            "frontend/src/pages/TaskDetailPage.tsx",
            "frontend/src/pages/CreateTaskPage.tsx",
            "frontend/src/stores/useTaskStore.ts",
            "frontend/src/components/features/TaskCard.tsx",
            "frontend/src/components/features/TaskForm.tsx",
            "frontend/src/components/features/TaskList.tsx",
            "frontend/tests/unit/TaskCard.test.tsx",
        ],
        "files_modified": [
            "backend/app/api/v1/router.py",
            "frontend/src/App.tsx",
            "frontend/src/api/endpoints.ts",
        ],
        "tests_run": 32,
        "tests_passed": 32,
        "tests_failed": 0,
        "duration_seconds": 52.8,
        "commit_sha": "a1b2c3d4e5f6",
    }


# ---------------------------------------------------------------------------
# Config fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_config_dict() -> dict[str, Any]:
    """A sample NC Dev System Config as a plain dict."""
    return {
        "project_name": "task-management-app",
        "output_dir": "/tmp/nc-dev-test-output",
        "nc_dev_dir": ".nc-dev",
        "worktrees_dir": ".worktrees",
        "ports": {
            "frontend": 23000,
            "backend": 23001,
            "mongodb": 23002,
            "redis": 23003,
            "keycloak": 23004,
            "keycloak_postgres": 23005,
        },
        "ollama": {
            "url": "http://localhost:11434",
            "code_model": "qwen3-coder:30b",
            "code_model_fallback": "qwen3-coder:30b",
            "vision_model": "qwen2.5vl:7b",
            "bulk_model": "qwen3:8b",
            "timeout": 120,
        },
        "build": {
            "max_codex_attempts": 2,
            "codex_timeout": 600,
            "max_parallel_builders": 3,
            "max_fix_iterations": 3,
        },
        "phases": [1, 2, 3, 4, 5, 6],
    }


# ---------------------------------------------------------------------------
# Test results fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_test_results() -> dict[str, Any]:
    """A realistic TestSuiteResults dict for a passing test run."""
    return {
        "unit": {
            "suite_name": "backend-unit",
            "total": 42,
            "passed": 42,
            "failed": 0,
            "skipped": 0,
            "duration_seconds": 3.7,
            "failures": [],
        },
        "e2e": {
            "suite_name": "playwright-e2e",
            "total": 8,
            "passed": 8,
            "failed": 0,
            "skipped": 0,
            "duration_seconds": 24.5,
            "failures": [],
        },
        "visual": {
            "screenshots": {
                "/login": {"desktop": "docs/screenshots/login-desktop.png", "mobile": "docs/screenshots/login-mobile.png"},
                "/": {"desktop": "docs/screenshots/dashboard-desktop.png", "mobile": "docs/screenshots/dashboard-mobile.png"},
                "/tasks": {"desktop": "docs/screenshots/tasks-desktop.png", "mobile": "docs/screenshots/tasks-mobile.png"},
                "/tasks/new": {"desktop": "docs/screenshots/create-task-desktop.png"},
                "/categories": {"desktop": "docs/screenshots/categories-desktop.png"},
            },
            "vision_results": [
                {
                    "screenshot_path": "docs/screenshots/login-desktop.png",
                    "route": "/login",
                    "viewport": "desktop",
                    "passed": True,
                    "confidence": 0.95,
                    "issues": [],
                    "suggestions": [],
                    "analyzer": "ollama",
                    "raw_response": "",
                },
                {
                    "screenshot_path": "docs/screenshots/dashboard-desktop.png",
                    "route": "/",
                    "viewport": "desktop",
                    "passed": True,
                    "confidence": 0.92,
                    "issues": [],
                    "suggestions": ["Consider adding more contrast to the statistics cards"],
                    "analyzer": "ollama",
                    "raw_response": "",
                },
            ],
            "comparison_results": [],
        },
        "timestamp": "2026-01-15T14:30:00Z",
        "metadata": {
            "project_name": "task-management-app",
            "commit_sha": "a1b2c3d4e5f6",
        },
    }


@pytest.fixture
def sample_failing_test_results() -> dict[str, Any]:
    """A realistic TestSuiteResults dict for a failing test run."""
    return {
        "unit": {
            "suite_name": "backend-unit",
            "total": 42,
            "passed": 39,
            "failed": 3,
            "skipped": 0,
            "duration_seconds": 4.1,
            "failures": [
                {
                    "test_name": "tests/unit/test_task_service.py::test_create_task_missing_title",
                    "file": "tests/unit/test_task_service.py",
                    "error": "AssertionError: Expected ValidationError but no exception was raised",
                    "stdout": "",
                    "duration_seconds": 0.02,
                },
                {
                    "test_name": "tests/unit/test_task_service.py::test_update_task_invalid_status",
                    "file": "tests/unit/test_task_service.py",
                    "error": "AssertionError: Expected status 'invalid' to raise ValueError",
                    "stdout": "",
                    "duration_seconds": 0.01,
                },
                {
                    "test_name": "tests/unit/test_auth_service.py::test_password_hash_verification",
                    "file": "tests/unit/test_auth_service.py",
                    "error": "bcrypt.exceptions.InvalidSalt: Invalid salt",
                    "stdout": "Using mock bcrypt implementation",
                    "duration_seconds": 0.03,
                },
            ],
        },
        "e2e": {
            "suite_name": "playwright-e2e",
            "total": 8,
            "passed": 7,
            "failed": 1,
            "skipped": 0,
            "duration_seconds": 28.3,
            "failures": [
                {
                    "test_name": "e2e/test_task_flow.py::test_create_task_with_category",
                    "file": "e2e/test_task_flow.py",
                    "error": "TimeoutError: Waiting for selector '.category-dropdown' exceeded 30000ms",
                    "stdout": "Page loaded at /tasks/new\nFilled title: Test Task\nClicked category dropdown",
                    "duration_seconds": 30.5,
                },
            ],
        },
        "visual": {
            "screenshots": {
                "/login": {"desktop": "docs/screenshots/login-desktop.png"},
            },
            "vision_results": [
                {
                    "screenshot_path": "docs/screenshots/login-desktop.png",
                    "route": "/login",
                    "viewport": "desktop",
                    "passed": False,
                    "confidence": 0.88,
                    "issues": [
                        {
                            "severity": "warning",
                            "description": "Login form is not vertically centered",
                            "element": ".login-form",
                            "suggestion": "Add flex centering to the form container",
                        },
                    ],
                    "suggestions": ["Center the login form vertically"],
                    "analyzer": "ollama",
                    "raw_response": "",
                },
            ],
            "comparison_results": [],
        },
        "timestamp": "2026-01-15T14:35:00Z",
        "metadata": {
            "project_name": "task-management-app",
            "commit_sha": "b2c3d4e5f6a7",
        },
    }


# ---------------------------------------------------------------------------
# Generated project structure fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def scaffolded_project(tmp_project_dir: Path) -> Path:
    """A scaffolded project directory with the expected file structure.

    Creates the directory tree and empty/minimal placeholder files matching
    the NC Dev System generated project structure. Useful for testing the
    scaffolder output validation and builder file creation.
    """
    dirs = [
        "backend/app/api/v1/endpoints",
        "backend/app/core",
        "backend/app/models",
        "backend/app/schemas",
        "backend/app/services",
        "backend/app/db/migrations",
        "backend/tests/unit/test_services",
        "backend/tests/integration/test_api",
        "backend/tests/e2e/test_workflows",
        "frontend/src/api",
        "frontend/src/stores",
        "frontend/src/components/ui",
        "frontend/src/components/layout",
        "frontend/src/components/features",
        "frontend/src/pages",
        "frontend/src/hooks",
        "frontend/src/types",
        "frontend/src/utils",
        "frontend/src/styles",
        "frontend/src/mocks",
        "frontend/e2e",
        "frontend/tests/unit",
        "frontend/tests/integration",
        "scripts",
        "docs/screenshots",
        ".github/workflows",
        ".nc-dev/prompts",
        ".nc-dev/codex-results",
    ]

    for d in dirs:
        (tmp_project_dir / d).mkdir(parents=True, exist_ok=True)

    # Create minimal placeholder files
    files: dict[str, str] = {
        "docker-compose.yml": "version: '3.8'\nservices: {}\n",
        "docker-compose.dev.yml": "version: '3.8'\nservices: {}\n",
        "docker-compose.test.yml": "version: '3.8'\nservices: {}\n",
        ".env.example": "MONGO_URI=mongodb://localhost:23002\nREDIS_URL=redis://localhost:23003\n",
        ".env.development": "MONGO_URI=mongodb://localhost:23002\nREDIS_URL=redis://localhost:23003\nDEBUG=true\n",
        ".env.test": "MONGO_URI=mongodb://localhost:23002\nREDIS_URL=redis://localhost:23003\nTESTING=true\n",
        "Makefile": "dev:\n\tdocker compose -f docker-compose.dev.yml up\n",
        "README.md": "# Task Management App\n",
        "backend/Dockerfile": "FROM python:3.12-slim\n",
        "backend/Dockerfile.dev": "FROM python:3.12-slim\n",
        "backend/requirements.txt": "fastapi>=0.115\nuvicorn>=0.34\nmotor>=3.6\npydantic>=2.0\n",
        "backend/requirements-dev.txt": "pytest>=8.0\npytest-asyncio>=0.23\nhttpx>=0.27\n",
        "backend/pyproject.toml": "[project]\nname = \"task-management-app-backend\"\n",
        "backend/app/__init__.py": "",
        "backend/app/main.py": "from fastapi import FastAPI\napp = FastAPI()\n",
        "backend/app/config.py": "from pydantic_settings import BaseSettings\n",
        "backend/app/api/__init__.py": "",
        "backend/app/api/deps.py": "# Dependency injection\n",
        "backend/app/api/middleware.py": "# Middleware\n",
        "backend/app/api/v1/__init__.py": "",
        "backend/app/api/v1/router.py": "from fastapi import APIRouter\nrouter = APIRouter()\n",
        "backend/app/api/v1/endpoints/__init__.py": "",
        "backend/app/api/v1/endpoints/health.py": "from fastapi import APIRouter\nrouter = APIRouter()\n",
        "backend/app/core/__init__.py": "",
        "backend/app/core/exceptions.py": "class AppException(Exception): pass\n",
        "backend/app/core/logging.py": "# Structured logging\n",
        "backend/app/models/__init__.py": "",
        "backend/app/models/base.py": "# Base MongoDB document model\n",
        "backend/app/schemas/__init__.py": "",
        "backend/app/schemas/base.py": "# Base Pydantic schemas\n",
        "backend/app/services/__init__.py": "",
        "backend/app/services/base.py": "# BaseService(ABC, Generic[T])\n",
        "backend/app/db/__init__.py": "",
        "backend/app/db/mongodb.py": "# MongoDB connection\n",
        "backend/app/db/indexes.py": "# Database index creation\n",
        "backend/tests/__init__.py": "",
        "backend/tests/conftest.py": "import pytest\n",
        "frontend/Dockerfile": "FROM node:22-alpine AS build\n",
        "frontend/Dockerfile.dev": "FROM node:22-alpine\n",
        "frontend/nginx.conf": "server { listen 23000; }\n",
        "frontend/package.json": json.dumps({"name": "task-management-app", "version": "0.1.0"}),
        "frontend/tsconfig.json": json.dumps({"compilerOptions": {"strict": True}}),
        "frontend/vite.config.ts": "import { defineConfig } from 'vite';\n",
        "frontend/tailwind.config.js": "module.exports = { content: ['./src/**/*.tsx'] };\n",
        "frontend/vitest.config.ts": "import { defineConfig } from 'vitest/config';\n",
        "frontend/playwright.config.ts": "import { defineConfig } from '@playwright/test';\n",
        "frontend/src/main.tsx": "import React from 'react';\n",
        "frontend/src/App.tsx": "export default function App() { return <div />; }\n",
        "frontend/src/vite-env.d.ts": '/// <reference types="vite/client" />\n',
        "frontend/src/api/index.ts": "import axios from 'axios';\nexport const api = axios.create();\n",
        "frontend/src/api/endpoints.ts": "export const API_ENDPOINTS = {};\n",
        "frontend/src/api/types.ts": "export interface ApiResponse<T> { data: T; }\n",
        "frontend/src/stores/index.ts": "// Zustand stores\n",
        "frontend/src/styles/globals.css": "@tailwind base;\n@tailwind components;\n@tailwind utilities;\n",
        "frontend/src/mocks/browser.ts": "// MSW browser setup\n",
        "frontend/src/mocks/server.ts": "// MSW server setup\n",
        "frontend/src/mocks/handlers.ts": "// Mock API handlers\n",
        "scripts/setup.sh": "#!/bin/bash\necho 'Setup'\n",
        "scripts/seed-data.sh": "#!/bin/bash\necho 'Seed'\n",
        "scripts/run-tests.sh": "#!/bin/bash\necho 'Tests'\n",
        "scripts/validate-system.sh": "#!/bin/bash\necho 'Validate'\n",
        ".github/workflows/ci.yml": "name: CI\non: [push]\n",
    }

    for rel_path, content in files.items():
        file_path = tmp_project_dir / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

    return tmp_project_dir
