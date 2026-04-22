"""Project context ingestion into Citex — Opus synthesis + structured helpers."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Iterable

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


def ingest_project_context(
    run_dir: Path,
    target_path: Path,
    feature_queue: FeatureQueueDoc,
    project_id: str = "",
    citex_api: str = "http://localhost:20161",
) -> IngestionReport:
    """Read discovery artifacts + actual project code, ingest into Citex."""
    project_id = project_id or target_path.name
    client = CitexClient(project_id=project_id, base_url=citex_api)
    records: list[IngestionRecord] = []
    outputs = run_dir / "outputs"

    # 1. Design brief
    design_payload = _read_json(outputs / "design-brief.json")
    if design_payload:
        records.append(_ingest_document(
            client, "design",
            _serialize_json_document("Design Brief", design_payload),
            metadata={"source": "design-brief.json"},
        ))

    # 2. Architecture (build plan + project config files)
    arch_payload = _read_json(outputs / "build-plan.json")
    if arch_payload:
        records.append(_ingest_document(
            client, "architecture",
            _serialize_json_document("Build Plan", arch_payload),
            metadata={"source": "build-plan.json"},
        ))
    records.extend(_ingest_code_category(
        client, target_path, "architecture",
        ["CLAUDE.md", "AGENTS.md", "pyproject.toml", "package.json"],
    ))

    # 3. Feature specs
    records.extend(_ingest_feature_specs(client, feature_queue))

    # 4. Existing code — synthesize with Opus then ingest
    code_categories = [
        ("api_contract", ["backend/app/api/**/*.py"]),
        ("data_model", ["backend/app/models/**/*.py"]),
        ("service_layer", ["backend/app/services/**/*.py"]),
        ("frontend_pattern", [
            "frontend/src/stores/**/*.ts",
            "frontend/src/components/**/*.tsx",
            "frontend/src/pages/**/*.tsx",
        ]),
        ("test_pattern", ["backend/tests/**/*.py", "tests/**/*.py"]),
    ]

    for category, patterns in code_categories:
        raw_content = _read_code_files(target_path, patterns)
        if raw_content:
            synthesized = _synthesize_with_opus(category, raw_content)
            if synthesized:
                records.append(_ingest_document(
                    client, category, synthesized,
                    metadata={"opus_synthesized": True},
                ))

    successful = sum(1 for r in records if r.success)
    failed = sum(1 for r in records if not r.success)

    for r in records:
        status = "[green]ok[/green]" if r.success else "[red]fail[/red]"
        console.print(f"  Citex ingest [{r.category}]: {r.char_count} chars — {status}")

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
    project_id: str = "",
    citex_api: str = "http://localhost:20161",
) -> bool:
    """Ingest a completed feature result into Citex for the next feature to query."""
    project_id = project_id or target_path.name
    client = CitexClient(project_id=project_id, base_url=citex_api)

    created_lines = [f"- {f}" for f in result.files_created] or ["- none"]
    modified_lines = [f"- {f}" for f in result.files_modified] or ["- none"]
    content = "\n".join([
        f"# Prior Feature: {feature.title}",
        f"Feature ID: {feature.feature_id}",
        f"Status: {result.status.value}",
        f"Description: {feature.description}",
        "",
        "Acceptance Criteria:",
        *[f"- {c}" for c in feature.acceptance_criteria],
        "",
        "Files Created:",
        *created_lines,
        "",
        "Files Modified:",
        *modified_lines,
        "",
        f"Repair Attempts: {result.repair_attempts}",
        f"Commit: {result.commit_sha or 'none'}",
        f"Error: {result.error_message or 'none'}",
    ])

    return client.ingest(
        content=content,
        category="prior_feature",
        metadata={"feature_id": feature.feature_id, "status": result.status.value},
    )


# ── Helpers ──────────────────────────────────────────────────────────────


def _ingest_feature_specs(client: CitexClient, feature_queue: FeatureQueueDoc) -> list[IngestionRecord]:
    records: list[IngestionRecord] = []
    for feature in feature_queue.features:
        test_lines = [f"- {t}" for t in feature.test_requirements] or ["- none"]
        dep_lines = [f"- {d}" for d in feature.depends_on_features] or ["- none"]
        content = "\n".join([
            f"# Feature Spec: {feature.title}",
            f"Feature ID: {feature.feature_id}",
            f"Description: {feature.description}",
            "",
            "Acceptance Criteria:",
            *[f"- {c}" for c in feature.acceptance_criteria],
            "",
            "Test Requirements:",
            *test_lines,
            "",
            "Dependencies:",
            *dep_lines,
        ])
        records.append(_ingest_document(
            client, "feature_spec", content,
            metadata={"feature_id": feature.feature_id},
        ))
    return records


def _ingest_code_category(
    client: CitexClient,
    root: Path,
    category: str,
    patterns: Iterable[str],
    per_document_limit: int = 12000,
) -> list[IngestionRecord]:
    """Read code files matching patterns, chunk, and ingest directly."""
    chunks: list[str] = []
    seen: set[Path] = set()
    for pattern in patterns:
        for path in root.glob(pattern):
            if not path.is_file() or path in seen:
                continue
            seen.add(path)
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            chunks.append(f"## FILE: {path.relative_to(root)}\n{text[:3000]}")
    if not chunks:
        return []

    content = "\n\n".join(chunks)
    documents = [content[i:i + per_document_limit] for i in range(0, len(content), per_document_limit)]
    records: list[IngestionRecord] = []
    for idx, doc in enumerate(documents, start=1):
        records.append(_ingest_document(
            client, category, doc,
            metadata={"part": idx, "parts": len(documents)},
        ))
    return records


def _read_code_files(target_path: Path, patterns: Iterable[str], max_files: int = 20) -> str:
    """Read source files matching glob patterns, return concatenated content for Opus synthesis."""
    parts: list[str] = []
    count = 0
    seen: set[Path] = set()
    for pattern in patterns:
        for fpath in sorted(target_path.glob(pattern)):
            if fpath in seen or not fpath.is_file() or fpath.stat().st_size > 50_000:
                continue
            seen.add(fpath)
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
                parts.append(f"### {fpath.relative_to(target_path)}\n```\n{content}\n```")
                count += 1
                if count >= max_files:
                    return "\n\n".join(parts)
            except OSError:
                pass
    return "\n\n".join(parts)


def _synthesize_with_opus(category: str, raw_content: str) -> str:
    """Call the configured source-ingest provider to synthesize context.

    Historical name kept for call-site compatibility; the provider (Claude,
    Codex, or OpenRouter) is resolved from ``source_ingest`` routing.
    """
    if not raw_content.strip():
        return ""

    prompt = (
        f"You are summarizing project context for the '{category}' category.\n"
        f"Produce a concise, structured summary that another AI agent can use "
        f"to understand and build on this code. Include specific names, types, "
        f"signatures, and field definitions. No vague descriptions.\n\n"
        f"Raw content:\n{raw_content[:30000]}"
    )

    from ncdev.provider_dispatch import get_provider_for, preferred_model_for

    try:
        provider = get_provider_for("source_ingest")
        model = preferred_model_for("source_ingest", "planning")
        argv = provider.build_argv(prompt, model=model)
        result = subprocess.run(
            argv,
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return raw_content[:5000]


def _ingest_document(
    client: CitexClient,
    category: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> IngestionRecord:
    success = client.ingest(content=content, category=category, metadata=metadata)
    return IngestionRecord(category=category, char_count=len(content), success=success)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _serialize_json_document(title: str, payload: dict[str, Any]) -> str:
    return f"# {title}\n\n```json\n{json.dumps(payload, indent=2, sort_keys=True)}\n```"
