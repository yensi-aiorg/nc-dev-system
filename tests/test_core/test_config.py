from pathlib import Path

from ncdev.core.config import ensure_default_config, load_config
from ncdev.core.models import TaskType


def test_config_roundtrip(tmp_path: Path) -> None:
    config = ensure_default_config(tmp_path)
    loaded = load_config(tmp_path)
    assert loaded.providers["anthropic_claude_code"].enabled is True
    assert loaded.providers["anthropic_claude_code"].preferred_models["planning"] == "opus"
    assert loaded.providers["openai_codex"].enabled is True
    assert loaded.providers["openai_codex"].preferred_models["implementation"] == "gpt-5.4"
    assert config.routing.providers_for(TaskType.BUILD_BATCH) == ["openai_codex"]
    assert config.routing.providers_for(TaskType.MARKET_RESEARCH) == ["anthropic_claude_code"]
