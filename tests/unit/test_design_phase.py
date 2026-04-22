"""Tests for Phase C design system phase."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from ncdev.claude_session import ClaudeSessionResult
from ncdev.v3.design_phase import (
    DESIGN_TOOLS,
    DesignPhaseResult,
    existing_design_system_present,
    is_ui_project,
    run_design_phase,
    stitch_available,
)
from ncdev.v3.models import DesignSystemDoc, TargetProjectContract


def _web_contract(**overrides) -> TargetProjectContract:
    defaults = dict(
        project_name="myapp",
        project_type="web",
        frontend_framework="react",
        design_archetype="Technical Elegance",
        is_brownfield=False,
    )
    defaults.update(overrides)
    return TargetProjectContract(**defaults)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_is_ui_project_detects_web_types():
    assert is_ui_project(_web_contract(project_type="web"))
    assert is_ui_project(_web_contract(project_type="webapp"))
    assert is_ui_project(_web_contract(project_type="saas"))


def test_is_ui_project_false_for_cli_and_library():
    assert not is_ui_project(_web_contract(project_type="cli"))
    assert not is_ui_project(_web_contract(project_type="library"))


def test_existing_design_system_detects_populated_dir(tmp_path: Path):
    ds = tmp_path / "docs" / "design-system"
    ds.mkdir(parents=True)
    (ds / "tokens.css").write_text(":root { --brand: #000; }")
    assert existing_design_system_present(tmp_path) is True


def test_existing_design_system_false_for_empty_or_missing(tmp_path: Path):
    assert existing_design_system_present(tmp_path) is False
    ds = tmp_path / "docs" / "design-system"
    ds.mkdir(parents=True)
    assert existing_design_system_present(tmp_path) is False


def test_existing_design_system_rejects_junk_files(tmp_path: Path):
    """A README or a stray image doesn't make a valid design system."""
    ds = tmp_path / "docs" / "design-system"
    ds.mkdir(parents=True)
    (ds / "README.md").write_text("coming soon")
    (ds / "screenshot.png").write_bytes(b"\x89PNG")
    # Must not falsely claim a design system is present
    assert existing_design_system_present(tmp_path) is False

    # Now drop a real token file — should flip to True
    (ds / "tokens.css").write_text(":root { --brand: #000; }")
    assert existing_design_system_present(tmp_path) is True


def test_stitch_available_via_env_var_with_stitch_entry(tmp_path: Path, monkeypatch):
    fake_cfg = tmp_path / "stitch.json"
    fake_cfg.write_text('{"mcpServers": {"stitch": {"command": "node"}}}')
    monkeypatch.setenv("NCDEV_STITCH_MCP_CONFIG", str(fake_cfg))
    monkeypatch.setenv("HOME", str(tmp_path))  # isolate from real ~/.claude
    monkeypatch.chdir(tmp_path)
    assert stitch_available() is True


def test_stitch_available_via_env_var_but_no_stitch_entry(tmp_path: Path, monkeypatch):
    """Explicit override with a file that doesn't list stitch → False.
    We don't silently fall through to other locations when the override
    was set intentionally."""
    fake_cfg = tmp_path / "stitch.json"
    fake_cfg.write_text('{"mcpServers": {"other": {"command": "node"}}}')
    monkeypatch.setenv("NCDEV_STITCH_MCP_CONFIG", str(fake_cfg))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    assert stitch_available() is False


def test_stitch_available_via_home_mcp_json(tmp_path: Path, monkeypatch):
    """~/.claude/mcp.json is where Claude Code actually keeps MCP
    server definitions on this box — our probe must look there."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "mcp.json").write_text(
        '{"mcpServers": {"stitch": {"command": "node", "args": []}}}'
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("NCDEV_STITCH_MCP_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)
    assert stitch_available() is True


def test_stitch_available_via_settings_json_legacy_layout(tmp_path: Path, monkeypatch):
    """Older installs kept MCP servers inside settings.json."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "settings.json").write_text(
        '{"mcpServers": {"stitch-local": {"command": "node"}}}'
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("NCDEV_STITCH_MCP_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)
    assert stitch_available() is True


def test_stitch_available_via_project_local_mcp_json(tmp_path: Path, monkeypatch):
    """Project-local .mcp.json in CWD or ancestor counts too."""
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / ".mcp.json").write_text(
        '{"mcpServers": {"stitch-design": {"command": "stitch-server"}}}'
    )
    monkeypatch.setenv("HOME", str(tmp_path / "home-empty"))
    monkeypatch.delenv("NCDEV_STITCH_MCP_CONFIG", raising=False)
    monkeypatch.chdir(proj)
    assert stitch_available() is True


def test_stitch_available_false_when_nothing_configured(monkeypatch, tmp_path):
    """No env var, empty home, no project config → False."""
    monkeypatch.delenv("NCDEV_STITCH_MCP_CONFIG", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    assert stitch_available() is False


def test_stitch_available_ignores_unrelated_mcp_servers(monkeypatch, tmp_path):
    """MCP config with other servers but no stitch → False."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "mcp.json").write_text(
        '{"mcpServers": {"github": {}, "playwright": {}, "filesystem": {}}}'
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("NCDEV_STITCH_MCP_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)
    assert stitch_available() is False


def test_stitch_available_case_insensitive_match(monkeypatch, tmp_path):
    """Key matching is case-insensitive for 'stitch'."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "mcp.json").write_text(
        '{"mcpServers": {"Stitch-MCP": {"command": "node"}}}'
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("NCDEV_STITCH_MCP_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)
    assert stitch_available() is True


def test_stitch_available_tolerates_malformed_json(monkeypatch, tmp_path):
    """Broken JSON in one config doesn't crash the probe — just skip it."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "mcp.json").write_text("{not valid json")
    (claude_dir / "settings.json").write_text(
        '{"mcpServers": {"stitch": {"command": "node"}}}'
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("NCDEV_STITCH_MCP_CONFIG", raising=False)
    monkeypatch.chdir(tmp_path)
    # Should still find stitch via settings.json after mcp.json fails to parse
    assert stitch_available() is True


# ---------------------------------------------------------------------------
# Non-UI skip path
# ---------------------------------------------------------------------------


def test_cli_project_skips_design_phase(tmp_path: Path):
    contract = _web_contract(project_type="cli")
    result = run_design_phase(contract, tmp_path, tmp_path / "out")
    assert result.skipped is True
    assert result.hard_failed is False
    assert result.design_doc is None


# ---------------------------------------------------------------------------
# Hard-fail path
# ---------------------------------------------------------------------------


def test_greenfield_ui_without_stitch_or_designs_hard_fails(tmp_path: Path):
    contract = _web_contract(is_brownfield=False)
    output_dir = tmp_path / "out"

    result = run_design_phase(
        contract, tmp_path, output_dir,
        stitch_probe=lambda: False,   # no Stitch
    )

    assert result.hard_failed is True
    assert result.error is not None
    assert "greenfield" in result.error.lower() or "design" in result.error.lower()
    # Error artifact written for downstream processing / human
    err = output_dir / "design-phase-error.json"
    assert err.exists()
    payload = json.loads(err.read_text(encoding="utf-8"))
    assert "error" in payload
    assert "fix" in payload


# ---------------------------------------------------------------------------
# Brownfield with existing design system
# ---------------------------------------------------------------------------


def test_brownfield_with_design_system_runs_summariser(tmp_path: Path):
    contract = _web_contract(is_brownfield=True)
    # Seed existing design system
    ds = tmp_path / "docs" / "design-system"
    ds.mkdir(parents=True)
    (ds / "tokens.css").write_text(":root { --brand: #abcdef; }")

    output_dir = tmp_path / "out"
    captured: dict = {}

    def fake_session(prompt, **kwargs):
        captured["prompt"] = prompt
        captured.update(kwargs)
        doc = DesignSystemDoc(
            project_name="myapp",
            design_archetype="Technical Elegance",
            source="existing",
            tokens_files=["tokens.css"],
        )
        (output_dir / "design-system.json").write_text(
            doc.model_dump_json(indent=2), encoding="utf-8",
        )
        return ClaudeSessionResult(success=True, final_text="summarised", exit_code=0)

    with patch("ncdev.v3.design_phase.run_ai_session", side_effect=fake_session):
        result = run_design_phase(
            contract, tmp_path, output_dir,
            stitch_probe=lambda: False,   # doesn't matter, existing wins
        )

    assert result.hard_failed is False
    assert result.design_doc is not None
    assert result.design_doc.source == "existing"
    # Prompt must be the brownfield-summariser variant
    assert "read the existing" in captured["prompt"].lower()
    assert "Do NOT modify" in captured["prompt"]


# ---------------------------------------------------------------------------
# Stitch path
# ---------------------------------------------------------------------------


def test_greenfield_with_stitch_runs_stitch_prompt(tmp_path: Path):
    contract = _web_contract(is_brownfield=False)
    output_dir = tmp_path / "out"
    captured: dict = {}

    def fake_session(prompt, **kwargs):
        captured["prompt"] = prompt
        doc = DesignSystemDoc(
            project_name="myapp",
            design_archetype="Technical Elegance",
            source="stitch",
            stitch_project_id="stitch-abc",
            tokens_files=["tokens.css", "tailwind.config.js"],
        )
        (output_dir / "design-system.json").write_text(
            doc.model_dump_json(indent=2), encoding="utf-8",
        )
        return ClaudeSessionResult(success=True, final_text="stitch done", exit_code=0)

    with patch("ncdev.v3.design_phase.run_ai_session", side_effect=fake_session):
        result = run_design_phase(
            contract, tmp_path, output_dir,
            stitch_probe=lambda: True,
        )

    assert result.hard_failed is False
    assert result.design_doc is not None
    assert result.design_doc.source == "stitch"
    assert result.design_doc.stitch_project_id == "stitch-abc"
    # Stitch prompt
    assert "Stitch" in captured["prompt"]
    assert "MCP" in captured["prompt"]


def test_stitch_phase_that_writes_error_file_is_hard_failed(tmp_path: Path):
    contract = _web_contract(is_brownfield=False)
    output_dir = tmp_path / "out"

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "design-phase-error.json").write_text(
            '{"error": "Stitch auth failed", "fix": "re-auth"}', encoding="utf-8",
        )
        return ClaudeSessionResult(success=True, final_text="stitch unreachable", exit_code=0)

    with patch("ncdev.v3.design_phase.run_ai_session", side_effect=fake_session):
        result = run_design_phase(
            contract, tmp_path, output_dir,
            stitch_probe=lambda: True,
        )

    assert result.hard_failed is True
    assert "error artifact" in (result.error or "")


# ---------------------------------------------------------------------------
# Brownfield without designs + no Stitch: Claude decides
# ---------------------------------------------------------------------------


def test_brownfield_without_designs_and_no_stitch_lets_claude_decide(tmp_path: Path):
    contract = _web_contract(is_brownfield=True)
    output_dir = tmp_path / "out"
    captured: dict = {}

    def fake_session(prompt, **kwargs):
        captured["prompt"] = prompt
        doc = DesignSystemDoc(
            project_name="myapp",
            design_archetype="Technical Elegance",
            source="claude_generated",
        )
        (output_dir / "design-system.json").write_text(
            doc.model_dump_json(indent=2), encoding="utf-8",
        )
        return ClaudeSessionResult(success=True, final_text="ok", exit_code=0)

    with patch("ncdev.v3.design_phase.run_ai_session", side_effect=fake_session):
        result = run_design_phase(
            contract, tmp_path, output_dir,
            stitch_probe=lambda: False,
        )

    assert result.hard_failed is False
    assert result.design_doc is not None
    assert result.design_doc.source == "claude_generated"
    # Prompt instructs Claude it MAY hard-fail itself if it thinks Stitch needed
    assert "frontend-design" in captured["prompt"]
    assert "design-phase-error.json" in captured["prompt"]


def test_design_phase_fails_loud_when_session_succeeds_but_no_doc_produced(tmp_path: Path):
    """Codex flagged: session.success=True with no design-system.json
    must NOT be silently accepted as passing — it must hard-fail."""
    contract = _web_contract(is_brownfield=True)
    ds = tmp_path / "docs" / "design-system"
    ds.mkdir(parents=True)
    (ds / "tokens.css").write_text(":root {}")
    output_dir = tmp_path / "out"

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        # "Claude" exits clean but forgets to write design-system.json
        return ClaudeSessionResult(success=True, final_text="I forgot", exit_code=0)

    with patch("ncdev.v3.design_phase.run_ai_session", side_effect=fake_session):
        result = run_design_phase(
            contract, tmp_path, output_dir,
            stitch_probe=lambda: False,
        )

    assert result.hard_failed is True
    assert "design-system.json" in (result.error or "")


def test_design_phase_fails_when_session_exits_unsuccessfully(tmp_path: Path):
    """Codex flagged: session.success=False must hard-fail even if the
    session wrote a valid design-system.json by accident."""
    contract = _web_contract(is_brownfield=True)
    ds = tmp_path / "docs" / "design-system"
    ds.mkdir(parents=True)
    (ds / "tokens.css").write_text(":root {}")
    output_dir = tmp_path / "out"

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        doc = DesignSystemDoc(
            project_name="myapp",
            design_archetype="Technical Elegance",
            source="existing",
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "design-system.json").write_text(doc.model_dump_json(), encoding="utf-8")
        return ClaudeSessionResult(success=False, final_text="crashed", exit_code=1,
                                    error="session timed out")

    with patch("ncdev.v3.design_phase.run_ai_session", side_effect=fake_session):
        result = run_design_phase(
            contract, tmp_path, output_dir,
            stitch_probe=lambda: False,
        )

    assert result.hard_failed is True
    assert "unsuccessfully" in (result.error or "")


def test_brownfield_summariser_uses_read_only_tools(tmp_path: Path):
    """Codex flagged: summariser branch had Edit/Bash/Task which contradicts
    the 'read and summarise only' contract. Verify read-only toolset."""
    contract = _web_contract(is_brownfield=True)
    ds = tmp_path / "docs" / "design-system"
    ds.mkdir(parents=True)
    (ds / "tokens.css").write_text(":root {}")
    output_dir = tmp_path / "out"
    captured: dict = {}

    def fake_session(prompt, **kwargs):
        captured.update(kwargs)
        doc = DesignSystemDoc(project_name="x", design_archetype="y", source="existing")
        (output_dir / "design-system.json").write_text(doc.model_dump_json(), encoding="utf-8")
        return ClaudeSessionResult(success=True, final_text="ok", exit_code=0)

    with patch("ncdev.v3.design_phase.run_ai_session", side_effect=fake_session):
        run_design_phase(contract, tmp_path, output_dir, stitch_probe=lambda: False)

    tools = list(captured["tools"])
    # Read-only: no Edit, no Bash, no Task
    assert "Edit" not in tools
    assert "Bash" not in tools
    assert "Task" not in tools
    # But Write is allowed (for design-system.json itself)
    assert "Write" in tools
    assert "Read" in tools


def test_design_session_does_not_include_codex_protocol(tmp_path: Path):
    contract = _web_contract(is_brownfield=True)
    ds = tmp_path / "docs" / "design-system"
    ds.mkdir(parents=True)
    (ds / "tokens.css").write_text(":root {}")
    output_dir = tmp_path / "out"
    captured: dict = {}

    def fake_session(prompt, **kwargs):
        captured.update(kwargs)
        doc = DesignSystemDoc(project_name="x", design_archetype="y", source="existing")
        (output_dir / "design-system.json").write_text(doc.model_dump_json(), encoding="utf-8")
        return ClaudeSessionResult(success=True, final_text="ok", exit_code=0)

    with patch("ncdev.v3.design_phase.run_ai_session", side_effect=fake_session):
        run_design_phase(
            contract, tmp_path, output_dir,
            stitch_probe=lambda: False,
        )

    # Design phase does not shell out to Codex — protocol must be off
    assert captured["include_codex_protocol"] is False
