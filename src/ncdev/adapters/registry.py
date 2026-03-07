from __future__ import annotations

from ncdev.adapters.anthropic_claude_code import AnthropicClaudeCodeAdapter
from ncdev.adapters.base import ProviderAdapter
from ncdev.adapters.openai_codex import OpenAICodexAdapter
from ncdev.v2.models import CapabilitySnapshotDoc, ProviderCapabilitySnapshot


def build_provider_registry() -> dict[str, ProviderAdapter]:
    adapters: list[ProviderAdapter] = [
        AnthropicClaudeCodeAdapter(),
        OpenAICodexAdapter(),
    ]
    return {adapter.name(): adapter for adapter in adapters}


def probe_registry_capabilities(registry: dict[str, ProviderAdapter]) -> CapabilitySnapshotDoc:
    snapshots: list[ProviderCapabilitySnapshot] = []
    for adapter in registry.values():
        models = adapter.available_models()
        version = adapter.version_info().version
        for model in models:
            snapshots.append(
                ProviderCapabilitySnapshot(
                    provider=adapter.name(),
                    model=model,
                    available=adapter.healthcheck(),
                    version=version,
                    capabilities=adapter.capabilities(model),
                    notes=[],
                )
            )
    return CapabilitySnapshotDoc(generator="ncdev.v2.adapters.registry", source_inputs=[], snapshots=snapshots)
