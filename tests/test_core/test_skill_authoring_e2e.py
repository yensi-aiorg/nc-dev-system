"""End-to-end: a recurring ledger pattern -> detected -> authored -> promoted."""

from ncdev.core.capability_ledger import LedgerEntry, append_entry, read_entries
from ncdev.core.skill_author import author_skill, list_pending_skills, promote_skill
from ncdev.core.skill_candidate import detect_skill_candidates


def test_pattern_to_promoted_skill(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.capability_ledger.Path.home", lambda: tmp_path)
    monkeypatch.setattr("ncdev.core.skill_author.Path.home", lambda: tmp_path)

    # 3 cycles record the same recurring lesson.
    for i in range(3):
        append_entry(
            LedgerEntry(
                timestamp="t",
                project_name="demo",
                run_id=f"r{i}",
                cycle=1,
                provider="openai_codex",
                model="gpt-5.5",
                capability_lessons=["kept hand-fixing the pagination helper"],
            )
        )

    # Detect.
    candidates = detect_skill_candidates(read_entries(), threshold=3)
    assert len(candidates) == 1

    # Author (session faked -- writes the skill file).
    def fake_runner(prompt, *, cwd, **kwargs):
        (cwd / "SKILL.md").write_text("# pagination-helper", encoding="utf-8")

        class _R:
            success = True
            final_text = "ok"

        return _R()

    author_skill(candidates[0], skill_name="pagination-helper", run_session=fake_runner)
    assert list_pending_skills() == ["pagination-helper"]

    # Promote.
    dest = promote_skill("pagination-helper")
    assert (dest / "SKILL.md").is_file()
    assert dest == tmp_path / ".claude" / "skills" / "pagination-helper"
