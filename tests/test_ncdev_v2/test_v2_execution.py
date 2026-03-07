from pathlib import Path

from ncdev.adapters.registry import build_provider_registry
from ncdev.utils import read_text
from ncdev.utils import write_json
from ncdev.v2.execution import execute_routed_tasks
from ncdev.v2.models import RoutingDecision, RoutingPlanDoc, TaskType


def test_execute_routed_tasks_records_stubbed_results(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    write_json(outputs / "source-pack.json", {"ok": True})
    write_json(outputs / "research-pack.json", {"ok": True})
    write_json(outputs / "feature-map.json", {"ok": True})
    write_json(outputs / "design-pack.json", {"ok": True})
    write_json(outputs / "build-plan.json", {"ok": True})
    write_json(outputs / "target-project-contract.json", {"ok": True})
    write_json(outputs / "scaffold-plan.json", {"ok": True})

    routing = RoutingPlanDoc(
        generator="test",
        source_inputs=[],
        decisions=[
            RoutingDecision(task_type=TaskType.SOURCE_INGEST, provider="anthropic_claude_code", model="opus", rationale="test"),
            RoutingDecision(task_type=TaskType.MARKET_RESEARCH, provider="anthropic_claude_code", model="opus", rationale="test"),
            RoutingDecision(task_type=TaskType.FEATURE_EXTRACTION, provider="anthropic_claude_code", model="opus", rationale="test"),
            RoutingDecision(task_type=TaskType.DESIGN_BRIEF, provider="anthropic_claude_code", model="opus", rationale="test"),
            RoutingDecision(task_type=TaskType.BUILD_BATCH, provider="openai_codex", model="gpt-5.2-codex", rationale="test"),
            RoutingDecision(task_type=TaskType.TEST_AUTHORING, provider="openai_codex", model="gpt-5.2-codex", rationale="test"),
        ],
    )
    log = execute_routed_tasks(routing, build_provider_registry(), outputs)
    assert len(log.results) == 6
    assert all(result.status == "stubbed" for result in log.results)
    assert all(result.artifact_paths for result in log.results)
    assert (outputs / "task-requests" / "source_ingest.json").exists()
    assert (outputs / "task-requests" / "build_batch.json").exists()
    build_request = read_text(outputs / "task-requests" / "build_batch.json")
    assert "Codex implementing a routed V2 task" in build_request
