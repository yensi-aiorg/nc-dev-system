"""Adapter: capability_router.Resolved -> SessionOptions.

Keeps the Resolved dataclass minimal. Session entry points consume one
SessionOptions struct instead of each growing new keyword arguments.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ncdev.core.capability_policy import resolve_codex_options, resolve_model
from ncdev.core.capability_router import Resolved
from ncdev.core.models import CapabilitySnapshotDoc, ProviderCapabilitySnapshot


@dataclass(frozen=True)
class SessionOptions:
    """Everything a session runner needs to start a provider session."""

    provider: str
    model: str
    extra_args: list[str] = field(default_factory=list)
    append_system_prompt_additions: str = ""


def _snapshot_for(
    doc: CapabilitySnapshotDoc, provider: str
) -> ProviderCapabilitySnapshot:
    for snap in doc.snapshots:
        if snap.provider == provider:
            return snap
    # Provider absent from the snapshot: synthesise an unavailable stub so
    # resolution still yields the provider default rather than crashing.
    return ProviderCapabilitySnapshot(provider=provider, model="auto", available=False)


def build_session_options(
    resolved: Resolved,
    snapshot: CapabilitySnapshotDoc,
    *,
    provider_defaults: dict[str, str] | None = None,
    append_system_prompt_additions: str = "",
) -> SessionOptions:
    """Turn a capability resolution into concrete session options."""
    provider_snap = _snapshot_for(snapshot, resolved.provider)
    model = resolve_model(resolved.provider, resolved.model, provider_snap)
    extra_args: list[str] = []
    if resolved.provider == "openai_codex":
        extra_args = resolve_codex_options(provider_defaults)
    return SessionOptions(
        provider=resolved.provider,
        model=model,
        extra_args=extra_args,
        append_system_prompt_additions=append_system_prompt_additions,
    )
