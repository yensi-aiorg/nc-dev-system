from __future__ import annotations

import re
from pathlib import Path

from ncdev.models import ArchitectureDoc, FeatureItem, FeaturesDoc, TestPlanDoc

FEATURE_PREFIXES = ("-", "*", "1.", "2.", "3.", "4.", "5.")


def parse_requirements(requirements_path: Path) -> tuple[FeaturesDoc, ArchitectureDoc, TestPlanDoc]:
    text = requirements_path.read_text(encoding="utf-8")
    lines = [x.strip() for x in text.splitlines() if x.strip()]

    features: list[FeatureItem] = []
    for raw in lines:
        if raw.startswith(FEATURE_PREFIXES):
            item = re.sub(r"^(-|\*|\d+\.)\s*", "", raw).strip()
            if len(item) > 4:
                features.append(
                    FeatureItem(
                        name=item[:80],
                        description=item,
                        priority="P1",
                        complexity="medium",
                    )
                )

    if not features:
        features = [
            FeatureItem(
                name="core-delivery",
                description="Implement requirements-derived core functionality.",
                priority="P0",
                complexity="complex",
            )
        ]

    features_doc = FeaturesDoc(features=features)

    arch = ArchitectureDoc(
        summary="Generated from requirements markdown using baseline parser.",
        components=["frontend", "backend", "database", "test-runner"],
        api_contracts=[{"name": "health", "method": "GET", "path": "/health"}],
        data_stores=["mongodb"],
        external_dependencies=[],
    )

    test_plan = TestPlanDoc(
        e2e_scenarios=[f"Validate feature: {f.name}" for f in features[:10]],
        visual_checkpoints=["home-page", "core-flows"],
        mock_requirements=["All external APIs must be mockable with deterministic responses."],
    )

    return features_doc, arch, test_plan
