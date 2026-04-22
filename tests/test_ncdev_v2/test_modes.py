"""Tests for the `mode` switch + MODE_PRESETS in v2 config."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from ncdev.v2.config import (
    DEFAULT_MODE,
    MODE_PRESETS,
    NCDevV2Config,
    ROUTING_TASK_KEYS,
    load_v2_config,
)
from ncdev.v2.models import TaskType


# ---------------------------------------------------------------------------
# Preset coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode,expected", [
    ("codex_only", "openai_codex"),
    ("claude_only", "anthropic_claude_code"),
    ("openrouter", "openrouter"),
])
def test_uniform_preset_maps_every_task_to_one_provider(mode, expected):
    cfg = NCDevV2Config(mode=mode)
    for key in ROUTING_TASK_KEYS:
        assert getattr(cfg.routing, key) == [expected], (
            f"mode={mode} key={key} expected=[{expected}] "
            f"actual={getattr(cfg.routing, key)}"
        )


def test_claude_plan_codex_build_splits_planning_from_impl():
    cfg = NCDevV2Config(mode="claude_plan_codex_build")
    # Planning/review go to Claude
    for key in ("source_ingest", "design_brief", "review", "second_opinion",
                "market_research", "feature_extraction", "sentinel_reproduce"):
        assert getattr(cfg.routing, key) == ["anthropic_claude_code"], key
    # Development/tests go to Codex
    for key in ("implementation", "test_authoring", "sentinel_fix"):
        assert getattr(cfg.routing, key) == ["openai_codex"], key


def test_custom_mode_preserves_hand_tuned_routing():
    cfg = NCDevV2Config(
        mode="custom",
        routing={
            "implementation": ["anthropic_claude_code"],
            "review": ["openai_codex"],
        },
    )
    assert cfg.routing.implementation == ["anthropic_claude_code"]
    assert cfg.routing.review == ["openai_codex"]


def test_unknown_mode_rejected():
    with pytest.raises(ValueError, match="Unknown mode"):
        NCDevV2Config(mode="nonsense")


def test_default_mode_is_claude_plan_codex_build():
    assert DEFAULT_MODE == "claude_plan_codex_build"
    cfg = NCDevV2Config()
    assert cfg.mode == DEFAULT_MODE
    assert cfg.routing.implementation == ["openai_codex"]
    assert cfg.routing.design_brief == ["anthropic_claude_code"]


def test_all_presets_cover_all_routing_keys():
    """Guards against forgetting a key when a new routing field is added."""
    for preset_name, preset in MODE_PRESETS.items():
        if not preset:  # "custom"
            continue
        assert set(preset.keys()) == set(ROUTING_TASK_KEYS), (
            f"preset '{preset_name}' is missing keys: "
            f"{set(ROUTING_TASK_KEYS) - set(preset.keys())}"
        )


# ---------------------------------------------------------------------------
# Persistence — mode survives YAML round-trip and is applied on reload.
# ---------------------------------------------------------------------------


def test_mode_roundtrip_via_yaml(tmp_path: Path):
    cfg_path = tmp_path / ".nc-dev" / "v2" / "config.yaml"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    NCDevV2Config(mode="codex_only").to_yaml_dict()
    raw = NCDevV2Config(mode="codex_only").to_yaml_dict()
    yaml.safe_dump(raw, cfg_path.open("w"), sort_keys=False)

    loaded = load_v2_config(tmp_path)
    assert loaded.mode == "codex_only"
    assert loaded.routing.design_brief == ["openai_codex"]
    assert loaded.routing.implementation == ["openai_codex"]


def test_yaml_without_mode_field_loads_with_default(tmp_path: Path):
    cfg_path = tmp_path / ".nc-dev" / "v2" / "config.yaml"
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text("routing:\n  implementation: [openai_codex]\n")

    loaded = load_v2_config(tmp_path)
    assert loaded.mode == DEFAULT_MODE
    # Default mode's preset overrides whatever routing was in the file.
    assert loaded.routing.design_brief == ["anthropic_claude_code"]


# ---------------------------------------------------------------------------
# providers_for() reflects the active mode.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode,task,expected", [
    ("codex_only", TaskType.DESIGN_BRIEF, ["openai_codex"]),
    ("claude_only", TaskType.BUILD_BATCH, ["anthropic_claude_code"]),
    ("openrouter", TaskType.TEST_AUTHORING, ["openrouter"]),
    ("claude_plan_codex_build", TaskType.DESIGN_BRIEF, ["anthropic_claude_code"]),
    ("claude_plan_codex_build", TaskType.BUILD_BATCH, ["openai_codex"]),
])
def test_providers_for_task_respects_mode(mode, task, expected):
    cfg = NCDevV2Config(mode=mode)
    assert cfg.routing.providers_for(task) == expected
