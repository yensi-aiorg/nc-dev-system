"""Tests for the deterministic design-system seed (v4 defect #8).

design_seed is the always-works fallback for greenfield UI runs without
Stitch. Its output flows untouched into every downstream feature build,
so a silent malformation would propagate everywhere. These tests assert
the seed produces schema-valid, well-formed, reloadable artifacts for
every archetype.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ncdev.pipeline.design_seed import ARCHETYPES, seed_design_system
from ncdev.pipeline.models import DesignSystemDoc


@pytest.mark.parametrize("archetype", sorted(ARCHETYPES.keys()))
def test_seed_produces_valid_doc_for_every_archetype(tmp_path: Path, archetype: str):
    target = tmp_path / "repo"
    outputs = tmp_path / "run" / "outputs"

    doc = seed_design_system(
        target, outputs, project_name="demo", archetype=archetype,
    )

    assert isinstance(doc, DesignSystemDoc)
    assert doc.design_archetype == archetype
    assert doc.source == "claude_generated"
    assert doc.project_name == "demo"


@pytest.mark.parametrize("archetype", sorted(ARCHETYPES.keys()))
def test_seed_writes_all_four_files(tmp_path: Path, archetype: str):
    target = tmp_path / "repo"
    outputs = tmp_path / "run" / "outputs"
    seed_design_system(target, outputs, project_name="demo", archetype=archetype)

    ds_dir = target / "docs" / "design-system"
    for name in ("tokens.json", "tokens.css", "tailwind-preset.js", "components.md"):
        path = ds_dir / name
        assert path.is_file(), f"{name} not written"
        assert path.read_text(encoding="utf-8").strip(), f"{name} is empty"


@pytest.mark.parametrize("archetype", sorted(ARCHETYPES.keys()))
def test_tokens_json_is_valid_and_complete(tmp_path: Path, archetype: str):
    target = tmp_path / "repo"
    seed_design_system(
        target, tmp_path / "out", project_name="demo", archetype=archetype,
    )
    tokens = json.loads(
        (target / "docs/design-system/tokens.json").read_text(encoding="utf-8")
    )
    for key in (
        "colors", "fonts", "typography_scale", "spacing",
        "radii", "shadows", "motion", "archetype", "summary",
    ):
        assert key in tokens, f"tokens.json missing {key!r}"
    # Core colour roles every component template references must exist.
    for role in ("background", "surface", "text", "primary", "primary_text", "border"):
        assert role in tokens["colors"], f"colour role {role!r} missing"
    assert tokens["archetype"] == archetype


def test_design_system_json_reloads_as_model(tmp_path: Path):
    outputs = tmp_path / "run" / "outputs"
    seed_design_system(
        tmp_path / "repo", outputs,
        project_name="demo", archetype="Technical Elegance",
    )
    raw = (outputs / "design-system.json").read_text(encoding="utf-8")
    # Must round-trip back through the Pydantic model — schema-valid.
    reloaded = DesignSystemDoc.model_validate_json(raw)
    assert reloaded.design_archetype == "Technical Elegance"
    assert "tokens.json" in reloaded.tokens_files


def test_css_contains_every_colour_token(tmp_path: Path):
    target = tmp_path / "repo"
    seed_design_system(
        target, tmp_path / "out",
        project_name="demo", archetype="Opinionated Darkness",
    )
    css = (target / "docs/design-system/tokens.css").read_text(encoding="utf-8")
    colors = ARCHETYPES["Opinionated Darkness"]["colors"]
    for key in colors:
        assert f"--color-{key.replace('_', '-')}:" in css


def test_unknown_archetype_falls_back_and_records_resolved_name(tmp_path: Path):
    """An unknown archetype must fall back to Warm Playfulness AND record
    that resolved name — never claim an archetype whose tokens were not
    actually used."""
    target = tmp_path / "repo"
    outputs = tmp_path / "out"
    doc = seed_design_system(
        target, outputs, project_name="demo", archetype="Nonexistent Vibe",
    )
    assert doc.design_archetype == "Warm Playfulness"
    tokens = json.loads(
        (target / "docs/design-system/tokens.json").read_text(encoding="utf-8")
    )
    assert tokens["archetype"] == "Warm Playfulness"
    assert tokens["colors"] == ARCHETYPES["Warm Playfulness"]["colors"]


def test_bootstrap_feature_id_is_tagged_into_tokens(tmp_path: Path):
    target = tmp_path / "repo"
    seed_design_system(
        target, tmp_path / "out",
        project_name="demo", archetype="Cinematic Minimalism",
        bootstrap_feature_id="f00-init",
    )
    tokens = json.loads(
        (target / "docs/design-system/tokens.json").read_text(encoding="utf-8")
    )
    assert tokens["owned_by_feature"] == "f00-init"
    components = (target / "docs/design-system/components.md").read_text(encoding="utf-8")
    assert "f00-init" in components
