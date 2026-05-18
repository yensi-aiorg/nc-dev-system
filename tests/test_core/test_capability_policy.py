from ncdev.core.capability_policy import resolve_model
from ncdev.core.capability_probe import probe_claude, probe_codex


def _claude_snap(monkeypatch, available=True):
    monkeypatch.setattr(
        "ncdev.core.capability_probe.shutil.which",
        lambda b: "/usr/bin/claude" if available else None,
    )
    monkeypatch.setattr(
        "ncdev.core.capability_probe._run_version", lambda _b: "1.2.3 (Claude Code)"
    )
    return probe_claude()


def test_auto_resolves_to_provider_default(monkeypatch):
    snap = _claude_snap(monkeypatch)
    assert resolve_model("anthropic_claude_code", "auto", snap) == "opus"


def test_none_resolves_to_provider_default(monkeypatch):
    snap = _claude_snap(monkeypatch)
    assert resolve_model("anthropic_claude_code", None, snap) == "opus"


def test_known_alias_passes_through(monkeypatch):
    snap = _claude_snap(monkeypatch)
    assert resolve_model("anthropic_claude_code", "sonnet", snap) == "sonnet"


def test_explicit_pin_always_wins(monkeypatch):
    snap = _claude_snap(monkeypatch)
    assert (
        resolve_model("anthropic_claude_code", "claude-opus-4-7", snap)
        == "claude-opus-4-7"
    )


def test_codex_auto_resolves_to_codex_default(monkeypatch):
    monkeypatch.setattr("ncdev.core.capability_probe.shutil.which", lambda _: "/usr/bin/codex")
    monkeypatch.setattr(
        "ncdev.core.capability_probe._run_version", lambda _b: "OpenAI Codex v0.130.0"
    )
    snap = probe_codex()
    assert resolve_model("openai_codex", "auto", snap) == "gpt-5.5"


def test_unavailable_provider_still_resolves_to_default(monkeypatch):
    snap = _claude_snap(monkeypatch, available=False)
    assert resolve_model("anthropic_claude_code", "auto", snap) == "opus"


from ncdev.core.capability_policy import resolve_codex_options


def test_reasoning_effort_translates_to_codex_config_flag():
    args = resolve_codex_options({"reasoning_effort": "high"})
    assert args == ["-c", 'model_reasoning_effort="high"']


def test_empty_defaults_yield_no_args():
    assert resolve_codex_options({}) == []
    assert resolve_codex_options(None) == []


def test_unknown_defaults_keys_are_ignored():
    args = resolve_codex_options({"base_url": "http://x", "reasoning_effort": "low"})
    assert args == ["-c", 'model_reasoning_effort="low"']
