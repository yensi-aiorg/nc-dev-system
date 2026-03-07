from pathlib import Path

from ncdev.v2.config import ensure_default_v2_config, load_v2_config
from ncdev.v2.models import TaskType


def test_v2_config_roundtrip(tmp_path: Path) -> None:
    config = ensure_default_v2_config(tmp_path)
    loaded = load_v2_config(tmp_path)
    assert loaded.providers["anthropic_claude_code"].enabled is True
    assert loaded.providers["openai_codex"].preferred_models["implementation"] == "gpt-5.2-codex"
    assert config.routing.providers_for(TaskType.BUILD_BATCH) == ["openai_codex"]

