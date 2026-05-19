from __future__ import annotations

from ncdev.core.config import CAPABILITY_KEYS, CapabilityChoice, NCDevConfig


def test_sentinel_service_config_has_deploy_fields() -> None:
    from ncdev.core.config import SentinelServiceConfig

    svc = SentinelServiceConfig()

    assert svc.staging_branch == "staging"
    assert svc.deploy_command == ""
    assert svc.staging_url == ""
    assert svc.protected_files == []
    assert svc.repo_clone_url == ""


def test_resolve_service_returns_registered() -> None:
    from ncdev.core.config import NCDevConfig, SentinelServiceConfig, resolve_service

    cfg = NCDevConfig()
    cfg.sentinel.services["citebot"] = SentinelServiceConfig(
        repo_path="/srv/citebot",
        staging_url="http://staging",
    )

    svc = resolve_service("citebot", cfg)

    assert svc.repo_path == "/srv/citebot"


def test_resolve_service_unknown_raises() -> None:
    import pytest

    from ncdev.core.config import NCDevConfig, UnknownServiceError, resolve_service

    cfg = NCDevConfig()

    with pytest.raises(UnknownServiceError, match="not registered"):
        resolve_service("ghost-service", cfg)


def test_validate_service_for_deploy_lists_missing() -> None:
    from ncdev.core.config import SentinelServiceConfig, validate_service_for_deploy

    svc = SentinelServiceConfig()

    violations = validate_service_for_deploy(svc)

    assert any("repo_clone_url" in v for v in violations)
    assert any("deploy_command" in v for v in violations)
    assert any("staging_url" in v for v in violations)
    assert any("test_commands" in v for v in violations)


def test_validate_service_for_deploy_clean_when_complete() -> None:
    from ncdev.core.config import SentinelServiceConfig, validate_service_for_deploy

    svc = SentinelServiceConfig(
        repo_clone_url="git@github.com:org/repo.git",
        deploy_command="docker compose up -d",
        staging_url="http://staging.example.com",
        test_commands={"backend": "pytest"},
    )

    assert validate_service_for_deploy(svc) == []


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
        CapabilityChoice(provider="anthropic_claude_code", model="auto")
    ]
