"""Real provider availability probes.

The capability router's default availability check used to trust the
``enabled`` flag in config. That's fine for "is this provider supposed
to be in play" but not for "is the provider actually reachable right
now." This module supplies cheap, actionable probes:

  - CLI providers: shutil.which(<binary>)
  - API providers: required env var(s) set
  - Optional health check: a quick HTTP GET (currently off by default -
    not all callers want to pay the latency)

Composed via :func:`make_default_checker` which the capability router
uses unless the caller passes their own callable.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Callable

from ncdev.core.config import NCDevConfig

# Provider -> (kind, probe argument)
# kind in {"cli_binary", "env_var"}.
PROVIDER_PROBES: dict[str, tuple[str, str | list[str]]] = {
    "anthropic_claude_code": ("cli_binary", "claude"),
    "openai_codex": ("cli_binary", "codex"),
    "openrouter": ("env_var", "OPENROUTER_API_KEY"),
    "gemini_cli": ("cli_binary", "gemini"),
}


def cli_binary_available(name: str) -> bool:
    return shutil.which(name) is not None


def env_var_set(name: str) -> bool:
    return bool(os.environ.get(name))


def provider_available(name: str, config: NCDevConfig | None = None) -> bool:
    """Probe whether ``provider`` (long name) is actually usable now."""
    # First respect the enabled flag: disabled means "don't use" even if the
    # binary is on PATH. Then run the kind-specific probe.
    if config is not None:
        prov_cfg = config.providers.get(name)
        if prov_cfg is not None and not prov_cfg.enabled:
            return False

    probe = PROVIDER_PROBES.get(name)
    if probe is None:
        # Unknown provider: fall back to enabled flag if any, else True.
        return True
    kind, arg = probe
    if kind == "cli_binary":
        return cli_binary_available(arg if isinstance(arg, str) else arg[0])
    if kind == "env_var":
        return env_var_set(arg if isinstance(arg, str) else arg[0])
    return True


def make_default_checker(config: NCDevConfig | None) -> Callable[[str], bool]:
    """Bind config to a capability-router-compatible availability checker."""

    def _check(provider_name: str) -> bool:
        return provider_available(provider_name, config)

    return _check
