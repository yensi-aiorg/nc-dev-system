from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from ncdev.v2.models import TaskType


class ProviderPreferenceConfig(BaseModel):
    enabled: bool = True
    preferred_models: dict[str, str] = Field(default_factory=dict)
    defaults: dict[str, str] = Field(default_factory=dict)
    features: dict[str, bool] = Field(default_factory=dict)


class RoutingConfig(BaseModel):
    source_ingest: list[str] = Field(default_factory=lambda: ["anthropic_claude_code"])
    repo_analysis: list[str] = Field(default_factory=lambda: ["anthropic_claude_code"])
    market_research: list[str] = Field(default_factory=lambda: ["anthropic_claude_code"])
    feature_extraction: list[str] = Field(default_factory=lambda: ["anthropic_claude_code"])
    design_brief: list[str] = Field(default_factory=lambda: ["anthropic_claude_code"])
    implementation: list[str] = Field(default_factory=lambda: ["openai_codex"])
    test_authoring: list[str] = Field(default_factory=lambda: ["openai_codex"])
    review: list[str] = Field(default_factory=lambda: ["anthropic_claude_code"])
    second_opinion: list[str] = Field(default_factory=lambda: ["anthropic_claude_code", "openai_codex"])
    sentinel_reproduce: list[str] = Field(default_factory=lambda: ["anthropic_claude_code"])
    sentinel_fix: list[str] = Field(default_factory=lambda: ["openai_codex"])

    def providers_for(self, task_type: TaskType) -> list[str]:
        mapping = {
            TaskType.SOURCE_INGEST: self.source_ingest,
            TaskType.REPO_ANALYSIS: self.repo_analysis,
            TaskType.MARKET_RESEARCH: self.market_research,
            TaskType.FEATURE_EXTRACTION: self.feature_extraction,
            TaskType.DESIGN_BRIEF: self.design_brief,
            TaskType.BUILD_BATCH: self.implementation,
            TaskType.TEST_AUTHORING: self.test_authoring,
            TaskType.SENTINEL_REPRODUCE: self.sentinel_reproduce,
            TaskType.SENTINEL_FIX: self.sentinel_fix,
        }
        return mapping.get(task_type, self.review)


class SentinelServiceConfig(BaseModel):
    repo_path: str = ""
    git_remote: str = ""
    default_branch: str = "main"
    language: str = "python"
    test_commands: dict[str, str] = Field(default_factory=dict)
    pr_labels: list[str] = Field(default_factory=lambda: ["sentinel-auto", "bug"])
    auto_deploy: bool = False


class SentinelIntakeConfig(BaseModel):
    enabled: bool = True
    port: int = 16650
    api_key: str = ""
    max_concurrent_runs: int = 3
    queue_max_size: int = 50


class SentinelRateLimitConfig(BaseModel):
    max_fixes_per_hour: int = 10
    max_fixes_per_service_per_hour: int = 5
    cooldown_after_failure_seconds: int = 300


class SentinelCallbackConfig(BaseModel):
    enabled: bool = True
    url: str = ""
    api_key: str = ""
    retry_count: int = 3
    retry_delay_seconds: int = 5


class SentinelGitConfig(BaseModel):
    branch_prefix: str = "sentinel/fix/"
    commit_prefix: str = "[sentinel-fix]"
    pr_label: str = "sentinel-auto"


class SentinelConfig(BaseModel):
    intake: SentinelIntakeConfig = Field(default_factory=SentinelIntakeConfig)
    rate_limits: SentinelRateLimitConfig = Field(default_factory=SentinelRateLimitConfig)
    services: dict[str, SentinelServiceConfig] = Field(default_factory=dict)
    callback: SentinelCallbackConfig = Field(default_factory=SentinelCallbackConfig)
    git: SentinelGitConfig = Field(default_factory=SentinelGitConfig)


class QualityGateConfig(BaseModel):
    require_local_harness: bool = True
    require_artifacts: bool = True
    require_human_release: bool = True


class NCDevV2Config(BaseModel):
    providers: dict[str, ProviderPreferenceConfig] = Field(
        default_factory=lambda: {
            "anthropic_claude_code": ProviderPreferenceConfig(
                enabled=True,
                preferred_models={"planning": "opus", "review": "sonnet"},
                features={"use_subagents": True, "use_hooks": True, "use_mcp": True},
            ),
            "openai_codex": ProviderPreferenceConfig(
                enabled=True,
                preferred_models={"implementation": "gpt-5.2-codex", "test_implementation": "gpt-5.2-codex"},
                defaults={"reasoning_effort": "high"},
            ),
            "gemini_cli": ProviderPreferenceConfig(enabled=False),
        }
    )
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    quality_gates: QualityGateConfig = Field(default_factory=QualityGateConfig)
    sentinel: SentinelConfig = Field(default_factory=SentinelConfig)

    def to_yaml_dict(self) -> dict[str, object]:
        return self.model_dump(mode="python")


def load_v2_config(workspace: Path) -> NCDevV2Config:
    config_path = workspace / ".nc-dev" / "v2" / "config.yaml"
    if not config_path.exists():
        return NCDevV2Config()
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return NCDevV2Config.model_validate(raw)


def ensure_default_v2_config(workspace: Path) -> NCDevV2Config:
    workspace.mkdir(parents=True, exist_ok=True)
    config = load_v2_config(workspace)
    config_path = workspace / ".nc-dev" / "v2" / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if not config_path.exists():
        yaml.safe_dump(config.to_yaml_dict(), config_path.open("w", encoding="utf-8"), sort_keys=False)
    return config
