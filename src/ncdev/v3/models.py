"""V3 models — sequential verified sprint engine."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class FeatureStep(BaseModel):
    """A single feature to implement in sequence."""

    feature_id: str
    title: str
    description: str
    acceptance_criteria: list[str]
    test_requirements: list[str] = Field(default_factory=list)
    depends_on_features: list[str] = Field(default_factory=list)
    priority: int = 0
    estimated_complexity: str = "medium"  # low, medium, high


class FeatureQueueDoc(BaseModel):
    """Ordered list of features to implement sequentially."""

    version: str = "v3"
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    generator: str = "ncdev.v3.feature_queue"
    project_name: str = ""
    features: list[FeatureStep] = Field(default_factory=list)
    sprint_zero_criteria: list[str] = Field(default_factory=lambda: [
        "App installs without errors",
        "App boots and health endpoint returns OK",
        "Empty test suite runs",
        "First screenshot captured",
    ])


class StepStatus(str, Enum):
    PENDING = "pending"
    BUILDING = "building"
    VERIFYING = "verifying"
    REPAIRING = "repairing"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TestResult(BaseModel):
    """Result of running a test suite."""

    suite: str  # "unit", "integration", "e2e"
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    output: str = ""
    success: bool = False
    duration_seconds: float = 0.0


class ScreenshotEvidence(BaseModel):
    """A screenshot captured during verification."""

    path: str
    description: str
    viewport: str = "desktop"  # desktop, mobile
    captured_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class StepVerification(BaseModel):
    """Verification results for a single feature step."""

    lint_passed: bool = False
    lint_output: str = ""
    unit_tests: TestResult | None = None
    integration_tests: TestResult | None = None
    e2e_tests: TestResult | None = None
    screenshots: list[ScreenshotEvidence] = Field(default_factory=list)
    prohibited_patterns: list[str] = Field(default_factory=list)
    app_boots: bool = False
    overall_passed: bool = False
    failure_reasons: list[str] = Field(default_factory=list)


class StepResult(BaseModel):
    """Result of executing one feature step."""

    feature_id: str
    status: StepStatus
    build_duration_seconds: float = 0.0
    verify_duration_seconds: float = 0.0
    repair_attempts: int = 0
    verification: StepVerification | None = None
    files_created: list[str] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)
    commit_sha: str = ""
    error_message: str = ""
    builder_output: str = ""


class V3RunState(BaseModel):
    """Overall state of a V3 pipeline run."""

    run_id: str
    command: str = "full"
    workspace: str = ""
    run_dir: str = ""
    target_path: str = ""
    phase: str = "init"
    status: str = "running"
    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    feature_queue: FeatureQueueDoc | None = None
    completed_steps: list[StepResult] = Field(default_factory=list)
    current_step: str = ""
    total_features: int = 0
    completed_features: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)
