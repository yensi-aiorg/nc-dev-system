from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ncdev.v2.jobs import materialize_fix_from_report
from ncdev.v2.models import (
    SentinelFailureReport,
    TaskType,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "sentinel_reports"


def _load_report(name: str) -> SentinelFailureReport:
    data = json.loads((FIXTURES / name).read_text())
    return SentinelFailureReport.model_validate(data)


class TestMaterializeFixFromReport:
    def test_creates_exactly_two_jobs(self, tmp_path: Path):
        run_dir = tmp_path / "run"
        (run_dir / "outputs").mkdir(parents=True)
        report = _load_report("backend_error.json")
        queue = materialize_fix_from_report(run_dir, report, "/target/repo", {})
        assert len(queue.jobs) == 2

    def test_correct_task_types(self, tmp_path: Path):
        run_dir = tmp_path / "run"
        (run_dir / "outputs").mkdir(parents=True)
        report = _load_report("backend_error.json")
        queue = materialize_fix_from_report(run_dir, report, "/target/repo", {})
        assert queue.jobs[0].task_type == TaskType.SENTINEL_REPRODUCE
        assert queue.jobs[1].task_type == TaskType.SENTINEL_FIX

    def test_correct_providers_and_models(self, tmp_path: Path):
        run_dir = tmp_path / "run"
        (run_dir / "outputs").mkdir(parents=True)
        report = _load_report("backend_error.json")
        queue = materialize_fix_from_report(run_dir, report, "/target/repo", {})
        assert queue.jobs[0].provider == "anthropic_claude_code"
        assert queue.jobs[0].model == "opus"
        assert queue.jobs[1].provider == "openai_codex"
        assert queue.jobs[1].model == "gpt-5.2-codex"

    def test_fix_depends_on_reproduce(self, tmp_path: Path):
        run_dir = tmp_path / "run"
        (run_dir / "outputs").mkdir(parents=True)
        report = _load_report("backend_error.json")
        queue = materialize_fix_from_report(run_dir, report, "/target/repo", {})
        reproduce_id = queue.jobs[0].job_id
        assert reproduce_id in queue.jobs[1].depends_on

    def test_job_ids_contain_report_id(self, tmp_path: Path):
        run_dir = tmp_path / "run"
        (run_dir / "outputs").mkdir(parents=True)
        report = _load_report("backend_error.json")
        queue = materialize_fix_from_report(run_dir, report, "/target/repo", {})
        assert report.report_id in queue.jobs[0].job_id
        assert report.report_id in queue.jobs[1].job_id

    def test_metadata_contains_report_id(self, tmp_path: Path):
        run_dir = tmp_path / "run"
        (run_dir / "outputs").mkdir(parents=True)
        report = _load_report("backend_error.json")
        queue = materialize_fix_from_report(run_dir, report, "/target/repo", {})
        for job in queue.jobs:
            assert job.metadata["report_id"] == report.report_id

    def test_persists_task_request_artifacts(self, tmp_path: Path):
        run_dir = tmp_path / "run"
        (run_dir / "outputs").mkdir(parents=True)
        report = _load_report("backend_error.json")
        queue = materialize_fix_from_report(run_dir, report, "/target/repo", {})
        for job in queue.jobs:
            assert Path(job.request_artifact).exists()

    def test_persists_job_queue_on_disk(self, tmp_path: Path):
        run_dir = tmp_path / "run"
        (run_dir / "outputs").mkdir(parents=True)
        report = _load_report("backend_error.json")
        materialize_fix_from_report(run_dir, report, "/target/repo", {})
        queue_path = run_dir / "outputs" / "job-queue.json"
        assert queue_path.exists()
        data = json.loads(queue_path.read_text())
        assert len(data["jobs"]) == 2

    def test_works_for_frontend_report(self, tmp_path: Path):
        run_dir = tmp_path / "run"
        (run_dir / "outputs").mkdir(parents=True)
        report = _load_report("frontend_error.json")
        queue = materialize_fix_from_report(run_dir, report, "/target/ui", {})
        assert len(queue.jobs) == 2
        assert queue.jobs[0].task_type == TaskType.SENTINEL_REPRODUCE
        assert queue.jobs[1].task_type == TaskType.SENTINEL_FIX
        assert report.report_id in queue.jobs[0].job_id

    def test_works_for_backend_report(self, tmp_path: Path):
        run_dir = tmp_path / "run"
        (run_dir / "outputs").mkdir(parents=True)
        report = _load_report("backend_error.json")
        queue = materialize_fix_from_report(run_dir, report, "/target/api", {})
        assert len(queue.jobs) == 2
        assert queue.project_name == report.service.name
