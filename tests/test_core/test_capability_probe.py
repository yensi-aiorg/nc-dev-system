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


from pathlib import Path

from ncdev.core.capability_probe import scan_installed_skills


def test_scan_installed_skills_finds_skill_dirs(tmp_path, monkeypatch):
    home_skills = tmp_path / "home" / ".claude" / "skills"
    (home_skills / "systematic-debugging").mkdir(parents=True)
    (home_skills / "frontend-design").mkdir(parents=True)
    workspace = tmp_path / "proj"
    ws_skills = workspace / ".claude" / "skills"
    (ws_skills / "project-local-skill").mkdir(parents=True)
    monkeypatch.setattr("ncdev.core.capability_probe.Path.home", lambda: tmp_path / "home")

    found = scan_installed_skills(workspace)

    assert "systematic-debugging" in found
    assert "frontend-design" in found
    assert "project-local-skill" in found


def test_scan_installed_skills_handles_missing_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr("ncdev.core.capability_probe.Path.home", lambda: tmp_path / "nope")
    assert scan_installed_skills(tmp_path / "also-nope") == []


from ncdev.core.capability_probe import (
    load_snapshot,
    probe_toolchain,
    write_snapshot,
)
from ncdev.core.models import CapabilitySnapshotDoc


def test_probe_toolchain_returns_snapshot_doc(tmp_path, monkeypatch):
    monkeypatch.setattr("ncdev.core.capability_probe.shutil.which", lambda _: None)
    monkeypatch.setattr("ncdev.core.capability_probe.Path.home", lambda: tmp_path)
    doc = probe_toolchain(workspace=tmp_path)
    assert isinstance(doc, CapabilitySnapshotDoc)
    assert doc.schema_id == "capability-snapshot.1"
    providers = {s.provider for s in doc.snapshots}
    assert providers == {"anthropic_claude_code", "openai_codex"}


def test_write_then_load_snapshot_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr("ncdev.core.capability_probe.shutil.which", lambda _: None)
    monkeypatch.setattr("ncdev.core.capability_probe.Path.home", lambda: tmp_path)
    doc = probe_toolchain(workspace=tmp_path)
    out = tmp_path / ".nc-dev" / "capabilities.json"

    write_snapshot(doc, out)

    assert out.exists()
    loaded = load_snapshot(out)
    assert loaded is not None
    assert loaded.schema_id == "capability-snapshot.1"
    assert len(loaded.snapshots) == 2


def test_load_snapshot_missing_returns_none(tmp_path):
    assert load_snapshot(tmp_path / "nope.json") is None


def test_load_snapshot_corrupt_returns_none(tmp_path):
    bad = tmp_path / "capabilities.json"
    bad.write_text("{not valid json", encoding="utf-8")
    assert load_snapshot(bad) is None
