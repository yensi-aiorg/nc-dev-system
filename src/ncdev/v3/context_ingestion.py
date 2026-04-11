"""Context ingestion — Opus reads project state, ingests structured summaries into Citex."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from rich.console import Console

from ncdev.v3.citex_client import CitexClient, CITEX_DEFAULT_URL
from ncdev.v3.models import (
    FeatureQueueDoc,
    FeatureStep,
    IngestionRecord,
    IngestionReport,
    StepResult,
)

console = Console()


def _read_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _read_code_files(target_path: Path, glob_pattern: str, max_files: int = 20) -> str:
    """Read source files matching a glob pattern, return concatenated content."""
    parts = []
    count = 0
    for fpath in sorted(target_path.glob(glob_pattern)):
        if fpath.is_file() and fpath.stat().st_size < 50_000:
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
                parts.append(f"### {fpath.relative_to(target_path)}\n```\n{content}\n```")
                count += 1
                if count >= max_files:
                    break
            except Exception:
                pass
    return "\n\n".join(parts)


def _synthesize_with_opus(category: str, raw_content: str) -> str:
    """Call Claude Opus to synthesize raw content into a structured summary."""
    if not raw_content.strip():
        return ""

    prompt = (
        f"You are summarizing project context for the '{category}' category.\n"
        f"Produce a concise, structured summary that another AI agent can use "
        f"to understand and build on this code. Include specific names, types, "
        f"signatures, and field definitions. No vague descriptions.\n\n"
        f"Raw content:\n{raw_content[:30000]}"
    )

    try:
        result = subprocess.run(
            [
                "claude", "-p", prompt,
                "--output-format", "text",
                "--model", "claude-opus-4-6",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    # Fallback: return raw content truncated
    return raw_content[:5000]


def ingest_project_context(
    run_dir: Path,
    target_path: Path,
    feature_queue: FeatureQueueDoc,
    project_id: str,
    citex_api: str = CITEX_DEFAULT_URL,
) -> IngestionReport:
    """Read discovery artifacts + actual project code, ingest into Citex."""
    client = CitexClient(base_url=citex_api, project_id=project_id)
    records: list[IngestionRecord] = []
    outputs = run_dir / "outputs"

    # Category → (source description, content)
    ingestion_items: list[tuple[str, str]] = []

    # 1. Design brief
    design_brief = _read_json(outputs / "design-brief.json")
    if design_brief:
        ingestion_items.append(("design", json.dumps(design_brief, indent=2)))

    # 2. Feature specs
    for feature in feature_queue.features:
        spec_text = (
            f"Feature: {feature.title}\n"
            f"ID: {feature.feature_id}\n"
            f"Description: {feature.description}\n"
            f"Acceptance Criteria:\n" +
            "\n".join(f"- {c}" for c in feature.acceptance_criteria) +
            f"\nTest Requirements:\n" +
            "\n".join(f"- {t}" for t in feature.test_requirements)
        )
        ingestion_items.append(("feature_spec", spec_text))

    # 3. Architecture / stack / constraints
    target_contract = _read_json(outputs / "target-project-contract.json")
    build_plan = _read_json(outputs / "build-plan.json")
    arch_content = json.dumps({"target_contract": target_contract, "build_plan": build_plan}, indent=2)
    if target_contract or build_plan:
        ingestion_items.append(("architecture", arch_content))

    # 4. Existing code — read and synthesize with Opus
    code_categories = [
        ("api_contract", "backend/app/api/**/*.py"),
        ("data_model", "backend/app/models/**/*.py"),
        ("service_layer", "backend/app/services/**/*.py"),
        ("frontend_pattern", "frontend/src/stores/**/*.ts"),
        ("frontend_pattern", "frontend/src/components/**/*.tsx"),
        ("test_pattern", "backend/tests/**/*.py"),
    ]

    for category, pattern in code_categories:
        code_content = _read_code_files(target_path, pattern)
        if code_content:
            synthesized = _synthesize_with_opus(category, code_content)
            if synthesized:
                ingestion_items.append((category, synthesized))

    # Ingest all items
    for category, content in ingestion_items:
        success = client.ingest(content=content, category=category)
        records.append(IngestionRecord(
            category=category,
            char_count=len(content),
            success=success,
        ))
        status = "[green]ok[/green]" if success else "[red]fail[/red]"
        console.print(f"  Citex ingest [{category}]: {len(content)} chars — {status}")

    successful = sum(1 for r in records if r.success)
    failed = sum(1 for r in records if not r.success)

    return IngestionReport(
        project_id=project_id,
        total_documents=len(records),
        successful=successful,
        failed=failed,
        records=records,
    )


def ingest_feature_result(
    feature: FeatureStep,
    result: StepResult,
    target_path: Path,
    project_id: str,
    citex_api: str = CITEX_DEFAULT_URL,
) -> bool:
    """Ingest a completed feature result into Citex for the next feature to query."""
    client = CitexClient(base_url=citex_api, project_id=project_id)

    content = (
        f"Feature: {feature.title} ({feature.feature_id})\n"
        f"Status: {result.status.value}\n"
        f"Files created: {', '.join(result.files_created)}\n"
        f"Files modified: {', '.join(result.files_modified)}\n"
        f"Repair attempts: {result.repair_attempts}\n"
        f"Commit: {result.commit_sha}\n"
    )

    return client.ingest(
        content=content,
        category="prior_feature",
        metadata={"feature_id": feature.feature_id, "status": result.status.value},
    )
