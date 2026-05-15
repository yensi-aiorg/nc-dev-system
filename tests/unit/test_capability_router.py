from __future__ import annotations

import pytest

from ncdev.core.capability_router import (
    NoAvailableProviderError,
    UnknownCapabilityError,
    resolve_capability,
)
from ncdev.core.config import (
    CAPABILITY_KEYS,
    CapabilityChoice,
    CapabilityMatrixConfig,
    NCDevConfig,
    ProviderPreferenceConfig,
)


def _cfg_with_frontend_chain(*, codex_enabled: bool = True) -> NCDevConfig:
    return NCDevConfig(
        mode="custom",
        providers={
            "openai_codex": ProviderPreferenceConfig(enabled=codex_enabled),
            "openrouter": ProviderPreferenceConfig(enabled=True),
        },
        capabilities=CapabilityMatrixConfig(
            chains={
                "frontend_implementation": [
                    CapabilityChoice(provider="openai_codex", model="gpt-5.5"),
                    CapabilityChoice(provider="openrouter", model="openai/gpt-5.5"),
                ]
            }
        ),
    )


def test_resolve_uses_first_available_choice(monkeypatch) -> None:
    from ncdev.core import availability

    cfg = _cfg_with_frontend_chain()
    monkeypatch.setattr(availability, "cli_binary_available", lambda n: n == "codex")

    resolved = resolve_capability("frontend_implementation", config=cfg)

    assert resolved.provider == "openai_codex"
    assert resolved.model == "gpt-5.5"
    assert resolved.chain_position == 0


def test_resolve_skips_disabled_first_choice(monkeypatch) -> None:
    from ncdev.core import availability

    cfg = _cfg_with_frontend_chain(codex_enabled=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setattr(availability, "cli_binary_available", lambda _name: False)

    resolved = resolve_capability("frontend_implementation", config=cfg)

    assert resolved.provider == "openrouter"
    assert resolved.model == "openai/gpt-5.5"
    assert resolved.chain_position == 1


def test_resolve_unknown_capability_raises() -> None:
    with pytest.raises(UnknownCapabilityError, match="Unknown capability 'foo'"):
        resolve_capability("foo", config=NCDevConfig())


def test_resolve_no_chain_raises() -> None:
    cfg = NCDevConfig(mode="custom")

    with pytest.raises(NoAvailableProviderError, match="No capability chain"):
        resolve_capability("frontend_implementation", config=cfg)


def test_resolve_custom_availability_callable() -> None:
    cfg = _cfg_with_frontend_chain()

    with pytest.raises(NoAvailableProviderError, match="No available provider"):
        resolve_capability(
            "frontend_implementation",
            config=cfg,
            is_provider_available=lambda _provider: False,
        )


def test_router_uses_default_availability_skips_disabled(monkeypatch) -> None:
    """The router consults make_default_checker when no callable is passed."""
    cfg = NCDevConfig(
        mode="custom",
        providers={
            "openai_codex": ProviderPreferenceConfig(enabled=False),
            "anthropic_claude_code": ProviderPreferenceConfig(enabled=True),
        },
        capabilities=CapabilityMatrixConfig(
            chains={
                "frontend_implementation": [
                    CapabilityChoice(provider="openai_codex", model="gpt-5.5"),
                    CapabilityChoice(
                        provider="anthropic_claude_code",
                        model="opus",
                    ),
                ],
            },
        ),
    )

    # Stub binary checks so this test doesn't depend on local installs.
    from ncdev.core import availability

    monkeypatch.setenv("PATH", "")
    monkeypatch.setattr(availability, "cli_binary_available", lambda n: n == "claude")

    resolved = resolve_capability("frontend_implementation", config=cfg)
    assert resolved.provider == "anthropic_claude_code"
    assert resolved.chain_position == 1


def test_defaults_populate_from_mode_preset() -> None:
    cfg = NCDevConfig(mode="claude_plan_codex_build")

    assert set(CAPABILITY_KEYS) <= set(cfg.capabilities.chains)
    for key in CAPABILITY_KEYS:
        assert cfg.capabilities.chains[key], key


def test_user_chains_preserved_across_validation() -> None:
    cfg = NCDevConfig(
        mode="claude_plan_codex_build",
        capabilities={
            "chains": {
                "frontend_implementation": [
                    {"provider": "openrouter", "model": "custom/frontier"}
                ]
            }
        },
    )

    assert cfg.capabilities.chains["frontend_implementation"] == [
        CapabilityChoice(provider="openrouter", model="custom/frontier")
    ]
    assert cfg.capabilities.chains["backend_implementation"] == [
        CapabilityChoice(provider="openai_codex", model="gpt-5.5")
    ]
