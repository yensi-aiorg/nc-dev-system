from __future__ import annotations

from ncdev.core.config import CAPABILITY_KEYS, CapabilityChoice, NCDevConfig


def test_apply_mode_preset_seeds_capabilities_without_overwriting_user_chain() -> None:
    cfg = NCDevConfig(
        mode="claude_plan_codex_build",
        capabilities={
            "chains": {
                "frontend_implementation": [
                    {"provider": "openrouter", "model": "user/model"}
                ]
            }
        },
    )

    assert set(CAPABILITY_KEYS) <= set(cfg.capabilities.chains)
    assert cfg.capabilities.chains["frontend_implementation"] == [
        CapabilityChoice(provider="openrouter", model="user/model")
    ]
    assert cfg.capabilities.chains["product_coherence_review"] == [
        CapabilityChoice(provider="anthropic_claude_code", model="opus")
    ]
