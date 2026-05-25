"""TestCraftr verification report reader."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class ScenarioVerificationResult(BaseModel):
    scenario_id: str
    feature_id: str = ""
    title: str = ""
    verdict: str
    blocking: bool = True
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
    return {
        "run_id": report.run_id,
        "contract_id": report.contract_id,
        "verdict": report.verdict,
        "suggested_action": report.suggested_action,
        "blocking_issue_count": len(report.blocking_issues),
        "infrastructure_error_count": len(report.infrastructure_errors),
        "coverage": report.coverage,
    }

