"""Prompt assembler — builds self-contained, concrete prompts for builder execution.

The critical fix: builders receive prompts that contain ALL the context they need
to implement a feature batch. No external file references. No abstract instructions.
Everything inlined.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


# Conventions imported from builder/prompt_gen.py patterns
_BACKEND_CONVENTIONS = """
## Backend Conventions (Python/FastAPI)
- Use FastAPI with async routes where beneficial
- Pydantic v2 models for all request/response schemas
- MongoDB via pymongo (sync) or motor (async)
- JWT auth middleware validating Keycloak tokens
- Health endpoint at GET /api/health returning {"status": "ok"}
- Environment config via pydantic-settings
- All routes under /api/ prefix
- Error responses: {"detail": "message"} with appropriate HTTP status
- Use Python 3.12+ features
"""

_FRONTEND_CONVENTIONS = """
## Frontend Conventions (React/Vite)
- React 18+ with TypeScript
- Vite as build tool
- Tailwind CSS for styling
- React Router v6 for navigation
- Axios or fetch for API calls
- Auth context with JWT token management
- Protected route wrapper component
- All API calls through a centralized client service
"""

_GENERAL_CONVENTIONS = """
## General Conventions
- Each file should have a single clear responsibility
- No placeholder or TODO comments in production code
- All user-facing strings should be descriptive
- Include proper error handling for API calls
- Docker-ready: include Dockerfile per service
- Include .env.example with all required variables documented
"""


def assemble_build_prompt(
    batch_id: str,
    batch_summary: str,
    acceptance_criteria: list[str],
    build_plan: dict[str, Any],
    feature_map: dict[str, Any],
    design_brief: dict[str, Any],
    target_contract: dict[str, Any],
    scaffold_manifest: dict[str, Any],
    verification_contract: dict[str, Any],
    source_spec: str | None = None,
) -> str:
    """Assemble a complete, self-contained prompt for a BUILD_BATCH job.

    The prompt contains everything the builder needs — no external file references.
    """
    stack = target_contract.get("stack", {})
    operating_mode = target_contract.get("operating_mode", "website_saas")
    project_name = target_contract.get("project_name", build_plan.get("project_name", "unknown"))
    target_path = scaffold_manifest.get("target_path", "")

    # Extract relevant features for this batch
    all_batches = build_plan.get("batches", [])
    this_batch = next((b for b in all_batches if b.get("id") == batch_id), {})

    # Extract relevant features from feature map
    features = feature_map.get("features", [])
    feature_names = [f.get("name", "") for f in features]

    # Build the verification commands
    verification_commands = verification_contract.get("commands", [])
    required_checks = verification_contract.get("required_checks", [])

    # Scaffold info
    scaffold_files = scaffold_manifest.get("files", [])
    scaffold_dirs = scaffold_manifest.get("directories", [])

    prompt_parts = [
        f"# Build Task: {batch_summary}",
        f"**Batch ID:** {batch_id}",
        f"**Project:** {project_name}",
        f"**Operating Mode:** {operating_mode}",
        "",
        "## What You Must Do",
        f"Implement the following for batch `{batch_id}`: **{batch_summary}**",
        "",
        "### Acceptance Criteria",
        *[f"- {criterion}" for criterion in acceptance_criteria],
        "",
        "## Project Context",
        f"**Target repository:** {target_path}",
        f"**Tech stack:** {json.dumps(stack, indent=2) if stack else 'See design brief below'}",
        "",
    ]

    # Include the source spec if available (this is the original SPEC.md content)
    if source_spec:
        prompt_parts.extend([
            "## Original Product Specification",
            "```markdown",
            source_spec[:15000],  # Cap at 15K chars to stay within prompt limits
            "```",
            "",
        ])

    # Include the full feature map
    if features:
        prompt_parts.extend([
            "## Feature Map",
            "All features for this product (implement only what's relevant to this batch):",
            "```json",
            json.dumps(features, indent=2)[:8000],
            "```",
            "",
        ])

    # Include the design brief
    if design_brief:
        prompt_parts.extend([
            "## Design Brief",
            "```json",
            json.dumps(design_brief, indent=2)[:5000],
            "```",
            "",
        ])

    # Include all batches for context (so builder understands scope)
    if all_batches:
        prompt_parts.extend([
            "## All Build Batches (for context — implement ONLY this batch)",
            "```json",
            json.dumps(all_batches, indent=2)[:5000],
            "```",
            "",
        ])

    # Include scaffold info
    if scaffold_files or scaffold_dirs:
        prompt_parts.extend([
            "## Existing Project Structure",
            "These files/directories already exist in the target repo:",
        ])
        for d in scaffold_dirs[:20]:
            prompt_parts.append(f"- `{d}/`")
        for f in scaffold_files[:30]:
            path = f.get("path", f) if isinstance(f, dict) else f
            prompt_parts.append(f"- `{path}`")
        prompt_parts.append("")

    # Include verification requirements
    if verification_commands or required_checks:
        prompt_parts.extend([
            "## Verification Requirements",
            "After implementing, these commands/checks must pass:",
        ])
        for cmd in verification_commands:
            prompt_parts.append(f"- `{cmd}`")
        for check in required_checks:
            prompt_parts.append(f"- {check}")
        prompt_parts.append("")

    # Add conventions
    prompt_parts.extend([
        _BACKEND_CONVENTIONS,
        _FRONTEND_CONVENTIONS,
        _GENERAL_CONVENTIONS,
    ])

    # Final instructions
    prompt_parts.extend([
        "## Execution Instructions",
        "1. You are running inside the target repository directory.",
        "2. Read any existing files to understand current project state.",
        "3. Implement ONLY the features specified in this batch's acceptance criteria.",
        "4. Create or modify files as needed. Write complete, working code.",
        "5. Do NOT create placeholder files or TODO stubs.",
        "6. After implementation, verify your changes make sense in context.",
        "7. If tests are required by the verification contract, write them.",
        "",
        "**IMPORTANT:** You have full access to the filesystem within this repository.",
        "Do NOT reference any files outside this directory.",
        "Everything you need is in this prompt.",
    ])

    return "\n".join(prompt_parts)


def assemble_repair_prompt(
    failed_job_id: str,
    failure_summary: str,
    original_acceptance_criteria: list[str],
    verification_issues: list[str] | None = None,
    target_contract: dict[str, Any] | None = None,
) -> str:
    """Assemble a prompt for a FIX_BATCH job."""
    parts = [
        f"# Repair Task: Fix {failed_job_id}",
        "",
        "## What Failed",
        f"Job `{failed_job_id}` failed with: {failure_summary}",
        "",
        "## Original Acceptance Criteria",
        *[f"- {criterion}" for criterion in original_acceptance_criteria],
        "",
        "## What You Must Do",
        "1. Read the existing code in this repository.",
        "2. Identify why the original implementation failed.",
        "3. Fix the issues so that the acceptance criteria pass.",
        "4. Do NOT rewrite from scratch — fix the specific failures.",
        "",
    ]

    if verification_issues:
        parts.extend([
            "## Verification Issues to Fix",
            *[f"- {issue}" for issue in verification_issues],
            "",
        ])

    if target_contract:
        stack = target_contract.get("stack", {})
        if stack:
            parts.extend([
                "## Tech Stack",
                f"```json\n{json.dumps(stack, indent=2)}\n```",
                "",
            ])

    parts.extend([
        "## Execution Instructions",
        "1. You are running inside the target repository directory.",
        "2. Read existing files to understand current state.",
        "3. Make targeted fixes — minimal changes to resolve the failures.",
        "4. Verify your changes make sense in context.",
    ])

    return "\n".join(parts)


def assemble_test_authoring_prompt(
    build_plan: dict[str, Any],
    scaffold_manifest: dict[str, Any],
    verification_contract: dict[str, Any],
) -> str:
    """Assemble a prompt for TEST_AUTHORING job."""
    commands = verification_contract.get("commands", [])
    required_checks = verification_contract.get("required_checks", [])
    target_path = scaffold_manifest.get("target_path", "")

    parts = [
        "# Test Authoring Task",
        "",
        f"**Target repository:** {target_path}",
        "",
        "## What You Must Do",
        "Write comprehensive tests for the project in this repository.",
        "",
        "### Requirements",
        "1. Read all existing source files to understand what was built.",
        "2. Write unit tests for backend routes and services.",
        "3. Write integration tests for API endpoints.",
        "4. If a frontend exists, write basic component tests.",
        "5. Ensure all tests can be run with standard commands.",
        "",
    ]

    if commands:
        parts.extend([
            "## Verification Commands (tests must pass these)",
            *[f"- `{cmd}`" for cmd in commands],
            "",
        ])

    if required_checks:
        parts.extend([
            "## Required Checks",
            *[f"- {check}" for check in required_checks],
            "",
        ])

    parts.extend([
        "## Execution Instructions",
        "1. You are running inside the target repository.",
        "2. Read existing code first, then write tests for it.",
        "3. Use pytest for Python tests, vitest/jest for TypeScript.",
        "4. Tests should be meaningful — not just smoke tests.",
    ])

    return "\n".join(parts)
