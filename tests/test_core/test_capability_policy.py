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


# Append to tests/test_core/test_capability_policy.py
from ncdev.core.capability_ledger import LedgerEntry
from ncdev.core.capability_policy import resolve_model as _rm


def _led(model, fpsr, n=1):
    return [
        LedgerEntry(
            timestamp="t", project_name="p", run_id=f"r{i}", cycle=1,
            provider="anthropic_claude_code", model=model,
            first_pass_success_rate=fpsr,
        )
        for i in range(n)
    ]


def test_gate_demotes_model_with_bad_track_record(monkeypatch):
    snap = _claude_snap(monkeypatch)
    ledger = _led("opus", 0.2, n=4)
    assert _rm("anthropic_claude_code", "auto", snap, ledger_entries=ledger) == "sonnet"


def test_gate_keeps_model_with_good_track_record(monkeypatch):
    snap = _claude_snap(monkeypatch)
    ledger = _led("opus", 0.9, n=4)
    assert _rm("anthropic_claude_code", "auto", snap, ledger_entries=ledger) == "opus"


def test_gate_needs_minimum_samples(monkeypatch):
    snap = _claude_snap(monkeypatch)
    ledger = _led("opus", 0.0, n=2)
    assert _rm("anthropic_claude_code", "auto", snap, ledger_entries=ledger) == "opus"


def test_gate_does_not_apply_to_explicit_pin(monkeypatch):
    snap = _claude_snap(monkeypatch)
    ledger = _led("claude-opus-4-7", 0.0, n=5)
    assert _rm("anthropic_claude_code", "claude-opus-4-7", snap, ledger_entries=ledger) == "claude-opus-4-7"


# Append to tests/test_core/test_capability_policy.py
from ncdev.core.capability_policy import is_model_rejection_error, next_alias_down


def test_is_model_rejection_error_matches_known_phrases():
    assert is_model_rejection_error("Error: model not found")
    assert is_model_rejection_error("you do not have access to this model")
    assert is_model_rejection_error(None, "invalid model: opus-9")
    assert not is_model_rejection_error("timed out after 600s")
    assert not is_model_rejection_error(None, None)


def test_next_alias_down_steps_through_the_chain():
    assert next_alias_down("anthropic_claude_code", "opus") == "sonnet"
    assert next_alias_down("anthropic_claude_code", "sonnet") == "haiku"
    assert next_alias_down("anthropic_claude_code", "haiku") is None
    assert next_alias_down("anthropic_claude_code", "claude-opus-4-7") is None
    assert next_alias_down("openai_codex", "gpt-5.5") is None


# Append to tests/test_core/test_capability_policy.py
from ncdev.core.config import CapabilityGateConfig


def test_capability_gate_config_defaults_match_constants():
    cfg = CapabilityGateConfig()
    assert cfg.window == 5
    assert cfg.min_samples == 3
    assert cfg.fail_threshold == 0.5


def test_gate_uses_supplied_config(monkeypatch):
    snap = _claude_snap(monkeypatch)
    ledger = _led("opus", 0.4, n=4)  # 0.6 mean failure
    strict = CapabilityGateConfig(window=5, min_samples=3, fail_threshold=0.3)
    lenient = CapabilityGateConfig(window=5, min_samples=3, fail_threshold=0.9)
    assert _rm("anthropic_claude_code", "auto", snap,
               ledger_entries=ledger, gate_config=strict) == "sonnet"
    assert _rm("anthropic_claude_code", "auto", snap,
               ledger_entries=ledger, gate_config=lenient) == "opus"
