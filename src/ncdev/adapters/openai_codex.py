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
        if options.get("dry_run"):
            return TaskExecutionResult(
                provider=self.name(),
                model=model,
                task_type=task_type,
                status="stubbed",
                summary=f"Codex dry-run prepared {task_type.value} using {len(artifact_paths)} input artifact(s).",
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
                summary=f"Codex CLI unavailable for {task_type.value}.",
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

        result_path = self._result_path(task_request_path)
        cmd = [
            self.cli_name,
            "exec",
            "--full-auto",
            "--json",
        ]
        target_path = str(options.get("target_path", "")).strip()
        if target_path:
            cmd.extend(["--cd", target_path])
        cmd.append(prompt)
        if result_path is not None:
            result_path.parent.mkdir(parents=True, exist_ok=True)
            cmd.extend(["-o", str(result_path)])

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
                summary=f"Codex task {task_type.value} timed out after {timeout_seconds:.0f}s.",
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
        raw_output: dict[str, Any] = {}
        if result_path is not None and result_path.exists():
            try:
                raw_output = json.loads(result_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                raw_output = {}
        elif stdout.startswith("{"):
            try:
                raw_output = json.loads(stdout)
            except json.JSONDecodeError:
                raw_output = {}
        if result_path is not None and not result_path.exists():
            write_json(
                result_path,
                {
                    "task_type": task_type.value,
                    "provider": self.name(),
                    "model": model,
                    "returncode": proc.returncode,
                    "stdout": stdout,
                    "stderr": stderr,
                },
            )

        failure_kind = ""
        if proc.returncode != 0:
            failure_kind = "cli_error"
        elif result_path is not None and not raw_output and not stdout:
            failure_kind = "empty_result"

        return TaskExecutionResult(
            provider=self.name(),
            model=model,
            task_type=task_type,
            status="passed" if not failure_kind else "failed",
            summary=stdout[:500] if stdout else (stderr[:500] if stderr else f"Codex task {task_type.value} completed."),
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
