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


def test_skill_author_and_promote_parse():
    p = build_parser()
    a = p.parse_args(["skill-author", "--name", "retry-helper", "--pattern", "x"])
    assert a.command == "skill-author" and a.name == "retry-helper"
    b = p.parse_args(["skill-promote", "--name", "retry-helper"])
    assert b.command == "skill-promote" and b.name == "retry-helper"


def test_skill_promote_moves_pending_into_library(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("ncdev.core.skill_author.Path.home", lambda: tmp_path)
    pend = tmp_path / ".ncdev" / "skill-candidates" / "retry-helper"
    pend.mkdir(parents=True)
    (pend / "SKILL.md").write_text("# s", encoding="utf-8")

    rc = main(["skill-promote", "--name", "retry-helper"])

    assert rc == 0
    assert (tmp_path / ".claude" / "skills" / "retry-helper" / "SKILL.md").is_file()


def test_skill_promote_unknown_returns_nonzero(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.skill_author.Path.home", lambda: tmp_path)
    assert main(["skill-promote", "--name", "nope"]) == 1


def test_skill_review_command_parses():
    args = build_parser().parse_args(["skill-review", "--name", "retry-helper"])
    assert args.command == "skill-review" and args.name == "retry-helper"


def test_skill_review_missing_candidate_returns_nonzero(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.skill_author.Path.home", lambda: tmp_path)
    assert main(["skill-review", "--name", "nope"]) == 1
