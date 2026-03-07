from __future__ import annotations

import json
from pathlib import Path

from ncdev.v2.engine import run_v2_full, run_v2_prepare, run_v2_repair
from ncdev.v2.jobs import materialize_repair_job_queue


def test_materialize_repair_job_queue_from_failed_job_log(tmp_path: Path) -> None:
    req = tmp_path / "requirements.md"
    req.write_text(
        """
# Product
- User can sign in
- User can manage projects
""".strip(),
        encoding="utf-8",
    )
    prepared = run_v2_prepare(tmp_path, req, dry_run=True)
    run_dir = Path(prepared.run_dir)

    (run_dir / "outputs" / "job-run-log.json").write_text(
        json.dumps(
            {
                "generator": "test",
                "schema_id": "job-run-log.v2",
                "version": "v2",
                "generated_at": "2026-03-07T00:00:00+00:00",
                "source_inputs": [],
                "project_name": "requirements",
                "records": [
                    {
                        "job_id": "batch-001",
                        "task_type": "build_batch",
                        "provider": "openai_codex",
                        "model": "gpt-5.2-codex",
                        "status": "failed",
                        "summary": "Build failed",
                        "request_artifact": "x.json",
                        "output_artifacts": [],
                        "metadata": {},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "outputs" / "verification-run.json").write_text(
        json.dumps(
            {
                "generator": "test",
                "schema_id": "verification-run.v2",
                "version": "v2",
                "generated_at": "2026-03-07T00:00:00+00:00",
                "source_inputs": [],
                "project_name": "requirements",
                "target_path": prepared.metadata["target_project_path"],
                "base_url": "http://localhost:23000",
                "routes": ["/"],
                "dry_run": True,
                "overall_passed": False,
                "summary": {"overall_passed": False},
                "report_path": "",
            }
        ),
        encoding="utf-8",
    )

    from ncdev.adapters.registry import build_provider_registry

    queue = materialize_repair_job_queue(run_dir, build_provider_registry())
    assert queue.jobs
    assert queue.jobs[0].task_type.value == "fix_batch"


def test_v2_repair_dry_run_writes_repair_artifacts(tmp_path: Path) -> None:
    req = tmp_path / "requirements.md"
    req.write_text(
        """
# Product
- User can sign in
- User can manage projects
""".strip(),
        encoding="utf-8",
    )
    prepared = run_v2_prepare(tmp_path, req, dry_run=True)
    run_dir = Path(prepared.run_dir)

    (run_dir / "outputs" / "job-run-log.json").write_text(
        json.dumps(
            {
                "generator": "test",
                "schema_id": "job-run-log.v2",
                "version": "v2",
                "generated_at": "2026-03-07T00:00:00+00:00",
                "source_inputs": [],
                "project_name": "requirements",
                "records": [
                    {
                        "job_id": "batch-001",
                        "task_type": "build_batch",
                        "provider": "openai_codex",
                        "model": "gpt-5.2-codex",
                        "status": "failed",
                        "summary": "Build failed",
                        "request_artifact": "x.json",
                        "output_artifacts": [],
                        "metadata": {},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "outputs" / "verification-run.json").write_text(
        json.dumps(
            {
                "generator": "test",
                "schema_id": "verification-run.v2",
                "version": "v2",
                "generated_at": "2026-03-07T00:00:00+00:00",
                "source_inputs": [],
                "project_name": "requirements",
                "target_path": prepared.metadata["target_project_path"],
                "base_url": "http://localhost:23000",
                "routes": ["/"],
                "dry_run": True,
                "overall_passed": False,
                "summary": {"overall_passed": False},
                "report_path": "",
            }
        ),
        encoding="utf-8",
    )

    repaired = run_v2_repair(tmp_path, prepared.run_id, dry_run=True)
    assert repaired.metadata["repair_job_count"] >= 1
    assert (run_dir / "outputs" / "repair-queue.json").exists()
    assert (run_dir / "outputs" / "repair-run-log.json").exists()


def test_v2_full_dry_run_completes_without_repairs(tmp_path: Path) -> None:
    req = tmp_path / "requirements.md"
    req.write_text(
        """
# Product
- User can sign in
- User can manage projects
""".strip(),
        encoding="utf-8",
    )
    state = run_v2_full(
        workspace=tmp_path,
        source_path=req,
        base_url="http://localhost:23000",
        dry_run=True,
        repair_cycles=1,
    )
    run_dir = Path(state.run_dir)
    assert state.status.value == "passed"
    assert state.metadata["repair_cycles_run"] == 0
    assert (run_dir / "outputs" / "full-run-report.json").exists()
    assert (run_dir / "outputs" / "full-run-summary.md").exists()
