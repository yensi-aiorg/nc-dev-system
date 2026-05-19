from pathlib import Path

from ncdev.core.config import (
    DEFAULT_CAPABILITY_CHAINS,
    NCDevConfig,
    ensure_default_config,
    load_config,
)
from ncdev.core.models import TaskType


def test_config_roundtrip(tmp_path: Path) -> None:
    config = ensure_default_config(tmp_path)
    loaded = load_config(tmp_path)
    assert loaded.providers["anthropic_claude_code"].enabled is True
    assert loaded.providers["anthropic_claude_code"].preferred_models["planning"] == "auto"
    assert loaded.providers["openai_codex"].enabled is True
    assert loaded.providers["openai_codex"].preferred_models["implementation"] == "auto"
    assert config.routing.providers_for(TaskType.BUILD_BATCH) == ["openai_codex"]
    assert config.routing.providers_for(TaskType.MARKET_RESEARCH) == ["anthropic_claude_code"]


def test_capability_chains_carry_no_anthropic_or_codex_literals():
    for mode, chains in DEFAULT_CAPABILITY_CHAINS.items():
        for capability, choices in chains.items():
            for choice in choices:
                if choice.provider in ("anthropic_claude_code", "openai_codex"):
                    assert choice.model == "auto", (
                        f"{mode}/{capability} pins {choice.model!r}; expected 'auto'"
                    )


def test_provider_preferred_models_use_auto_sentinel():
    cfg = NCDevConfig()
    for name in ("anthropic_claude_code", "openai_codex"):
        for key, model in cfg.providers[name].preferred_models.items():
            assert model == "auto", f"{name}.{key} still pins {model!r}"
