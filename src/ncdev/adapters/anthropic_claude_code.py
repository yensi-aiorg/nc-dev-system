from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from ncdev.adapters.base import ProviderAdapter, ProviderVersionInfo, TaskExecutionResult
from ncdev.v2.models import CapabilityDescriptor, TaskRequestDoc, TaskType


TASK_REQUEST_TITLES: dict[TaskType, str] = {
    TaskType.SOURCE_INGEST: "Normalize source inputs",
    TaskType.REPO_ANALYSIS: "Analyze repository structure",
    TaskType.MARKET_RESEARCH: "Synthesize market research",
    TaskType.FEATURE_EXTRACTION: "Extract feature map",
    TaskType.UX_ANALYSIS: "Develop UX recommendations",
    TaskType.DESIGN_BRIEF: "Generate design brief",
    TaskType.QA_SWEEP: "Review verification coverage",
    TaskType.DELIVERY_PACK: "Assemble delivery summary",
}


TASK_REQUEST_OUTPUTS: dict[TaskType, list[str]] = {
    TaskType.SOURCE_INGEST: ["source-pack.json"],
    TaskType.REPO_ANALYSIS: ["repo-analysis.md"],
    TaskType.MARKET_RESEARCH: ["research-pack.json"],
    TaskType.FEATURE_EXTRACTION: ["feature-map.json"],
    TaskType.UX_ANALYSIS: ["ux-analysis.md"],
    TaskType.DESIGN_BRIEF: ["design-pack.json"],
    TaskType.QA_SWEEP: ["qa-findings.json"],
    TaskType.DELIVERY_PACK: ["delivery-report.md"],
}


class AnthropicClaudeCodeAdapter(ProviderAdapter):
    def __init__(self, cli_name: str = "claude") -> None:
        self.cli_name = cli_name

    def name(self) -> str:
        return "anthropic_claude_code"

    def healthcheck(self) -> bool:
        return shutil.which(self.cli_name) is not None

    def version_info(self) -> ProviderVersionInfo:
        version = "unknown"
        if self.healthcheck():
            proc = subprocess.run(
                [self.cli_name, "--version"],
                capture_output=True,
                text=True,
                check=False,
            )
            version = (proc.stdout or proc.stderr).strip() or "unknown"
        return ProviderVersionInfo(provider=self.name(), cli=self.cli_name, version=version)

    def available_models(self) -> list[str]:
        return ["opus", "sonnet", "haiku"]

    def capabilities(self, model: str) -> CapabilityDescriptor:
        _ = model
        return CapabilityDescriptor(
            planning=True,
            test_planning=True,
            code_review=True,
            image_input=True,
            shell_execution=True,
            mcp=True,
            subagents=True,
            hooks=True,
            structured_output=True,
            long_context=True,
            reasoning_effort_levels=["medium", "high"],
        )

    def supports_feature(self, feature_name: str) -> bool:
        return feature_name in {"subagents", "hooks", "mcp", "structured_output"}

    def build_task_request(
        self,
        task_type: TaskType,
        artifact_paths: list[Path],
        model: str,
        options: dict[str, Any] | None = None,
    ) -> TaskRequestDoc:
        resolved_inputs = [str(path) for path in artifact_paths]
        title = TASK_REQUEST_TITLES.get(task_type, task_type.value.replace("_", " ").title())
        prompt = (
            f"You are Claude Code running as the V2 control-plane planner/reviewer.\n"
            f"Task: {title}.\n"
            f"Use the provided artifact set as the only local source of truth for this phase.\n"
            f"Inputs: {', '.join(path.name for path in artifact_paths)}.\n"
            f"Return a concise, implementation-ready output that another agent can execute without reinterpretation."
        )
        return TaskRequestDoc(
            generator=f"{self.name()}.build_task_request",
            source_inputs=resolved_inputs,
            task_type=task_type,
            provider=self.name(),
            model=model,
            title=title,
            prompt=prompt,
            input_artifacts=resolved_inputs,
            expected_outputs=TASK_REQUEST_OUTPUTS.get(task_type, []),
            fallback_providers=list((options or {}).get("fallback_providers", [])),
            metadata={
                "adapter": self.name(),
                "mode": "planning",
            },
        )

    def run_task(
        self,
        task_type: TaskType,
        artifact_paths: list[Path],
        model: str,
        options: dict[str, Any] | None = None,
    ) -> TaskExecutionResult:
        task_request_path = str((options or {}).get("task_request_path", ""))
        resolved_inputs = [str(path) for path in artifact_paths]
        return TaskExecutionResult(
            provider=self.name(),
            model=model,
            task_type=task_type,
            status="stubbed",
            summary=f"Claude Code adapter stub prepared {task_type.value} using {len(artifact_paths)} input artifact(s).",
            input_artifact=resolved_inputs[0] if resolved_inputs else "",
            input_artifacts=resolved_inputs,
            artifact_paths=[task_request_path] if task_request_path else [],
            metadata=options or {},
        )
