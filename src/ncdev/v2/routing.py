from __future__ import annotations

from ncdev.adapters.base import ProviderAdapter
from ncdev.v2.config import NCDevV2Config
from ncdev.v2.models import RoutingDecision, RoutingPlanDoc, TaskType


TASK_MODEL_PREFS: dict[TaskType, str] = {
    TaskType.SOURCE_INGEST: "planning",
    TaskType.REPO_ANALYSIS: "planning",
    TaskType.MARKET_RESEARCH: "planning",
    TaskType.FEATURE_EXTRACTION: "planning",
    TaskType.UX_ANALYSIS: "planning",
    TaskType.DESIGN_BRIEF: "planning",
    TaskType.DESIGN_REFERENCE_GENERATION: "planning",
    TaskType.BUILD_BATCH: "implementation",
    TaskType.TEST_PLAN_GENERATION: "planning",
    TaskType.TEST_AUTHORING: "test_implementation",
    TaskType.QA_SWEEP: "review",
    TaskType.ISSUE_TRIAGE: "review",
    TaskType.FIX_BATCH: "implementation",
    TaskType.DELIVERY_PACK: "review",
}


def _choose_model(config: NCDevV2Config, provider_name: str, adapter: ProviderAdapter, task_type: TaskType) -> str:
    pref_key = TASK_MODEL_PREFS.get(task_type, "review")
    provider_cfg = config.providers.get(provider_name)
    models = adapter.available_models()
    if provider_cfg is not None:
        preferred = provider_cfg.preferred_models.get(pref_key)
        if preferred:
            return preferred
    return models[0] if models else "unknown"


def resolve_routing_plan(config: NCDevV2Config, registry: dict[str, ProviderAdapter]) -> RoutingPlanDoc:
    task_types = [
        TaskType.SOURCE_INGEST,
        TaskType.REPO_ANALYSIS,
        TaskType.MARKET_RESEARCH,
        TaskType.FEATURE_EXTRACTION,
        TaskType.DESIGN_BRIEF,
        TaskType.BUILD_BATCH,
        TaskType.TEST_AUTHORING,
        TaskType.QA_SWEEP,
        TaskType.DELIVERY_PACK,
    ]
    decisions: list[RoutingDecision] = []

    for task_type in task_types:
        configured = config.routing.providers_for(task_type)
        available = [
            provider_name
            for provider_name in configured
            if provider_name in registry and config.providers.get(provider_name, None) and config.providers[provider_name].enabled
        ]
        if not available:
            decisions.append(
                RoutingDecision(
                    task_type=task_type,
                    provider="unassigned",
                    model="unassigned",
                    rationale=f"No enabled provider configured for {task_type.value}.",
                    fallback_providers=[],
                )
            )
            continue

        primary = available[0]
        adapter = registry[primary]
        model = _choose_model(config, primary, adapter, task_type)
        decisions.append(
            RoutingDecision(
                task_type=task_type,
                provider=primary,
                model=model,
                rationale=f"Selected from routing config for {task_type.value}.",
                fallback_providers=available[1:],
            )
        )

    return RoutingPlanDoc(
        generator="ncdev.v2.routing",
        source_inputs=[],
        decisions=decisions,
    )
