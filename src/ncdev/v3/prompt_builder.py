"""Lean Citex-backed prompt builder for V3 feature execution."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from ncdev.v3.models import FeatureStep, StepResult


def build_feature_prompt(
    feature: FeatureStep,
    target_path: Path,
    project_id: str = "",
    citex_api: str = "http://localhost:20161",
    spec_content: str = "",
    prior_results: list[StepResult] | None = None,
    stack: dict | None = None,
    design_brief: dict | None = None,
) -> str:
    """Build a lean prompt with Citex query instructions.

    Codex gets told WHAT to build and WHERE to find context.
    It pulls what it needs from Citex during its build session.
    """
    payload = json.dumps(
        {"project_id": project_id, "query": "your question", "limit": 5},
        separators=(", ", ": "),
    )
    parts = [
        f"# Build: {feature.title}",
        "",
        "## Your Task",
        feature.description,
        "",
        "## Acceptance Criteria",
        *[f"- {c}" for c in feature.acceptance_criteria],
    ]
    if feature.test_requirements:
        parts.extend([
            "",
            "## Test Requirements",
            *[f"- {t}" for t in feature.test_requirements],
        ])
    parts.extend([
        "",
        "## Context Retrieval",
        f"You have access to a project knowledge base at {citex_api}.",
        f"Use project_id `{project_id}` for every query during implementation.",
        "",
        "### How to query",
        "```bash",
        f"curl -s -X POST {citex_api}/api/retrieval/query \\",
        '  -H "Content-Type: application/json" \\',
        f"  -d '{payload}' \\",
        '  | python3 -c "import sys,json; [print(d.get(\'content\', \'\')) for d in json.load(sys.stdin).get(\'results\',[])]"',
        "```",
        "",
        "### What to query for",
        '- "design tokens colors typography" before writing any UI',
        '- "existing API routes and schemas" before adding endpoints',
        '- "data models and MongoDB schemas" before creating models',
        '- "frontend store patterns" before adding Zustand stores or client state',
        '- "prior feature integration points" to see what earlier steps built',
        '- "test patterns and fixtures" before writing tests',
        '- "architectural constraints and conventions" before making structural changes',
        "",
        "## Verification Protocol",
        "After implementing:",
        "1. Run backend tests: `cd backend && python -m pytest -q`",
        "2. Run frontend tests: `cd frontend && npx vitest run`",
        "3. Verify backend boots: `cd backend && python -c \"from app.main import app; print('OK')\"`",
        "4. Fix ALL failures before finishing.",
        "",
        "## Rules",
        "- READ existing code before writing new code",
        "- Build ON TOP of what exists; do not rewrite working code",
        "- Every file must be importable and functional",
        "- No placeholder stubs, TODO comments, or fake implementations",
    ])
    return "\n".join(parts)


def build_repair_prompt(
    feature: FeatureStep,
    target_path: Path,
    verification_output: str,
    error_traces: str,
) -> str:
    """Build a repair prompt with full error context."""
    file_tree = _get_file_tree(target_path)

    parts = [
        f"# REPAIR: {feature.title}",
        "",
        "The previous implementation of this feature FAILED verification.",
        "You must fix the issues below.",
        "",
        "## Current Project Files",
        "```",
        file_tree[:5000],
        "```",
        "",
        "## Verification Failures",
        "```",
        verification_output[:5000],
        "```",
        "",
    ]

    if error_traces:
        parts.extend([
            "## Error Traces",
            "```",
            error_traces[:5000],
            "```",
            "",
        ])

    parts.extend([
        "## What To Do",
        "1. Read the error output carefully.",
        "2. Read the existing code files to understand the current state.",
        "3. Fix the specific issues — do NOT rewrite from scratch.",
        "4. Run tests after fixing: `cd backend && python -m pytest -q`",
        "5. Fix ALL failures before finishing.",
    ])

    return "\n".join(parts)


def _get_file_tree(target_path: Path) -> str:
    """Get the actual file tree of the project, excluding noise."""
    try:
        result = subprocess.run(
            ["find", ".", "-type", "f",
             "-not", "-path", "./.git/*",
             "-not", "-path", "*/node_modules/*",
             "-not", "-path", "*/.venv/*",
             "-not", "-path", "*/__pycache__/*",
             "-not", "-path", "*.egg-info/*",
             "-not", "-path", "*/.ncdev/*",
             ],
            cwd=str(target_path),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            lines = sorted(result.stdout.strip().split("\n"))
            return "\n".join(lines[:200])
    except Exception:
        pass
    return ""


def _get_recent_changes(target_path: Path) -> str:
    """Get recent git log for context."""
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-10"],
            cwd=str(target_path),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""
