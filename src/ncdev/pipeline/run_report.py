"""Structured run report — Phase 6 observability.

A pipeline run leaves a lot of evidence scattered across the run
directory: per-step results, per-step gauntlet reports, the charter,
the integration result. ``build_run_report`` consolidates it into one
:class:`RunReport` and ``write_run_report`` persists it as both
``report.json`` (machine) and ``report.md`` (human).

The report answers, at a glance: did the product build, what did the
charter assume, which gauntlet layers blocked which features, and what
needs human attention.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from ncdev.pipeline.models import PipelineRunState, StepResult, StepStatus


@dataclass
class FeatureReport:
    """Per-feature line in the run report."""

    feature_id: str
    status: str
    commit: str = ""
    build_seconds: float = 0.0
    gauntlet_ran: bool = False
    gauntlet_passed: bool | None = None
    gauntlet_blocking: list[str] = field(default_factory=list)
    error: str = ""


@dataclass
class RunReport:
    """Consolidated outcome of one pipeline run."""

    run_id: str
    command: str
    status: str
    target_path: str
    features: list[FeatureReport] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    integration_passed: bool | None = None
    integration_failures: list[str] = field(default_factory=list)

    @property
    def passed_count(self) -> int:
        return sum(1 for f in self.features if f.status == StepStatus.PASSED.value)

    @property
    def failed_count(self) -> int:
        return len(self.features) - self.passed_count

    @property
    def attention_items(self) -> list[str]:
        """Everything a human should look at, in one list."""
        items: list[str] = []
        for f in self.features:
            if f.status != StepStatus.PASSED.value:
                why = f.error or "see step log"
                items.append(f"{f.feature_id} [{f.status}] — {why}")
        items.extend(f"integration: {x}" for x in self.integration_failures)
        return items

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "command": self.command,
            "status": self.status,
            "target_path": self.target_path,
            "passed": self.passed_count,
            "failed": self.failed_count,
            "assumptions": self.assumptions,
            "integration_passed": self.integration_passed,
            "integration_failures": self.integration_failures,
            "features": [
                {
                    "feature_id": f.feature_id,
                    "status": f.status,
                    "commit": f.commit,
                    "build_seconds": round(f.build_seconds, 1),
                    "gauntlet_ran": f.gauntlet_ran,
                    "gauntlet_passed": f.gauntlet_passed,
                    "gauntlet_blocking": f.gauntlet_blocking,
                    "error": f.error,
                }
                for f in self.features
            ],
        }

    def to_markdown(self) -> str:
        lines = [
            f"# Run report — {self.run_id}",
            "",
            f"- **Command:** `{self.command}`",
            f"- **Status:** {self.status}",
            f"- **Target:** `{self.target_path}`",
            f"- **Features:** {self.passed_count} passed, {self.failed_count} failed",
        ]
        if self.integration_passed is not None:
            lines.append(
                f"- **Integration gate:** "
                f"{'passed' if self.integration_passed else 'FAILED'}"
            )
        lines.append("")

        if self.assumptions:
            lines.append("## Charter assumptions")
            lines.append("")
            lines.append(
                "_The PRD was ambiguous here; the charter resolved each "
                "by a judgment call. Verify before relying on the build._"
            )
            lines.append("")
            lines += [f"- {a}" for a in self.assumptions]
            lines.append("")

        lines.append("## Features")
        lines.append("")
        lines.append("| Feature | Status | Gauntlet | Commit | Build |")
        lines.append("|---------|--------|----------|--------|-------|")
        for f in self.features:
            if not f.gauntlet_ran:
                g = "—"
            elif f.gauntlet_passed:
                g = "pass"
            else:
                g = f"BLOCKED ({len(f.gauntlet_blocking)})"
            lines.append(
                f"| {f.feature_id} | {f.status} | {g} | "
                f"`{f.commit[:8]}` | {f.build_seconds:.0f}s |"
            )
        lines.append("")

        blocked = [f for f in self.features if f.gauntlet_blocking]
        if blocked:
            lines.append("## Gauntlet blocking failures")
            lines.append("")
            for f in blocked:
                lines.append(f"### {f.feature_id}")
                lines += [f"- {b}" for b in f.gauntlet_blocking]
                lines.append("")

        attention = self.attention_items
        if attention:
            lines.append("## Needs attention")
            lines.append("")
            lines += [f"- {item}" for item in attention]
            lines.append("")

        return "\n".join(lines)


def _load_gauntlet(run_dir: Path, feature_id: str) -> dict | None:
    """Read a feature's persisted gauntlet.json, or None if absent."""
    path = run_dir / "steps" / feature_id / "gauntlet.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _feature_report(result: StepResult, run_dir: Path) -> FeatureReport:
    fr = FeatureReport(
        feature_id=result.feature_id,
        status=result.status.value,
        commit=result.commit_sha,
        build_seconds=result.build_duration_seconds,
        error=result.error_message,
    )
    gauntlet = _load_gauntlet(run_dir, result.feature_id)
    if gauntlet is not None:
        fr.gauntlet_ran = True
        fr.gauntlet_passed = bool(gauntlet.get("passed", False))
        fr.gauntlet_blocking = [
            f"{layer.get('layer', '?')}: {layer.get('summary', '')}"
            for layer in gauntlet.get("layers", [])
            if layer.get("blocking")
            and layer.get("status") in ("failed", "error")
        ]
    return fr


def build_run_report(state: PipelineRunState, run_dir: Path) -> RunReport:
    """Consolidate a finished run's state + on-disk evidence into a report."""
    report = RunReport(
        run_id=state.run_id,
        command=state.command,
        status=state.status,
        target_path=state.target_path,
        assumptions=list(state.metadata.get("charter_assumptions", [])),
        features=[_feature_report(r, run_dir) for r in state.completed_steps],
    )
    integration = state.metadata.get("integration")
    if isinstance(integration, dict):
        report.integration_passed = integration.get("passed")
        report.integration_failures = list(integration.get("failures", []))
    return report


def write_run_report(state: PipelineRunState, run_dir: Path) -> Path:
    """Build and persist report.json + report.md. Returns the .md path."""
    report = build_run_report(state, run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "report.json").write_text(
        json.dumps(report.to_dict(), indent=2), encoding="utf-8",
    )
    md_path = run_dir / "report.md"
    md_path.write_text(report.to_markdown(), encoding="utf-8")
    return md_path
