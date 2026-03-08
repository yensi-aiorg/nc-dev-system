from __future__ import annotations

import asyncio
import json
import os
import shutil
import shlex
import signal
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from tester.results import TestSuiteResults
from tester.runner import TestRunner

from ncdev.utils import write_json
from ncdev.v2.models import (
    BootstrapCommandRecord,
    BootstrapRunDoc,
    EvidenceIndexDoc,
    VerificationIssue,
    VerificationIssueBundleDoc,
    VerificationRunDoc,
)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _derive_routes(feature_map: dict) -> list[str]:
    routes = ["/"]
    for feature in feature_map.get("features", []):
        name = str(feature.get("name", "")).strip().lower()
        if not name:
            continue
        slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in name).strip("-")
        if slug:
            route = f"/{slug}"
            if route not in routes:
                routes.append(route)
    return routes


def _build_evidence_index(target_path: Path, project_name: str) -> EvidenceIndexDoc:
    screenshot_dirs = [
        target_path / ".nc-dev" / "screenshots",
        target_path / "frontend" / "e2e" / "screenshots",
    ]
    reports_dir = target_path / ".nc-dev" / "test-reports"
    playwright_report = target_path / "frontend" / "playwright-report"
    test_results_dir = target_path / "frontend" / "test-results"

    screenshots: list[str] = []
    for screenshots_dir in screenshot_dirs:
        if screenshots_dir.exists():
            screenshots.extend(
                sorted(
                    str(path)
                    for path in screenshots_dir.rglob("*")
                    if path.is_file() and path.name != ".gitkeep"
                )
            )
    reports = sorted(str(path) for path in reports_dir.rglob("*") if path.is_file()) if reports_dir.exists() else []
    videos = sorted(str(path) for path in test_results_dir.rglob("*.webm")) if test_results_dir.exists() else []
    traces = sorted(str(path) for path in test_results_dir.rglob("trace.zip")) if test_results_dir.exists() else []
    if playwright_report.exists():
        reports.extend(sorted(str(path) for path in playwright_report.rglob("*") if path.is_file()))

    return EvidenceIndexDoc(
        generator="ncdev.v2.verification",
        source_inputs=[str(target_path)],
        project_name=project_name,
        target_path=str(target_path),
        screenshots=screenshots,
        reports=sorted(set(reports)),
        videos=videos,
        traces=traces,
    )


def _build_verification_issues(
    project_name: str,
    target_path: Path,
    verification_run: VerificationRunDoc,
    evidence_index: EvidenceIndexDoc,
    bootstrap_run: BootstrapRunDoc,
    verification_contract: dict,
) -> VerificationIssueBundleDoc:
    issues: list[VerificationIssue] = []
    required_viewports = [
        str(viewport).strip()
        for viewport in verification_contract.get("required_viewports", [])
        if str(viewport).strip()
    ]
    required_checks = {
        str(check).strip()
        for check in verification_contract.get("required_checks", [])
        if str(check).strip()
    }
    expected_screenshots = len(verification_run.routes) * len(required_viewports)

    bootstrap_commands = [record.command for record in getattr(bootstrap_run, "commands", [])]
    teardown_attempted = bool(getattr(bootstrap_run, "teardown_attempted", False))
    teardown_succeeded = bool(getattr(bootstrap_run, "teardown_succeeded", False))
    teardown_commands = [record.command for record in getattr(bootstrap_run, "teardown_commands", [])]

    if not verification_run.bootstrap_succeeded:
        issues.append(
            VerificationIssue(
                issue_id="bootstrap-unreachable",
                title="Target project did not become reachable",
                severity="high",
                category="bootstrap",
                expected=f"{verification_run.base_url} should be reachable before verification runs.",
                actual=verification_run.summary.get(
                    "bootstrap_error",
                    f"{verification_run.base_url} remained unreachable after bootstrap attempts.",
                ),
                related_artifacts=bootstrap_commands,
            )
        )

    runner_error = str(verification_run.summary.get("runner_error", "")).strip()
    if runner_error:
        issues.append(
            VerificationIssue(
                issue_id="verification-runner-error",
                title="Verification runner raised an exception",
                severity="high",
                category="verification",
                expected="Verification should complete and produce a stable result summary.",
                actual=runner_error,
                related_artifacts=[verification_run.report_path] if verification_run.report_path else [],
            )
        )

    e2e_summary = verification_run.summary.get("e2e", {})
    if isinstance(e2e_summary, dict) and int(e2e_summary.get("failed", 0)) > 0:
        issues.append(
            VerificationIssue(
                issue_id="e2e-failures",
                title="End-to-end verification failures detected",
                severity="high",
                category="e2e",
                expected="All Playwright or route-level E2E checks should pass.",
                actual=f"{e2e_summary.get('failed', 0)} E2E checks failed.",
                related_artifacts=evidence_index.videos + evidence_index.traces,
            )
        )

    missing_evidence = [
        str(target_path / rel_path)
        for rel_path in verification_contract.get("evidence_paths", [])
        if not (target_path / rel_path).exists()
    ]
    if missing_evidence:
        issues.append(
            VerificationIssue(
                issue_id="missing-evidence",
                title="Verification evidence paths are incomplete",
                severity="medium",
                category="evidence",
                expected="All required evidence directories should exist after verification.",
                actual=", ".join(missing_evidence),
                related_artifacts=missing_evidence,
            )
        )

    if required_viewports and expected_screenshots > 0 and len(evidence_index.screenshots) < expected_screenshots:
        issues.append(
            VerificationIssue(
                issue_id="missing-screenshots",
                title="Required screenshot coverage is incomplete",
                severity="high",
                category="evidence",
                expected=(
                    f"{expected_screenshots} screenshots across "
                    f"{len(verification_run.routes)} routes and {len(required_viewports)} viewports."
                ),
                actual=f"Only {len(evidence_index.screenshots)} screenshots were captured.",
                related_artifacts=evidence_index.screenshots,
            )
        )

    if {"unit", "integration", "e2e"} & required_checks and not evidence_index.reports:
        issues.append(
            VerificationIssue(
                issue_id="missing-test-reports",
                title="Verification reports are missing",
                severity="high",
                category="evidence",
                expected="Verification should emit at least one persisted test report artifact.",
                actual="No report files were found in the configured evidence locations.",
                related_artifacts=[str(target_path / rel_path) for rel_path in verification_contract.get("evidence_paths", [])],
            )
        )

    if isinstance(e2e_summary, dict) and int(e2e_summary.get("failed", 0)) > 0 and not (evidence_index.traces or evidence_index.videos):
        issues.append(
            VerificationIssue(
                issue_id="missing-e2e-diagnostics",
                title="E2E failures did not produce trace or video diagnostics",
                severity="medium",
                category="evidence",
                expected="Failed E2E runs should capture trace or video artifacts for triage.",
                actual="No trace.zip or .webm files were found for the failing E2E run.",
                related_artifacts=evidence_index.reports,
            )
        )

    if teardown_attempted and not teardown_succeeded:
        issues.append(
            VerificationIssue(
                issue_id="teardown-failed",
                title="Verification teardown did not fully succeed",
                severity="medium",
                category="teardown",
                expected="Services started for verification should be shut down cleanly afterward.",
                actual="One or more teardown commands returned a non-zero exit code.",
                related_artifacts=teardown_commands,
            )
        )

    return VerificationIssueBundleDoc(
        generator="ncdev.v2.verification",
        source_inputs=[str(target_path)],
        project_name=project_name,
        target_path=str(target_path),
        issue_count=len(issues),
        issues=issues,
    )


def _url_reachable(base_url: str) -> bool:
    try:
        with urllib.request.urlopen(base_url, timeout=2.0) as response:
            return 200 <= response.status < 500
    except (urllib.error.URLError, TimeoutError, ValueError):
        return False


def _command_log_path(log_dir: Path, prefix: str, stream: str) -> Path:
    return log_dir / f"{prefix}-{stream}.log"


def _resolve_healthcheck_url(base_url: str, verification_contract: dict) -> str:
    override = str(verification_contract.get("healthcheck_url", "")).strip()
    if override:
        return override
    healthcheck_path = str(verification_contract.get("healthcheck_path", "/")).strip() or "/"
    if healthcheck_path.startswith(("http://", "https://")):
        return healthcheck_path
    normalized_base = base_url.rstrip("/")
    normalized_path = healthcheck_path if healthcheck_path.startswith("/") else f"/{healthcheck_path}"
    return f"{normalized_base}{normalized_path}"


def _wait_for_reachability(base_url: str, timeout_seconds: int = 45, interval_seconds: int = 1) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if _url_reachable(base_url):
            return True
        time.sleep(max(1, interval_seconds))
    return False


def _run_logged_command(target_path: Path, log_dir: Path, prefix: str, stage: str, cmd: list[str]) -> BootstrapCommandRecord:
    proc = subprocess.run(
        cmd,
        cwd=str(target_path),
        capture_output=True,
        text=True,
        check=False,
    )
    stdout_path = _command_log_path(log_dir, prefix, "stdout")
    stderr_path = _command_log_path(log_dir, prefix, "stderr")
    stdout_path.write_text(proc.stdout or "", encoding="utf-8")
    stderr_path.write_text(proc.stderr or "", encoding="utf-8")
    return BootstrapCommandRecord(
        stage=stage,
        command=" ".join(cmd),
        return_code=proc.returncode,
        succeeded=proc.returncode == 0,
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
    )


def _run_background_command(
    target_path: Path,
    log_dir: Path,
    prefix: str,
    stage: str,
    command_text: str,
) -> BootstrapCommandRecord:
    stdout_path = _command_log_path(log_dir, prefix, "stdout")
    stderr_path = _command_log_path(log_dir, prefix, "stderr")
    stdout_handle = stdout_path.open("w", encoding="utf-8")
    stderr_handle = stderr_path.open("w", encoding="utf-8")
    try:
        proc = subprocess.Popen(
            shlex.split(command_text),
            cwd=str(target_path),
            stdout=stdout_handle,
            stderr=stderr_handle,
            text=True,
            start_new_session=True,
        )
    finally:
        stdout_handle.close()
        stderr_handle.close()
    return BootstrapCommandRecord(
        stage=stage,
        command=command_text,
        return_code=None,
        succeeded=True,
        background=True,
        pid=proc.pid,
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
    )


def _terminate_background_process(record: BootstrapCommandRecord, log_dir: Path, index: int) -> BootstrapCommandRecord:
    if not record.pid:
        return BootstrapCommandRecord(
            stage="teardown",
            command=f"terminate {record.command}",
            return_code=None,
            succeeded=False,
            background=True,
            pid=record.pid,
        )

    stdout_path = _command_log_path(log_dir, f"teardown-{index:02d}", "stdout")
    stderr_path = _command_log_path(log_dir, f"teardown-{index:02d}", "stderr")
    try:
        os.killpg(record.pid, signal.SIGTERM)
        succeeded = True
        return_code = 0
        stderr_text = ""
    except ProcessLookupError:
        succeeded = True
        return_code = 0
        stderr_text = ""
    except OSError as exc:
        succeeded = False
        return_code = 1
        stderr_text = str(exc)

    stdout_path.write_text("", encoding="utf-8")
    stderr_path.write_text(stderr_text, encoding="utf-8")
    return BootstrapCommandRecord(
        stage="teardown",
        command=f"terminate {record.command}",
        return_code=return_code,
        succeeded=succeeded,
        background=True,
        pid=record.pid,
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
    )


def _background_startup_command(command_text: str) -> bool:
    normalized = command_text.strip().lower()
    if not normalized:
        return False
    if normalized in {"docker compose up -d", "docker-compose up -d"}:
        return False
    if normalized.startswith("bash scripts/setup.sh"):
        return False
    return True


def _bootstrap_target_project(
    target_path: Path,
    *,
    project_name: str,
    base_url: str,
    log_dir: Path,
    verification_contract: dict,
) -> BootstrapRunDoc:
    healthcheck_url = _resolve_healthcheck_url(base_url, verification_contract)
    startup_timeout_seconds = int(verification_contract.get("startup_timeout_seconds", 45) or 45)
    healthcheck_interval_seconds = int(verification_contract.get("healthcheck_interval_seconds", 1) or 1)
    reachable_before = _url_reachable(healthcheck_url)
    bootstrap_run = BootstrapRunDoc(
        generator="ncdev.v2.verification",
        source_inputs=[str(target_path)],
        project_name=project_name,
        target_path=str(target_path),
        base_url=base_url,
        reachable_before_bootstrap=reachable_before,
        bootstrap_succeeded=reachable_before,
        started_services=False,
        summary={"base_url": base_url, "healthcheck_url": healthcheck_url},
    )
    if reachable_before:
        bootstrap_run.summary["note"] = "Healthcheck URL already reachable before bootstrap."
        return bootstrap_run

    configured_startup = [str(command).strip() for command in verification_contract.get("startup_commands", []) if str(command).strip()]
    compose_candidates = configured_startup or [
        "docker compose up -d",
        "docker-compose up -d",
    ]
    for index, command_text in enumerate(compose_candidates, start=1):
        cmd = shlex.split(command_text)
        if not cmd:
            continue
        if shutil.which(cmd[0]) is None:
            continue
        if cmd[:3] in (["docker", "compose", "up"], ["docker-compose", "up", "-d"]) and not (target_path / "docker-compose.yml").exists():
            continue
        if _background_startup_command(command_text):
            record = _run_background_command(target_path, log_dir, f"bootstrap-{index:02d}", "bootstrap", command_text)
        else:
            record = _run_logged_command(target_path, log_dir, f"bootstrap-{index:02d}", "bootstrap", cmd)
        bootstrap_run.commands.append(record)
        if record.succeeded:
            if _wait_for_reachability(
                healthcheck_url,
                timeout_seconds=startup_timeout_seconds,
                interval_seconds=healthcheck_interval_seconds,
            ):
                bootstrap_run.bootstrap_succeeded = True
                bootstrap_run.started_services = True
                bootstrap_run.summary["note"] = "Target project became reachable after bootstrap."
                return bootstrap_run
            if record.background:
                teardown_record = _terminate_background_process(record, log_dir, len(bootstrap_run.commands))
                bootstrap_run.teardown_commands.append(teardown_record)

    setup_script = target_path / "scripts" / "setup.sh"
    if setup_script.exists():
        cmd = ["bash", str(setup_script)]
        record = _run_logged_command(
            target_path,
            log_dir,
            f"bootstrap-{len(bootstrap_run.commands) + 1:02d}",
            "bootstrap",
            cmd,
        )
        bootstrap_run.commands.append(record)
        if _wait_for_reachability(
            healthcheck_url,
            timeout_seconds=min(10, startup_timeout_seconds),
            interval_seconds=healthcheck_interval_seconds,
        ):
            bootstrap_run.bootstrap_succeeded = True
            bootstrap_run.started_services = True
            bootstrap_run.summary["note"] = "Target project became reachable after setup script."
            return bootstrap_run

    bootstrap_run.bootstrap_succeeded = _url_reachable(healthcheck_url)
    if not bootstrap_run.commands:
        bootstrap_run.summary["note"] = "No bootstrap commands were available."
    return bootstrap_run


def _teardown_target_project(target_path: Path, bootstrap_run: BootstrapRunDoc, log_dir: Path) -> BootstrapRunDoc:
    if not bootstrap_run.started_services:
        return bootstrap_run

    teardown_specs: list[list[str]] = []
    for record in bootstrap_run.commands:
        if record.command == "docker compose up -d":
            teardown_specs.append(["docker", "compose", "down"])
        elif record.command == "docker-compose up -d":
            teardown_specs.append(["docker-compose", "down"])

    bootstrap_run.teardown_attempted = True
    teardown_records: list[BootstrapCommandRecord] = list(getattr(bootstrap_run, "teardown_commands", []))
    for index, cmd in enumerate(teardown_specs, start=1):
        teardown_records.append(
            _run_logged_command(
                target_path,
                log_dir,
                f"teardown-{index:02d}",
                "teardown",
                cmd,
            )
        )
    background_records = [
        record
        for record in getattr(bootstrap_run, "commands", [])
        if getattr(record, "background", False) and getattr(record, "pid", None)
    ]
    start_index = len(teardown_records) + 1
    for offset, record in enumerate(background_records, start=start_index):
        teardown_records.append(_terminate_background_process(record, log_dir, offset))
    if not teardown_records:
        return bootstrap_run
    bootstrap_run.teardown_commands = teardown_records
    bootstrap_run.teardown_succeeded = all(record.succeeded for record in teardown_records)
    return bootstrap_run


def _apply_contract_teardown(
    target_path: Path,
    bootstrap_run: BootstrapRunDoc,
    log_dir: Path,
    verification_contract: dict,
) -> BootstrapRunDoc:
    configured_teardown = [str(command).strip() for command in verification_contract.get("teardown_commands", []) if str(command).strip()]
    if not configured_teardown:
        return _teardown_target_project(target_path, bootstrap_run, log_dir)

    if not bootstrap_run.started_services:
        return bootstrap_run

    bootstrap_run.teardown_attempted = True
    teardown_records: list[BootstrapCommandRecord] = list(getattr(bootstrap_run, "teardown_commands", []))
    for index, command_text in enumerate(configured_teardown, start=1):
        cmd = shlex.split(command_text)
        if not cmd or shutil.which(cmd[0]) is None:
            continue
        teardown_records.append(
            _run_logged_command(
                target_path,
                log_dir,
                f"teardown-{index:02d}",
                "teardown",
                cmd,
            )
        )
    background_records = [
        record
        for record in getattr(bootstrap_run, "commands", [])
        if getattr(record, "background", False) and getattr(record, "pid", None)
    ]
    start_index = len(teardown_records) + 1
    for offset, record in enumerate(background_records, start=start_index):
        teardown_records.append(_terminate_background_process(record, log_dir, offset))
    if teardown_records:
        bootstrap_run.teardown_commands = teardown_records
        bootstrap_run.teardown_succeeded = all(record.succeeded for record in teardown_records)
    return bootstrap_run


def run_v2_verification(
    run_dir: Path,
    *,
    base_url: str,
    dry_run: bool,
) -> tuple[VerificationRunDoc, EvidenceIndexDoc, BootstrapRunDoc, VerificationIssueBundleDoc]:
    outputs_dir = run_dir / "outputs"
    log_dir = run_dir / "logs" / "verification"
    log_dir.mkdir(parents=True, exist_ok=True)
    scaffold_manifest = _load_json(outputs_dir / "scaffold-manifest.json")
    feature_map = _load_json(outputs_dir / "feature-map.json")
    verification_contract = _load_json(outputs_dir / "verification-contract.json")
    project_name = str(scaffold_manifest["project_name"])
    target_path = Path(scaffold_manifest["target_path"])
    routes = _derive_routes(feature_map)

    if dry_run:
        bootstrap_run = BootstrapRunDoc(
            generator="ncdev.v2.verification",
            source_inputs=[str(target_path)],
            project_name=project_name,
            target_path=str(target_path),
            base_url=base_url,
            reachable_before_bootstrap=True,
            bootstrap_succeeded=True,
            started_services=False,
            summary={"note": "Dry-run skipped bootstrap and teardown."},
        )
        verification_run = VerificationRunDoc(
            generator="ncdev.v2.verification",
            source_inputs=[str(target_path)],
            project_name=project_name,
            target_path=str(target_path),
            base_url=base_url,
            routes=routes,
            dry_run=True,
            bootstrap_succeeded=True,
            bootstrap_commands=[],
            overall_passed=True,
            summary={
                "overall_passed": True,
                "unit": {"total": 0, "passed": 0, "failed": 0, "skipped": 0},
                "e2e": {"total": 0, "passed": 0, "failed": 0, "skipped": 0},
                "visual": {"screenshots_count": 0, "vision_issues": 0, "comparison_failures": 0},
            },
            report_path="",
        )
        evidence_index = _build_evidence_index(target_path, project_name)
        issue_bundle = _build_verification_issues(
            project_name,
            target_path,
            verification_run,
            evidence_index,
            bootstrap_run,
            verification_contract,
        )
        return verification_run, evidence_index, bootstrap_run, issue_bundle

    bootstrap_run = _bootstrap_target_project(
        target_path,
        project_name=project_name,
        base_url=base_url,
        log_dir=log_dir,
        verification_contract=verification_contract,
    )
    if not bootstrap_run.bootstrap_succeeded:
        verification_run = VerificationRunDoc(
            generator="ncdev.v2.verification",
            source_inputs=[str(target_path)],
            project_name=project_name,
            target_path=str(target_path),
            base_url=base_url,
            routes=routes,
            dry_run=False,
            bootstrap_succeeded=False,
            bootstrap_commands=[record.command for record in bootstrap_run.commands],
            overall_passed=False,
            summary={
                "overall_passed": False,
                "bootstrap_error": f"Could not reach {base_url} after bootstrap attempts.",
            },
            report_path="",
        )
        evidence_index = _build_evidence_index(target_path, project_name)
        issue_bundle = _build_verification_issues(
            project_name,
            target_path,
            verification_run,
            evidence_index,
            bootstrap_run,
            verification_contract,
        )
        return verification_run, evidence_index, bootstrap_run, issue_bundle

    runner = TestRunner(target_path, base_url=base_url)
    report_path = target_path / ".nc-dev" / "test-reports" / "test-suite-results.json"
    try:
        suite: TestSuiteResults = asyncio.run(runner.run_all(routes=routes))
        overall_passed = suite.overall_passed
        summary = suite.summary_dict()
    except Exception as exc:
        overall_passed = False
        summary = {
            "overall_passed": False,
            "runner_error": str(exc),
        }
    finally:
        bootstrap_run = _apply_contract_teardown(target_path, bootstrap_run, log_dir, verification_contract)

    verification_run = VerificationRunDoc(
        generator="ncdev.v2.verification",
        source_inputs=[str(target_path)],
        project_name=project_name,
        target_path=str(target_path),
        base_url=base_url,
        routes=routes,
        dry_run=False,
        bootstrap_succeeded=bootstrap_run.bootstrap_succeeded,
        bootstrap_commands=[record.command for record in bootstrap_run.commands],
        overall_passed=overall_passed,
        summary=summary,
        report_path=str(report_path),
    )
    evidence_index = _build_evidence_index(target_path, project_name)
    issue_bundle = _build_verification_issues(
        project_name,
        target_path,
        verification_run,
        evidence_index,
        bootstrap_run,
        verification_contract,
    )
    return verification_run, evidence_index, bootstrap_run, issue_bundle
