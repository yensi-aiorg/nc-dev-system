from ncdev.adapters.registry import build_provider_registry
from ncdev.v2.config import NCDevV2Config
from ncdev.v2.models import TaskType
from ncdev.v2.routing import resolve_routing_plan


def test_routing_plan_uses_configured_defaults() -> None:
    config = NCDevV2Config()
    registry = build_provider_registry()
    plan = resolve_routing_plan(config, registry)

    by_task = {decision.task_type: decision for decision in plan.decisions}
    assert by_task[TaskType.BUILD_BATCH].provider == "openai_codex"
    assert by_task[TaskType.BUILD_BATCH].model == "gpt-5.2-codex"
    assert by_task[TaskType.MARKET_RESEARCH].provider == "anthropic_claude_code"
    assert by_task[TaskType.MARKET_RESEARCH].model == "opus"
