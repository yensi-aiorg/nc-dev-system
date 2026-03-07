from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class V2Phase(str, Enum):
    INIT = "init"
    INGEST = "ingest"
    DISCOVERY = "discovery"
    COMPLETE = "complete"
    BLOCKED = "blocked"


class V2TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"


class TaskType(str, Enum):
    SOURCE_INGEST = "source_ingest"
    REPO_ANALYSIS = "repo_analysis"
    MARKET_RESEARCH = "market_research"
    FEATURE_EXTRACTION = "feature_extraction"
    UX_ANALYSIS = "ux_analysis"
    DESIGN_BRIEF = "design_brief"
    DESIGN_REFERENCE_GENERATION = "design_reference_generation"
    SCAFFOLD_PROJECT = "scaffold_project"
    BUILD_BATCH = "build_batch"
    TEST_PLAN_GENERATION = "test_plan_generation"
    TEST_AUTHORING = "test_authoring"
    QA_SWEEP = "qa_sweep"
    ISSUE_TRIAGE = "issue_triage"
    FIX_BATCH = "fix_batch"
    DELIVERY_PACK = "delivery_pack"


class ArtifactEnvelope(BaseModel):
    version: str = "v2"
    generated_at: datetime = Field(default_factory=_utc_now)
    generator: str
    schema_id: str
    source_inputs: list[str] = Field(default_factory=list)


class SourceAsset(BaseModel):
    path: str
    kind: str
    digest: str
    bytes: int


class SourcePackDoc(ArtifactEnvelope):
    schema_id: str = "source-pack.v2"
    project_name: str
    source_kind: str
    primary_source: str
    assets: list[SourceAsset] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ResearchFinding(BaseModel):
    title: str
    detail: str
    category: str = "product"


class ResearchPackDoc(ArtifactEnvelope):
    schema_id: str = "research-pack.v2"
    project_name: str
    market_present: bool = False
    user_segments: list[str] = Field(default_factory=list)
    pain_points: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    findings: list[ResearchFinding] = Field(default_factory=list)


class FeatureCandidate(BaseModel):
    name: str
    description: str
    audience: list[str] = Field(default_factory=list)
    priority: str = "P1"
    surfaces: list[str] = Field(default_factory=list)


class FeatureMapDoc(ArtifactEnvelope):
    schema_id: str = "feature-map.v2"
    project_name: str
    features: list[FeatureCandidate] = Field(default_factory=list)
    ux_principles: list[str] = Field(default_factory=list)
    recommended_platforms: list[str] = Field(default_factory=list)


class DesignDirection(BaseModel):
    name: str
    rationale: str
    traits: list[str] = Field(default_factory=list)


class DesignPackDoc(ArtifactEnvelope):
    schema_id: str = "design-pack.v2"
    project_name: str
    selected_direction: str
    directions: list[DesignDirection] = Field(default_factory=list)
    theme_tokens: dict[str, str] = Field(default_factory=dict)
    component_rules: list[str] = Field(default_factory=list)


class BuildBatchV2(BaseModel):
    id: str
    title: str
    task_type: TaskType
    summary: str
    acceptance_criteria: list[str] = Field(default_factory=list)


class BuildPlanDoc(ArtifactEnvelope):
    schema_id: str = "build-plan.v2"
    project_name: str
    batches: list[BuildBatchV2] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class TargetProjectContractDoc(ArtifactEnvelope):
    schema_id: str = "target-project-contract.v2"
    project_name: str
    target_type: str
    stack: dict[str, str] = Field(default_factory=dict)
    ownership_rules: list[str] = Field(default_factory=list)
    required_artifacts: list[str] = Field(default_factory=list)


class ScaffoldPlanDoc(ArtifactEnvelope):
    schema_id: str = "scaffold-plan.v2"
    project_name: str
    directories: list[str] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)
    commands: list[str] = Field(default_factory=list)
    test_harness: list[str] = Field(default_factory=list)


class CapabilityDescriptor(BaseModel):
    planning: bool = False
    implementation: bool = False
    test_planning: bool = False
    test_implementation: bool = False
    code_review: bool = False
    image_input: bool = False
    audio_input: bool = False
    video_input: bool = False
    shell_execution: bool = False
    mcp: bool = False
    subagents: bool = False
    hooks: bool = False
    structured_output: bool = False
    long_context: bool = False
    snapshot_support: bool = False
    reasoning_effort_levels: list[str] = Field(default_factory=list)


class ProviderCapabilitySnapshot(BaseModel):
    provider: str
    model: str
    available: bool
    version: str = "unknown"
    capabilities: CapabilityDescriptor = Field(default_factory=CapabilityDescriptor)
    notes: list[str] = Field(default_factory=list)


class CapabilitySnapshotDoc(ArtifactEnvelope):
    schema_id: str = "capability-snapshot.v2"
    snapshots: list[ProviderCapabilitySnapshot] = Field(default_factory=list)


class RoutingDecision(BaseModel):
    task_type: TaskType
    provider: str
    model: str
    rationale: str
    fallback_providers: list[str] = Field(default_factory=list)


class RoutingPlanDoc(ArtifactEnvelope):
    schema_id: str = "routing-plan.v2"
    decisions: list[RoutingDecision] = Field(default_factory=list)


class V2TaskState(BaseModel):
    name: str
    status: V2TaskStatus = V2TaskStatus.PENDING
    message: str = ""
    artifacts: list[str] = Field(default_factory=list)


class V2RunState(BaseModel):
    run_id: str
    command: str
    workspace: str
    run_dir: str
    phase: V2Phase = V2Phase.INIT
    status: V2TaskStatus = V2TaskStatus.RUNNING
    started_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    tasks: list[V2TaskState] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)
    provider_snapshots: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def touch(self) -> None:
        self.updated_at = _utc_now()
