from pathlib import Path

from ncdev.v2.delivery import assemble_delivery_summary
from ncdev.v2.engine import run_v2_deliver, run_v2_discovery
from ncdev.v2.models import (
    BuildBatchV2,
    BuildPlanDoc,
    TargetProjectContractDoc,
    TaskType,
)


def _make_build_plan(project_name: str = "test-project") -> BuildPlanDoc:
    return BuildPlanDoc(
        generator="test",
        source_inputs=["req.md"],
        project_name=project_name,
        batches=[
            BuildBatchV2(
                id="batch-001",
                title="Implement auth",
                task_type=TaskType.BUILD_BATCH,
                summary="User can sign in",
                acceptance_criteria=["Auth flow works end-to-end"],
            ),
            BuildBatchV2(
                id="batch-002",
                title="Implement projects",
                task_type=TaskType.BUILD_BATCH,
                summary="User can manage projects",
                acceptance_criteria=["CRUD for projects tested"],
            ),
        ],
        risks=["Discovery is heuristic"],
    )


def _make_target_contract(project_name: str = "test-project") -> TargetProjectContractDoc:
    return TargetProjectContractDoc(
        generator="test",
        source_inputs=["req.md"],
        project_name=project_name,
        target_type="web",
        stack={"frontend": "React 19 + Vite", "backend": "FastAPI"},
        ownership_rules=["All generated code belongs in the target project"],
        required_artifacts=["frontend/", "backend/", "docker-compose.yml"],
    )


def test_assemble_delivery_summary_maps_batches() -> None:
    summary = assemble_delivery_summary(_make_build_plan(), _make_target_contract())

    assert summary.schema_id == "delivery-summary.v2"
    assert summary.project_name == "test-project"
    assert summary.target_type == "web"
    assert summary.stack == {"frontend": "React 19 + Vite", "backend": "FastAPI"}
    assert summary.batch_count == 2
    assert len(summary.batches) == 2
    assert summary.batches[0].batch_id == "batch-001"
    assert summary.batches[0].title == "Implement auth"
    assert summary.batches[0].acceptance_criteria == ["Auth flow works end-to-end"]
    assert summary.batches[1].batch_id == "batch-002"


def test_assemble_delivery_summary_includes_execution_steps() -> None:
    summary = assemble_delivery_summary(_make_build_plan(), _make_target_contract())

    assert len(summary.execution_steps) > 0
    steps_text = "\n".join(summary.execution_steps)
    assert "frontend/" in steps_text or "docker-compose.yml" in steps_text


def test_assemble_delivery_summary_preserves_risks_and_required_artifacts() -> None:
    summary = assemble_delivery_summary(_make_build_plan(), _make_target_contract())

    assert summary.risks == ["Discovery is heuristic"]
    assert summary.required_artifacts == ["frontend/", "backend/", "docker-compose.yml"]


def test_assemble_delivery_summary_includes_ownership_rules() -> None:
    summary = assemble_delivery_summary(_make_build_plan(), _make_target_contract())

    assert summary.ownership_rules == ["All generated code belongs in the target project"]


def test_run_v2_deliver_writes_delivery_summary(tmp_path: Path) -> None:
    req = tmp_path / "requirements.md"
    req.write_text(
        "# Product\n- User can sign in\n- User can manage projects\n",
        encoding="utf-8",
    )
    discovery_state = run_v2_discovery(tmp_path, req, dry_run=True)
    run_dir = Path(discovery_state.run_dir)

    state = run_v2_deliver(tmp_path, discovery_state.run_id)

    assert (run_dir / "outputs" / "delivery-summary.json").exists()
    delivery_task = next(t for t in state.tasks if t.name == "delivery_summary")
    assert delivery_task.status.value == "passed"
    assert len(delivery_task.artifacts) == 1


def test_v2_discovery_writes_contract_artifacts(tmp_path: Path) -> None:
    req = tmp_path / "requirements.md"
    req.write_text(
        """
# Product
- User can sign in
- User can manage projects
- User can review evidence
""".strip(),
        encoding="utf-8",
    )
    state = run_v2_discovery(tmp_path, req, dry_run=True)
    run_dir = Path(state.run_dir)
    assert state.status.value == "passed"
    assert (run_dir / "run-state.json").exists()
    assert (run_dir / "outputs" / "source-pack.json").exists()
    assert (run_dir / "outputs" / "research-pack.json").exists()
    assert (run_dir / "outputs" / "feature-map.json").exists()
    assert (run_dir / "outputs" / "design-pack.json").exists()
    assert (run_dir / "outputs" / "design-brief.json").exists()
    assert (run_dir / "outputs" / "build-plan.json").exists()
    assert (run_dir / "outputs" / "phase-plan.json").exists()
    assert (run_dir / "outputs" / "target-project-contract.json").exists()
    assert (run_dir / "outputs" / "scaffold-plan.json").exists()
    assert (run_dir / "outputs" / "capability-snapshot.json").exists()
    assert (run_dir / "outputs" / "routing-plan.json").exists()
    assert (run_dir / "outputs" / "execution-log.json").exists()
    assert (run_dir / "outputs" / "task-requests" / "source_ingest.json").exists()
    assert (run_dir / "outputs" / "task-requests" / "build_batch.json").exists()
