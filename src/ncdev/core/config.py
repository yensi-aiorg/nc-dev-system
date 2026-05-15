from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, Field, model_validator

from ncdev.core.models import TaskType


# ---------------------------------------------------------------------------
# Routing task keys — single source of truth for RoutingConfig fields.
# ---------------------------------------------------------------------------

ROUTING_TASK_KEYS: tuple[str, ...] = (
    "source_ingest",
    "repo_analysis",
    "market_research",
    "feature_extraction",
    "design_brief",
    "implementation",
    "test_authoring",
    "review",
    "second_opinion",
    "sentinel_reproduce",
    "sentinel_fix",
)


CAPABILITY_KEYS: tuple[str, ...] = (
    "frontend_implementation",
    "backend_implementation",
    "test_authoring",
    "product_coherence_review",
    "visual_ux_judgment",
    "cheap_boilerplate",
    "code_review",
    "debugging",
)


def _uniform_preset(provider: str) -> dict[str, list[str]]:
    return {key: [provider] for key in ROUTING_TASK_KEYS}


# Named presets. Flipping `NCDevConfig.mode` picks one. "custom" leaves
# RoutingConfig untouched so users can hand-tune it.
MODE_PRESETS: dict[str, dict[str, list[str]]] = {
    "codex_only": _uniform_preset("openai_codex"),
    "claude_only": _uniform_preset("anthropic_claude_code"),
    "openrouter": _uniform_preset("openrouter"),
    "claude_plan_codex_build": {
        "source_ingest": ["anthropic_claude_code"],
        "repo_analysis": ["anthropic_claude_code"],
        "market_research": ["anthropic_claude_code"],
        "feature_extraction": ["anthropic_claude_code"],
        "design_brief": ["anthropic_claude_code"],
        "implementation": ["openai_codex"],
        "test_authoring": ["openai_codex"],
        "review": ["anthropic_claude_code"],
        "second_opinion": ["anthropic_claude_code"],
        "sentinel_reproduce": ["anthropic_claude_code"],
        "sentinel_fix": ["openai_codex"],
    },
    "custom": {},
}

DEFAULT_MODE = "claude_plan_codex_build"


class ProviderPreferenceConfig(BaseModel):
    enabled: bool = True
    preferred_models: dict[str, str] = Field(default_factory=dict)
    defaults: dict[str, str] = Field(default_factory=dict)
    features: dict[str, bool] = Field(default_factory=dict)


class CapabilityChoice(BaseModel):
    """A single (provider, model) candidate for a capability."""

    provider: str
    model: str


class CapabilityMatrixConfig(BaseModel):
    """Ordered fallback chains per capability key.

    Empty dict = no capability routing configured; callers fall back to the
    legacy mode/routing config. When populated, callers requesting a capability
    get the first available provider in the chain. "Available" means:
      - the provider is enabled in cfg.providers
      - (optional) the provider's binary/API is reachable
    """

    chains: dict[str, list[CapabilityChoice]] = Field(default_factory=dict)


DEFAULT_CAPABILITY_CHAINS: dict[str, dict[str, list[CapabilityChoice]]] = {
    "claude_plan_codex_build": {
        "frontend_implementation": [
            CapabilityChoice(provider="openai_codex", model="gpt-5.5")
        ],
        "backend_implementation": [
            CapabilityChoice(provider="openai_codex", model="gpt-5.5")
        ],
        "test_authoring": [
            CapabilityChoice(provider="openai_codex", model="gpt-5.5")
        ],
        "product_coherence_review": [
            CapabilityChoice(provider="anthropic_claude_code", model="opus")
        ],
        "visual_ux_judgment": [
            CapabilityChoice(provider="anthropic_claude_code", model="opus")
        ],
        "cheap_boilerplate": [
            CapabilityChoice(provider="openai_codex", model="gpt-5.5")
        ],
        "code_review": [
            CapabilityChoice(provider="anthropic_claude_code", model="opus")
        ],
        "debugging": [
            CapabilityChoice(provider="anthropic_claude_code", model="opus")
        ],
    },
    "claude_only": {
        k: [CapabilityChoice(provider="anthropic_claude_code", model="opus")]
        for k in CAPABILITY_KEYS
    },
    "codex_only": {
        k: [CapabilityChoice(provider="openai_codex", model="gpt-5.5")]
        for k in CAPABILITY_KEYS
    },
    "openrouter": {
        k: [
            CapabilityChoice(
                provider="openrouter",
                model="anthropic/claude-opus-4-6",
            )
        ]
        for k in CAPABILITY_KEYS
    },
}


class RoutingConfig(BaseModel):
    source_ingest: list[str] = Field(default_factory=lambda: ["anthropic_claude_code"])
    repo_analysis: list[str] = Field(default_factory=lambda: ["anthropic_claude_code"])
    market_research: list[str] = Field(default_factory=lambda: ["anthropic_claude_code"])
    feature_extraction: list[str] = Field(default_factory=lambda: ["anthropic_claude_code"])
    design_brief: list[str] = Field(default_factory=lambda: ["anthropic_claude_code"])
    implementation: list[str] = Field(default_factory=lambda: ["openai_codex"])
    test_authoring: list[str] = Field(default_factory=lambda: ["openai_codex"])
    review: list[str] = Field(default_factory=lambda: ["anthropic_claude_code"])
    second_opinion: list[str] = Field(default_factory=lambda: ["anthropic_claude_code"])
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


class NCDevConfig(BaseModel):
    mode: str = Field(
        default=DEFAULT_MODE,
        description=(
            "Named routing preset. One of: "
            + ", ".join(sorted(MODE_PRESETS.keys()))
            + ". Flipping this is the main budget switch — "
            "claude_plan_codex_build (default) uses Claude for planning + "
            "review and delegates implementation to Codex via Bash; "
            "codex_only skips Claude entirely for token-lean days; "
            "claude_only keeps everything on Claude; openrouter routes all "
            "tasks through the OpenRouter API. Use 'custom' to hand-tune."
        ),
    )
    providers: dict[str, ProviderPreferenceConfig] = Field(
        default_factory=lambda: {
            "anthropic_claude_code": ProviderPreferenceConfig(
                enabled=True,
                preferred_models={"planning": "opus", "review": "opus"},
                features={"use_subagents": True, "use_hooks": True, "use_mcp": True},
            ),
            "openai_codex": ProviderPreferenceConfig(
                enabled=True,
                preferred_models={
                    "planning": "gpt-5.5",
                    "review": "gpt-5.5",
                    "implementation": "gpt-5.5",
                    "test_implementation": "gpt-5.5",
                },
                defaults={"reasoning_effort": "high"},
            ),
            "openrouter": ProviderPreferenceConfig(
                enabled=False,
                preferred_models={"planning": "anthropic/claude-opus-4-6"},
                defaults={"base_url": "https://openrouter.ai/api/v1"},
            ),
            "gemini_cli": ProviderPreferenceConfig(enabled=False),
        }
    )
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    capabilities: CapabilityMatrixConfig = Field(default_factory=CapabilityMatrixConfig)
    quality_gates: QualityGateConfig = Field(default_factory=QualityGateConfig)
    sentinel: SentinelConfig = Field(default_factory=SentinelConfig)

    @model_validator(mode="after")
    def _apply_mode_preset(self) -> "NCDevConfig":
        preset = MODE_PRESETS.get(self.mode)
        if preset is None:
            raise ValueError(
                f"Unknown mode '{self.mode}'. Known modes: "
                + ", ".join(sorted(MODE_PRESETS.keys()))
            )
        if preset:
            for field, providers in preset.items():
                setattr(self.routing, field, list(providers))

        capability_preset = DEFAULT_CAPABILITY_CHAINS.get(self.mode, {})
        for capability, choices in capability_preset.items():
            if not self.capabilities.chains.get(capability):
                self.capabilities.chains[capability] = [
                    choice.model_copy(deep=True) for choice in choices
                ]
        return self

    def to_yaml_dict(self) -> dict[str, object]:
        return self.model_dump(mode="python")


def load_config(workspace: Path) -> NCDevConfig:
    config_path = workspace / ".nc-dev" / "config.yaml"
    if not config_path.exists():
        return NCDevConfig()
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return NCDevConfig.model_validate(raw)


def ensure_default_config(workspace: Path) -> NCDevConfig:
    workspace.mkdir(parents=True, exist_ok=True)
    config = load_config(workspace)
    config_path = workspace / ".nc-dev" / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if not config_path.exists():
        yaml.safe_dump(config.to_yaml_dict(), config_path.open("w", encoding="utf-8"), sort_keys=False)
    return config
