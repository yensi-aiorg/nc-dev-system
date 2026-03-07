from __future__ import annotations

from pathlib import Path

from ncdev.v2.design_brief import generate_design_brief
from ncdev.discovery.ingest import IngestedSource, ingest_source
from ncdev.v2.models import (
    BuildBatchV2,
    BuildPlanDoc,
    DesignBriefDoc,
    DesignDirection,
    DesignPackDoc,
    FeatureCandidate,
    FeatureMapDoc,
    PhaseDefinition,
    PhasePlanDoc,
    ResearchFinding,
    ResearchPackDoc,
    ScaffoldPlanDoc,
    SourceAsset,
    SourcePackDoc,
    TaskType,
    TargetProjectContractDoc,
)


def _feature_lines(text: str) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        item = raw.strip()
        if not item:
            continue
        if item.startswith(("-", "*")) or item[:2].isdigit():
            cleaned = item.lstrip("-*0123456789. ").strip()
            if cleaned and cleaned.lower() not in seen:
                seen.add(cleaned.lower())
                lines.append(cleaned)
            continue
        if item.startswith("|") and item.endswith("|"):
            cells = [cell.strip(" *`") for cell in item.split("|")[1:-1]]
            if not cells or set("".join(cells)) <= {"-", ":"}:
                continue
            candidate = cells[0].strip()
            if candidate and candidate.lower() not in {"capability", "requirement", "project", "service"} and candidate.lower() not in seen:
                seen.add(candidate.lower())
                lines.append(candidate)
    return lines


def run_discovery_pipeline(
    source_path: Path | str,
    dry_run: bool,
) -> tuple[SourcePackDoc, ResearchPackDoc, FeatureMapDoc, DesignPackDoc, DesignBriefDoc, BuildPlanDoc, PhasePlanDoc, TargetProjectContractDoc, ScaffoldPlanDoc]:
    return run_discovery_pipeline_with_target(source_path, dry_run=dry_run, target_repo_path=None)


def run_discovery_pipeline_with_target(
    source_path: Path | str,
    *,
    dry_run: bool,
    target_repo_path: Path | str | None,
) -> tuple[SourcePackDoc, ResearchPackDoc, FeatureMapDoc, DesignPackDoc, DesignBriefDoc, BuildPlanDoc, PhasePlanDoc, TargetProjectContractDoc, ScaffoldPlanDoc]:
    ingested: IngestedSource = ingest_source(str(source_path))
    source_inputs = [ingested.primary_source]
    text = ingested.content
    project_name = ingested.project_name
    target_repo_notes: list[str] = []
    target_repo_value = ""
    if target_repo_path:
        target_repo_value = str(Path(str(target_repo_path)).expanduser().resolve())
        if target_repo_value != ingested.primary_source:
            repo_ingested = ingest_source(target_repo_value)
            text = f"{text}\n\n## TARGET REPOSITORY CONTEXT\n{repo_ingested.content}".strip()
            source_inputs.append(repo_ingested.primary_source)
            target_repo_notes = repo_ingested.notes
    feature_lines = _feature_lines(text)
    if not feature_lines:
        feature_lines = ["Core delivery workflow", "Primary user journey", "Admin and support baseline"]

    source_pack = SourcePackDoc(
        generator="ncdev.v2.discovery.pipeline",
        source_inputs=source_inputs,
        project_name=project_name,
        source_kind=ingested.source_kind,
        primary_source=ingested.primary_source,
        assets=[
            SourceAsset(path=asset.path, kind=asset.kind, digest=asset.digest, bytes=asset.bytes)
            for asset in ingested.assets
        ],
        notes=ingested.notes + target_repo_notes + ["dry-run discovery heuristics applied" if dry_run else "local discovery heuristics applied"],
    )

    research_pack = ResearchPackDoc(
        generator="ncdev.v2.discovery.pipeline",
        source_inputs=source_inputs,
        project_name=project_name,
        market_present=bool(target_repo_value),
        user_segments=["primary operator", "end user", "administrator"],
        pain_points=[
            "Current workflow is fragmented or underspecified.",
            "Users need a clearer task flow with lower cognitive load.",
            "The product should differentiate through design quality, not only functionality.",
        ],
        opportunities=[
            "Use an opinionated visual system to stand out from default AI-generated layouts.",
            "Package testing and evidence in the target project from the start.",
        ],
        findings=[
            ResearchFinding(
                title="Initial product framing",
                detail="Source pack did not include an explicit market-research artifact, so discovery inferred likely user and operator needs from the requirements text.",
            )
        ],
    )

    features = [
        FeatureCandidate(
            name=item[:80],
            description=item,
            audience=["end user"],
            priority="P1" if idx else "P0",
            surfaces=["web"],
        )
        for idx, item in enumerate(feature_lines)
    ]
    feature_map = FeatureMapDoc(
        generator="ncdev.v2.discovery.pipeline",
        source_inputs=source_inputs,
        project_name=project_name,
        features=features,
        ux_principles=[
            "Prioritize clarity of primary flows over dashboard density.",
            "Keep design tokens separate from business logic.",
            "Support visually distinctive styling through theme-level changes.",
        ],
        recommended_platforms=["web"],
    )

    design_pack = DesignPackDoc(
        generator="ncdev.v2.discovery.pipeline",
        source_inputs=source_inputs,
        project_name=project_name,
        selected_direction="electric",
        directions=[
            DesignDirection(name="electric", rationale="High-contrast, vivid product identity with strong visual differentiation.", traits=["charged", "bold", "high-contrast"]),
            DesignDirection(name="gloss", rationale="Polished premium surfaces with reflective depth and restrained luxury.", traits=["polished", "premium", "layered"]),
            DesignDirection(name="editorial", rationale="Typography-led layout language that feels intentional rather than dashboard-generic.", traits=["typographic", "composed", "expressive"]),
        ],
        theme_tokens={
            "color.primary": "#0f172a",
            "color.accent": "#14b8a6",
            "color.highlight": "#f97316",
            "font.display": "Space Grotesk",
            "radius.card": "24px",
        },
        component_rules=[
            "Avoid default left-nav plus blank-content shell unless the product truly needs it.",
            "Use asymmetry and intentional visual hierarchy on primary entry screens.",
            "Prefer themed surfaces and motion presets over ad hoc inline styling.",
        ],
    )

    design_brief = generate_design_brief(design_pack, feature_map, research_pack)

    build_plan = BuildPlanDoc(
        generator="ncdev.v2.discovery.pipeline",
        source_inputs=source_inputs,
        project_name=project_name,
        batches=[
            BuildBatchV2(
                id=f"batch-{idx+1:03d}",
                title=f"Implement {feature.name}",
                task_type=TaskType.BUILD_BATCH,
                summary=feature.description,
                acceptance_criteria=[f"{feature.name} is implemented with target-project tests and harness coverage."],
            )
            for idx, feature in enumerate(features)
        ],
        risks=[
            "Discovery is heuristic in Phase 1 and should be upgraded with richer research sources.",
            "Design pack is generated locally and should later integrate visual-designer exports.",
        ],
    )
    phase_plan = PhasePlanDoc(
        generator="ncdev.v2.discovery.pipeline",
        source_inputs=source_inputs,
        project_name=project_name,
        target_repo_path=target_repo_value,
        phases=[
            PhaseDefinition(
                phase_id=f"phase-{idx+1:02d}",
                title=f"Phase {idx+1}: {feature.name}",
                goal=feature.description,
                feature_ids=[feature.name],
                deliverables=[
                    f"Implement {feature.name} in the target repository.",
                    "Add or update unit, integration, and Playwright coverage as required.",
                    "Produce evidence artifacts for the affected user flow.",
                ],
                exit_criteria=[
                    f"{feature.name} passes scoped verification.",
                    "Target-repo tests are updated and green for the phase.",
                    "Required screenshots and reports are produced for the phase.",
                ],
            )
            for idx, feature in enumerate(features)
        ],
    )
    target_contract = TargetProjectContractDoc(
        generator="ncdev.v2.discovery.pipeline",
        source_inputs=source_inputs,
        project_name=project_name,
        target_type="web",
        target_repo_path=target_repo_value,
        stack={
            "frontend": "React 19 + Vite + TypeScript",
            "backend": "FastAPI + Python 3.12",
            "storage": "MongoDB",
            "e2e": "Playwright",
        },
        ownership_rules=[
            "All generated application code belongs in the target project.",
            "All generated tests belong in the target project.",
            "NC Dev System only retains orchestration metadata and evidence artifacts.",
        ],
        required_artifacts=[
            "frontend/",
            "backend/",
            "docker-compose.yml",
            "frontend/playwright.config.ts",
            "frontend/e2e/screenshots/",
            "frontend/test-results/",
            "frontend/playwright-report/",
        ],
    )
    scaffold_plan = ScaffoldPlanDoc(
        generator="ncdev.v2.discovery.pipeline",
        source_inputs=source_inputs,
        project_name=project_name,
        directories=[
            "frontend/src",
            "frontend/e2e",
            "frontend/e2e/screenshots",
            "backend/app",
            "backend/tests",
            "docs/evidence",
        ],
        files=[
            "frontend/package.json",
            "frontend/playwright.config.ts",
            "backend/pyproject.toml",
            "docker-compose.yml",
            "scripts/run-tests.sh",
            "scripts/run-evidence-checks.sh",
        ],
        commands=[
            "npm install",
            "python -m venv .venv",
            "pytest -q",
            "npx playwright test",
        ],
        test_harness=[
            "frontend unit tests",
            "backend unit tests",
            "integration tests",
            "playwright e2e tests",
            "evidence capture directory",
        ],
    )
    return source_pack, research_pack, feature_map, design_pack, design_brief, build_plan, phase_plan, target_contract, scaffold_plan
