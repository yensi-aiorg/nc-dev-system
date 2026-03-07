from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from ncdev.adapters.base import ProviderAdapter, ProviderVersionInfo, TaskExecutionResult
from ncdev.v2.models import CapabilityDescriptor, TaskType


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
            summary=f"Claude Code adapter stub invoked for {task_type.value} using {artifact_path.name}",
            metadata=options or {},
        )
