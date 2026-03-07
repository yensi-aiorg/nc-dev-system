from __future__ import annotations

import json
from pathlib import Path

from ncdev.adapters.base import ProviderAdapter
from ncdev.utils import write_json
from ncdev.v2.models import (
    BuildPlanDoc,
    ExecutionJob,
    JobQueueDoc,
    JobRunLogDoc,
    RoutingDecision,
    RoutingPlanDoc,
    ScaffoldManifestDocV2,
    TaskRequestDoc,
    TaskType,
    TargetProjectContractDoc,
    VerificationContractDoc,
)


def _load_doc(path: Path, model_cls):
    return model_cls.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _routing_map(routing_doc: RoutingPlanDoc) -> dict[TaskType, RoutingDecision]:
    return {decision.task_type: decision for decision in routing_doc.decisions}


def _job_request_path(outputs_dir: Path, job_id: str) -> Path:
    return outputs_dir / "jobs" / "requests" / f"{job_id}.json"


def _persist_request(path: Path, request: TaskRequestDoc) -> str:
    write_json(path, request.model_dump(mode="json"))
    return str(path)


def _append_lines(base: str, lines: list[str]) -> str:
    extra = "\n".join(lines)
    return f"{base}\n{extra}" if extra else base


def materialize_job_queue(
    run_dir: Path,
    registry: dict[str, ProviderAdapter],
) -> JobQueueDoc:
    outputs_dir = run_dir / "outputs"
    build_plan = _load_doc(outputs_dir / "build-plan.json", BuildPlanDoc)
    routing_plan = _load_doc(outputs_dir / "routing-plan.json", RoutingPlanDoc)
    target_contract = _load_doc(outputs_dir / "target-project-contract.json", TargetProjectContractDoc)
    scaffold_manifest = _load_doc(outputs_dir / "scaffold-manifest.json", ScaffoldManifestDocV2)
    verification_contract = _load_doc(outputs_dir / "verification-contract.json", VerificationContractDoc)

    routing = _routing_map(routing_plan)
    jobs: list[ExecutionJob] = []

    build_decision = routing.get(TaskType.BUILD_BATCH)
    build_dependencies: list[str] = []
    if build_decision and build_decision.provider in registry:
        adapter = registry[build_decision.provider]
        build_inputs = [
            outputs_dir / "build-plan.json",
            outputs_dir / "target-project-contract.json",
            outputs_dir / "scaffold-plan.json",
            outputs_dir / "scaffold-manifest.json",
            outputs_dir / "verification-contract.json",
        ]
        for batch in build_plan.batches:
            request = adapter.build_task_request(
                task_type=TaskType.BUILD_BATCH,
                artifact_paths=build_inputs,
                model=build_decision.model,
                options={"fallback_providers": build_decision.fallback_providers},
            )
            request.title = f"{request.title}: {batch.title}"
            request.prompt = _append_lines(
                request.prompt,
                [
                    f"Batch ID: {batch.id}",
                    f"Batch summary: {batch.summary}",
                    "Acceptance criteria:",
                    *[f"- {criterion}" for criterion in batch.acceptance_criteria],
                ],
            )
            request.metadata.update(
                {
                    "batch_id": batch.id,
                    "batch_title": batch.title,
                    "target_path": scaffold_manifest.target_path,
                    "required_checks": verification_contract.required_checks,
                }
            )
            request_path = _persist_request(_job_request_path(outputs_dir, batch.id), request)
            jobs.append(
                ExecutionJob(
                    job_id=batch.id,
                    task_type=TaskType.BUILD_BATCH,
                    provider=build_decision.provider,
                    model=build_decision.model,
                    title=batch.title,
                    request_artifact=request_path,
                    target_path=scaffold_manifest.target_path,
                    input_artifacts=[str(path) for path in build_inputs],
                    depends_on=[],
                    metadata={"acceptance_criteria": batch.acceptance_criteria},
                )
            )
            build_dependencies.append(batch.id)

    def _append_single_job(
        job_id: str,
        task_type: TaskType,
        title: str,
        input_names: list[str],
        depends_on: list[str],
        extra_lines: list[str],
    ) -> None:
        decision = routing.get(task_type)
        if not decision or decision.provider not in registry:
            return
        adapter = registry[decision.provider]
        artifact_paths = [outputs_dir / name for name in input_names]
        request = adapter.build_task_request(
            task_type=task_type,
            artifact_paths=artifact_paths,
            model=decision.model,
            options={"fallback_providers": decision.fallback_providers},
        )
        request.title = title
        request.prompt = _append_lines(request.prompt, extra_lines)
        request.metadata.update(
            {
                "target_path": scaffold_manifest.target_path,
                "depends_on": depends_on,
            }
        )
        request_path = _persist_request(_job_request_path(outputs_dir, job_id), request)
        jobs.append(
            ExecutionJob(
                job_id=job_id,
                task_type=task_type,
                provider=decision.provider,
                model=decision.model,
                title=title,
                request_artifact=request_path,
                target_path=scaffold_manifest.target_path,
                input_artifacts=[str(path) for path in artifact_paths],
                depends_on=depends_on,
                metadata={"required_checks": verification_contract.required_checks},
            )
        )

    test_dependencies = list(build_dependencies)
    _append_single_job(
        job_id="test-authoring",
        task_type=TaskType.TEST_AUTHORING,
        title="Author target-project test coverage",
        input_names=["build-plan.json", "scaffold-manifest.json", "verification-contract.json"],
        depends_on=test_dependencies,
        extra_lines=[
            "Write or update tests inside the target project only.",
            "Include unit, integration, and Playwright coverage where applicable.",
            f"Required verification commands: {', '.join(verification_contract.commands)}",
        ],
    )
    _append_single_job(
        job_id="qa-sweep",
        task_type=TaskType.QA_SWEEP,
        title="Review generated evidence and verification coverage",
        input_names=["target-project-contract.json", "scaffold-manifest.json", "verification-contract.json"],
        depends_on=["test-authoring"] if test_dependencies else [],
        extra_lines=[
            "Review the generated test strategy against the target-project contract.",
            "Identify missing evidence paths, flaky areas, and user-visible risk.",
        ],
    )
    _append_single_job(
        job_id="delivery-pack",
        task_type=TaskType.DELIVERY_PACK,
        title="Assemble delivery pack summary",
        input_names=["build-plan.json", "scaffold-manifest.json", "verification-contract.json"],
        depends_on=["qa-sweep"],
        extra_lines=[
            "Summarize completed feature batches, remaining gaps, and required human review.",
            f"Target stack: {', '.join(f'{key}={value}' for key, value in target_contract.stack.items())}",
        ],
    )

    return JobQueueDoc(
        generator="ncdev.v2.jobs",
        source_inputs=[str(outputs_dir)],
        project_name=build_plan.project_name,
        jobs=jobs,
    )


def materialize_repair_job_queue(
    run_dir: Path,
    registry: dict[str, ProviderAdapter],
) -> JobQueueDoc:
    outputs_dir = run_dir / "outputs"
    routing_plan = _load_doc(outputs_dir / "routing-plan.json", RoutingPlanDoc)
    target_contract = _load_doc(outputs_dir / "target-project-contract.json", TargetProjectContractDoc)
    scaffold_manifest = _load_doc(outputs_dir / "scaffold-manifest.json", ScaffoldManifestDocV2)
    verification_contract = _load_doc(outputs_dir / "verification-contract.json", VerificationContractDoc)
    job_run_log = _load_doc(outputs_dir / "job-run-log.json", JobRunLogDoc)
    verification_run_path = outputs_dir / "verification-run.json"
    verification_run = json.loads(verification_run_path.read_text(encoding="utf-8")) if verification_run_path.exists() else {}

    routing = _routing_map(routing_plan)
    fix_decision = routing.get(TaskType.FIX_BATCH)
    if not fix_decision or fix_decision.provider not in registry:
        return JobQueueDoc(
            generator="ncdev.v2.jobs",
            source_inputs=[str(outputs_dir / "job-run-log.json")],
            project_name=target_contract.project_name,
            jobs=[],
        )

    adapter = registry[fix_decision.provider]
    jobs: list[ExecutionJob] = []
    failed_records = [record for record in job_run_log.records if record.status == "failed"]

    for idx, record in enumerate(failed_records, start=1):
        job_id = f"fix-{idx:03d}"
        artifact_paths = [
            outputs_dir / "build-plan.json",
            outputs_dir / "scaffold-manifest.json",
            outputs_dir / "verification-contract.json",
            outputs_dir / "job-run-log.json",
        ]
        artifact_paths.extend(Path(path) for path in record.output_artifacts if Path(path).exists())
        if verification_run_path.exists():
            artifact_paths.append(verification_run_path)
        request = adapter.build_task_request(
            task_type=TaskType.FIX_BATCH,
            artifact_paths=artifact_paths,
            model=fix_decision.model,
            options={"fallback_providers": fix_decision.fallback_providers},
        )
        request.title = f"Repair failed job: {record.job_id}"
        request.prompt = _append_lines(
            request.prompt,
            [
                f"Failed job id: {record.job_id}",
                f"Failed task type: {record.task_type.value}",
                f"Failure summary: {record.summary}",
                "Repair the target project so the original job and downstream verification pass.",
            ],
        )
        request.metadata.update(
            {
                "repair_target_job_id": record.job_id,
                "repair_target_task_type": record.task_type.value,
                "target_path": scaffold_manifest.target_path,
            }
        )
        request_path = _persist_request(_job_request_path(outputs_dir, job_id), request)
        jobs.append(
            ExecutionJob(
                job_id=job_id,
                task_type=TaskType.FIX_BATCH,
                provider=fix_decision.provider,
                model=fix_decision.model,
                title=f"Repair {record.job_id}",
                request_artifact=request_path,
                target_path=scaffold_manifest.target_path,
                input_artifacts=[str(path) for path in artifact_paths],
                depends_on=[],
                metadata={"repair_target_job_id": record.job_id},
            )
        )

    if verification_run and not verification_run.get("overall_passed", True) and not failed_records:
        job_id = "fix-verification"
        artifact_paths = [
            outputs_dir / "verification-run.json",
            outputs_dir / "evidence-index.json",
            outputs_dir / "verification-issues.json",
            outputs_dir / "verification-contract.json",
            outputs_dir / "scaffold-manifest.json",
        ]
        artifact_paths = [path for path in artifact_paths if path.exists()]
        request = adapter.build_task_request(
            task_type=TaskType.FIX_BATCH,
            artifact_paths=artifact_paths,
            model=fix_decision.model,
            options={"fallback_providers": fix_decision.fallback_providers},
        )
        request.title = "Repair verification failures"
        request.prompt = _append_lines(
            request.prompt,
            [
                "Verification did not pass after the initial execution phase.",
                f"Verification summary: {verification_run.get('summary', {})}",
                "Apply fixes in the target project and add regression coverage where possible.",
            ],
        )
        request.metadata.update({"repair_target_job_id": "verification"})
        request_path = _persist_request(_job_request_path(outputs_dir, job_id), request)
        jobs.append(
            ExecutionJob(
                job_id=job_id,
                task_type=TaskType.FIX_BATCH,
                provider=fix_decision.provider,
                model=fix_decision.model,
                title="Repair verification failures",
                request_artifact=request_path,
                target_path=scaffold_manifest.target_path,
                input_artifacts=[str(path) for path in artifact_paths],
                depends_on=[],
                metadata={"repair_target_job_id": "verification"},
            )
        )

    return JobQueueDoc(
        generator="ncdev.v2.jobs",
        source_inputs=[
            str(outputs_dir / "job-run-log.json"),
            str(verification_run_path) if verification_run_path.exists() else "",
        ],
        project_name=target_contract.project_name,
        jobs=jobs,
    )
