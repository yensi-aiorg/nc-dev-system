"""Pydantic v2 models for the NC Dev System requirements parser.

Defines the complete data model hierarchy for representing parsed requirements,
architecture decisions, and test plans extracted from markdown specifications.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class Priority(str, Enum):
    """Feature priority level. P0 = must-have, P1 = should-have, P2 = nice-to-have."""
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"


class Complexity(str, Enum):
    """Estimated implementation complexity."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class HTTPMethod(str, Enum):
    """Supported HTTP methods for API endpoints."""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"


class TestType(str, Enum):
    """Classification of test scenarios."""
    UNIT = "unit"
    INTEGRATION = "integration"
    E2E = "e2e"


class Viewport(str, Enum):
    """Viewport size categories for visual testing."""
    DESKTOP = "desktop"
    MOBILE = "mobile"


# ---------------------------------------------------------------------------
# Route & API Models
# ---------------------------------------------------------------------------

class Route(BaseModel):
    """A frontend UI route."""
    path: str = Field(..., description="URL path, e.g. '/tasks'")
    name: str = Field(..., description="Human-readable route name")
    description: str = Field(default="", description="What this route displays")
    requires_auth: bool = Field(default=False, description="Whether authentication is required")


class APIEndpoint(BaseModel):
    """A single REST API endpoint."""
    method: HTTPMethod = Field(..., description="HTTP method")
    path: str = Field(..., description="URL path, e.g. '/api/v1/tasks'")
    description: str = Field(default="", description="What this endpoint does")
    request_body: Optional[dict[str, Any]] = Field(
        default=None, description="JSON schema hint for the request body"
    )
    response_body: dict[str, Any] = Field(
        default_factory=dict, description="JSON schema hint for the response body"
    )
    requires_auth: bool = Field(default=True, description="Whether auth is required")


# ---------------------------------------------------------------------------
# Database Models
# ---------------------------------------------------------------------------

class FieldModel(BaseModel):
    """A single field in a database collection."""
    name: str = Field(..., description="Field name")
    type: str = Field(..., description="Field data type, e.g. 'str', 'int', 'datetime'")
    required: bool = Field(default=True, description="Whether the field is required")
    description: str = Field(default="", description="What this field represents")
    default: Optional[Any] = Field(default=None, description="Default value, if any")


class Index(BaseModel):
    """A database index definition."""
    fields: list[str] = Field(..., description="Fields included in the index")
    unique: bool = Field(default=False, description="Whether this is a unique index")


class DBCollection(BaseModel):
    """A MongoDB collection definition."""
    name: str = Field(..., description="Collection name")
    fields: list[FieldModel] = Field(default_factory=list, description="Fields in the collection")
    indexes: list[Index] = Field(default_factory=list, description="Indexes on the collection")


# ---------------------------------------------------------------------------
# Feature Model
# ---------------------------------------------------------------------------

class Feature(BaseModel):
    """A discrete product feature extracted from requirements."""
    name: str = Field(..., description="Feature name, e.g. 'User Authentication'")
    description: str = Field(default="", description="Detailed feature description")
    priority: Priority = Field(default=Priority.P1, description="Feature priority")
    dependencies: list[str] = Field(
        default_factory=list, description="Names of features this depends on"
    )
    complexity: Complexity = Field(
        default=Complexity.MEDIUM, description="Estimated complexity"
    )
    ui_routes: list[Route] = Field(
        default_factory=list, description="Frontend routes for this feature"
    )
    api_endpoints: list[APIEndpoint] = Field(
        default_factory=list, description="Backend API endpoints for this feature"
    )
    external_apis: list[str] = Field(
        default_factory=list, description="External API dependencies"
    )
    acceptance_criteria: list[str] = Field(
        default_factory=list, description="Acceptance criteria extracted from requirements"
    )


# ---------------------------------------------------------------------------
# Architecture Models
# ---------------------------------------------------------------------------

class ExternalAPI(BaseModel):
    """An external API dependency."""
    name: str = Field(..., description="API name, e.g. 'Stripe'")
    base_url: str = Field(default="", description="Base URL of the external API")
    endpoints: list[dict[str, Any]] = Field(
        default_factory=list, description="Endpoint definitions"
    )
    auth_type: Optional[str] = Field(
        default=None, description="Auth mechanism: 'api_key', 'oauth2', 'bearer', etc."
    )


class APIContract(BaseModel):
    """API contract grouping endpoints under a base path."""
    base_path: str = Field(..., description="Base path, e.g. '/api/v1/tasks'")
    endpoints: list[APIEndpoint] = Field(
        default_factory=list, description="Endpoints under this base path"
    )


class Architecture(BaseModel):
    """Complete system architecture derived from parsed features."""
    project_name: str = Field(..., description="Name of the project")
    description: str = Field(default="", description="Project description")
    features: list[Feature] = Field(default_factory=list, description="All features")
    db_collections: list[DBCollection] = Field(
        default_factory=list, description="MongoDB collections"
    )
    api_contracts: list[APIContract] = Field(
        default_factory=list, description="API contracts grouped by resource"
    )
    external_apis: list[ExternalAPI] = Field(
        default_factory=list, description="External API dependencies"
    )
    auth_required: bool = Field(
        default=False, description="Whether the project requires authentication"
    )
    port_allocation: dict[str, int] = Field(
        default_factory=lambda: {
            "frontend": 23000,
            "backend": 23001,
            "mongodb": 23002,
            "redis": 23003,
            "keycloak": 23004,
            "keycloak_postgres": 23005,
        },
        description="Port allocation for services",
    )


# ---------------------------------------------------------------------------
# Test Plan Models
# ---------------------------------------------------------------------------

class TestScenario(BaseModel):
    """A single test scenario."""
    name: str = Field(..., description="Test scenario name")
    description: str = Field(default="", description="What this test verifies")
    steps: list[str] = Field(default_factory=list, description="Ordered test steps")
    expected_result: str = Field(default="", description="Expected outcome")
    feature: str = Field(..., description="Name of the feature being tested")
    type: TestType = Field(default=TestType.UNIT, description="Test classification")


class VisualCheckpoint(BaseModel):
    """A visual regression checkpoint for screenshot comparison."""
    route: str = Field(..., description="Route path to screenshot")
    viewport: Viewport = Field(..., description="Viewport size category")
    description: str = Field(default="", description="What to verify visually")
    elements_to_check: list[str] = Field(
        default_factory=list,
        description="CSS selectors or element descriptions to verify",
    )


class TestPlan(BaseModel):
    """Complete test plan for a project."""
    scenarios: list[TestScenario] = Field(
        default_factory=list, description="All test scenarios"
    )
    visual_checkpoints: list[VisualCheckpoint] = Field(
        default_factory=list, description="Visual regression checkpoints"
    )
    mock_requirements: list[str] = Field(
        default_factory=list, description="External APIs that need mocking"
    )


# ---------------------------------------------------------------------------
# Top-Level Parse Result
# ---------------------------------------------------------------------------

class ParseResult(BaseModel):
    """Complete result of parsing a requirements document."""
    features: list[Feature] = Field(default_factory=list, description="Extracted features")
    architecture: Architecture = Field(
        ..., description="Generated architecture"
    )
    test_plan: TestPlan = Field(
        ..., description="Generated test plan"
    )
    ambiguities: list[str] = Field(
        default_factory=list,
        description="Ambiguous or unclear requirements that need clarification",
    )
