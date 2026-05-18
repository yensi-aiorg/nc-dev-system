from pathlib import Path

from ncdev import ai_session


def test_run_codex_session_resolves_model_and_passes_options(monkeypatch):
    captured = {}

    def fake_popen(cmd, *a, **kw):
        # OSError is what subprocess.Popen actually raises on a spawn
        # failure — run_codex_session catches it and returns a result,
        # so the test can read the captured argv without the exception
        # escaping.
        captured["cmd"] = cmd
        raise OSError("stop — argv captured")

    monkeypatch.setattr(ai_session.shutil, "which", lambda _: "/usr/bin/codex")
    monkeypatch.setattr(
        "ncdev.core.capability_probe._run_version",
        lambda _binary: "OpenAI Codex v0.130.0",
    )
    monkeypatch.setattr(ai_session.subprocess, "Popen", fake_popen)

    ai_session.run_codex_session(
        "task", cwd=Path("."), model="auto",
        codex_options=["-c", 'model_reasoning_effort="high"'],
    )

    cmd = captured["cmd"]
    assert cmd[cmd.index("--model") + 1] == "gpt-5.5"
    assert 'model_reasoning_effort="high"' in cmd
