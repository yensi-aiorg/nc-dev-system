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


class TypographySpec(BaseModel):
    font_display: str = "Inter"
    font_body: str = "Inter"
    font_mono: str = "JetBrains Mono"
    scale: dict[str, str] = Field(default_factory=dict)
    line_heights: dict[str, str] = Field(default_factory=dict)
    weights: dict[str, int] = Field(default_factory=dict)


class ColorSpec(BaseModel):
    primary: str = "#0f172a"
    secondary: str = "#1e293b"
    accent: str = "#14b8a6"
    highlight: str = "#f97316"
    background: str = "#ffffff"
    surface: str = "#f8fafc"
    error: str = "#ef4444"
    warning: str = "#eab308"
    success: str = "#22c55e"
    text_primary: str = "#0f172a"
    text_secondary: str = "#64748b"
    text_inverse: str = "#ffffff"
    border: str = "#e2e8f0"


class SpacingSpec(BaseModel):
    unit: str = "4px"
    scale: dict[str, str] = Field(default_factory=dict)


class RadiusShadowSpec(BaseModel):
    radius: dict[str, str] = Field(default_factory=dict)
    shadows: dict[str, str] = Field(default_factory=dict)


class MotionSpec(BaseModel):
    duration_fast: str = "100ms"
    duration_normal: str = "200ms"
    duration_slow: str = "400ms"
    easing_default: str = "cubic-bezier(0.4, 0, 0.2, 1)"
    easing_enter: str = "cubic-bezier(0, 0, 0.2, 1)"
    easing_exit: str = "cubic-bezier(0.4, 0, 1, 1)"
    rules: list[str] = Field(default_factory=list)


class LayoutSpec(BaseModel):
    breakpoints: dict[str, str] = Field(default_factory=dict)
    max_content_width: str = "1280px"
    grid_columns: int = 12
    shell_rules: list[str] = Field(default_factory=list)


class ComponentDensitySpec(BaseModel):
    default_density: str = "comfortable"
    input_height: str = "40px"
    button_height: str = "40px"
    rules: list[str] = Field(default_factory=list)


class IconographySpec(BaseModel):
    library: str = "lucide-react"
    default_size: str = "20px"
    stroke_width: str = "1.5"
    rules: list[str] = Field(default_factory=list)


class DesignBriefDoc(ArtifactEnvelope):
    schema_id: str = "design-brief.v2"
    project_name: str
    direction_name: str
    direction_rationale: str
    direction_traits: list[str] = Field(default_factory=list)
    typography: TypographySpec = Field(default_factory=TypographySpec)
    colors: ColorSpec = Field(default_factory=ColorSpec)
    spacing: SpacingSpec = Field(default_factory=SpacingSpec)
    radius_shadow: RadiusShadowSpec = Field(default_factory=RadiusShadowSpec)
    motion: MotionSpec = Field(default_factory=MotionSpec)
    layout: LayoutSpec = Field(default_factory=LayoutSpec)
    component_density: ComponentDensitySpec = Field(default_factory=ComponentDensitySpec)
    iconography: IconographySpec = Field(default_factory=IconographySpec)
    composition_rules: list[str] = Field(default_factory=list)


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


class PhaseDefinition(BaseModel):
    phase_id: str
    title: str
    goal: str
    feature_ids: list[str] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)
    exit_criteria: list[str] = Field(default_factory=list)


class PhasePlanDoc(ArtifactEnvelope):
    schema_id: str = "phase-plan.v2"
    project_name: str
    operating_mode: str = "website_saas"
    target_repo_path: str = ""
    phases: list[PhaseDefinition] = Field(default_factory=list)


class TargetProjectContractDoc(ArtifactEnvelope):
    schema_id: str = "target-project-contract.v2"
    project_name: str
    target_type: str
    operating_mode: str = "website_saas"
    target_repo_path: str = ""
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


class ScaffoldManifestDocV2(ArtifactEnvelope):
    schema_id: str = "scaffold-manifest.v2"
    project_name: str
    target_path: str
    files_written: list[str] = Field(default_factory=list)
    initialized_git: bool = False
    existing_repo: bool = False
    scaffold_applied: bool = True


class VerificationContractDoc(ArtifactEnvelope):
    schema_id: str = "verification-contract.v2"
    project_name: str
    commands: list[str] = Field(default_factory=list)
    startup_commands: list[str] = Field(default_factory=list)
    teardown_commands: list[str] = Field(default_factory=list)
    healthcheck_url: str = ""
    healthcheck_path: str = "/"
    startup_timeout_seconds: int = 45
    healthcheck_interval_seconds: int = 1
    required_viewports: list[str] = Field(default_factory=list)
    evidence_paths: list[str] = Field(default_factory=list)
    required_checks: list[str] = Field(default_factory=list)
    issue_bundle_fields: list[str] = Field(default_factory=list)


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


class TaskRequestDoc(ArtifactEnvelope):
    schema_id: str = "task-request.v2"
    task_type: TaskType
    provider: str
    model: str
    title: str
    prompt: str
    input_artifacts: list[str] = Field(default_factory=list)
    expected_outputs: list[str] = Field(default_factory=list)
    fallback_providers: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionJob(BaseModel):
    job_id: str
    task_type: TaskType
    provider: str
    model: str
    title: str
    request_artifact: str
    target_path: str = ""
    input_artifacts: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class JobQueueDoc(ArtifactEnvelope):
    schema_id: str = "job-queue.v2"
    project_name: str
    jobs: list[ExecutionJob] = Field(default_factory=list)


class JobRunRecord(BaseModel):
    job_id: str
    task_type: TaskType
    provider: str
    model: str
    status: str
    summary: str
    request_artifact: str
    output_artifacts: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class JobRunLogDoc(ArtifactEnvelope):
    schema_id: str = "job-run-log.v2"
    project_name: str
    records: list[JobRunRecord] = Field(default_factory=list)


class VerificationRunDoc(ArtifactEnvelope):
    schema_id: str = "verification-run.v2"
    project_name: str
    target_path: str
    base_url: str
    routes: list[str] = Field(default_factory=list)
    dry_run: bool = False
    bootstrap_succeeded: bool = False
    bootstrap_commands: list[str] = Field(default_factory=list)
    overall_passed: bool = False
    summary: dict[str, Any] = Field(default_factory=dict)
    report_path: str = ""


class BootstrapCommandRecord(BaseModel):
    stage: str
    command: str
    return_code: int | None = None
    succeeded: bool
    background: bool = False
    pid: int | None = None
    stdout_path: str = ""
    stderr_path: str = ""


class BootstrapRunDoc(ArtifactEnvelope):
    schema_id: str = "bootstrap-run.v2"
    project_name: str
    target_path: str
    base_url: str
    reachable_before_bootstrap: bool = False
    bootstrap_succeeded: bool = False
    started_services: bool = False
    commands: list[BootstrapCommandRecord] = Field(default_factory=list)
    teardown_attempted: bool = False
    teardown_succeeded: bool = False
    teardown_commands: list[BootstrapCommandRecord] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


class EvidenceIndexDoc(ArtifactEnvelope):
    schema_id: str = "evidence-index.v2"
    project_name: str
    target_path: str
    screenshots: list[str] = Field(default_factory=list)
    reports: list[str] = Field(default_factory=list)
    videos: list[str] = Field(default_factory=list)
    traces: list[str] = Field(default_factory=list)


class VerificationIssue(BaseModel):
    issue_id: str
    title: str
    severity: str
    category: str
    expected: str
    actual: str
    related_artifacts: list[str] = Field(default_factory=list)


class VerificationIssueBundleDoc(ArtifactEnvelope):
    schema_id: str = "verification-issues.v2"
    project_name: str
    target_path: str
    issue_count: int = 0
    issues: list[VerificationIssue] = Field(default_factory=list)


class TaskExecutionRecord(BaseModel):
    provider: str
    model: str
    task_type: TaskType
    status: str
    summary: str
    input_artifact: str = ""
    input_artifacts: list[str] = Field(default_factory=list)
    artifact_paths: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionLogDoc(ArtifactEnvelope):
    schema_id: str = "execution-log.v2"
    results: list[TaskExecutionRecord] = Field(default_factory=list)


class BatchDeliveryEntry(BaseModel):
    batch_id: str
    title: str
    summary: str
    acceptance_criteria: list[str] = Field(default_factory=list)

    @property
    def id(self) -> str:
        return self.batch_id


class DeliverySummaryDoc(ArtifactEnvelope):
    schema_id: str = "delivery-summary.v2"
    project_name: str
    target_type: str
    stack: dict[str, str] = Field(default_factory=dict)
    batch_count: int
    batches: list[BatchDeliveryEntry] = Field(default_factory=list)
    execution_steps: list[str] = Field(default_factory=list)
    ownership_rules: list[str] = Field(default_factory=list)
    required_artifacts: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)

    @property
    def instructions(self) -> list[str]:
        return self.execution_steps


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


class FullRunReportDoc(ArtifactEnvelope):
    schema_id: str = "full-run-report.v2"
    run_id: str
    command: str
    project_name: str = ""
    target_path: str = ""
    final_status: str
    readiness_decision: str = "blocked"
    release_recommendation: str = "hold"
    readiness_score: int = 0
    verification_passed: bool = False
    bootstrap_succeeded: bool = False
    teardown_succeeded: bool = False
    evidence_complete: bool = False
    human_approval_required: bool = True
    repair_cycles_requested: int = 0
    repair_cycles_run: int = 0
    tasks: dict[str, str] = Field(default_factory=dict)
    failed_tasks: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
