from __future__ import annotations

import json
from pathlib import Path

from ncdev.v2.design_brief import generate_design_brief
from ncdev.v2.engine import run_v2_prepare
from ncdev.v2.models import (
    DesignBriefDoc,
    DesignDirection,
    DesignPackDoc,
    FeatureCandidate,
    FeatureMapDoc,
    ResearchPackDoc,
)


def _make_design_pack(direction: str = "electric") -> DesignPackDoc:
    return DesignPackDoc(
        generator="test",
        source_inputs=[],
        project_name="test-project",
        selected_direction=direction,
        directions=[
            DesignDirection(name="electric", rationale="Bold.", traits=["charged", "bold"]),
            DesignDirection(name="gloss", rationale="Premium.", traits=["polished", "premium"]),
            DesignDirection(name="editorial", rationale="Typographic.", traits=["composed"]),
        ],
        theme_tokens={
            "color.primary": "#111111",
            "color.accent": "#00ff00",
            "font.display": "Custom Font",
            "radius.card": "20px",
        },
        component_rules=["Rule from design pack."],
    )


def _make_feature_map() -> FeatureMapDoc:
    return FeatureMapDoc(
        generator="test",
        source_inputs=[],
        project_name="test-project",
        features=[
            FeatureCandidate(name="Auth", description="Sign in"),
            FeatureCandidate(name="Projects", description="Manage projects"),
        ],
        ux_principles=["Clarity first.", "Token separation."],
    )


def _make_research_pack() -> ResearchPackDoc:
    return ResearchPackDoc(
        generator="test",
        source_inputs=[],
        project_name="test-project",
    )


def test_generate_design_brief_returns_doc() -> None:
    brief = generate_design_brief(_make_design_pack())
    assert isinstance(brief, DesignBriefDoc)
    assert brief.project_name == "test-project"
    assert brief.direction_name == "electric"
    assert brief.schema_id == "design-brief.v2"


def test_design_brief_applies_token_overrides() -> None:
    brief = generate_design_brief(_make_design_pack())
    assert brief.colors.primary == "#111111"
    assert brief.colors.accent == "#00ff00"
    assert brief.typography.font_display == "Custom Font"
    assert brief.radius_shadow.radius["lg"] == "20px"


def test_design_brief_includes_component_rules() -> None:
    brief = generate_design_brief(_make_design_pack())
    assert "Rule from design pack." in brief.composition_rules


def test_design_brief_with_feature_map_merges_ux_principles() -> None:
    brief = generate_design_brief(_make_design_pack(), _make_feature_map())
    assert "Clarity first." in brief.composition_rules
    assert "Token separation." in brief.composition_rules
    assert f"feature-map:test-project" in brief.source_inputs


def test_design_brief_with_research_pack_records_source() -> None:
    brief = generate_design_brief(_make_design_pack(), research_pack=_make_research_pack())
    assert "research-pack:test-project" in brief.source_inputs


def test_design_brief_gloss_direction() -> None:
    brief = generate_design_brief(_make_design_pack(direction="gloss"))
    assert brief.direction_name == "gloss"
    assert brief.colors.background == "#ffffff"


def test_design_brief_editorial_direction() -> None:
    brief = generate_design_brief(_make_design_pack(direction="editorial"))
    assert brief.direction_name == "editorial"
    assert brief.typography.font_display == "Custom Font"  # token override applied


def test_design_brief_unknown_direction_falls_back_to_electric() -> None:
    pack = _make_design_pack(direction="unknown")
    pack.directions = []
    brief = generate_design_brief(pack)
    assert brief.direction_name == "unknown"


def test_v2_prepare_produces_design_brief_artifact(tmp_path: Path) -> None:
    req = tmp_path / "requirements.md"
    req.write_text("# Product\n- User can sign in\n- User can manage projects\n", encoding="utf-8")
    state = run_v2_prepare(tmp_path, req, dry_run=True)
    run_dir = Path(state.run_dir)
    brief_path = run_dir / "outputs" / "design-brief.json"
    assert brief_path.exists()

    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    assert brief["schema_id"] == "design-brief.v2"
    assert brief["direction_name"] == "electric"
    assert brief["typography"]["font_display"] == "Space Grotesk"
    assert brief["colors"]["accent"] == "#14b8a6"
    assert len(brief["composition_rules"]) > 0
