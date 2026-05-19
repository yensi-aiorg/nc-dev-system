from ncdev.core.skill_review import SkillReview, review_skill_candidate


def test_review_parses_session_verdict(tmp_path):
    skill_dir = tmp_path / "retry-helper"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# retry-helper\nteaches retries", encoding="utf-8")

    def fake_runner(prompt, *, cwd, **kwargs):
        assert "retry-helper" in (skill_dir / "SKILL.md").read_text(encoding="utf-8")

        class _R:
            success = True
            final_text = '{"approved": true, "reasoning": "clear and well-scoped"}'
        return _R()

    review = review_skill_candidate(skill_dir, run_session=fake_runner)
    assert isinstance(review, SkillReview)
    assert review.approved is True
    assert "well-scoped" in review.reasoning


def test_review_handles_fenced_json(tmp_path):
    skill_dir = tmp_path / "s"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# s", encoding="utf-8")

    def fake_runner(prompt, *, cwd, **kwargs):
        class _R:
            success = True
            final_text = '```json\n{"approved": false, "reasoning": "too vague"}\n```'
        return _R()

    review = review_skill_candidate(skill_dir, run_session=fake_runner)
    assert review.approved is False
    assert review.reasoning == "too vague"


def test_review_missing_skill_md_raises(tmp_path):
    import pytest
    with pytest.raises(FileNotFoundError):
        review_skill_candidate(tmp_path / "nope", run_session=lambda *a, **k: None)
