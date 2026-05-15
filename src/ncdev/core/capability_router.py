"""Capability-aware routing: ask for a *capability*, get a model.

Replaces 'mode preset -> provider per task key' with 'capability -> ordered
choices'. Riding the model curve becomes 'edit one config file'; no
orchestrator code touches.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ncdev.core.config import (
    CAPABILITY_KEYS,
    NCDevConfig,
    load_config,
)


class UnknownCapabilityError(ValueError):
    pass


class NoAvailableProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class Resolved:
    """Result of a capability lookup."""

    capability: str
    provider: str
    model: str
    chain_position: int


def resolve_capability(
    capability: str,
    *,
    config: NCDevConfig | None = None,
    workspace: Path | None = None,
    is_provider_available: Callable[[str], bool] | None = None,
) -> Resolved:
    """Resolve `capability` to (provider, model).

    is_provider_available(provider_name: str) -> bool lets callers plug in a
    real availability check (binary on PATH, API key set, etc.). Defaults to
    "enabled in config".

    Raises UnknownCapabilityError on unknown capability.
    Raises NoAvailableProviderError if the chain is empty or no candidate
    passes availability.
    """
    if capability not in CAPABILITY_KEYS:
        raise UnknownCapabilityError(
            f"Unknown capability '{capability}'. Known: "
            f"{', '.join(sorted(CAPABILITY_KEYS))}"
        )
    cfg = config if config is not None else load_config(workspace or Path.cwd())
    chain = cfg.capabilities.chains.get(capability, [])
    if not chain:
        raise NoAvailableProviderError(
            f"No capability chain configured for '{capability}'. "
            "Set cfg.capabilities.chains or pick a built-in mode."
        )

    def default_available(provider: str) -> bool:
        prov = cfg.providers.get(provider)
        return prov is not None and prov.enabled

    check = is_provider_available or default_available
    for i, choice in enumerate(chain):
        if check(choice.provider):
            return Resolved(
                capability=capability,
                provider=choice.provider,
                model=choice.model,
                chain_position=i,
            )
    raise NoAvailableProviderError(
        f"No available provider for capability '{capability}' - chain "
        f"({len(chain)} choices) had no availability hit."
    )
