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
    report = json.loads((run_dir / "outputs" / "full-run-report.json").read_text(encoding="utf-8"))
    assert report["readiness_decision"] == "simulation_only"
    assert report["release_recommendation"] == "do_not_release"


def test_v2_full_report_blocks_when_verification_fails(tmp_path: Path) -> None:
    req = tmp_path / "requirements.md"
    req.write_text(
        """
# Product
- User can sign in
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
                "records": [],
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
                "dry_run": False,
                "bootstrap_succeeded": False,
                "overall_passed": False,
                "summary": {"overall_passed": False, "bootstrap_error": "unreachable"},
                "report_path": "",
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "outputs" / "verification-issues.json").write_text(
        json.dumps(
            {
                "generator": "test",
                "schema_id": "verification-issues.v2",
                "version": "v2",
                "generated_at": "2026-03-07T00:00:00+00:00",
                "source_inputs": [],
                "project_name": "requirements",
                "target_path": prepared.metadata["target_project_path"],
                "issue_count": 2,
                "issues": [
                    {"issue_id": "bootstrap-unreachable", "title": "bootstrap", "severity": "high", "category": "bootstrap", "expected": "", "actual": "", "related_artifacts": []},
                    {"issue_id": "missing-evidence", "title": "evidence", "severity": "medium", "category": "evidence", "expected": "", "actual": "", "related_artifacts": []},
                ],
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "outputs" / "evidence-index.json").write_text(
        json.dumps(
            {
                "generator": "test",
                "schema_id": "evidence-index.v2",
                "version": "v2",
                "generated_at": "2026-03-07T00:00:00+00:00",
                "source_inputs": [],
                "project_name": "requirements",
                "target_path": prepared.metadata["target_project_path"],
                "screenshots": [],
                "reports": [],
                "videos": [],
                "traces": [],
            }
        ),
        encoding="utf-8",
    )

    from ncdev.artifacts.state import persist_v2_run_state
    from ncdev.v2.engine import load_v2_run_state, run_v2_deliver, _build_full_run_report

    state = load_v2_run_state(tmp_path, prepared.run_id)
    state.metadata["dry_run"] = False
    state.metadata["verification_passed"] = False
    state.metadata["bootstrap_succeeded"] = False
    state.metadata["teardown_succeeded"] = False
    state.metadata["verification_issue_count"] = 2
    state.metadata["repair_cycles_requested"] = 1
    state.metadata["repair_cycles_run"] = 1
    persist_v2_run_state(state)
    run_v2_deliver(tmp_path, prepared.run_id)
    state = load_v2_run_state(tmp_path, prepared.run_id)
    report = _build_full_run_report(state)

    assert report.readiness_decision == "blocked"
    assert report.release_recommendation == "hold"
    assert report.blockers


def test_v2_full_report_surfaces_provider_failure_kinds(tmp_path: Path) -> None:
    req = tmp_path / "requirements.md"
    req.write_text(
        """
# Product
- User can sign in
""".strip(),
        encoding="utf-8",
    )
    prepared = run_v2_prepare(tmp_path, req, dry_run=True)
    run_dir = Path(prepared.run_dir)

    from ncdev.artifacts.state import persist_v2_run_state
    from ncdev.v2.engine import _build_full_run_report, load_v2_run_state, run_v2_deliver

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
                "dry_run": False,
                "bootstrap_succeeded": True,
                "overall_passed": True,
                "summary": {"overall_passed": True},
                "report_path": "",
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "outputs" / "verification-issues.json").write_text(
        json.dumps(
            {
                "generator": "test",
                "schema_id": "verification-issues.v2",
                "version": "v2",
                "generated_at": "2026-03-07T00:00:00+00:00",
                "source_inputs": [],
                "project_name": "requirements",
                "target_path": prepared.metadata["target_project_path"],
                "issue_count": 0,
                "issues": [],
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "outputs" / "evidence-index.json").write_text(
        json.dumps(
            {
                "generator": "test",
                "schema_id": "evidence-index.v2",
                "version": "v2",
                "generated_at": "2026-03-07T00:00:00+00:00",
                "source_inputs": [],
                "project_name": "requirements",
                "target_path": prepared.metadata["target_project_path"],
                "screenshots": ["a.png"],
                "reports": ["report.json"],
                "videos": [],
                "traces": [],
            }
        ),
        encoding="utf-8",
    )

    state = load_v2_run_state(tmp_path, prepared.run_id)
    state.metadata["dry_run"] = False
    state.metadata["verification_passed"] = True
    state.metadata["bootstrap_succeeded"] = True
    state.metadata["teardown_succeeded"] = True
    state.metadata["verification_issue_count"] = 0
    state.metadata["job_failure_kinds"] = {"timeout": 1}
    state.metadata["repair_failure_kinds"] = {"cli_unavailable": 2}
    persist_v2_run_state(state)
    run_v2_deliver(tmp_path, prepared.run_id)
    state = load_v2_run_state(tmp_path, prepared.run_id)
    report = _build_full_run_report(state)

    assert report.readiness_decision == "blocked"
    assert any("Provider execution failures were detected" in blocker for blocker in report.blockers)
    assert report.metadata["provider_failure_kinds"] == {"timeout": 1, "cli_unavailable": 2}
