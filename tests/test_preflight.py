from ncdev.preflight import required_commands, run_preflight


def test_required_commands_greenfield_full() -> None:
    cmds = required_commands(mode="greenfield", full=True)
    assert "claude" in cmds
    assert "codex" not in cmds  # codex no longer required by default
    assert "npm" in cmds


def test_preflight_detects_missing() -> None:
    result = run_preflight(["python3", "definitely_missing_binary_xyz"])
    assert result.ok is False
    assert "definitely_missing_binary_xyz" in result.missing
