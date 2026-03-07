from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from ncdev.adapters.base import ProviderAdapter, ProviderVersionInfo, TaskExecutionResult
from ncdev.v2.models import CapabilityDescriptor, TaskType


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

    def run_task(
        self,
        task_type: TaskType,
        artifact_path: Path,
        model: str,
        options: dict[str, Any] | None = None,
    ) -> TaskExecutionResult:
        return TaskExecutionResult(
            provider=self.name(),
            model=model,
            task_type=task_type,
            status="stubbed",
            summary=f"Codex adapter stub invoked for {task_type.value} using {artifact_path.name}",
            metadata=options or {},
        )
