from __future__ import annotations

import json
from pathlib import Path

from ncdev.v2.engine import run_v2_execute, run_v2_prepare
from ncdev.v2.job_runner import run_job_queue


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
