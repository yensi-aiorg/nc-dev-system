from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ncdev.adapters.base import ProviderAdapter, ProviderVersionInfo, TaskExecutionResult
from ncdev.utils import write_json
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
    TaskType.DESIGN_BRIEF: ["design-brief.json"],
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

    @staticmethod
    def _result_path(task_request_path: str) -> Path | None:
        if not task_request_path:
            return None
        request_path = Path(task_request_path)
        if request_path.parent.name == "task-requests":
            return request_path.parent.parent / "task-results" / request_path.name
        if request_path.parent.name == "requests":
            return request_path.parent.parent / "results" / request_path.name
        return request_path.with_name(f"{request_path.stem}.result.json")

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
        options = options or {}
        task_request_path = str(options.get("task_request_path", ""))
        resolved_inputs = [str(path) for path in artifact_paths]
        if options.get("dry_run"):
            return TaskExecutionResult(
                provider=self.name(),
                model=model,
                task_type=task_type,
                status="stubbed",
                summary=f"Claude dry-run prepared {task_type.value} using {len(artifact_paths)} input artifact(s).",
                input_artifact=resolved_inputs[0] if resolved_inputs else "",
                input_artifacts=resolved_inputs,
                artifact_paths=[task_request_path] if task_request_path else [],
                metadata=options,
            )
        if not self.healthcheck():
            return TaskExecutionResult(
                provider=self.name(),
                model=model,
                task_type=task_type,
                status="unavailable",
                summary=f"Claude CLI unavailable for {task_type.value}.",
                input_artifact=resolved_inputs[0] if resolved_inputs else "",
                input_artifacts=resolved_inputs,
                artifact_paths=[task_request_path] if task_request_path else [],
                metadata={**options, "failure_kind": "cli_unavailable"},
            )

        task_request = options.get("task_request")
        if not task_request and task_request_path and Path(task_request_path).exists():
            task_request = json.loads(Path(task_request_path).read_text(encoding="utf-8"))
        prompt = ""
        if isinstance(task_request, dict):
            prompt = str(task_request.get("prompt", ""))
        if not prompt:
            prompt = f"Complete task {task_type.value} using the provided artifacts."

        cmd = [
            self.cli_name,
            "-p",
            prompt,
            "--output-format",
            "json",
            "--model",
            model,
        ]
        target_path = str(options.get("target_path", "")).strip()
        if target_path:
            cmd.extend(["--cd", target_path])

        timeout_seconds = float(options.get("timeout_seconds", 600.0))
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            return TaskExecutionResult(
                provider=self.name(),
                model=model,
                task_type=task_type,
                status="failed",
                summary=f"Claude task {task_type.value} timed out after {timeout_seconds:.0f}s.",
                input_artifact=resolved_inputs[0] if resolved_inputs else "",
                input_artifacts=resolved_inputs,
                artifact_paths=[task_request_path] if task_request_path else [],
                metadata={
                    **options,
                    "failure_kind": "timeout",
                    "timeout_seconds": timeout_seconds,
                    "stdout": (exc.stdout or ""),
                    "stderr": (exc.stderr or ""),
                },
            )
        stdout = (proc.stdout or "").strip()
        stderr = (proc.stderr or "").strip()
        result_path = self._result_path(task_request_path)
        raw_output: dict[str, Any] = {}
        if stdout.startswith("{"):
            try:
                raw_output = json.loads(stdout)
            except json.JSONDecodeError:
                raw_output = {}
        if result_path is not None:
            payload = {
                "task_type": task_type.value,
                "provider": self.name(),
                "model": model,
                "returncode": proc.returncode,
                "stdout": stdout,
                "stderr": stderr,
            }
            write_json(result_path, payload)
        failure_kind = ""
        if proc.returncode != 0:
            failure_kind = "cli_error"
        elif result_path is not None and not raw_output and not stdout:
            failure_kind = "empty_result"
        summary = stdout[:500] if stdout else (stderr[:500] if stderr else f"Claude task {task_type.value} completed.")
        return TaskExecutionResult(
            provider=self.name(),
            model=model,
            task_type=task_type,
            status="passed" if not failure_kind else "failed",
            summary=summary,
            input_artifact=resolved_inputs[0] if resolved_inputs else "",
            input_artifacts=resolved_inputs,
            artifact_paths=[path for path in [task_request_path, str(result_path) if result_path else ""] if path],
            metadata={
                **options,
                "returncode": proc.returncode,
                "raw_output_keys": sorted(raw_output.keys()),
                "failure_kind": failure_kind,
                "stdout": stdout[:2000],
                "stderr": stderr[:2000],
            },
        )
