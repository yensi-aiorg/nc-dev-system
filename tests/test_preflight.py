import pytest

from ncdev.preflight import required_commands, require_citex, run_preflight


def test_required_commands_greenfield_full() -> None:
    cmds = required_commands(mode="greenfield", full=True)
    assert "claude" in cmds
    assert "codex" not in cmds  # codex no longer required by default
    assert "npm" in cmds


def test_preflight_detects_missing() -> None:
    result = run_preflight(["python3", "definitely_missing_binary_xyz"])
    assert result.ok is False
    assert "definitely_missing_binary_xyz" in result.missing


def test_require_citex_passes_when_healthy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ncdev.preflight.check_citex", lambda url="http://localhost:20161": True)
    require_citex()


def test_require_citex_raises_when_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ncdev.preflight.check_citex", lambda url="http://localhost:20161": False)
    with pytest.raises(RuntimeError, match="Citex RAG is required"):
        require_citex()
