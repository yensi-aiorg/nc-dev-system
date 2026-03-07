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
from ncdev.v2.models import EvidenceIndexDoc, VerificationRunDoc


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


def _bootstrap_target_project(target_path: Path, base_url: str) -> tuple[bool, list[str]]:
    commands: list[str] = []
    if _url_reachable(base_url):
        return True, commands

    compose_candidates = [
        ["docker", "compose", "up", "-d"],
        ["docker-compose", "up", "-d"],
    ]
    for cmd in compose_candidates:
        if shutil.which(cmd[0]) is None:
            continue
        if not (target_path / "docker-compose.yml").exists():
            continue
        commands.append(" ".join(cmd))
        proc = subprocess.run(
            cmd,
            cwd=str(target_path),
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode == 0:
            deadline = time.time() + 45
            while time.time() < deadline:
                if _url_reachable(base_url):
                    return True, commands
                time.sleep(1)

    setup_script = target_path / "scripts" / "setup.sh"
    if setup_script.exists():
        cmd = ["bash", str(setup_script)]
        commands.append(" ".join(cmd))
        subprocess.run(
            cmd,
            cwd=str(target_path),
            capture_output=True,
            text=True,
            check=False,
        )
        if _url_reachable(base_url):
            return True, commands

    return _url_reachable(base_url), commands


def run_v2_verification(run_dir: Path, *, base_url: str, dry_run: bool) -> tuple[VerificationRunDoc, EvidenceIndexDoc]:
    outputs_dir = run_dir / "outputs"
    scaffold_manifest = _load_json(outputs_dir / "scaffold-manifest.json")
    feature_map = _load_json(outputs_dir / "feature-map.json")
    project_name = str(scaffold_manifest["project_name"])
    target_path = Path(scaffold_manifest["target_path"])
    routes = _derive_routes(feature_map)

    if dry_run:
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
        return verification_run, _build_evidence_index(target_path, project_name)

    bootstrap_succeeded, bootstrap_commands = _bootstrap_target_project(target_path, base_url)
    if not bootstrap_succeeded:
        verification_run = VerificationRunDoc(
            generator="ncdev.v2.verification",
            source_inputs=[str(target_path)],
            project_name=project_name,
            target_path=str(target_path),
            base_url=base_url,
            routes=routes,
            dry_run=False,
            bootstrap_succeeded=False,
            bootstrap_commands=bootstrap_commands,
            overall_passed=False,
            summary={
                "overall_passed": False,
                "bootstrap_error": f"Could not reach {base_url} after bootstrap attempts.",
            },
            report_path="",
        )
        return verification_run, _build_evidence_index(target_path, project_name)

    runner = TestRunner(target_path, base_url=base_url)
    suite: TestSuiteResults = asyncio.run(runner.run_all(routes=routes))
    report_path = target_path / ".nc-dev" / "test-reports" / "test-suite-results.json"
    verification_run = VerificationRunDoc(
        generator="ncdev.v2.verification",
        source_inputs=[str(target_path)],
        project_name=project_name,
        target_path=str(target_path),
        base_url=base_url,
        routes=routes,
        dry_run=False,
        bootstrap_succeeded=bootstrap_succeeded,
        bootstrap_commands=bootstrap_commands,
        overall_passed=suite.overall_passed,
        summary=suite.summary_dict(),
        report_path=str(report_path),
    )
    return verification_run, _build_evidence_index(target_path, project_name)
