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
