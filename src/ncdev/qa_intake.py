from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _slug(text: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in text).strip("-")
    return "-".join(part for part in cleaned.split("-") if part)[:80] or "project"


@dataclass(frozen=True)
class ManualQAImport:
    project: str
    run_id: str
    status: str
    report_copy: str
    metadata_path: str
    fix_task_path: str


def import_manual_qa_report(
    *,
    workspace: Path,
    report_path: Path,
    target_repo: Path,
    project: str | None = None,
    base_url: str = "",
) -> ManualQAImport:
    """Persist a manual QA report as NC-dev actionable intake.

    The report remains human-readable Markdown, while the adjacent metadata and
    generated fix task give NC-dev a stable handoff point for bugfix sessions.
    Product code still lives in the target repository.
    """
    workspace = workspace.resolve()
    report_path = report_path.resolve()
    target_repo = target_repo.resolve()

    if not report_path.exists():
        raise FileNotFoundError(f"QA report not found: {report_path}")
    if not target_repo.exists():
        raise FileNotFoundError(f"Target repo not found: {target_repo}")

    project_name = project or target_repo.name
    run_id = f"manual-qa-{_slug(project_name)}-{_utc_stamp()}"
    intake_dir = workspace / ".nc-dev" / "manual-qa" / _slug(project_name) / run_id
    intake_dir.mkdir(parents=True, exist_ok=True)

    report_copy = intake_dir / report_path.name
    shutil.copy2(report_path, report_copy)

    metadata = {
        "schema": "manual-qa-intake.v1",
        "project": project_name,
        "run_id": run_id,
        "status": "queued",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_report": str(report_path),
        "target_repo": str(target_repo),
        "base_url": base_url,
        "report_copy": str(report_copy),
    }
    metadata_path = intake_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")

    report_text = report_path.read_text()
    fix_task = f"""# NC-dev Manual QA Fix Task

Project: {project_name}
Target repo: {target_repo}
Base URL: {base_url or "(not specified)"}
QA report: {report_copy}
Intake run: {run_id}

## Task

Use this manual QA report as the authoritative bugfix backlog. Fix every P1/P2/P3
finding that is actionable in the target repository, then run focused automated
tests and repeat the production-style QA checks.

## Required workflow

1. Read the QA report below and inspect the target repo.
2. Convert each finding into a reproduction check or regression test where practical.
3. Fix issues in severity order without unrelated refactors.
4. Verify locally with the target repo's build/test commands.
5. Re-run route/interaction QA against the relevant local or deployed URL.
6. Update this intake status and produce a concise fix report.

## QA Report

{report_text}
"""
    fix_task_path = intake_dir / "fix-task.md"
    fix_task_path.write_text(fix_task)

    return ManualQAImport(
        project=project_name,
        run_id=run_id,
        status="queued",
        report_copy=str(report_copy),
        metadata_path=str(metadata_path),
        fix_task_path=str(fix_task_path),
    )


def list_manual_qa_imports(*, workspace: Path, project: str | None = None) -> list[dict]:
    root = workspace.resolve() / ".nc-dev" / "manual-qa"
    if project:
        roots = [root / _slug(project)]
    else:
        roots = [p for p in root.iterdir()] if root.exists() else []

    imports: list[dict] = []
    for project_root in roots:
        if not project_root.exists():
            continue
        for metadata_path in sorted(project_root.glob("*/metadata.json")):
            try:
                imports.append(json.loads(metadata_path.read_text()))
            except json.JSONDecodeError:
                imports.append({
                    "project": project_root.name,
                    "run_id": metadata_path.parent.name,
                    "status": "corrupt",
                    "metadata_path": str(metadata_path),
                })
    return imports


def update_manual_qa_status(
    *,
    workspace: Path,
    project: str,
    run_id: str,
    status: str,
    note: str = "",
) -> dict:
    metadata_path = (
        workspace.resolve()
        / ".nc-dev"
        / "manual-qa"
        / _slug(project)
        / run_id
        / "metadata.json"
    )
    if not metadata_path.exists():
        raise FileNotFoundError(f"Manual QA intake not found: {metadata_path}")

    metadata = json.loads(metadata_path.read_text())
    metadata["status"] = status
    metadata["updated_at"] = datetime.now(timezone.utc).isoformat()
    if note:
        metadata.setdefault("notes", []).append({
            "at": metadata["updated_at"],
            "note": note,
        })
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata


def import_to_dict(item: ManualQAImport) -> dict:
    return asdict(item)
