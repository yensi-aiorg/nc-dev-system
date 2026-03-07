from __future__ import annotations

from pathlib import Path

from ncdev.v2.design_brief import generate_design_brief
from ncdev.discovery.ingest import IngestedSource, ingest_source
from ncdev.utils import sha256_text
from ncdev.v2.models import (
    BuildBatchV2,
    BuildPlanDoc,
    DesignBriefDoc,
    DesignDirection,
    DesignPackDoc,
    FeatureCandidate,
    FeatureMapDoc,
    ResearchFinding,
    ResearchPackDoc,
    ScaffoldPlanDoc,
    SourceAsset,
    SourcePackDoc,
    TaskType,
    TargetProjectContractDoc,
)


def _feature_lines(text: str) -> list[str]:
    lines = []
    for raw in text.splitlines():
        item = raw.strip()
        if not item:
            continue
        if item.startswith(("-", "*")) or item[:2].isdigit():
            cleaned = item.lstrip("-*0123456789. ").strip()
            if cleaned:
                lines.append(cleaned)
    return lines


def run_discovery_pipeline(
    source_path: Path | str,
    dry_run: bool,
) -> tuple[SourcePackDoc, ResearchPackDoc, FeatureMapDoc, DesignPackDoc, DesignBriefDoc, BuildPlanDoc, TargetProjectContractDoc, ScaffoldPlanDoc]:
    ingested: IngestedSource = ingest_source(str(source_path))
    text = ingested.content
    project_name = ingested.project_name
    feature_lines = _feature_lines(text)
    if not feature_lines:
        feature_lines = ["Core delivery workflow", "Primary user journey", "Admin and support baseline"]

    source_pack = SourcePackDoc(
        generator="ncdev.v2.discovery.pipeline",
        source_inputs=[ingested.primary_source],
        project_name=project_name,
        source_kind=ingested.source_kind,
        primary_source=ingested.primary_source,
        assets=[
            SourceAsset(path=asset.path, kind=asset.kind, digest=asset.digest, bytes=asset.bytes)
            for asset in ingested.assets
        ],
        notes=ingested.notes + ["dry-run discovery heuristics applied" if dry_run else "local discovery heuristics applied"],
    )

    research_pack = ResearchPackDoc(
        generator="ncdev.v2.discovery.pipeline",
        source_inputs=[ingested.primary_source],
        project_name=project_name,
        market_present=False,
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
        source_inputs=[ingested.primary_source],
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
        source_inputs=[ingested.primary_source],
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
        source_inputs=[ingested.primary_source],
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
    target_contract = TargetProjectContractDoc(
        generator="ncdev.v2.discovery.pipeline",
        source_inputs=[ingested.primary_source],
        project_name=project_name,
        target_type="web",
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
            "playwright.config.ts",
            "test-results/",
        ],
    )
    scaffold_plan = ScaffoldPlanDoc(
        generator="ncdev.v2.discovery.pipeline",
        source_inputs=[ingested.primary_source],
        project_name=project_name,
        directories=[
            "frontend/src",
            "frontend/e2e",
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
    return source_pack, research_pack, feature_map, design_pack, design_brief, build_plan, target_contract, scaffold_plan
