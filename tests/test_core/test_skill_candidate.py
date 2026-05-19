from ncdev.core.capability_ledger import LedgerEntry
from ncdev.core.skill_candidate import SkillCandidate, detect_skill_candidates


def _entry(run_id, lessons, project="demo"):
    return LedgerEntry(
        timestamp="t", project_name=project, run_id=run_id, cycle=1,
        provider="openai_codex", model="gpt-5.5", capability_lessons=lessons,
    )


def test_detects_lesson_recurring_at_or_above_threshold():
    entries = [
        _entry("r1", ["had to hand-fix the API client retry logic"]),
        _entry("r2", ["Had to hand-fix the API client retry logic  "]),
        _entry("r3", ["had to hand-fix the API client retry logic"]),
        _entry("r4", ["unrelated one-off note"]),
    ]
    candidates = detect_skill_candidates(entries, threshold=3)
    assert len(candidates) == 1
    c = candidates[0]
    assert isinstance(c, SkillCandidate)
    assert c.occurrences == 3
    assert "hand-fix the api client retry logic" in c.pattern
    assert len(c.example_lessons) == 3


def test_lesson_below_threshold_is_not_a_candidate():
    entries = [
        _entry("r1", ["had to hand-fix the retry logic"]),
        _entry("r2", ["had to hand-fix the retry logic"]),
    ]
    assert detect_skill_candidates(entries, threshold=3) == []


def test_candidate_records_distinct_projects():
    entries = [
        _entry("r1", ["recurring gap X"], project="alpha"),
        _entry("r2", ["recurring gap X"], project="beta"),
        _entry("r3", ["recurring gap X"], project="alpha"),
    ]
    candidates = detect_skill_candidates(entries, threshold=3)
    assert sorted(candidates[0].projects) == ["alpha", "beta"]


def test_empty_entries_yield_no_candidates():
    assert detect_skill_candidates([], threshold=3) == []
