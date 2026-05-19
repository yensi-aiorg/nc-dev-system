"""End-to-end: a capability resolves to a concrete model with no edits."""

from ncdev.core.capability_probe import probe_toolchain, write_snapshot
from ncdev.core.capability_policy import resolve_model


def test_auto_capability_resolves_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr("ncdev.core.capability_probe.shutil.which", lambda _: "/usr/bin/x")
    monkeypatch.setattr("ncdev.core.capability_probe._run_version", lambda _b: "1.2.3")
    monkeypatch.setattr("ncdev.core.capability_probe._run_help", lambda _b: "")
    monkeypatch.setattr("ncdev.core.capability_probe.Path.home", lambda: tmp_path)

    doc = probe_toolchain(workspace=tmp_path)
    out = tmp_path / ".nc-dev" / "capabilities.json"
    write_snapshot(doc, out)
    assert out.exists()

    # The claude snapshot in the doc resolves "auto" to a concrete model.
    claude_snap = next(s for s in doc.snapshots if s.provider == "anthropic_claude_code")
    model = resolve_model("anthropic_claude_code", "auto", claude_snap)
    assert model == "opus"
    assert "auto" not in model
