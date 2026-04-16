from pathlib import Path

from ncdev.v2.config import ensure_default_v2_config, load_v2_config
from ncdev.v2.models import TaskType


def test_v2_config_roundtrip(tmp_path: Path) -> None:
    config = ensure_default_v2_config(tmp_path)
    loaded = load_v2_config(tmp_path)
    assert loaded.providers["openai_codex"].enabled is True
    assert loaded.providers["openai_codex"].preferred_models["planning"] == "gpt-5.4"
    assert config.routing.providers_for(TaskType.BUILD_BATCH) == ["openai_codex"]
