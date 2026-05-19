from ncdev import claude_session


def test_auto_model_is_resolved_not_passed_literally(monkeypatch):
    captured = {}

    class FakeProcess:
        stdout = ()
        stderr = ()
        returncode = 0

        def poll(self):
            return self.returncode

        def wait(self, *a, **kw):
            return self.returncode

    def fake_popen(cmd, *a, **kw):
        captured["cmd"] = cmd
        return FakeProcess()

    from ncdev.core import capability_probe

    monkeypatch.setattr(capability_probe, "_run_version", lambda _: "")
    monkeypatch.setattr(claude_session.shutil, "which", lambda _: "/usr/bin/claude")
    monkeypatch.setattr(claude_session.subprocess, "Popen", fake_popen)

    claude_session.run_claude_session("hi", cwd=__import__("pathlib").Path("."))

    cmd = captured["cmd"]
    model_value = cmd[cmd.index("--model") + 1]
    assert model_value != "auto"
    assert model_value == "opus"


def test_auto_model_demoted_when_ledger_shows_bad_record(monkeypatch, tmp_path):
    """A bad track record for 'opus' in the ledger demotes the auto-resolved
    model to 'sonnet' for a new session."""
    from ncdev.core.capability_ledger import LedgerEntry, append_entry

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

    claude_session.run_claude_session("hi", cwd=__import__("pathlib").Path("."))

    cmd = captured["cmd"]
    assert cmd[cmd.index("--model") + 1] == "sonnet"
