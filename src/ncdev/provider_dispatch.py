"""Config-driven AI provider dispatch.

Bridges :mod:`ncdev.core.config` routing (keys like ``design_brief``,
``implementation``) to :mod:`ncdev.ai_provider` (short names like ``claude``,
``codex``, ``openrouter``). Callers ask for a provider by task key — the
preset/routing in ``.nc-dev/config.yaml`` decides which CLI or API backs it.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from ncdev.ai_provider import AIProvider, get_provider
from ncdev.core.config import NCDevConfig, load_config

logger = logging.getLogger(__name__)

# Long routing names → short registry keys used in ai_provider.py
PROVIDER_ALIASES: dict[str, str] = {
    "anthropic_claude_code": "claude",
    "openai_codex": "codex",
    "openrouter": "openrouter",
    # Pass-through short names
    "claude": "claude",
    "codex": "codex",
}

_config_cache: dict[str, NCDevConfig] = {}


def _workspace_root(workspace: Path | None) -> Path:
    if workspace is not None:
        return Path(workspace)
    env = os.environ.get("NCDEV_WORKSPACE")
    if env:
        return Path(env)
    return Path.cwd()


def _load_cached_config(workspace: Path | None = None) -> NCDevConfig:
    """Load (and cache) the core config for the given workspace."""
    root = _workspace_root(workspace)
    key = str(root.resolve())
    cached = _config_cache.get(key)
    if cached is not None:
        return cached
    cfg = load_config(root)
    _config_cache[key] = cfg
    return cfg


def reset_cache() -> None:
    """Clear cached configs (useful between tests)."""
    _config_cache.clear()


def resolve_provider_name(routing_name: str) -> str:
    """Translate a core routing provider name (or short alias) to registry key."""
    short = PROVIDER_ALIASES.get(routing_name)
    if short is None:
        raise ValueError(
            f"Unknown provider routing name '{routing_name}'. "
            f"Known: {', '.join(sorted(PROVIDER_ALIASES))}"
        )
    return short


def provider_name_for(
    task_key: str,
    *,
    workspace: Path | None = None,
    config: NCDevConfig | None = None,
) -> str:
    """Return the registry short name of the provider for ``task_key``."""
    cfg = config if config is not None else _load_cached_config(workspace)
    routing = getattr(cfg.routing, task_key, None)
    if not routing:
        raise ValueError(
            f"No providers configured for routing task '{task_key}'"
        )
    return resolve_provider_name(routing[0])


def get_provider_for(
    task_key: str,
    *,
    workspace: Path | None = None,
    config: NCDevConfig | None = None,
) -> AIProvider:
    """Return the :class:`AIProvider` assigned to ``task_key`` by routing."""
    short = provider_name_for(task_key, workspace=workspace, config=config)
    return get_provider(short)


def preferred_model_for(
    task_key: str,
    model_key: str,
    *,
    workspace: Path | None = None,
    config: NCDevConfig | None = None,
) -> Optional[str]:
    """Look up the preferred model name for a task on its assigned provider.

    Example: ``preferred_model_for("design_brief", "planning")``.
    Returns ``None`` if no preference is configured.
    """
    cfg = config if config is not None else _load_cached_config(workspace)
    routing = getattr(cfg.routing, task_key, None)
    if not routing:
        return None
    long_name = routing[0]
    prov_cfg = cfg.providers.get(long_name)
    if prov_cfg is None:
        return None
    return prov_cfg.preferred_models.get(model_key)
