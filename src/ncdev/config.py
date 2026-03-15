from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class AnalysisConsensusConfig(BaseModel):
    min_agreement_score: float = 0.6
    min_model_confidence: float = 0.55
    timeout_seconds: int = 120


class AnalysisModelCommand(BaseModel):
    name: str
    command: list[str]


class AnalysisConfig(BaseModel):
    models_required: list[str] = Field(default_factory=lambda: ["claude_cli", "codex_cli"])
    model_commands: list[AnalysisModelCommand] = Field(
        default_factory=lambda: [
            AnalysisModelCommand(
                name="claude_cli",
                command=["claude", "--print", "{prompt}"],
            ),
            AnalysisModelCommand(
                name="codex_cli",
                command=["codex", "exec", "--skip-git-repo-check", "--sandbox", "danger-full-access", "{prompt}"],
            ),
        ]
    )
    consensus: AnalysisConsensusConfig = Field(default_factory=AnalysisConsensusConfig)


class BrownfieldScopeConfig(BaseModel):
    include_paths: list[str] = Field(default_factory=list)
    exclude_paths: list[str] = Field(default_factory=lambda: [".git", "node_modules", "dist", "build", "venv", ".venv"])


class BrownfieldConfig(BaseModel):
    scope: BrownfieldScopeConfig = Field(default_factory=BrownfieldScopeConfig)


class SafetyConfig(BaseModel):
    max_retries: int = 2


class PortsConfig(BaseModel):
    policy: str = "sequential-start-at-23000"


class IntegrationClientConfig(BaseModel):
    enabled: bool = False
    base_url: str


class IntegrationsConfig(BaseModel):
    test_crafter: IntegrationClientConfig = Field(
        default_factory=lambda: IntegrationClientConfig(enabled=False, base_url="http://localhost:16630")
    )
    visual_designer: IntegrationClientConfig = Field(
        default_factory=lambda: IntegrationClientConfig(enabled=False, base_url="http://localhost:12101")
    )


class NCDevConfig(BaseModel):
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)
    brownfield: BrownfieldConfig = Field(default_factory=BrownfieldConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    ports: PortsConfig = Field(default_factory=PortsConfig)
    integrations: IntegrationsConfig = Field(default_factory=IntegrationsConfig)

    def to_yaml_dict(self) -> dict[str, Any]:
        model_commands = [{"name": m.name, "command": m.command} for m in self.analysis.model_commands]
        return {
            "analysis": {
                "models": {"required": self.analysis.models_required, "commands": model_commands},
                "consensus": {
                    "min_agreement_score": self.analysis.consensus.min_agreement_score,
                    "min_model_confidence": self.analysis.consensus.min_model_confidence,
                    "timeout_seconds": self.analysis.consensus.timeout_seconds,
                },
            },
            "brownfield": {
                "scope": {
                    "include_paths": self.brownfield.scope.include_paths,
                    "exclude_paths": self.brownfield.scope.exclude_paths,
                }
            },
            "safety": {"max_retries": self.safety.max_retries},
            "ports": {"policy": self.ports.policy},
            "integrations": {
                "test_crafter": {
                    "enabled": self.integrations.test_crafter.enabled,
                    "base_url": self.integrations.test_crafter.base_url,
                },
                "visual_designer": {
                    "enabled": self.integrations.visual_designer.enabled,
                    "base_url": self.integrations.visual_designer.base_url,
                },
            },
        }


def load_config(workspace: Path) -> NCDevConfig:
    config_path = workspace / ".nc-dev" / "config.yaml"
    if not config_path.exists():
        return NCDevConfig()

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    analysis = raw.get("analysis", {})
    models = analysis.get("models", {})
    commands = models.get("commands", [])

    return NCDevConfig(
        analysis=AnalysisConfig(
            models_required=models.get("required", ["claude_cli", "codex_cli"]),
            model_commands=[AnalysisModelCommand(name=x["name"], command=x["command"]) for x in commands]
            if commands
            else AnalysisConfig().model_commands,
            consensus=AnalysisConsensusConfig(
                min_agreement_score=analysis.get("consensus", {}).get("min_agreement_score", 0.6),
                min_model_confidence=analysis.get("consensus", {}).get("min_model_confidence", 0.55),
                timeout_seconds=analysis.get("consensus", {}).get("timeout_seconds", 120),
            ),
        ),
        brownfield=BrownfieldConfig(
            scope=BrownfieldScopeConfig(
                include_paths=raw.get("brownfield", {}).get("scope", {}).get("include_paths", []),
                exclude_paths=raw.get("brownfield", {}).get("scope", {}).get(
                    "exclude_paths", BrownfieldScopeConfig().exclude_paths
                ),
            )
        ),
        safety=SafetyConfig(max_retries=raw.get("safety", {}).get("max_retries", 2)),
        ports=PortsConfig(policy=raw.get("ports", {}).get("policy", "sequential-start-at-23000")),
        integrations=IntegrationsConfig(
            test_crafter=IntegrationClientConfig(
                enabled=raw.get("integrations", {}).get("test_crafter", {}).get("enabled", False),
                base_url=raw.get("integrations", {}).get("test_crafter", {}).get(
                    "base_url", "http://localhost:16630"
                ),
            ),
            visual_designer=IntegrationClientConfig(
                enabled=raw.get("integrations", {}).get("visual_designer", {}).get("enabled", False),
                base_url=raw.get("integrations", {}).get("visual_designer", {}).get(
                    "base_url", "http://localhost:12101"
                ),
            ),
        ),
    )


def ensure_default_config(workspace: Path) -> NCDevConfig:
    workspace.mkdir(parents=True, exist_ok=True)
    config = load_config(workspace)
    config_path = workspace / ".nc-dev" / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if not config_path.exists():
        yaml.safe_dump(config.to_yaml_dict(), config_path.open("w", encoding="utf-8"), sort_keys=False)
    return config
