from pathlib import Path

from ncdev.v2.config import (
    NCDevV2Config,
    SentinelConfig,
    ensure_default_v2_config,
    load_v2_config,
)
from ncdev.v2.models import TaskType


def test_sentinel_config_defaults() -> None:
    config = SentinelConfig()
    assert config.intake.port == 16650
    assert config.intake.enabled is True
    assert config.intake.max_concurrent_runs == 3
    assert config.intake.queue_max_size == 50
    assert config.rate_limits.max_fixes_per_hour == 10
    assert config.rate_limits.max_fixes_per_service_per_hour == 5
    assert config.rate_limits.cooldown_after_failure_seconds == 300
    assert config.callback.enabled is True
    assert config.callback.retry_count == 3
    assert config.callback.retry_delay_seconds == 5
    assert config.git.branch_prefix == "sentinel/fix/"
    assert config.git.commit_prefix == "[sentinel-fix]"
    assert config.git.pr_label == "sentinel-auto"


def test_sentinel_service_registry_starts_empty() -> None:
    config = SentinelConfig()
    assert config.services == {}


def test_ncdev_config_includes_sentinel() -> None:
    config = NCDevV2Config()
    assert isinstance(config.sentinel, SentinelConfig)
    assert config.sentinel.intake.port == 16650
    assert config.sentinel.rate_limits.max_fixes_per_hour == 10


def test_sentinel_config_roundtrip(tmp_path: Path) -> None:
    config = ensure_default_v2_config(tmp_path)
    loaded = load_v2_config(tmp_path)
    assert loaded.sentinel.intake.port == config.sentinel.intake.port
    assert loaded.sentinel.rate_limits.max_fixes_per_hour == config.sentinel.rate_limits.max_fixes_per_hour
    assert loaded.sentinel.services == config.sentinel.services
    assert loaded.sentinel.callback.retry_count == config.sentinel.callback.retry_count
    assert loaded.sentinel.git.branch_prefix == config.sentinel.git.branch_prefix


def test_routing_sentinel_reproduce(tmp_path: Path) -> None:
    config = ensure_default_v2_config(tmp_path)
    providers = config.routing.providers_for(TaskType.SENTINEL_REPRODUCE)
    assert providers == ["anthropic_claude_code"]


def test_routing_sentinel_fix(tmp_path: Path) -> None:
    config = ensure_default_v2_config(tmp_path)
    providers = config.routing.providers_for(TaskType.SENTINEL_FIX)
    assert providers == ["openai_codex"]
