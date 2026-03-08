from __future__ import annotations

import asyncio
import json
from pathlib import Path

from builder.codex_runner import CodexRunner, CodexRunnerError
from builder.reviewer import BuildReviewer
from builder.worktree import WorktreeError, WorktreeManager, _run_git

from ncdev.adapters.base import ProviderAdapter
from ncdev.utils import write_json, write_text
from ncdev.v2.models import (
    ExecutionJob,
    JobQueueDoc,
    JobRunLogDoc,
    JobRunRecord,
    TaskRequestDoc,
    TaskType,
)


def _load_job_queue(path: Path) -> JobQueueDoc:
    return JobQueueDoc.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _job_output_path(run_dir: Path, job_id: str) -> Path:
    return run_dir / "logs" / "jobs" / f"{job_id}.json"


def _job_review_path(run_dir: Path, job_id: str) -> Path:
    return run_dir / "logs" / "jobs" / f"{job_id}-review.json"


def _job_artifact_path(run_dir: Path, job_id: str, suffix: str) -> Path:
    return run_dir / "logs" / "jobs" / f"{job_id}-{suffix}"


def _load_json(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_task_request(path: str | Path) -> TaskRequestDoc:
    return TaskRequestDoc.model_validate(_load_json(path))


async def _current_branch(repo_path: Path) -> str:
    branch, _ = await _run_git(
        "rev-parse",
        "--abbrev-ref",
        "HEAD",
        cwd=repo_path,
    )
    return branch.strip() or "main"


async def _commit_worktree_changes(worktree_path: Path, job: ExecutionJob) -> tuple[bool, str]:
    status, _ = await _run_git(
        "status",
        "--porcelain",
        cwd=worktree_path,
    )
    if not status.strip():
        return False, "No worktree changes to commit."

    await _run_git("add", "-A", cwd=worktree_path)
    try:
        await _run_git(
            "-c",
            "user.name=NC Dev System",
            "-c",
            "user.email=ncdev@example.invalid",
            "commit",
            "-m",
            f"feat({job.job_id}): {job.title}",
            cwd=worktree_path,
        )
    except WorktreeError as exc:
        return False, str(exc)
    return True, "Committed worktree changes."


async def _run_codex_job(job: ExecutionJob, run_dir: Path) -> JobRunRecord:
    runner = CodexRunner()
    reviewer = BuildReviewer()
    output_path = _job_output_path(run_dir, job.job_id)
    target_repo = Path(job.target_path)
    manager = WorktreeManager(target_repo)
    base_branch = await _current_branch(target_repo)

    try:
        worktree = await manager.create(job.job_id, base_branch=base_branch)
    except WorktreeError as exc:
        return JobRunRecord(
            job_id=job.job_id,
            task_type=job.task_type,
            provider=job.provider,
            model=job.model,
            status="failed",
            summary=f"Worktree setup failed: {exc}",
            request_artifact=job.request_artifact,
            output_artifacts=[],
            metadata={"runner": "codex", "target_path": str(target_repo)},
        )

    try:
        result = await runner.run(
            prompt_path=job.request_artifact,
            worktree_path=str(worktree.path),
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
            output_artifacts=[str(worktree.path)],
            metadata={
                "runner": "codex",
                "target_path": str(target_repo),
                "worktree_path": str(worktree.path),
                "worktree_branch": worktree.branch,
                "preserved_worktree": True,
            },
        )

    feature = {
        "name": job.title,
        "expected_files": [],
    }
    review = await reviewer.review(str(worktree.path), feature)
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

    merged = False
    preserved_worktree = True
    merge_error = ""
    committed = False
    commit_message = ""
    if result.success and review.passed:
        committed, commit_message = await _commit_worktree_changes(worktree.path, job)
        if committed:
            merged = await manager.merge(job.job_id, target_branch=base_branch)
            if merged:
                await manager.cleanup(job.job_id)
                preserved_worktree = False
            else:
                merge_error = f"Merge failed back into {base_branch}."
        else:
            merge_error = commit_message

    status = "passed" if result.success and review.passed and committed and merged else "failed"
    summary = (
        f"Codex job completed with review {'passed' if review.passed else 'failed'}; "
        f"{len(review.issues)} issue(s), {len(result.errors)} runner error(s)."
    )
    if merge_error:
        summary = f"{summary} {merge_error}"
    return JobRunRecord(
        job_id=job.job_id,
        task_type=job.task_type,
        provider=job.provider,
        model=job.model,
        status=status,
        summary=summary,
        request_artifact=job.request_artifact,
        output_artifacts=[str(output_path), str(review_path), str(worktree.path)],
        metadata={
            "files_created": result.files_created,
            "files_modified": result.files_modified,
            "runner_errors": result.errors,
            "review_passed": review.passed,
            "review_issues": review.issues,
            "target_path": str(target_repo),
            "worktree_path": str(worktree.path),
            "worktree_branch": worktree.branch,
            "merged": merged,
            "committed": committed,
            "commit_summary": commit_message,
            "preserved_worktree": preserved_worktree,
            "base_branch": base_branch,
        },
    )


def _run_qa_job(job: ExecutionJob, run_dir: Path) -> JobRunRecord:
    target_path = Path(job.target_path)
    verification_contract = _load_json(next(path for path in job.input_artifacts if path.endswith("verification-contract.json")))
    evidence_paths = verification_contract.get("evidence_paths", [])
    missing_paths = [path for path in evidence_paths if not (target_path / path).exists()]
    findings_path = _job_artifact_path(run_dir, job.job_id, "findings.json")
    payload = {
        "target_path": str(target_path),
        "missing_evidence_paths": missing_paths,
        "required_checks": verification_contract.get("required_checks", []),
        "commands": verification_contract.get("commands", []),
        "summary": (
            "Evidence paths are incomplete."
            if missing_paths
            else "Verification contract evidence paths are present."
        ),
    }
    write_json(findings_path, payload)
    return JobRunRecord(
        job_id=job.job_id,
        task_type=job.task_type,
        provider=job.provider,
        model=job.model,
        status="passed",
        summary=payload["summary"],
        request_artifact=job.request_artifact,
        output_artifacts=[str(findings_path)],
        metadata=payload,
    )


def _run_delivery_job(job: ExecutionJob, run_dir: Path, records: list[JobRunRecord]) -> JobRunRecord:
    target_contract = _load_json(next(path for path in job.input_artifacts if path.endswith("verification-contract.json")))
    report_path = _job_artifact_path(run_dir, job.job_id, "report.md")
    passed = [record.job_id for record in records if record.status == "passed"]
    failed = [record.job_id for record in records if record.status == "failed"]
    blocked = [record.job_id for record in records if record.status == "blocked"]
    report = "\n".join(
        [
            "# Delivery Pack",
            "",
            f"Target project: `{job.target_path}`",
            f"Verification commands: {', '.join(target_contract.get('commands', []))}",
            "",
            f"Passed jobs: {', '.join(passed) if passed else 'none'}",
            f"Failed jobs: {', '.join(failed) if failed else 'none'}",
            f"Blocked jobs: {', '.join(blocked) if blocked else 'none'}",
        ]
    )
    write_text(report_path, report + "\n")
    return JobRunRecord(
        job_id=job.job_id,
        task_type=job.task_type,
        provider=job.provider,
        model=job.model,
        status="passed",
        summary="Delivery pack summary generated.",
        request_artifact=job.request_artifact,
        output_artifacts=[str(report_path)],
        metadata={
            "passed_jobs": passed,
            "failed_jobs": failed,
            "blocked_jobs": blocked,
        },
    )


async def _run_adapter_job(
    job: ExecutionJob,
    registry: dict[str, ProviderAdapter],
    *,
    provider_name: str | None = None,
    model_name: str | None = None,
) -> JobRunRecord:
    resolved_provider = provider_name or job.provider
    resolved_model = model_name or job.model
    adapter = registry[resolved_provider]
    input_paths = [Path(path) for path in job.input_artifacts]
    result = adapter.run_task(
        task_type=job.task_type,
        artifact_paths=input_paths,
        model=resolved_model,
        options={
            "task_request_path": job.request_artifact,
            "job_id": job.job_id,
            "target_path": job.target_path,
        },
    )
    return JobRunRecord(
        job_id=job.job_id,
        task_type=job.task_type,
        provider=resolved_provider,
        model=resolved_model,
        status=result.status,
        summary=result.summary,
        request_artifact=job.request_artifact,
        output_artifacts=result.artifact_paths,
        metadata=result.metadata,
    )


def _fallback_candidates(job: ExecutionJob) -> list[str]:
    if Path(job.request_artifact).exists():
        request = _load_task_request(job.request_artifact)
        return [provider for provider in request.fallback_providers if provider != job.provider]
    return [provider for provider in job.metadata.get("fallback_providers", []) if provider != job.provider]


def _fallback_model(adapter: ProviderAdapter, preferred_model: str) -> str:
    models = adapter.available_models()
    if preferred_model in models:
        return preferred_model
    return models[0] if models else preferred_model


async def _run_with_fallbacks(
    job: ExecutionJob,
    registry: dict[str, ProviderAdapter],
    primary_record: JobRunRecord,
) -> JobRunRecord:
    if primary_record.status in {"passed", "stubbed", "dry-run"}:
        return primary_record

    fallback_attempts: list[dict[str, str]] = []
    for provider_name in _fallback_candidates(job):
        if provider_name not in registry:
            fallback_attempts.append({"provider": provider_name, "status": "unavailable"})
            continue
        adapter = registry[provider_name]
        model_name = _fallback_model(adapter, job.model)
        if provider_name == "openai_codex" and job.task_type in {
            TaskType.BUILD_BATCH,
            TaskType.TEST_AUTHORING,
            TaskType.FIX_BATCH,
        }:
            fallback_record = await _run_codex_job(
                ExecutionJob(
                    job_id=job.job_id,
                    task_type=job.task_type,
                    provider=provider_name,
                    model=model_name,
                    title=job.title,
                    request_artifact=job.request_artifact,
                    target_path=job.target_path,
                    input_artifacts=job.input_artifacts,
                    depends_on=job.depends_on,
                    metadata=job.metadata,
                ),
                Path(job.request_artifact).parents[3],
            )
        else:
            fallback_record = await _run_adapter_job(
                job,
                registry,
                provider_name=provider_name,
                model_name=model_name,
            )
        fallback_record.metadata = {
            **fallback_record.metadata,
            "fallback_from": primary_record.provider,
            "fallback_attempts": fallback_attempts + [{"provider": provider_name, "status": fallback_record.status}],
        }
        if fallback_record.status in {"passed", "stubbed"}:
            return fallback_record
        fallback_attempts.append({"provider": provider_name, "status": fallback_record.status})

    primary_record.metadata = {
        **primary_record.metadata,
        "fallback_attempts": fallback_attempts,
    }
    return primary_record


async def _run_job(
    job: ExecutionJob,
    run_dir: Path,
    registry: dict[str, ProviderAdapter],
    dry_run: bool,
    prior_records: list[JobRunRecord],
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

    if job.task_type == TaskType.QA_SWEEP:
        return _run_qa_job(job, run_dir)

    if job.task_type == TaskType.DELIVERY_PACK:
        return _run_delivery_job(job, run_dir, prior_records)

    if job.provider == "openai_codex" and job.task_type in {
        TaskType.BUILD_BATCH,
        TaskType.TEST_AUTHORING,
        TaskType.FIX_BATCH,
    }:
        primary_record = await _run_codex_job(job, run_dir)
        return await _run_with_fallbacks(job, registry, primary_record)

    if job.provider in registry:
        primary_record = await _run_adapter_job(job, registry)
        return await _run_with_fallbacks(job, registry, primary_record)

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
    queue_name: str = "job-queue.json",
) -> JobRunLogDoc:
    queue_path = run_dir / "outputs" / queue_name
    job_queue = _load_job_queue(queue_path)
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

        record = asyncio.run(_run_job(job, run_dir, registry, dry_run=dry_run, prior_records=records))
        records.append(record)
        completed[job.job_id] = "passed" if record.status in {"passed", "stubbed", "dry-run"} else record.status

    return JobRunLogDoc(
        generator="ncdev.v2.job_runner",
        source_inputs=[str(queue_path)],
        project_name=job_queue.project_name,
        records=records,
    )
