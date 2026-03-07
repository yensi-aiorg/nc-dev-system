from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

from src.tester.results import TestSuiteResults
from src.tester.runner import TestRunner

from ncdev.utils import write_json
from ncdev.v2.models import BootstrapCommandRecord, BootstrapRunDoc, EvidenceIndexDoc, VerificationRunDoc


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
    screenshots_dir = target_path / ".nc-dev" / "screenshots"
    reports_dir = target_path / ".nc-dev" / "test-reports"
    playwright_report = target_path / "frontend" / "playwright-report"
    test_results_dir = target_path / "frontend" / "test-results"

    screenshots = sorted(str(path) for path in screenshots_dir.rglob("*") if path.is_file()) if screenshots_dir.exists() else []
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


def _url_reachable(base_url: str) -> bool:
    try:
        with urllib.request.urlopen(base_url, timeout=2.0) as response:
            return 200 <= response.status < 500
    except (urllib.error.URLError, TimeoutError, ValueError):
        return False


def _command_log_path(log_dir: Path, prefix: str, stream: str) -> Path:
    return log_dir / f"{prefix}-{stream}.log"


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


def _bootstrap_target_project(
    target_path: Path,
    *,
    project_name: str,
    base_url: str,
    log_dir: Path,
) -> BootstrapRunDoc:
    reachable_before = _url_reachable(base_url)
    bootstrap_run = BootstrapRunDoc(
        generator="ncdev.v2.verification",
        source_inputs=[str(target_path)],
        project_name=project_name,
        target_path=str(target_path),
        base_url=base_url,
        reachable_before_bootstrap=reachable_before,
        bootstrap_succeeded=reachable_before,
        started_services=False,
        summary={"base_url": base_url},
    )
    if reachable_before:
        bootstrap_run.summary["note"] = "Base URL already reachable before bootstrap."
        return bootstrap_run

    compose_candidates = [
        ["docker", "compose", "up", "-d"],
        ["docker-compose", "up", "-d"],
    ]
    for index, cmd in enumerate(compose_candidates, start=1):
        if shutil.which(cmd[0]) is None:
            continue
        if not (target_path / "docker-compose.yml").exists():
            continue
        record = _run_logged_command(target_path, log_dir, f"bootstrap-{index:02d}", "bootstrap", cmd)
        bootstrap_run.commands.append(record)
        if record.succeeded:
            deadline = time.time() + 45
            while time.time() < deadline:
                if _url_reachable(base_url):
                    bootstrap_run.bootstrap_succeeded = True
                    bootstrap_run.started_services = True
                    bootstrap_run.summary["note"] = "Target project became reachable after bootstrap."
                    return bootstrap_run
                time.sleep(1)

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
        if _url_reachable(base_url):
            bootstrap_run.bootstrap_succeeded = True
            bootstrap_run.started_services = True
            bootstrap_run.summary["note"] = "Target project became reachable after setup script."
            return bootstrap_run

    bootstrap_run.bootstrap_succeeded = _url_reachable(base_url)
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

    if not teardown_specs:
        return bootstrap_run

    bootstrap_run.teardown_attempted = True
    teardown_records: list[BootstrapCommandRecord] = []
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
    bootstrap_run.teardown_commands = teardown_records
    bootstrap_run.teardown_succeeded = all(record.succeeded for record in teardown_records)
    return bootstrap_run


def run_v2_verification(run_dir: Path, *, base_url: str, dry_run: bool) -> tuple[VerificationRunDoc, EvidenceIndexDoc, BootstrapRunDoc]:
    outputs_dir = run_dir / "outputs"
    log_dir = run_dir / "logs" / "verification"
    log_dir.mkdir(parents=True, exist_ok=True)
    scaffold_manifest = _load_json(outputs_dir / "scaffold-manifest.json")
    feature_map = _load_json(outputs_dir / "feature-map.json")
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
        return verification_run, _build_evidence_index(target_path, project_name), bootstrap_run

    bootstrap_run = _bootstrap_target_project(
        target_path,
        project_name=project_name,
        base_url=base_url,
        log_dir=log_dir,
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
        return verification_run, _build_evidence_index(target_path, project_name), bootstrap_run

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
        bootstrap_run = _teardown_target_project(target_path, bootstrap_run, log_dir)

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
    return verification_run, _build_evidence_index(target_path, project_name), bootstrap_run
