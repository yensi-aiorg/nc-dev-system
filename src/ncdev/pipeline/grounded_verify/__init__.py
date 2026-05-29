# src/ncdev/pipeline/grounded_verify/__init__.py
"""Grounded agentic verifier — public entrypoint."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from ncdev.claude_session import run_claude_session
from ncdev.pipeline.grounded_verify.evidence import gather_evidence
from ncdev.pipeline.grounded_verify.hard_floor import check_hard_floor
from ncdev.pipeline.grounded_verify.judge import judge
from ncdev.pipeline.models import StepVerification

__all__ = ["grounded_verify"]


def grounded_verify(
    target_path: Path,
    *,
    feature_id: str,
    intent: str,
    pre_commit: str,
    backend_test_cmd: str | None,
    frontend_test_cmd: str | None,
    build_command: str | None = None,
    changed_files: list[str],
    diff: str,
    screenshots: list[str] | None = None,
    prior_context: str = "",
    step_dir: Path | None = None,
    session_runner: Callable = run_claude_session,
) -> StepVerification:
    ver = StepVerification()
    floor = check_hard_floor(target_path, pre_commit=pre_commit, changed_files=changed_files)
    if not floor.passed:
        ver.overall_passed = False
        ver.failure_reasons = [floor.reason]
        return ver

    evidence = gather_evidence(
        target_path, backend_test_cmd=backend_test_cmd,
        frontend_test_cmd=frontend_test_cmd, changed_files=changed_files,
        diff=diff, screenshots=screenshots or [], build_command=build_command,
    )
    verdict = judge(feature_id, intent, evidence, prior_context=prior_context,
                    target_path=target_path, session_runner=session_runner)

    ver.overall_passed = verdict.verdict == "PASS"
    ver.failure_reasons = [] if ver.overall_passed else list(verdict.reasons)

    if step_dir is not None:
        step_dir.mkdir(parents=True, exist_ok=True)
        (step_dir / "evidence-bundle.json").write_text(
            evidence.model_dump_json(indent=2), encoding="utf-8")
        (step_dir / "verdict.json").write_text(
            verdict.model_dump_json(indent=2), encoding="utf-8")
    return ver
