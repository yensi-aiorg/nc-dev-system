"""TestCraftr verification report reader."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from pydantic import BaseModel, Field


class RouteProbeResult(BaseModel):
    url: str = ""
    status_code: int | None = None
    ok: bool = False
    error: str = ""


class FileCheckResult(BaseModel):
    path: str = ""
    kind: str = "file"
    exists: bool = False
    error: str = ""


class BrowserSmokeResult(BaseModel):
    url: str = ""
    ok: bool = False
    title: str = ""
    screenshot_path: str = ""
    console_errors: list[str] = Field(default_factory=list)
    failed_requests: list[str] = Field(default_factory=list)
    dom_text_chars: int = 0
    body_child_count: int = 0
    error: str = ""


class InteractionStepResult(BaseModel):
    action: str = ""
    target: str = ""
    ok: bool = False
    final_url: str = ""
    screenshot_path: str = ""
    error: str = ""


class VisualCheckResult(BaseModel):
    route: str = ""
    baseline_path: str = ""
    screenshot_path: str = ""
    ok: bool = False
    diff_ratio: float | None = None
    threshold: float = 0.0
    error: str = ""


class CommandResult(BaseModel):
    name: str = ""
    command: str = ""
    cwd: str = ""
    exit_code: int | None = None
    duration_ms: int = 0
    ok: bool = False
    timed_out: bool = False
    stdout_tail: str = ""
    stderr_tail: str = ""
    error: str = ""


class PersonaResult(BaseModel):
    persona: str
    verdict: str = "pass"
    findings: list[str] = Field(default_factory=list)


class ScenarioVerificationResult(BaseModel):
    scenario_id: str
    feature_id: str = ""
    title: str = ""
    verdict: str
    blocking: bool = True
    route_probes: list[RouteProbeResult] = Field(default_factory=list)
    file_checks: list[FileCheckResult] = Field(default_factory=list)
    browser_smokes: list[BrowserSmokeResult] = Field(default_factory=list)
    interaction_steps: list[InteractionStepResult] = Field(default_factory=list)
    visual_checks: list[VisualCheckResult] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)


class VerificationIssue(BaseModel):
    issue_id: str
    scenario_id: str = ""
    feature_id: str = ""
    title: str
    severity: str = "high"
    issue_type: str = "behavior"
    blocking: bool = True
    expected: str = ""
    actual: str = ""
    evidence_refs: list[str] = Field(default_factory=list)


class VerificationReport(BaseModel):
    version: str = "1.0"
    kind: str = "verification-report"
    run_id: str
    contract_id: str
    target_url: str
    verdict: str
    suggested_action: str = "stop"
    scenario_results: list[ScenarioVerificationResult] = Field(default_factory=list)
    command_results: list[CommandResult] = Field(default_factory=list)
    persona_results: list[PersonaResult] = Field(default_factory=list)
    issues: list[VerificationIssue] = Field(default_factory=list)
    coverage: dict[str, object] = Field(default_factory=dict)
    infrastructure_errors: list[str] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.verdict == "pass"

    @property
    def blocking_issues(self) -> list[VerificationIssue]:
        return [issue for issue in self.issues if issue.blocking]

    @property
    def is_infrastructure_failure(self) -> bool:
        return self.verdict == "infrastructure_failure"


def load_verification_report(path: str | Path) -> VerificationReport:
    p = Path(path)
    return VerificationReport.model_validate_json(p.read_text(encoding="utf-8"))


def summarize_verification_report(report: VerificationReport) -> dict[str, object]:
    categories = _failure_categories(report)
    return {
        "run_id": report.run_id,
        "contract_id": report.contract_id,
        "verdict": report.verdict,
        "suggested_action": report.suggested_action,
        "blocking_issue_count": len(report.blocking_issues),
        "infrastructure_error_count": len(report.infrastructure_errors),
        "coverage": report.coverage,
        "failure_categories": categories,
        "issue_types": dict(Counter(issue.issue_type for issue in report.issues)),
        "persona_results": [
            {
                "persona": result.persona,
                "verdict": result.verdict,
                "finding_count": len(result.findings),
            }
            for result in report.persona_results
        ],
    }


def _failure_categories(report: VerificationReport) -> dict[str, int]:
    categories = {
        "route": 0,
        "file": 0,
        "browser": 0,
        "interaction": 0,
        "visual": 0,
        "command": 0,
        "persona": 0,
    }
    for result in report.scenario_results:
        categories["route"] += sum(1 for probe in result.route_probes if not probe.ok)
        categories["file"] += sum(
            1 for check in result.file_checks if not check.exists
        )
        categories["browser"] += sum(
            1 for smoke in result.browser_smokes if not smoke.ok
        )
        categories["interaction"] += sum(
            1 for step in result.interaction_steps if not step.ok
        )
        categories["visual"] += sum(
            1 for check in result.visual_checks if not check.ok
        )
    categories["command"] = sum(
        1 for result in report.command_results if not result.ok
    )
    categories["persona"] = sum(
        1 for result in report.persona_results if result.verdict != "pass"
    )
    return {key: value for key, value in categories.items() if value}
