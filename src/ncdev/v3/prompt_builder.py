"""Context-aware prompt builder — reads ACTUAL project state, not stale manifests.

The critical difference from V2's prompt_assembler: this module reads the REAL
current file tree and builds prompts based on what actually exists in the repo.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from ncdev.v3.models import FeatureStep, StepResult


def build_feature_prompt(
    feature: FeatureStep,
    target_path: Path,
    spec_content: str,
    prior_results: list[StepResult],
    stack: dict | None = None,
    design_brief: dict | None = None,
) -> str:
    """Build a complete, context-aware prompt for implementing one feature.

    This reads the ACTUAL current state of the project — not cached manifests.
    """
    # Read the real file tree
    file_tree = _get_file_tree(target_path)
    recent_changes = _get_recent_changes(target_path)

    parts = [
        f"# Implement: {feature.title}",
        f"**Feature ID:** {feature.feature_id}",
        "",
        "## What You Must Do",
        feature.description,
        "",
        "### Acceptance Criteria",
        *[f"- {c}" for c in feature.acceptance_criteria],
        "",
        "### Test Requirements",
        *[f"- {t}" for t in feature.test_requirements],
        "",
    ]

    # Include the original spec (capped but generous)
    if spec_content:
        parts.extend([
            "## Product Specification",
            "```markdown",
            spec_content[:20000],
            "```",
            "",
        ])

    # Include the ACTUAL current project state
    if file_tree:
        parts.extend([
            "## Current Project State",
            "These files already exist in the project. READ them before writing new code.",
            "Build ON TOP of what exists — do not rewrite working code.",
            "```",
            file_tree[:5000],
            "```",
            "",
        ])

    # Include what was built in prior steps
    if prior_results:
        parts.extend([
            "## Previously Completed Features",
        ])
        for pr in prior_results:
            if pr.status.value == "passed":
                parts.append(f"- **{pr.feature_id}**: {len(pr.files_created)} files created, {len(pr.files_modified)} modified")
        parts.append("")

    # Include recent git changes for context
    if recent_changes:
        parts.extend([
            "## Recent Changes (git log)",
            "```",
            recent_changes[:2000],
            "```",
            "",
        ])

    # Stack info
    if stack:
        parts.extend([
            "## Tech Stack",
            f"```json\n{json.dumps(stack, indent=2)}\n```",
            "",
        ])

    # Design brief (condensed)
    if design_brief:
        traits = design_brief.get("design_traits", [])
        if traits:
            parts.extend([
                "## Design Traits",
                *[f"- {t}" for t in traits[:10]],
                "",
            ])

    # Conventions
    parts.extend([
        "## Conventions",
        "- Backend: Python/FastAPI, Pydantic v2 models, MongoDB via motor/pymongo",
        "- Frontend: React 19 + TypeScript + Vite + Tailwind CSS",
        "- Auth: JWT tokens from Keycloak (support dev: prefix tokens for development)",
        "- All API routes under /api/ prefix",
        "- Health endpoint: GET /api/health returning {\"status\": \"ok\"}",
        "- Error responses: {\"detail\": \"message\"} with appropriate HTTP status",
        "",
        "## CRITICAL: Verification Protocol",
        "After implementing the feature, you MUST do the following:",
        "1. Run backend tests: `cd backend && python -m pytest -q` (fix any failures)",
        "2. Run frontend tests: `cd frontend && npx vitest run` (fix any failures)",
        "3. Verify the backend boots: `cd backend && timeout 10 python -c \"from app.main import app; print('OK')\"` ",
        "4. If you created new test files, run them individually to confirm they pass.",
        "5. Fix ALL test failures and import errors before finishing.",
        "",
        "## Execution Instructions",
        "1. You are running inside the project root directory.",
        "2. READ existing files first to understand what's already built.",
        "3. BUILD on top of existing code — do NOT rewrite things that work.",
        "4. Write tests alongside your code — not as an afterthought.",
        "5. Run tests and fix failures before finishing.",
        "6. Every file you create must be importable and functional.",
        "7. No placeholder stubs, no TODO comments, no \"coming soon\" text.",
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
