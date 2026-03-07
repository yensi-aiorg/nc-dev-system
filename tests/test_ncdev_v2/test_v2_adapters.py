import subprocess
from pathlib import Path
from unittest.mock import patch

from ncdev.adapters.registry import build_provider_registry, probe_registry_capabilities
from ncdev.v2.models import TaskType


def test_registry_contains_default_adapters() -> None:
    registry = build_provider_registry()
    assert "anthropic_claude_code" in registry
    assert "openai_codex" in registry


def test_capability_probe_emits_snapshots() -> None:
    registry = build_provider_registry()
    doc = probe_registry_capabilities(registry)
    assert len(doc.snapshots) >= 2
    providers = {snapshot.provider for snapshot in doc.snapshots}
    assert "anthropic_claude_code" in providers
    assert "openai_codex" in providers


def test_claude_adapter_run_task_writes_result_artifact(tmp_path: Path) -> None:
    adapter = build_provider_registry()["anthropic_claude_code"]
    task_request = tmp_path / "outputs" / "task-requests" / "market_research.json"
    task_request.parent.mkdir(parents=True, exist_ok=True)
    task_request.write_text('{"prompt":"Summarize research."}', encoding="utf-8")

    class FakeCompleted:
        returncode = 0
        stdout = '{"ok": true}'
        stderr = ""

    with patch("shutil.which", return_value="/usr/bin/claude"):
        with patch("subprocess.run", return_value=FakeCompleted()):
            result = adapter.run_task(
                task_type=TaskType.MARKET_RESEARCH,
                artifact_paths=[tmp_path / "outputs" / "research-pack.json"],
                model="opus",
                options={"task_request_path": str(task_request)},
            )

    assert result.status == "passed"
    result_path = tmp_path / "outputs" / "task-results" / "market_research.json"
    assert result_path.exists()
    assert str(result_path) in result.artifact_paths


def test_codex_adapter_run_task_writes_result_artifact(tmp_path: Path) -> None:
    adapter = build_provider_registry()["openai_codex"]
    task_request = tmp_path / "outputs" / "task-requests" / "test_authoring.json"
    task_request.parent.mkdir(parents=True, exist_ok=True)
    task_request.write_text('{"prompt":"Write tests."}', encoding="utf-8")

    class FakeCompleted:
        returncode = 0
        stdout = '{"ok": true, "changed": ["frontend/src/app.tsx"]}'
        stderr = ""

    with patch("shutil.which", return_value="/usr/bin/codex"):
        with patch("subprocess.run", return_value=FakeCompleted()) as mock_run:
            result = adapter.run_task(
                task_type=TaskType.TEST_AUTHORING,
                artifact_paths=[tmp_path / "outputs" / "build-plan.json"],
                model="gpt-5.2-codex",
                options={
                    "task_request_path": str(task_request),
                    "target_path": str(tmp_path),
                },
            )

    assert result.status == "passed"
    result_path = tmp_path / "outputs" / "task-results" / "test_authoring.json"
    assert result_path.exists()
    assert str(result_path) in result.artifact_paths
    called_cmd = mock_run.call_args.args[0]
    assert called_cmd[:4] == ["codex", "exec", "--full-auto", "--json"]
    assert "--cd" in called_cmd


def test_claude_adapter_timeout_is_classified(tmp_path: Path) -> None:
    adapter = build_provider_registry()["anthropic_claude_code"]
    task_request = tmp_path / "outputs" / "task-requests" / "market_research.json"
    task_request.parent.mkdir(parents=True, exist_ok=True)
    task_request.write_text('{"prompt":"Summarize research."}', encoding="utf-8")

    timeout = subprocess.TimeoutExpired(cmd=["claude"], timeout=30)
    with patch("shutil.which", return_value="/usr/bin/claude"):
        with patch("subprocess.run", side_effect=timeout):
            result = adapter.run_task(
                task_type=TaskType.MARKET_RESEARCH,
                artifact_paths=[tmp_path / "outputs" / "research-pack.json"],
                model="opus",
                options={"task_request_path": str(task_request), "timeout_seconds": 30},
            )

    assert result.status == "failed"
    assert result.metadata["failure_kind"] == "timeout"
    assert "timed out" in result.summary


def test_codex_adapter_timeout_is_classified(tmp_path: Path) -> None:
    adapter = build_provider_registry()["openai_codex"]
    task_request = tmp_path / "outputs" / "task-requests" / "test_authoring.json"
    task_request.parent.mkdir(parents=True, exist_ok=True)
    task_request.write_text('{"prompt":"Write tests."}', encoding="utf-8")

    timeout = subprocess.TimeoutExpired(cmd=["codex"], timeout=45)
    with patch("shutil.which", return_value="/usr/bin/codex"):
        with patch("subprocess.run", side_effect=timeout):
            result = adapter.run_task(
                task_type=TaskType.TEST_AUTHORING,
                artifact_paths=[tmp_path / "outputs" / "build-plan.json"],
                model="gpt-5.2-codex",
                options={
                    "task_request_path": str(task_request),
                    "target_path": str(tmp_path),
                    "timeout_seconds": 45,
                },
            )

    assert result.status == "failed"
    assert result.metadata["failure_kind"] == "timeout"
    assert "timed out" in result.summary
