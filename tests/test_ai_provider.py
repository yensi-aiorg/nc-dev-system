from ncdev.ai_provider import ClaudeCLIProvider, CodexCLIProvider


def test_claude_build_argv_no_hardcoded_literal_for_auto():
    argv = ClaudeCLIProvider().build_argv("p", model="auto")
    model = argv[argv.index("--model") + 1]
    assert model == "opus"


def test_claude_build_argv_pin_passes_through():
    argv = ClaudeCLIProvider().build_argv("p", model="claude-opus-4-7")
    assert argv[argv.index("--model") + 1] == "claude-opus-4-7"


def test_codex_build_argv_emits_reasoning_when_requested():
    argv = CodexCLIProvider().build_argv(
        "p", model="auto", codex_options=["-c", 'model_reasoning_effort="high"']
    )
    assert "-c" in argv
    assert 'model_reasoning_effort="high"' in argv


def test_resolve_claude_model_demotes_on_bad_ledger(monkeypatch, tmp_path):
    from ncdev.core.capability_ledger import LedgerEntry, append_entry
    from ncdev.ai_provider import ClaudeCLIProvider

    monkeypatch.setattr("ncdev.core.capability_ledger.Path.home", lambda: tmp_path)
    for i in range(4):
        append_entry(LedgerEntry(
            timestamp="t", project_name="p", run_id=f"r{i}", cycle=1,
            provider="anthropic_claude_code", model="opus",
            first_pass_success_rate=0.1,
        ))
    argv = ClaudeCLIProvider().build_argv("p", model="auto")
    assert argv[argv.index("--model") + 1] == "sonnet"
