from ncdev.cli import build_parser, main


def test_skill_candidates_command_parses():
    args = build_parser().parse_args(["skill-candidates"])
    assert args.command == "skill-candidates"


def test_skill_candidates_runs_and_reports(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("ncdev.core.capability_ledger.Path.home", lambda: tmp_path)
    monkeypatch.setattr("ncdev.core.skill_author.Path.home", lambda: tmp_path)
    from ncdev.core.capability_ledger import LedgerEntry, append_entry
    for i in range(3):
        append_entry(LedgerEntry(
            timestamp="t", project_name="demo", run_id=f"r{i}", cycle=1,
            provider="openai_codex", model="gpt-5.5",
            capability_lessons=["recurring gap in retry handling"],
        ))
    rc = main(["skill-candidates"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "recurring gap in retry handling" in out
