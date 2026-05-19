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


import pytest

from ncdev.core.skill_author import promote_skill


def _make_pending(tmp_path, name):
    d = tmp_path / ".ncdev" / "skill-candidates" / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text("# skill", encoding="utf-8")
    return d


def test_promote_copies_candidate_into_live_library(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.skill_author.Path.home", lambda: tmp_path)
    _make_pending(tmp_path, "retry-helper")
    dest = promote_skill("retry-helper")
    assert dest == tmp_path / ".claude" / "skills" / "retry-helper"
    assert (dest / "SKILL.md").read_text(encoding="utf-8") == "# skill"


def test_promote_unknown_candidate_raises(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.skill_author.Path.home", lambda: tmp_path)
    with pytest.raises(FileNotFoundError):
        promote_skill("does-not-exist")


def test_promote_refuses_to_overwrite_existing_skill(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.skill_author.Path.home", lambda: tmp_path)
    _make_pending(tmp_path, "retry-helper")
    (tmp_path / ".claude" / "skills" / "retry-helper").mkdir(parents=True)
    with pytest.raises(FileExistsError):
        promote_skill("retry-helper")


from ncdev.core.skill_author import author_skill
from ncdev.core.skill_candidate import SkillCandidate


def test_author_skill_spawns_session_into_pending_dir(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.skill_author.Path.home", lambda: tmp_path)
    candidate = SkillCandidate(
        pattern="had to hand-fix retry logic",
        occurrences=4,
        example_lessons=["had to hand-fix retry logic"],
        projects=["demo"],
    )
    captured = {}

    def fake_runner(prompt, *, cwd, **kwargs):
        captured["prompt"] = prompt
        captured["cwd"] = cwd
        (cwd / "SKILL.md").write_text("# retry-helper", encoding="utf-8")

        class _Result:
            success = True
            final_text = "authored"
        return _Result()

    dest = author_skill(candidate, skill_name="retry-helper", run_session=fake_runner)

    assert dest == tmp_path / ".ncdev" / "skill-candidates" / "retry-helper"
    assert (dest / "SKILL.md").is_file()
    assert captured["cwd"] == dest
    assert "writing-skills" in captured["prompt"]
    assert "had to hand-fix retry logic" in captured["prompt"]


def test_author_skill_rejects_a_name_that_already_has_a_pending_dir(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.skill_author.Path.home", lambda: tmp_path)
    _make_pending(tmp_path, "retry-helper")
    candidate = SkillCandidate(pattern="x", occurrences=3)
    with pytest.raises(FileExistsError):
        author_skill(candidate, skill_name="retry-helper", run_session=lambda *a, **k: None)
