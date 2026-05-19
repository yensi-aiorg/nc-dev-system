from ncdev.core.skill_author import (
    candidate_skills_dir,
    list_pending_skills,
    skills_install_dir,
)


def test_candidate_dir_is_under_home_ncdev(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.skill_author.Path.home", lambda: tmp_path)
    assert candidate_skills_dir() == tmp_path / ".ncdev" / "skill-candidates"


def test_install_dir_is_under_home_claude(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.skill_author.Path.home", lambda: tmp_path)
    assert skills_install_dir() == tmp_path / ".claude" / "skills"


def test_list_pending_skills_finds_dirs_with_skill_md(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.skill_author.Path.home", lambda: tmp_path)
    cand = tmp_path / ".ncdev" / "skill-candidates"
    (cand / "retry-helper").mkdir(parents=True)
    (cand / "retry-helper" / "SKILL.md").write_text("# skill", encoding="utf-8")
    (cand / "half-baked").mkdir(parents=True)  # no SKILL.md — not pending
    assert list_pending_skills() == ["retry-helper"]


def test_list_pending_skills_empty_when_no_dir(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.skill_author.Path.home", lambda: tmp_path)
    assert list_pending_skills() == []
