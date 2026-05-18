from ncdev.core.capability_probe import (
    CLAUDE_MODEL_ALIASES,
    detect_cli_version,
    probe_claude,
    probe_codex,
)
from ncdev.core.models import ProviderCapabilitySnapshot


def test_detect_cli_version_parses_semver():
    assert detect_cli_version("OpenAI Codex v0.130.0") == "0.130.0"
    assert detect_cli_version("1.2.3 (Claude Code)") == "1.2.3"
    assert detect_cli_version("no version here") == "unknown"


def test_probe_claude_when_binary_missing(monkeypatch):
    monkeypatch.setattr("ncdev.core.capability_probe.shutil.which", lambda _: None)
    snap = probe_claude()
    assert isinstance(snap, ProviderCapabilitySnapshot)
    assert snap.provider == "anthropic_claude_code"
    assert snap.available is False
    assert "claude CLI not found on PATH" in snap.notes


def test_probe_claude_records_aliases_when_present(monkeypatch):
    monkeypatch.setattr("ncdev.core.capability_probe.shutil.which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(
        "ncdev.core.capability_probe._run_version", lambda _b: "1.2.3 (Claude Code)"
    )
    snap = probe_claude()
    assert snap.available is True
    assert snap.version == "1.2.3"
    assert snap.model == CLAUDE_MODEL_ALIASES[0]  # "opus" — the default alias


def test_probe_codex_records_version(monkeypatch):
    monkeypatch.setattr("ncdev.core.capability_probe.shutil.which", lambda _: "/usr/bin/codex")
    monkeypatch.setattr(
        "ncdev.core.capability_probe._run_version", lambda _b: "OpenAI Codex v0.130.0"
    )
    snap = probe_codex()
    assert snap.provider == "openai_codex"
    assert snap.available is True
    assert snap.version == "0.130.0"
