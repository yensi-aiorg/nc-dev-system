from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path

from src.scaffolder.generator import ProjectConfig, ProjectGenerator

from ncdev.utils import write_text
from ncdev.v2.models import (
    FeatureMapDoc,
    ScaffoldManifestDocV2,
    ScaffoldPlanDoc,
    TargetProjectContractDoc,
    VerificationContractDoc,
)


def _slug(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-") or "project"


def _to_project_config(feature_map: FeatureMapDoc, target_contract: TargetProjectContractDoc) -> ProjectConfig:
    features = []
    db_collections = []
    api_contracts = [
        {
            "base_path": "/api/v1/features",
            "endpoints": [
                {"method": "GET", "path": "/api/v1/features", "description": "List feature records"},
                {"method": "POST", "path": "/api/v1/features", "description": "Create feature record"},
            ],
        }
    ]
    for feature in feature_map.features:
        features.append(
            {
                "name": feature.name,
                "description": feature.description,
                "priority": feature.priority,
                "fields": [
                    {"name": "title", "type": "string", "required": True},
                    {"name": "status", "type": "string", "required": True},
                ],
            }
        )
    if feature_map.features:
        db_collections.append(
            {
                "name": "features",
                "fields": [
                    {"name": "_id", "type": "ObjectId", "required": True},
                    {"name": "title", "type": "string", "required": True},
                    {"name": "status", "type": "string", "required": True},
                    {"name": "created_at", "type": "datetime", "required": True},
                ],
                "indexes": [{"fields": ["title"], "unique": False}],
            }
        )

    return ProjectConfig(
        name=_slug(feature_map.project_name),
        description=f"Generated target project for {feature_map.project_name}",
        auth_required=False,
        features=features,
        db_collections=db_collections,
        api_contracts=api_contracts,
        external_apis=[],
    )


def _init_git_repo(project_root: Path) -> bool:
    try:
        subprocess.run(["git", "init"], cwd=project_root, capture_output=True, text=True, check=False)
        subprocess.run(["git", "add", "."], cwd=project_root, capture_output=True, text=True, check=False)
        subprocess.run(
            [
                "git",
                "-c",
                "user.name=NC Dev System",
                "-c",
                "user.email=ncdev@example.invalid",
                "commit",
                "-m",
                "chore: initialize generated project scaffold",
            ],
            cwd=project_root,
            capture_output=True,
            text=True,
            check=False,
        )
        return (project_root / ".git").exists()
    except FileNotFoundError:
        return False


def _verification_startup_commands(project_root: Path) -> tuple[list[str], list[str]]:
    startup_commands: list[str] = []
    teardown_commands: list[str] = []
    if (project_root / "docker-compose.yml").exists():
        startup_commands.append("docker compose up -d")
        teardown_commands.append("docker compose down")
    if (project_root / "scripts" / "setup.sh").exists():
        startup_commands.append("bash scripts/setup.sh")
    return startup_commands, teardown_commands


def _has_non_git_content(project_root: Path) -> bool:
    return any(path.name != ".git" for path in project_root.iterdir())


def _ensure_website_saas_baseline(project_root: Path) -> None:
    evidence_dir = project_root / "docs" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    write_text(
        evidence_dir / "README.md",
        "# Evidence\n\nStore screenshots, traces, videos, issue bundles, and review notes here.\n",
    )
    screenshots_dir = project_root / "frontend" / "e2e" / "screenshots"
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    gitkeep = screenshots_dir / ".gitkeep"
    if not gitkeep.exists():
        write_text(gitkeep, "")
    scripts_dir = project_root / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    run_evidence = scripts_dir / "run-evidence-checks.sh"
    if not run_evidence.exists():
        write_text(
            run_evidence,
            "#!/usr/bin/env bash\nset -euo pipefail\n"
            "if [ -d backend ]; then (cd backend && pytest -q); else pytest -q; fi\n"
            "if [ -f frontend/package.json ]; then (cd frontend && npm run test -- --run); fi\n"
            "if [ -f frontend/playwright.config.ts ]; then (cd frontend && npx playwright test); fi\n",
        )
        run_evidence.chmod(0o755)


def _verification_contract_for_target(project_root: Path, project_name: str) -> VerificationContractDoc:
    commands: list[str] = []
    if (project_root / "backend").exists():
        commands.append("cd backend && pytest -q")
    else:
        commands.append("pytest -q")
    if (project_root / "frontend" / "package.json").exists():
        commands.append("cd frontend && npm run test -- --run")
    if (project_root / "frontend" / "playwright.config.ts").exists():
        commands.append("cd frontend && npx playwright test")

    startup_commands, teardown_commands = _verification_startup_commands(project_root)
    return VerificationContractDoc(
        generator="ncdev.v2.prepare",
        source_inputs=[str(project_root)],
        project_name=project_name,
        commands=commands,
        startup_commands=startup_commands,
        teardown_commands=teardown_commands,
        healthcheck_path="/",
        startup_timeout_seconds=45,
        healthcheck_interval_seconds=1,
        required_viewports=["desktop", "mobile"],
        evidence_paths=[
            "docs/evidence",
            "frontend/e2e/screenshots",
            "frontend/test-results",
            "frontend/playwright-report",
        ],
        required_checks=[
            "unit",
            "integration",
            "e2e",
            "visual_evidence_capture",
        ],
        issue_bundle_fields=[
            "title",
            "severity",
            "expected",
            "actual",
            "screenshot_path",
            "console_logs",
            "network_requests",
        ],
    )


def prepare_target_project(
    output_root: Path,
    feature_map: FeatureMapDoc,
    target_contract: TargetProjectContractDoc,
    scaffold_plan: ScaffoldPlanDoc,
    *,
    target_root: Path | None = None,
) -> tuple[ScaffoldManifestDocV2, VerificationContractDoc]:
    _ = scaffold_plan
    existing_repo = False
    scaffold_applied = True
    if target_root is not None:
        project_root = target_root.resolve()
        project_root.mkdir(parents=True, exist_ok=True)
        existing_repo = (project_root / ".git").exists() or _has_non_git_content(project_root)
        scaffold_applied = False
    else:
        project_config = _to_project_config(feature_map, target_contract)
        generator = ProjectGenerator(project_config)
        project_root = asyncio.run(generator.generate(output_root))

    _ensure_website_saas_baseline(project_root)
    initialized_git = (project_root / ".git").exists() or _init_git_repo(project_root)

    files_written = sorted(
        [
            str(path.relative_to(project_root))
            for path in project_root.rglob("*")
            if path.is_file()
        ]
    )
    manifest = ScaffoldManifestDocV2(
        generator="ncdev.v2.prepare",
        source_inputs=[feature_map.project_name],
        project_name=feature_map.project_name,
        target_path=str(project_root),
        files_written=files_written,
        initialized_git=initialized_git,
        existing_repo=existing_repo,
        scaffold_applied=scaffold_applied,
    )
    verification_contract = _verification_contract_for_target(project_root, feature_map.project_name)
    return manifest, verification_contract
