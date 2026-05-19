"""Resolve a model *request* into a concrete model string.

The CLIs expose no machine-readable model inventory, so resolution is
alias-based, with a version-keyed table as a pinning fallback. Order:
explicit pin > known alias > version table > provider default.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from ncdev.core.capability_probe import (
    CLAUDE_MODEL_ALIASES,
    CODEX_DEFAULT_MODEL,
)
from ncdev.core.models import ProviderCapabilitySnapshot

# Sentinels that mean "resolve me" rather than "use this exact model".
_AUTO_SENTINELS: frozenset[str] = frozenset({"auto", "latest", ""})

_PROVIDER_DEFAULT: dict[str, str] = {
    "anthropic_claude_code": CLAUDE_MODEL_ALIASES[0],  # "opus"
    "openai_codex": CODEX_DEFAULT_MODEL,
}

# Pinning fallback: map a CLI version floor to a concrete model. Consulted
# only when an alias cannot satisfy a request. Seeded conservatively;
# extend as new generations ship. Phase 2 will keep this fresh from the
# ledger.
VERSION_MODEL_TABLE: dict[str, dict[str, str]] = {
    "anthropic_claude_code": {},
    "openai_codex": {},
}


# --- Metrics gate (Phase 2) -------------------------------------------------
# Per-provider alias chain, best-first. Demotion steps one rung down.
_ALIAS_CHAIN: dict[str, tuple[str, ...]] = {
    "anthropic_claude_code": CLAUDE_MODEL_ALIASES,  # ("opus", "sonnet", "haiku")
    "openai_codex": (CODEX_DEFAULT_MODEL,),         # single model — no demotion target
}

_MODEL_REJECTION_MARKERS: tuple[str, ...] = (
    "model not found",
    "does not exist",
    "do not have access",
    "invalid model",
    "unknown model",
    "not authorized",
)


def is_model_rejection_error(*text_parts: str | None) -> bool:
    """True if any text part looks like the CLI rejecting the model.

    Heuristic — the CLIs expose no machine-readable error code.
    """
    blob = " ".join(p for p in text_parts if p).lower()
    return any(marker in blob for marker in _MODEL_REJECTION_MARKERS)


def next_alias_down(provider: str, model: str) -> str | None:
    """The next alias one rung down `provider`'s chain, or None.

    Returns None when `model` is not a chain alias (e.g. an explicit
    pin) or is already the last rung.
    """
    chain = _ALIAS_CHAIN.get(provider, ())
    if model not in chain:
        return None
    idx = chain.index(model)
    return chain[idx + 1] if idx + 1 < len(chain) else None


@lru_cache(maxsize=1)
def _default_gate_config():
    """Load gate thresholds from .nc-dev/config.yaml, or defaults on any error."""
    from ncdev.core.config import CapabilityGateConfig, load_config

    try:
        return load_config(Path.cwd()).capability_gate
    except Exception:  # noqa: BLE001
        return CapabilityGateConfig()


def _gated_model(provider: str, model: str, ledger_entries: list, gate_config=None) -> str:
    """Demote `model` one alias rung if its recent track record is bad."""
    if gate_config is None:
        gate_config = _default_gate_config()
    chain = _ALIAS_CHAIN.get(provider, ())
    if model not in chain:
        return model
    idx = chain.index(model)
    if idx + 1 >= len(chain):
        return model  # already at the last rung — nowhere to demote
    recent = [
        e for e in ledger_entries
        if e.provider == provider and e.model == model
    ][-gate_config.window:]
    if len(recent) < gate_config.min_samples:
        return model
    mean_failure = sum(1.0 - e.first_pass_success_rate for e in recent) / len(recent)
    if mean_failure > gate_config.fail_threshold:
        return chain[idx + 1]
    return model


def resolve_model(
    provider: str,
    requested: str | None,
    snapshot: ProviderCapabilitySnapshot,
    *,
    ledger_entries: list | None = None,
    gate_config=None,
) -> str:
    """Resolve `requested` to a concrete model string for `provider`.

    - None / "auto" / "latest" / ""  -> the provider default alias
    - a known alias (opus/sonnet/...) -> passed through
    - anything else                   -> treated as an explicit pin, passed through

    When `ledger_entries` is supplied, a resolved *alias* (not an explicit
    pin) is run through the metrics gate: a model with a bad recent track
    record is demoted one rung down its alias chain.
    """
    default = _PROVIDER_DEFAULT.get(provider, CLAUDE_MODEL_ALIASES[0])
    if requested is None or requested.strip().lower() in _AUTO_SENTINELS:
        resolved = default
    else:
        resolved = requested.strip()
    if ledger_entries:
        resolved = _gated_model(provider, resolved, ledger_entries, gate_config)
    return resolved


def resolve_codex_options(defaults: dict[str, str] | None) -> list[str]:
    """Translate a provider's `defaults` dict into Codex CLI argv fragments.

    Only keys that map to a real Codex CLI option are emitted; unknown
    keys (e.g. base_url) are ignored. `reasoning_effort` maps to the
    Codex config key `model_reasoning_effort` via `-c key="value"`.
    """
    if not defaults:
        return []
    args: list[str] = []
    effort = defaults.get("reasoning_effort")
    if effort:
        args += ["-c", f'model_reasoning_effort="{effort}"']
    return args
