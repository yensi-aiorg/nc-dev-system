"""Quality Gate data models for the pipeline state, fix manifests, and scores."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class QualityScores(BaseModel):
    """Aggregate quality scores across three dimensions."""

    core_flow: int = 0
    resilience: int = 0
    polish: int = 0


class IssueEvidence(BaseModel):
    """Artifacts captured while reproducing an issue."""

    screenshot: str = ""
    console_errors: list[str] = []
    network_log: str = ""
    video_clip: str = ""


class FixIssue(BaseModel):
    """A single issue that needs fixing."""

    id: str
    priority: str
    persona: str
    category: str
    title: str
    flow: str
    expected: str
    actual: str
    root_cause_hint: str
    reproduction: list[str]
    evidence: IssueEvidence = IssueEvidence()
    affected_files_hint: list[str] = []


class FixManifest(BaseModel):
    """Collection of issues discovered in a single test run."""

    run_id: str
    target_path: str
    scores: QualityScores
    issues: list[FixIssue]


class CycleResult(BaseModel):
    """Outcome of one build-test-fix cycle."""

    cycle: int
    scores: QualityScores
    issues_found: int
    issues_fixed: int
    passed: bool
    regression: bool = False


class PipelineState(BaseModel):
    """Top-level state for the quality gate pipeline."""

    project_name: str
    target_url: str
    current_cycle: int = 0
    max_cycles: int = 3
    phase: str = "pending"
    cycles: list[CycleResult] = []
    final_scores: Optional[QualityScores] = None
