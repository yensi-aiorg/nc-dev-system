import os
import sys

from ncdev.core.availability import (
    cli_binary_available,
    env_var_set,
    make_default_checker,
    provider_available,
)
from ncdev.core.config import NCDevConfig, ProviderPreferenceConfig


def test_cli_binary_available_finds_python() -> None:
    # Some Python binary must exist for the test runner itself.
    assert cli_binary_available(os.path.basename(sys.executable)) is True


def test_cli_binary_available_returns_false_for_garbage() -> None:
    assert cli_binary_available("definitely-not-a-real-binary-zzz999") is False


def test_env_var_set_true(monkeypatch) -> None:
    monkeypatch.setenv("TEST_VAR_XYZ", "value")
    assert env_var_set("TEST_VAR_XYZ") is True


def test_env_var_set_false(monkeypatch) -> None:
    monkeypatch.delenv("TEST_VAR_XYZ", raising=False)
    assert env_var_set("TEST_VAR_XYZ") is False


def test_provider_available_disabled_returns_false() -> None:
    cfg = NCDevConfig(
        mode="custom",
        providers={
            "openai_codex": ProviderPreferenceConfig(enabled=False),
        },
    )
    assert provider_available("openai_codex", cfg) is False


def test_provider_available_unknown_provider_returns_true() -> None:
    """Unknown providers fall through to default (no probe defined)."""
    assert provider_available("some_future_provider", None) is True


def test_provider_available_openrouter_requires_env_var(monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    cfg = NCDevConfig(
        mode="custom",
        providers={
            "openrouter": ProviderPreferenceConfig(enabled=True),
        },
    )
    assert provider_available("openrouter", cfg) is False

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    assert provider_available("openrouter", cfg) is True


def test_make_default_checker_curries_config() -> None:
    cfg = NCDevConfig(
        mode="custom",
        providers={
            "openrouter": ProviderPreferenceConfig(enabled=False),
        },
    )
    check = make_default_checker(cfg)
    # Disabled -> False regardless of env.
    assert check("openrouter") is False
