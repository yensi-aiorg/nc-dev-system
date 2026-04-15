"""Quality Gate configuration."""

from pydantic import BaseModel


class QualityGateConfig(BaseModel):
    """Settings for the quality gate pipeline."""

    enabled: bool = False
    test_craftr_url: str = "http://localhost:16630"
    redis_url: str = "redis://localhost:16633"
    max_cycles: int = 3
    core_flow_threshold: int = 100
    resilience_threshold: int = 70
    polish_threshold: int = 80

    # AI provider settings
    ai_provider: str = "codex"  # "codex" or "claude"
    ai_fallback: str = "claude"
    ai_fix_timeout: int = 600  # seconds per fix group
