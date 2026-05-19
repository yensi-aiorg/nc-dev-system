"""End-to-end: a bad ledger record changes what a real session spawns,
and a 'hurt' lesson drops a skill from a real selection."""

from pathlib import Path

from ncdev import claude_session
from ncdev.core.capability_ledger import LedgerEntry, append_entry
from ncdev.core.skill_selector import select_skills


def test_bad_ledger_demotes_a_real_claude_session(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.capability_ledger.Path.home", lambda: tmp_path)
    for i in range(4):
        append_entry(LedgerEntry(
            timestamp="t", project_name="p", run_id=f"r{i}", cycle=1,
            provider="anthropic_claude_code", model="opus",
            first_pass_success_rate=0.1,
        ))

    captured = {}

    def fake_popen(cmd, *a, **kw):
        captured["cmd"] = cmd
        raise OSError("stop — argv captured")

    monkeypatch.setattr(claude_session.shutil, "which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(claude_session.subprocess, "Popen", fake_popen)

    claude_session.run_claude_session("hi", cwd=Path("."))

    cmd = captured["cmd"]
    assert cmd[cmd.index("--model") + 1] == "sonnet"


def test_clean_ledger_leaves_a_real_claude_session_on_opus(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.capability_ledger.Path.home", lambda: tmp_path)
    captured = {}

    def fake_popen(cmd, *a, **kw):
        captured["cmd"] = cmd
        raise OSError("stop")

    monkeypatch.setattr(claude_session.shutil, "which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(claude_session.subprocess, "Popen", fake_popen)

    claude_session.run_claude_session("hi", cwd=Path("."))

    cmd = captured["cmd"]
    assert cmd[cmd.index("--model") + 1] == "opus"


def test_hurt_lesson_drops_skill_with_real_selector(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.capability_ledger.Path.home", lambda: tmp_path)
    from ncdev.core.capability_ledger import recent_lessons

    append_entry(LedgerEntry(
        timestamp="t", project_name="p", run_id="r1", cycle=1,
        provider="openai_codex", model="gpt-5.5",
        capability_lessons=["frontend-design hurt — inconsistent output"],
    ))
    picked = select_skills(
        "greenfield_ui",
        ["frontend-design", "test-driven-development", "writing-plans"],
        lessons=recent_lessons(),
    )
    assert "frontend-design" not in picked
    assert "test-driven-development" in picked
