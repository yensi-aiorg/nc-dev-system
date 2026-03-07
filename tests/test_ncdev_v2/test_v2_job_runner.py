from __future__ import annotations

import json
from pathlib import Path

from ncdev.adapters.base import ProviderVersionInfo
from ncdev.v2.engine import run_v2_execute, run_v2_prepare
from ncdev.v2.job_runner import run_job_queue
from ncdev.v2.models import CapabilityDescriptor, JobRunLogDoc, JobRunRecord, TaskExecutionRecord, TaskType


def test_v2_execute_dry_run_writes_job_run_log(tmp_path: Path) -> None:
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
    prepared = run_v2_prepare(tmp_path, req, dry_run=True)
    executed = run_v2_execute(tmp_path, prepared.run_id, dry_run=True)
    run_dir = Path(executed.run_dir)

    assert executed.status.value == "passed"
    assert executed.metadata["job_run_count"] >= 3
    assert (run_dir / "outputs" / "job-run-log.json").exists()

    payload = json.loads((run_dir / "outputs" / "job-run-log.json").read_text(encoding="utf-8"))
    assert payload["records"]
    assert all(record["status"] == "dry-run" for record in payload["records"])


def test_v2_execute_tracks_failure_kinds_in_metadata(tmp_path: Path, monkeypatch) -> None:
    req = tmp_path / "requirements.md"
    req.write_text(
        """
# Product
- User can sign in
""".strip(),
        encoding="utf-8",
    )
    prepared = run_v2_prepare(tmp_path, req, dry_run=True)

    def fake_run_job_queue(run_dir, registry, dry_run, queue_name="job-queue.json"):
        return JobRunLogDoc(
            generator="test",
            source_inputs=[str(Path(run_dir) / "outputs" / queue_name)],
            project_name="requirements",
            records=[
                JobRunRecord(
                    job_id="batch-001",
                    task_type=TaskType.BUILD_BATCH,
                    provider="openai_codex",
                    model="gpt-5.2-codex",
                    status="failed",
                    summary="provider timeout",
                    request_artifact="x.json",
                    output_artifacts=[],
                    metadata={"failure_kind": "timeout"},
                ),
                JobRunRecord(
                    job_id="test-authoring",
                    task_type=TaskType.TEST_AUTHORING,
                    provider="openai_codex",
                    model="gpt-5.2-codex",
                    status="failed",
                    summary="cli unavailable",
                    request_artifact="y.json",
                    output_artifacts=[],
                    metadata={"failure_kind": "cli_unavailable"},
                ),
            ],
        )

    monkeypatch.setattr("ncdev.v2.engine.run_job_queue", fake_run_job_queue)

    executed = run_v2_execute(tmp_path, prepared.run_id, dry_run=False)

    assert executed.status.value == "failed"
    assert executed.metadata["job_failed_count"] == 2
    assert executed.metadata["job_failure_kinds"] == {
        "timeout": 1,
        "cli_unavailable": 1,
    }


def test_run_job_queue_executes_codex_jobs_with_mocked_runner(tmp_path: Path, monkeypatch) -> None:
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

    class FakeCodexResult:
        success = True
        files_created = ["frontend/src/generated.tsx"]
        files_modified = ["backend/app/main.py"]
        test_results = {"passed": 2, "failed": 0}
        errors: list[str] = []

    class FakeReviewResult:
        passed = True
        issues: list[str] = []
        warnings: list[str] = []
        test_results = {"total": {"passed": 2, "failed": 0}}
        files_changed = ["frontend/src/generated.tsx", "backend/app/main.py"]

    class FakeCodexRunner:
        async def run(self, prompt_path: str, worktree_path: str, output_path: str):
            job_name = Path(prompt_path).stem
            generated = Path(worktree_path) / "frontend" / "src" / f"{job_name}.tsx"
            generated.parent.mkdir(parents=True, exist_ok=True)
            generated.write_text(f"export const {job_name.replace('-', '_')} = true;\n", encoding="utf-8")
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).write_text('{"status":"ok"}', encoding="utf-8")
            return FakeCodexResult()

    class FakeReviewer:
        async def review(self, worktree_path: str, feature: dict):
            return FakeReviewResult()

    monkeypatch.setattr("ncdev.v2.job_runner.CodexRunner", FakeCodexRunner)
    monkeypatch.setattr("ncdev.v2.job_runner.BuildReviewer", FakeReviewer)

    log = run_job_queue(
        run_dir=run_dir,
        registry={},
        dry_run=False,
    )

    assert log.records
    build_records = [record for record in log.records if record.task_type == "build_batch"]
    assert build_records
    assert all(record.status == "passed" for record in build_records)
    assert any(Path(path).name.endswith("-review.json") for record in build_records for path in record.output_artifacts)
    assert all(record.metadata["merged"] is True for record in build_records)
    assert all(record.metadata["committed"] is True for record in build_records)
    qa_record = next(record for record in log.records if record.job_id == "qa-sweep")
    delivery_record = next(record for record in log.records if record.job_id == "delivery-pack")
    assert qa_record.status == "passed"
    assert delivery_record.status == "passed"
    assert any(Path(path).name.endswith("-findings.json") for path in qa_record.output_artifacts)
    assert any(Path(path).name.endswith("-report.md") for path in delivery_record.output_artifacts)


def test_run_job_queue_falls_back_to_secondary_provider(tmp_path: Path, monkeypatch) -> None:
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

    requests_dir = run_dir / "outputs" / "jobs" / "requests"
    for request_path in requests_dir.glob("batch-*.json"):
        payload = json.loads(request_path.read_text(encoding="utf-8"))
        payload["fallback_providers"] = ["anthropic_claude_code"]
        request_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    async def fake_codex_job(job, run_dir):
        return JobRunRecord(
            job_id=job.job_id,
            provider="openai_codex",
            model="gpt-5.2-codex",
            task_type=job.task_type,
            status="failed",
            summary="codex failed",
            request_artifact=job.request_artifact,
            artifact_paths=[],
            metadata={},
        )

    class FakeClaudeAdapter:
        def name(self) -> str:
            return "anthropic_claude_code"

        def healthcheck(self) -> bool:
            return True

        def version_info(self) -> ProviderVersionInfo:
            return ProviderVersionInfo(provider=self.name(), cli="claude", version="test")

        def available_models(self) -> list[str]:
            return ["opus"]

        def capabilities(self, model: str) -> CapabilityDescriptor:
            _ = model
            return CapabilityDescriptor(planning=True, code_review=True)

        def supports_feature(self, feature_name: str) -> bool:
            return False

        def build_task_request(self, task_type, artifact_paths, model, options=None):
            raise NotImplementedError

        def run_task(self, task_type, artifact_paths, model, options=None):
            return TaskExecutionRecord(
                provider="anthropic_claude_code",
                model=model,
                task_type=task_type,
                status="passed",
                summary="fallback passed",
                input_artifacts=[str(path) for path in artifact_paths],
                artifact_paths=[str(Path(options["task_request_path"]))],
                metadata={"adapter": "fake-claude"},
            )

    monkeypatch.setattr("ncdev.v2.job_runner._run_codex_job", fake_codex_job)

    log = run_job_queue(
        run_dir=run_dir,
        registry={"anthropic_claude_code": FakeClaudeAdapter()},
        dry_run=False,
    )

    build_records = [record for record in log.records if record.task_type == TaskType.BUILD_BATCH]
    assert build_records
    assert any(record.provider == "anthropic_claude_code" for record in build_records)
    assert any(record.metadata["fallback_from"] == "openai_codex" for record in build_records if record.provider == "anthropic_claude_code")
