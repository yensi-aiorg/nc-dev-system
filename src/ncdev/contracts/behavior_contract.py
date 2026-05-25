"""Behavior contract shared between NC Dev and TestCraftr.

The behavior contract is the machine-readable bridge between product intent
and verification. NC Dev owns producing it from the charter; TestCraftr owns
executing and reporting against it.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from ncdev.pipeline.models import CharterBundle, FeatureStep


class BehaviorScenario(BaseModel):
    """One executable behavioral obligation."""

    scenario_id: str
    feature_id: str
    title: str
    given: list[str] = Field(default_factory=list)
    when: list[str] = Field(default_factory=list)
    then: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    required_files: list[str] = Field(default_factory=list)
    required_routes: list[str] = Field(default_factory=list)
    required_tests: list[str] = Field(default_factory=list)
    required_screenshots: list[str] = Field(default_factory=list)
    forbidden_behaviors: list[str] = Field(default_factory=list)
    invariants: list[str] = Field(default_factory=list)
    priority: int = 0
    requires_auth: bool = False


class BehaviorContract(BaseModel):
    """Canonical behavior contract consumed by verification tools."""

    version: str = "1.0"
    kind: str = "behavior-contract"
    contract_id: str
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    generator: str = "ncdev.contracts.behavior_contract"
    project_name: str
    project_type: str = "web"
    target_repo_path: str = ""
    target_url: str = ""
    frontend_url: str = ""
    health_url: str = ""
    assumptions: list[str] = Field(default_factory=list)
    scenarios: list[BehaviorScenario] = Field(default_factory=list)
    global_invariants: list[str] = Field(default_factory=list)
    permission_matrix: dict[str, list[str]] = Field(default_factory=dict)
    performance_budget: dict[str, dict[str, float]] = Field(default_factory=dict)
    required_commands: dict[str, str] = Field(default_factory=dict)
    prohibited_patterns: list[str] = Field(default_factory=list)
    source_artifacts: dict[str, str] = Field(default_factory=dict)


def _contract_id(bundle: CharterBundle) -> str:
    payload = (
        bundle.contract.project_name
        + "|"
        + "|".join(f.feature_id for f in bundle.feature_queue.features)
        + "|"
        + "|".join(bundle.feature_queue.assumptions)
    )
    return "bc-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def _scenario_from_feature(feature: FeatureStep, index: int) -> BehaviorScenario:
    acceptance = feature.acceptance
    criteria = [c.strip() for c in feature.acceptance_criteria if c.strip()]
    scenario_id = f"{feature.feature_id}-s{index + 1:02d}"
    return BehaviorScenario(
        scenario_id=scenario_id,
        feature_id=feature.feature_id,
        title=feature.title,
        given=[
            "The application is installed, configured, and in a valid starting state."
        ],
        when=[feature.description.strip() or feature.title],
        then=criteria,
        acceptance_criteria=criteria,
        required_files=list(acceptance.required_files),
        required_routes=list(acceptance.required_routes),
        required_tests=list(acceptance.required_tests),
        required_screenshots=list(acceptance.required_screenshots),
        priority=feature.priority,
    )


def build_behavior_contract(
    bundle: CharterBundle,
    *,
    source_path: Path | None = None,
    output_dir: Path | None = None,
) -> BehaviorContract:
    """Build a behavior contract from a validated charter bundle."""

    verification = bundle.verification
    commands = {
        key: value
        for key, value in {
            "backend_test": verification.backend_test_command,
            "frontend_test": verification.frontend_test_command,
            "integration_test": verification.integration_test_command,
            "e2e_test": verification.e2e_test_command,
            "typecheck": verification.typecheck_command,
            "lint": verification.lint_command,
            "build": verification.build_command,
            "start": verification.start_command,
            "stop": verification.stop_command,
        }.items()
        if value
    }
    source_artifacts: dict[str, str] = {}
    if source_path is not None:
        source_artifacts["source"] = str(source_path)
    if output_dir is not None:
        source_artifacts.update(
            {
                "target_project_contract": str(
                    output_dir / "target-project-contract.json"
                ),
                "verification_contract": str(output_dir / "verification-contract.json"),
                "feature_queue": str(output_dir / "feature-queue.json"),
            }
        )

    return BehaviorContract(
        contract_id=_contract_id(bundle),
        project_name=bundle.contract.project_name,
        project_type=bundle.contract.project_type,
        target_repo_path=bundle.contract.existing_repo_path,
        target_url=verification.frontend_url or verification.backend_health_url,
        frontend_url=verification.frontend_url,
        health_url=verification.backend_health_url,
        assumptions=list(bundle.feature_queue.assumptions),
        scenarios=[
            _scenario_from_feature(feature, index)
            for index, feature in enumerate(bundle.feature_queue.features)
        ],
        global_invariants=[
            "The implementation must preserve the target project architecture.",
            "The implementation must not introduce prohibited patterns.",
            "Required tests and verification commands must pass before release.",
        ],
        performance_budget=dict(verification.performance_budget),
        required_commands=commands,
        prohibited_patterns=list(verification.prohibited_patterns),
        source_artifacts=source_artifacts,
    )


def render_behavior_contract_markdown(contract: BehaviorContract) -> str:
    """Render a human-reviewable Markdown companion for the JSON contract."""

    lines = [
        f"# Behavior Contract: {contract.project_name}",
        "",
        f"**Contract ID:** `{contract.contract_id}`",
        f"**Project type:** `{contract.project_type}`",
        f"**Target URL:** `{contract.target_url or 'not set'}`",
        "",
        "## Assumptions",
        "",
    ]
    if contract.assumptions:
        lines.extend(f"- {item}" for item in contract.assumptions)
    else:
        lines.append("- None recorded.")

    lines.extend(["", "## Scenarios", ""])
    for scenario in contract.scenarios:
        lines.extend(
            [
                f"### {scenario.scenario_id}: {scenario.title}",
                "",
                "**Given**",
                "",
                *[f"- {item}" for item in scenario.given],
                "",
                "**When**",
                "",
                *[f"- {item}" for item in scenario.when],
                "",
                "**Then**",
                "",
                *[f"- {item}" for item in scenario.then],
                "",
            ]
        )
        obligations = (
            scenario.required_routes
            + scenario.required_files
            + scenario.required_tests
            + scenario.required_screenshots
        )
        if obligations:
            lines.extend(["**Verification obligations**", ""])
            lines.extend(f"- {item}" for item in obligations)
            lines.append("")

    lines.extend(["## Required Commands", ""])
    if contract.required_commands:
        for name, command in contract.required_commands.items():
            lines.append(f"- `{name}`: `{command}`")
    else:
        lines.append("- None recorded.")
    lines.append("")
    return "\n".join(lines)


def write_behavior_contract(contract: BehaviorContract, output_dir: Path) -> None:
    """Write JSON and Markdown behavior contract artifacts."""

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "behavior-contract.v1.json").write_text(
        contract.model_dump_json(indent=2), encoding="utf-8"
    )
    (output_dir / "behavior-contract.md").write_text(
        render_behavior_contract_markdown(contract), encoding="utf-8"
    )

