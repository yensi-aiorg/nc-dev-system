from pathlib import Path

import pytest

from ncdev.core.config import NCDevConfig, ProviderPreferenceConfig, RoutingConfig
from ncdev.provider_dispatch import (
    PROVIDER_ALIASES,
    _load_cached_config,
    _workspace_root,
    get_provider_for,
    preferred_model_for,
    provider_name_for,
    reset_cache,
    resolve_provider_name,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    reset_cache()
    yield
    reset_cache()


def test_resolve_provider_name_long_alias() -> None:
    assert resolve_provider_name("anthropic_claude_code") == "claude"
    assert resolve_provider_name("openai_codex") == "codex"


def test_resolve_provider_name_short_passthrough() -> None:
    assert resolve_provider_name("claude") == "claude"
    assert resolve_provider_name("codex") == "codex"
    assert resolve_provider_name("openrouter") == "openrouter"


def test_resolve_provider_name_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unknown provider routing name"):
        resolve_provider_name("gemini_cli")


def test_provider_aliases_cover_all_short_names() -> None:
    short_names = set(PROVIDER_ALIASES.values())
    assert {"claude", "codex", "openrouter"} <= short_names


def test_workspace_root_explicit_wins(tmp_path: Path) -> None:
    assert _workspace_root(tmp_path) == tmp_path


def test_workspace_root_falls_back_to_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NCDEV_WORKSPACE", str(tmp_path))
    assert _workspace_root(None) == tmp_path


def test_workspace_root_defaults_to_cwd(monkeypatch) -> None:
    monkeypatch.delenv("NCDEV_WORKSPACE", raising=False)
    assert _workspace_root(None) == Path.cwd()


def test_load_cached_config_caches_per_workspace(tmp_path: Path) -> None:
    cfg1 = _load_cached_config(tmp_path)
    cfg2 = _load_cached_config(tmp_path)
    assert cfg1 is cfg2  # cached
    reset_cache()
    cfg3 = _load_cached_config(tmp_path)
    assert cfg3 is not cfg1  # fresh after reset


def _build_config_with_routing(task_key: str, providers: list[str]) -> NCDevConfig:
    routing = RoutingConfig(**{task_key: providers})
    return NCDevConfig(mode="custom", routing=routing)


def test_provider_name_for_returns_short_alias() -> None:
    cfg = _build_config_with_routing("implementation", ["openai_codex"])
    assert provider_name_for("implementation", config=cfg) == "codex"


def test_provider_name_for_unrouted_task_raises() -> None:
    cfg = NCDevConfig()
    with pytest.raises(ValueError, match="No providers configured"):
        provider_name_for("unknown_task_key", config=cfg)


def test_get_provider_for_resolves_to_provider_instance() -> None:
    cfg = _build_config_with_routing("implementation", ["openai_codex"])
    provider = get_provider_for("implementation", config=cfg)
    assert provider is not None


def test_preferred_model_for_returns_configured_model() -> None:
    cfg = NCDevConfig(
        mode="custom",
        routing=RoutingConfig(implementation=["openai_codex"]),
        providers={
            "openai_codex": ProviderPreferenceConfig(
                enabled=True,
                preferred_models={"implementation": "gpt-5.5"},
            ),
        },
    )
    assert preferred_model_for("implementation", "implementation", config=cfg) == "gpt-5.5"


def test_preferred_model_for_returns_none_when_unrouted() -> None:
    cfg = NCDevConfig()
    assert preferred_model_for("nope", "planning", config=cfg) is None


def test_preferred_model_for_returns_none_when_provider_missing() -> None:
    cfg = _build_config_with_routing("implementation", ["openai_codex"])
    cfg.providers.pop("openai_codex", None)
    assert preferred_model_for("implementation", "implementation", config=cfg) is None


def test_preferred_model_for_returns_none_when_model_key_missing() -> None:
    cfg = NCDevConfig(
        mode="custom",
        routing=RoutingConfig(implementation=["openai_codex"]),
        providers={
            "openai_codex": ProviderPreferenceConfig(
                enabled=True,
                preferred_models={"implementation": "gpt-5.5"},
            ),
        },
    )
    assert preferred_model_for("implementation", "nonexistent_key", config=cfg) is None
