"""Resolve a model *request* into a concrete model string.

The CLIs expose no machine-readable model inventory, so resolution is
alias-based, with a version-keyed table as a pinning fallback. Order:
explicit pin > known alias > version table > provider default.
"""

from __future__ import annotations

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


def resolve_model(
    provider: str,
    requested: str | None,
    snapshot: ProviderCapabilitySnapshot,
) -> str:
    """Resolve `requested` to a concrete model string for `provider`.

    - None / "auto" / "latest" / ""  -> the provider default alias
    - a known alias (opus/sonnet/...) -> passed through
    - anything else                   -> treated as an explicit pin, passed through
    """
    default = _PROVIDER_DEFAULT.get(provider, CLAUDE_MODEL_ALIASES[0])
    if requested is None or requested.strip().lower() in _AUTO_SENTINELS:
        return default
    # Explicit alias or explicit pin: the CLI accepts it verbatim.
    return requested.strip()
