from ncdev.adapters.registry import build_provider_registry, probe_registry_capabilities


def test_registry_contains_default_adapters() -> None:
    registry = build_provider_registry()
    assert "anthropic_claude_code" in registry
    assert "openai_codex" in registry


def test_capability_probe_emits_snapshots() -> None:
    registry = build_provider_registry()
    doc = probe_registry_capabilities(registry)
    assert len(doc.snapshots) >= 2
    providers = {snapshot.provider for snapshot in doc.snapshots}
    assert "anthropic_claude_code" in providers
    assert "openai_codex" in providers

