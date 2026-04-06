"""Feature queue — converts discovery artifacts into an ordered feature list.

Replaces V2's parallel batch model with sequential vertical slices.
Each feature is a complete vertical slice: backend + frontend + tests.
"""

from __future__ import annotations

import json
from pathlib import Path

from ncdev.v3.models import FeatureQueueDoc, FeatureStep


def materialize_feature_queue(
    run_dir: Path,
    project_name: str = "",
) -> FeatureQueueDoc:
    """Read discovery artifacts and produce an ordered feature queue.

    The ordering is critical: infrastructure first, then data layer,
    then API, then UI, then integration. Each feature builds on the last.
    """
    outputs_dir = run_dir / "outputs"

    # Load discovery artifacts
    build_plan = _load_json(outputs_dir / "build-plan.json")
    feature_map = _load_json(outputs_dir / "feature-map.json")
    target_contract = _load_json(outputs_dir / "target-project-contract.json")
    design_brief = _load_json(outputs_dir / "design-brief.json")

    project_name = project_name or build_plan.get("project_name", "unknown")
    stack = target_contract.get("stack", {})

    features: list[FeatureStep] = []

    # Sprint 0: Project scaffold (always first)
    features.append(FeatureStep(
        feature_id="sprint-0",
        title="Project Scaffold & Boot",
        description=(
            f"Create the base project structure for {project_name}. "
            f"Stack: {json.dumps(stack)}. "
            "Set up the backend (FastAPI), frontend (React/Vite/Tailwind), "
            "Docker Compose, environment config, and health endpoint. "
            "The app must install, boot, and respond to GET /api/health with {\"status\": \"ok\"}. "
            "Set up test infrastructure (pytest for backend, vitest for frontend, Playwright for e2e). "
            "Run the empty test suite to confirm it works."
        ),
        acceptance_criteria=[
            "Backend boots with uvicorn and GET /api/health returns {\"status\": \"ok\"}",
            "Frontend boots with Vite dev server and renders a page",
            "pytest runs with 0 errors (even if 0 tests)",
            "Docker Compose file exists with all services",
            ".env.example documents all required variables",
            "Project installs without errors (pip install -e . and npm install)",
        ],
        test_requirements=[
            "One backend test: test_health_returns_ok",
            "One frontend smoke test: app renders without crashing",
        ],
        priority=0,
    ))

    # Convert build plan batches into ordered feature steps
    raw_features = feature_map.get("features", [])
    batches = build_plan.get("batches", [])

    # Group features by type for proper ordering
    data_features = []
    api_features = []
    ui_features = []
    integration_features = []
    other_features = []

    for i, batch in enumerate(batches):
        summary = batch.get("summary", "").lower()
        title = batch.get("title", batch.get("summary", f"Feature {i+1}"))
        criteria = batch.get("acceptance_criteria", [f"{title} works end-to-end"])

        step = FeatureStep(
            feature_id=f"feature-{i+1:02d}",
            title=title,
            description=batch.get("summary", title),
            acceptance_criteria=criteria,
            test_requirements=[
                f"Unit tests for {title}",
                f"Integration test verifying {title} works with the rest of the app",
            ],
            priority=i + 1,
        )

        # Classify for ordering
        if any(kw in summary for kw in ["model", "schema", "database", "data"]):
            data_features.append(step)
        elif any(kw in summary for kw in ["route", "api", "endpoint", "auth"]):
            api_features.append(step)
        elif any(kw in summary for kw in ["page", "ui", "frontend", "component", "view"]):
            ui_features.append(step)
        elif any(kw in summary for kw in ["docker", "deploy", "config", "environment"]):
            integration_features.append(step)
        else:
            other_features.append(step)

    # Order: data → API → UI → integration → other
    ordered = data_features + api_features + ui_features + other_features + integration_features

    # Set dependencies — each feature depends on the previous
    prev_id = "sprint-0"
    for step in ordered:
        step.depends_on_features = [prev_id]
        prev_id = step.feature_id
        features.append(step)

    return FeatureQueueDoc(
        project_name=project_name,
        features=features,
    )


def _load_json(path: Path) -> dict:
    """Load a JSON file, returning empty dict if not found."""
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}
