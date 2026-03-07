from __future__ import annotations

from pathlib import Path

from ncdev.utils import read_text, sha256_text
from ncdev.v2.models import (
    BuildBatchV2,
    BuildPlanDoc,
    DesignDirection,
    DesignPackDoc,
    FeatureCandidate,
    FeatureMapDoc,
    ResearchFinding,
    ResearchPackDoc,
    SourceAsset,
    SourcePackDoc,
    TaskType,
)


def _project_name(source_path: Path) -> str:
    return source_path.stem or source_path.name or "project"


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


def run_discovery_pipeline(source_path: Path, dry_run: bool) -> tuple[SourcePackDoc, ResearchPackDoc, FeatureMapDoc, DesignPackDoc, BuildPlanDoc]:
    text = read_text(source_path)
    digest = sha256_text(text)
    project_name = _project_name(source_path)
    feature_lines = _feature_lines(text)
    if not feature_lines:
        feature_lines = ["Core delivery workflow", "Primary user journey", "Admin and support baseline"]

    source_pack = SourcePackDoc(
        generator="ncdev.v2.discovery.pipeline",
        source_inputs=[str(source_path)],
        project_name=project_name,
        source_kind="requirements_markdown",
        primary_source=str(source_path),
        assets=[
            SourceAsset(
                path=str(source_path),
                kind="requirements_markdown",
                digest=digest,
                bytes=len(text.encode("utf-8")),
            )
        ],
        notes=["dry-run discovery heuristics applied" if dry_run else "local discovery heuristics applied"],
    )

    research_pack = ResearchPackDoc(
        generator="ncdev.v2.discovery.pipeline",
        source_inputs=[str(source_path)],
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
        source_inputs=[str(source_path)],
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
        source_inputs=[str(source_path)],
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

    build_plan = BuildPlanDoc(
        generator="ncdev.v2.discovery.pipeline",
        source_inputs=[str(source_path)],
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
    return source_pack, research_pack, feature_map, design_pack, build_plan
