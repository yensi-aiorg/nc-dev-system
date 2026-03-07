from __future__ import annotations

import asyncio
import json
from pathlib import Path

from src.builder.codex_runner import CodexRunner, CodexRunnerError
from src.builder.reviewer import BuildReviewer

from ncdev.adapters.base import ProviderAdapter
from ncdev.v2.models import (
    ExecutionJob,
    JobQueueDoc,
    JobRunLogDoc,
    JobRunRecord,
    TaskType,
)


def _load_job_queue(path: Path) -> JobQueueDoc:
    return JobQueueDoc.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _job_output_path(run_dir: Path, job_id: str) -> Path:
    return run_dir / "logs" / "jobs" / f"{job_id}.json"


def _job_review_path(run_dir: Path, job_id: str) -> Path:
    return run_dir / "logs" / "jobs" / f"{job_id}-review.json"


async def _run_codex_job(job: ExecutionJob, run_dir: Path) -> JobRunRecord:
    runner = CodexRunner()
    reviewer = BuildReviewer()
    output_path = _job_output_path(run_dir, job.job_id)

    try:
        result = await runner.run(
            prompt_path=job.request_artifact,
            worktree_path=job.target_path,
            output_path=str(output_path),
        )
    except CodexRunnerError as exc:
        return JobRunRecord(
            job_id=job.job_id,
            task_type=job.task_type,
            provider=job.provider,
            model=job.model,
            status="failed",
            summary=str(exc),
            request_artifact=job.request_artifact,
            output_artifacts=[],
            metadata={"runner": "codex"},
        )

    feature = {
        "name": job.title,
        "expected_files": [],
    }
    review = await reviewer.review(job.target_path, feature)
    review_path = _job_review_path(run_dir, job.job_id)
    review_path.write_text(
        json.dumps(
            {
                "passed": review.passed,
                "issues": review.issues,
                "warnings": review.warnings,
                "test_results": review.test_results,
                "files_changed": review.files_changed,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    status = "passed" if result.success and review.passed else "failed"
    summary = (
        f"Codex job completed with review {'passed' if review.passed else 'failed'}; "
        f"{len(review.issues)} issue(s), {len(result.errors)} runner error(s)."
    )
    return JobRunRecord(
        job_id=job.job_id,
        task_type=job.task_type,
        provider=job.provider,
        model=job.model,
        status=status,
        summary=summary,
        request_artifact=job.request_artifact,
        output_artifacts=[str(output_path), str(review_path)],
        metadata={
            "files_created": result.files_created,
            "files_modified": result.files_modified,
            "runner_errors": result.errors,
            "review_passed": review.passed,
            "review_issues": review.issues,
        },
    )


async def _run_adapter_job(
    job: ExecutionJob,
    registry: dict[str, ProviderAdapter],
) -> JobRunRecord:
    adapter = registry[job.provider]
    input_paths = [Path(path) for path in job.input_artifacts]
    result = adapter.run_task(
        task_type=job.task_type,
        artifact_paths=input_paths,
        model=job.model,
        options={
            "task_request_path": job.request_artifact,
            "job_id": job.job_id,
            "target_path": job.target_path,
        },
    )
    return JobRunRecord(
        job_id=job.job_id,
        task_type=job.task_type,
        provider=job.provider,
        model=job.model,
        status=result.status,
        summary=result.summary,
        request_artifact=job.request_artifact,
        output_artifacts=result.artifact_paths,
        metadata=result.metadata,
    )


async def _run_job(
    job: ExecutionJob,
    run_dir: Path,
    registry: dict[str, ProviderAdapter],
    dry_run: bool,
) -> JobRunRecord:
    if dry_run:
        return JobRunRecord(
            job_id=job.job_id,
            task_type=job.task_type,
            provider=job.provider,
            model=job.model,
            status="dry-run",
            summary=f"Dry-run skipped execution for {job.job_id}.",
            request_artifact=job.request_artifact,
            output_artifacts=[],
            metadata={"depends_on": job.depends_on},
        )

    if job.provider == "openai_codex" and job.task_type in {
        TaskType.BUILD_BATCH,
        TaskType.TEST_AUTHORING,
        TaskType.FIX_BATCH,
    }:
        return await _run_codex_job(job, run_dir)

    if job.provider in registry:
        return await _run_adapter_job(job, registry)

    return JobRunRecord(
        job_id=job.job_id,
        task_type=job.task_type,
        provider=job.provider,
        model=job.model,
        status="skipped",
        summary=f"Provider {job.provider} is unavailable.",
        request_artifact=job.request_artifact,
        output_artifacts=[],
    )


def run_job_queue(
    run_dir: Path,
    registry: dict[str, ProviderAdapter],
    dry_run: bool,
) -> JobRunLogDoc:
    job_queue = _load_job_queue(run_dir / "outputs" / "job-queue.json")
    records: list[JobRunRecord] = []
    completed: dict[str, str] = {}

    for job in job_queue.jobs:
        blocked = [job_id for job_id in job.depends_on if completed.get(job_id) != "passed"]
        if blocked:
            records.append(
                JobRunRecord(
                    job_id=job.job_id,
                    task_type=job.task_type,
                    provider=job.provider,
                    model=job.model,
                    status="blocked",
                    summary=f"Blocked by incomplete dependencies: {', '.join(blocked)}",
                    request_artifact=job.request_artifact,
                    output_artifacts=[],
                    metadata={"blocked_by": blocked},
                )
            )
            completed[job.job_id] = "blocked"
            continue

        record = asyncio.run(_run_job(job, run_dir, registry, dry_run=dry_run))
        records.append(record)
        completed[job.job_id] = "passed" if record.status in {"passed", "stubbed", "dry-run"} else record.status

    return JobRunLogDoc(
        generator="ncdev.v2.job_runner",
        source_inputs=[str(run_dir / "outputs" / "job-queue.json")],
        project_name=job_queue.project_name,
        records=records,
    )
