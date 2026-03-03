from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Phase(str, Enum):
    INIT = "init"
    ANALYZE = "analyze"
    BUILD = "build"
    TEST = "test"
    DELIVER = "deliver"
    BLOCKED = "blocked"
    COMPLETE = "complete"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"


class FeatureItem(BaseModel):
    name: str
    description: str
    priority: str = Field(default="P1")
    dependencies: list[str] = Field(default_factory=list)
    complexity: str = Field(default="medium")
    routes: list[str] = Field(default_factory=list)
    api_endpoints: list[str] = Field(default_factory=list)
    external_apis: list[str] = Field(default_factory=list)


class FeaturesDoc(BaseModel):
    version: str = "v1"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    features: list[FeatureItem] = Field(default_factory=list)


class ArchitectureDoc(BaseModel):
    version: str = "v1"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    summary: str
    components: list[str] = Field(default_factory=list)
    api_contracts: list[dict[str, Any]] = Field(default_factory=list)
    data_stores: list[str] = Field(default_factory=list)
    external_dependencies: list[str] = Field(default_factory=list)


class TestPlanDoc(BaseModel):
    version: str = "v1"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    e2e_scenarios: list[str] = Field(default_factory=list)
    visual_checkpoints: list[str] = Field(default_factory=list)
    mock_requirements: list[str] = Field(default_factory=list)


class RepoInventoryDoc(BaseModel):
    version: str = "v1"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    repo_path: str
    detected_languages: list[str] = Field(default_factory=list)
    package_managers: list[str] = Field(default_factory=list)
    ci_files: list[str] = Field(default_factory=list)
    docker_files: list[str] = Field(default_factory=list)
    test_frameworks: list[str] = Field(default_factory=list)
    entrypoints: list[str] = Field(default_factory=list)
    api_surfaces: list[str] = Field(default_factory=list)
    db_indicators: list[str] = Field(default_factory=list)
    monorepo: bool = False
    package_roots: list[str] = Field(default_factory=list)
    dependency_graph: dict[str, list[str]] = Field(default_factory=dict)
    hotspots: list[str] = Field(default_factory=list)


class RiskItem(BaseModel):
    id: str
    severity: str
    area: str
    detail: str
    mitigation: str


class RiskMapDoc(BaseModel):
    version: str = "v1"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    risks: list[RiskItem] = Field(default_factory=list)


class ChangeBatch(BaseModel):
    id: str
    title: str
    changes: list[str]
    validations: list[str]
    rollback: list[str]


class ChangePlanDoc(BaseModel):
    version: str = "v1"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    batches: list[ChangeBatch] = Field(default_factory=list)


class ModelAssessment(BaseModel):
    task_id: str
    model: str
    input_digest: str
    output: str
    confidence: float = 0.0
    output_format: str = "text"
    structured_output: dict[str, Any] | None = None
    risks: list[str] = Field(default_factory=list)
    status: str = "ok"
    error: str | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ConsensusDoc(BaseModel):
    version: str = "v1"
    decision: str
    agreement_score: float
    merged_output: str
    conflicts: list[str] = Field(default_factory=list)
    requires_human: bool = False


class HumanQuestion(BaseModel):
    id: str
    question: str
    context: str
    options: list[str] = Field(default_factory=list)
    required: bool = True


class HumanQuestionsDoc(BaseModel):
    version: str = "v1"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    questions: list[HumanQuestion] = Field(default_factory=list)


class ScaffoldingManifestDoc(BaseModel):
    version: str = "v1"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    project_name: str
    target_path: str
    files_written: list[str] = Field(default_factory=list)


class BuildBatchResult(BaseModel):
    batch_id: str
    status: str
    branch: str
    worktree_path: str
    attempts: int = 0
    builder_used: str = ""
    notes: str = ""


class BuildResultDoc(BaseModel):
    version: str = "v1"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    mode: str
    project_path: str
    results: list[BuildBatchResult] = Field(default_factory=list)


class TestResultDoc(BaseModel):
    version: str = "v1"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    project_path: str
    commands: list[str] = Field(default_factory=list)
    passed: bool = False
    failures: list[str] = Field(default_factory=list)
    screenshots: list[str] = Field(default_factory=list)


class HardenReportDoc(BaseModel):
    version: str = "v1"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    project_path: str
    checks: dict[str, str] = Field(default_factory=dict)
    recommendations: list[str] = Field(default_factory=list)


class DeliveryReportDoc(BaseModel):
    version: str = "v1"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    run_id: str
    mode: str
    project_path: str
    summary: str
    artifacts: list[str] = Field(default_factory=list)
    known_limitations: list[str] = Field(default_factory=list)


class TaskState(BaseModel):
    name: str
    status: TaskStatus = TaskStatus.PENDING
    retries: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    message: str = ""


class RunState(BaseModel):
    run_id: str
    command: str
    mode: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    phase: Phase = Phase.INIT
    status: TaskStatus = TaskStatus.RUNNING
    workspace: str
    run_dir: str
    retries: dict[str, int] = Field(default_factory=dict)
    tasks: list[TaskState] = Field(default_factory=list)
    model_outputs: list[str] = Field(default_factory=list)
    logs: list[str] = Field(default_factory=list)

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)
