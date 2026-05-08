from ncdev.adapters.registry import build_provider_registry
from ncdev.core.config import NCDevConfig
from ncdev.core.models import TaskType
from ncdev.core.routing import resolve_routing_plan


def test_routing_plan_uses_configured_defaults() -> None:
    config = NCDevConfig()
    registry = build_provider_registry()
    plan = resolve_routing_plan(config, registry)

    by_task = {decision.task_type: decision for decision in plan.decisions}
    # Codex builds and writes tests
    assert by_task[TaskType.BUILD_BATCH].provider == "openai_codex"
    assert by_task[TaskType.BUILD_BATCH].model == "gpt-5.4"
    # Claude plans and reviews
    assert by_task[TaskType.MARKET_RESEARCH].provider == "anthropic_claude_code"
    assert by_task[TaskType.MARKET_RESEARCH].model == "opus"
