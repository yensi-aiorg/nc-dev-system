from __future__ import annotations

import asyncio
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


def prepare_target_project(
    output_root: Path,
    feature_map: FeatureMapDoc,
    target_contract: TargetProjectContractDoc,
    scaffold_plan: ScaffoldPlanDoc,
) -> tuple[ScaffoldManifestDocV2, VerificationContractDoc]:
    _ = scaffold_plan
    project_config = _to_project_config(feature_map, target_contract)
    generator = ProjectGenerator(project_config)
    project_root = asyncio.run(generator.generate(output_root))

    evidence_dir = project_root / "docs" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    write_text(
        evidence_dir / "README.md",
        "# Evidence\n\nStore screenshots, traces, videos, and issue bundles here.\n",
    )
    write_text(
        project_root / "scripts" / "run-evidence-checks.sh",
        "#!/usr/bin/env bash\nset -euo pipefail\npytest -q\n(cd frontend && npx playwright test)\n",
    )
    initialized_git = _init_git_repo(project_root)

    files_written = sorted(
        [
            str(path.relative_to(project_root))
            for path in project_root.rglob("*")
            if path.is_file()
        ]
    )
    startup_commands, teardown_commands = _verification_startup_commands(project_root)
    manifest = ScaffoldManifestDocV2(
        generator="ncdev.v2.prepare",
        source_inputs=[feature_map.project_name],
        project_name=feature_map.project_name,
        target_path=str(project_root),
        files_written=files_written,
        initialized_git=initialized_git,
    )
    verification_contract = VerificationContractDoc(
        generator="ncdev.v2.prepare",
        source_inputs=[str(project_root)],
        project_name=feature_map.project_name,
        commands=[
            "pytest -q",
            "cd frontend && npm run test",
            "cd frontend && npx playwright test",
        ],
        startup_commands=startup_commands,
        teardown_commands=teardown_commands,
        healthcheck_path="/",
        startup_timeout_seconds=45,
        healthcheck_interval_seconds=1,
        required_viewports=[
            "desktop",
            "mobile",
        ],
        evidence_paths=[
            "docs/evidence",
            "frontend/test-results",
            "playwright-report",
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
    return manifest, verification_contract
