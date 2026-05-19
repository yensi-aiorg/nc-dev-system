"""End-to-end: a capability resolves to a concrete model with no edits."""

from ncdev.core.capability_probe import probe_toolchain, write_snapshot
from ncdev.core.capability_router import Resolved
from ncdev.core.session_options import build_session_options


def test_auto_capability_resolves_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr("ncdev.core.capability_probe.shutil.which", lambda _: "/usr/bin/x")
    monkeypatch.setattr("ncdev.core.capability_probe._run_version", lambda _b: "1.2.3")
    monkeypatch.setattr("ncdev.core.capability_probe.Path.home", lambda: tmp_path)

    doc = probe_toolchain(workspace=tmp_path)
    out = tmp_path / ".nc-dev" / "capabilities.json"
    write_snapshot(doc, out)
    assert out.exists()

    resolved = Resolved(
        capability="debugging", provider="anthropic_claude_code",
        model="auto", chain_position=0,
    )
    opts = build_session_options(resolved, doc)
    assert opts.model == "opus"
    assert "auto" not in opts.model
