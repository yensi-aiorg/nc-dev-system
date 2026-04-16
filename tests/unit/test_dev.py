from __future__ import annotations

from pathlib import Path

from ncdev import dev


def test_invoke_ai_planning_uses_codex(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    class FakeCompleted:
        returncode = 0
        stdout = "planned"
        stderr = ""

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return FakeCompleted()

    monkeypatch.setattr(dev.subprocess, "run", fake_run)

    result = dev.invoke_ai_planning("project context", "Build feature X", tmp_path)

    assert result == "planned"
    assert calls
    assert calls[0][:4] == ["codex", "exec", "--full-auto", "--sandbox"]
    assert "claude" not in " ".join(calls[0])
