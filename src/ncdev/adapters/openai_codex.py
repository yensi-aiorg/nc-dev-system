from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from ncdev.adapters.base import ProviderAdapter, ProviderVersionInfo, TaskExecutionResult
from ncdev.v2.models import CapabilityDescriptor, TaskRequestDoc, TaskType


TASK_REQUEST_TITLES: dict[TaskType, str] = {
    TaskType.BUILD_BATCH: "Implement build batch",
    TaskType.TEST_AUTHORING: "Author target-project tests",
    TaskType.FIX_BATCH: "Repair failing implementation batch",
    TaskType.QA_SWEEP: "Review implementation evidence",
}


TASK_REQUEST_OUTPUTS: dict[TaskType, list[str]] = {
    TaskType.BUILD_BATCH: ["target-project code changes", "target-project tests"],
    TaskType.TEST_AUTHORING: ["unit tests", "integration tests", "playwright tests"],
    TaskType.FIX_BATCH: ["bug fixes", "regression coverage"],
    TaskType.QA_SWEEP: ["review notes", "issue bundle candidates"],
}


class OpenAICodexAdapter(ProviderAdapter):
    def __init__(self, cli_name: str = "codex") -> None:
        self.cli_name = cli_name

    def name(self) -> str:
        return "openai_codex"

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
        return ["gpt-5.2-codex"]

    def capabilities(self, model: str) -> CapabilityDescriptor:
        _ = model
        return CapabilityDescriptor(
            implementation=True,
            test_implementation=True,
            code_review=True,
            shell_execution=True,
            mcp=True,
            structured_output=True,
            long_context=True,
            snapshot_support=True,
            reasoning_effort_levels=["low", "medium", "high"],
        )

    def supports_feature(self, feature_name: str) -> bool:
        return feature_name in {"structured_output", "shell", "mcp", "reasoning_effort"}

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
            f"You are Codex implementing a routed V2 task.\n"
            f"Task: {title}.\n"
            f"Read the provided artifact set and produce code or test changes inside the target project only.\n"
            f"Inputs: {', '.join(path.name for path in artifact_paths)}.\n"
            f"Keep the output deterministic and aligned with the existing scaffold and verification contract."
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
                "mode": "implementation",
                "reasoning_effort": (options or {}).get("reasoning_effort", "high"),
            },
        )

    def run_task(
        self,
        task_type: TaskType,
        artifact_paths: list[Path],
        model: str,
        options: dict[str, Any] | None = None,
    ) -> TaskExecutionResult:
        options = options or {}
        task_request_path = str(options.get("task_request_path", ""))
        resolved_inputs = [str(path) for path in artifact_paths]
        return TaskExecutionResult(
            provider=self.name(),
            model=model,
            task_type=task_type,
            status="stubbed",
            summary=f"Codex adapter stub prepared {task_type.value} using {len(artifact_paths)} input artifact(s).",
            input_artifact=resolved_inputs[0] if resolved_inputs else "",
            input_artifacts=resolved_inputs,
            artifact_paths=[task_request_path] if task_request_path else [],
            metadata=options,
        )
