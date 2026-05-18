from ncdev.core.capability_router import Resolved
from ncdev.core.capability_probe import probe_toolchain
from ncdev.core.session_options import SessionOptions, build_session_options


def _snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr("ncdev.core.capability_probe.shutil.which", lambda _: "/usr/bin/x")
    monkeypatch.setattr(
        "ncdev.core.capability_probe._run_version", lambda _b: "1.2.3"
    )
    monkeypatch.setattr("ncdev.core.capability_probe.Path.home", lambda: tmp_path)
    return probe_toolchain(workspace=tmp_path)


def test_build_session_options_resolves_auto_model(tmp_path, monkeypatch):
    snap = _snapshot(tmp_path, monkeypatch)
    resolved = Resolved(
        capability="debugging",
        provider="anthropic_claude_code",
        model="auto",
        chain_position=0,
    )
    opts = build_session_options(resolved, snap)
    assert isinstance(opts, SessionOptions)
    assert opts.model == "opus"
    assert opts.extra_args == []


def test_build_session_options_codex_includes_reasoning(tmp_path, monkeypatch):
    snap = _snapshot(tmp_path, monkeypatch)
    resolved = Resolved(
        capability="backend_implementation",
        provider="openai_codex",
        model="auto",
        chain_position=0,
    )
    opts = build_session_options(
        resolved, snap, provider_defaults={"reasoning_effort": "high"}
    )
    assert opts.model == "gpt-5.5"
    assert opts.extra_args == ["-c", 'model_reasoning_effort="high"']


def test_build_session_options_pin_passes_through(tmp_path, monkeypatch):
    snap = _snapshot(tmp_path, monkeypatch)
    resolved = Resolved(
        capability="debugging",
        provider="anthropic_claude_code",
        model="claude-opus-4-7",
        chain_position=0,
    )
    opts = build_session_options(resolved, snap)
    assert opts.model == "claude-opus-4-7"
