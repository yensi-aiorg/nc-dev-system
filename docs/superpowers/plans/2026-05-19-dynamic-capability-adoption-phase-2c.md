# Dynamic Capability Adoption — Phase 2c (Gated Skill Authoring) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the last loop of the spec — when the capability ledger shows a recurring pattern, let NC Dev author a new Claude skill for it, behind a human-review gate so nothing reaches the global skill library without an explicit promote.

**Architecture:** `skill_candidate.py` detects recurring `capability_lessons` across the ledger (`≥ threshold` occurrences → a candidate). `skill_author.py` spawns a Claude session that uses the `superpowers:writing-skills` skill to author a skill into a pending directory (`~/.ncdev/skill-candidates/`), and exposes `promote_skill()` which copies an approved candidate into the live library (`~/.claude/skills/`). Three `ncdev` commands — `skill-candidates`, `skill-author`, `skill-promote` — let a human drive detection → authoring → promotion. Authoring is never auto-run; the expensive, irreversible step is always human-triggered.

**Tech Stack:** Python 3.13, Pydantic v2, pytest. Builds on Phase 2a/2b (`capability_ledger`) and `claude_session.run_claude_session`.

**Scope:** Phase 2c of the spec `docs/superpowers/specs/2026-05-18-dynamic-capability-adoption-design.md` — implements §4.3. This is the final phase of the dynamic-capability-adoption effort.

---

## Decisions & assumptions (review before executing)

1. **Authoring is human-triggered.** Detection (`ncdev skill-candidates`) is cheap and can be run anytime; actual authoring (`ncdev skill-author`) spawns a Claude session and is run by a human, never automatically inside the factory loop. The spec calls skill creation "a heavier commitment" — keeping the trigger manual is the gate's first layer.
2. **The promotion gate is human review.** Authored skills land in `~/.ncdev/skill-candidates/<name>/` and only reach the live library `~/.claude/skills/<name>/` via an explicit `ncdev skill-promote`. (The spec offered "human review *or* Steward A/B"; human review is chosen — simplest, safest, fully sufficient.)
3. **Pattern detection is naive.** Recurring lessons are matched by normalised text (lowercased, whitespace-collapsed) exact-equality counting. Semantic clustering of similar-but-not-identical lessons is future work — noted, not built.
4. **Skill quality depends on the authoring session.** The plan delivers the plumbing and a strong authoring prompt that points the session at `superpowers:writing-skills`. It does not guarantee the authored skill is good — that is what the human-review gate exists for.

---

## File Structure

**New files:**
- `src/ncdev/core/skill_candidate.py` — `SkillCandidate` model + `detect_skill_candidates()`
- `src/ncdev/core/skill_author.py` — pending/live dir helpers, `list_pending_skills()`, `promote_skill()`, `author_skill()`
- `tests/test_core/test_skill_candidate.py`
- `tests/test_core/test_skill_author.py`
- `tests/test_core/test_skill_authoring_cli.py`

**Modified files:**
- `src/ncdev/cli.py` — three new subcommands: `skill-candidates`, `skill-author`, `skill-promote`

---

## Task 1: `skill_candidate.py` — detect recurring patterns

**Files:**
- Create: `src/ncdev/core/skill_candidate.py`
- Test: `tests/test_core/test_skill_candidate.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_core/test_skill_candidate.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_core/test_skill_candidate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ncdev.core.skill_candidate'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/ncdev/core/skill_candidate.py
"""Detect recurring patterns in the capability ledger.

A capability lesson that the Steward records across many cycles is a
signal that NC Dev keeps hitting the same gap — a candidate for a new
skill. Matching is naive (normalised exact-equality); semantic
clustering is future work.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from ncdev.core.capability_ledger import LedgerEntry

_WS = re.compile(r"\s+")


class SkillCandidate(BaseModel):
    """A recurring ledger pattern worth authoring a skill for."""

    pattern: str                                    # normalised lesson text
    occurrences: int
    example_lessons: list[str] = Field(default_factory=list)  # raw lesson strings
    projects: list[str] = Field(default_factory=list)         # distinct projects


def _normalise(lesson: str) -> str:
    """Lowercase + collapse whitespace so near-identical lessons match."""
    return _WS.sub(" ", lesson.strip().lower())


def detect_skill_candidates(
    entries: list[LedgerEntry],
    *,
    threshold: int = 3,
) -> list[SkillCandidate]:
    """Return ledger patterns recurring `>= threshold` times.

    Each distinct normalised lesson string is counted across all
    entries; those at or above `threshold` become candidates, sorted
    most-frequent first.
    """
    raw: dict[str, list[str]] = {}
    projects: dict[str, set[str]] = {}
    for entry in entries:
        for lesson in entry.capability_lessons:
            key = _normalise(lesson)
            if not key:
                continue
            raw.setdefault(key, []).append(lesson)
            projects.setdefault(key, set()).add(entry.project_name)

    candidates = [
        SkillCandidate(
            pattern=key,
            occurrences=len(examples),
            example_lessons=examples,
            projects=sorted(projects[key]),
        )
        for key, examples in raw.items()
        if len(examples) >= threshold
    ]
    candidates.sort(key=lambda c: c.occurrences, reverse=True)
    return candidates
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_core/test_skill_candidate.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/core/skill_candidate.py tests/test_core/test_skill_candidate.py
git commit -m "feat(capability): detect recurring skill-candidate patterns from the ledger"
```

---

## Task 2: `skill_author.py` — directories + `list_pending_skills()`

**Files:**
- Create: `src/ncdev/core/skill_author.py`
- Test: `tests/test_core/test_skill_author.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_core/test_skill_author.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_core/test_skill_author.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ncdev.core.skill_author'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/ncdev/core/skill_author.py
"""Author new Claude skills from ledger patterns, behind a human gate.

Authored skills land in a pending directory (~/.ncdev/skill-candidates/)
and only reach the live library (~/.claude/skills/) via an explicit
promote. Authoring spawns a Claude session — it is never auto-run.
"""

from __future__ import annotations

from pathlib import Path


def candidate_skills_dir() -> Path:
    """Pending directory — authored-but-unpromoted skills live here."""
    return Path.home() / ".ncdev" / "skill-candidates"


def skills_install_dir() -> Path:
    """The live Claude skill library."""
    return Path.home() / ".claude" / "skills"


def list_pending_skills() -> list[str]:
    """Names of pending skills — candidate subdirs that contain a SKILL.md."""
    root = candidate_skills_dir()
    if not root.is_dir():
        return []
    return sorted(
        child.name
        for child in root.iterdir()
        if child.is_dir() and (child / "SKILL.md").is_file()
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_core/test_skill_author.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/core/skill_author.py tests/test_core/test_skill_author.py
git commit -m "feat(capability): skill-author dirs + list_pending_skills"
```

---

## Task 3: `skill_author.py` — `promote_skill()`

**Files:**
- Modify: `src/ncdev/core/skill_author.py`
- Test: `tests/test_core/test_skill_author.py` (append)

- [ ] **Step 1: Append the failing test**

```python
# Append to tests/test_core/test_skill_author.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_core/test_skill_author.py -k promote -v`
Expected: FAIL — `ImportError: cannot import name 'promote_skill'`

- [ ] **Step 3: Write minimal implementation**

```python
# Add to src/ncdev/core/skill_author.py — add `import shutil` to the imports
def promote_skill(name: str) -> Path:
    """Copy a pending skill into the live Claude skill library.

    Raises FileNotFoundError if the candidate does not exist (or has no
    SKILL.md), and FileExistsError if a live skill of that name already
    exists — promotion never overwrites.
    """
    source = candidate_skills_dir() / name
    if not (source / "SKILL.md").is_file():
        raise FileNotFoundError(
            f"No pending skill '{name}' in {candidate_skills_dir()}"
        )
    dest = skills_install_dir() / name
    if dest.exists():
        raise FileExistsError(
            f"A skill '{name}' already exists at {dest} — remove it first"
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, dest)
    return dest
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_core/test_skill_author.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/core/skill_author.py tests/test_core/test_skill_author.py
git commit -m "feat(capability): promote_skill — gated copy into the live library"
```

---

## Task 4: `skill_author.py` — `author_skill()`

**Files:**
- Modify: `src/ncdev/core/skill_author.py`
- Test: `tests/test_core/test_skill_author.py` (append)

`author_skill` spawns a Claude session that uses `superpowers:writing-skills`. The session runner is an injectable parameter so the test can supply a fake.

- [ ] **Step 1: Append the failing test**

```python
# Append to tests/test_core/test_skill_author.py
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
        # Simulate the session writing the skill.
        (cwd / "SKILL.md").write_text("# retry-helper", encoding="utf-8")

        class _Result:
            success = True
            final_text = "authored"
        return _Result()

    dest = author_skill(candidate, skill_name="retry-helper", run_session=fake_runner)

    assert dest == tmp_path / ".ncdev" / "skill-candidates" / "retry-helper"
    assert (dest / "SKILL.md").is_file()
    assert captured["cwd"] == dest
    # The prompt must steer the session to the writing-skills skill and
    # carry the pattern.
    assert "writing-skills" in captured["prompt"]
    assert "had to hand-fix retry logic" in captured["prompt"]


def test_author_skill_rejects_a_name_that_already_has_a_pending_dir(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.skill_author.Path.home", lambda: tmp_path)
    _make_pending(tmp_path, "retry-helper")
    candidate = SkillCandidate(pattern="x", occurrences=3)
    with pytest.raises(FileExistsError):
        author_skill(candidate, skill_name="retry-helper", run_session=lambda *a, **k: None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_core/test_skill_author.py -k author_skill -v`
Expected: FAIL — `ImportError: cannot import name 'author_skill'`

- [ ] **Step 3: Write minimal implementation**

```python
# Add to src/ncdev/core/skill_author.py — add to imports:
#   from collections.abc import Callable
#   from typing import Any
#   from ncdev.core.skill_candidate import SkillCandidate

def _build_authoring_prompt(candidate: SkillCandidate, skill_name: str) -> str:
    """The prompt for the skill-authoring Claude session."""
    examples = "\n".join(f"  - {ex}" for ex in candidate.example_lessons)
    return (
        f"Author a new Claude skill named `{skill_name}` in the current "
        f"directory.\n\n"
        f"Use the `superpowers:writing-skills` skill to do this — follow "
        f"its TDD-for-documentation process.\n\n"
        f"The skill must address this recurring pattern, which NC Dev's "
        f"capability ledger flagged {candidate.occurrences} times across "
        f"projects {', '.join(candidate.projects) or '(unknown)'}:\n\n"
        f"  Pattern: {candidate.pattern}\n"
        f"  Example observations:\n{examples}\n\n"
        f"Write the skill as `SKILL.md` in the current directory (plus any "
        f"supporting files the writing-skills process calls for). The skill "
        f"should teach an agent how to handle this pattern correctly so the "
        f"recurring hand-fixing stops."
    )


def author_skill(
    candidate: SkillCandidate,
    *,
    skill_name: str,
    run_session: Callable[..., Any] | None = None,
) -> Path:
    """Spawn a Claude session that authors a skill for `candidate`.

    The authored skill lands in the pending directory and must still be
    promoted by a human. `run_session` defaults to
    claude_session.run_claude_session; tests inject a fake.

    Raises FileExistsError if a pending dir of that name already exists.
    """
    dest = candidate_skills_dir() / skill_name
    if dest.exists():
        raise FileExistsError(
            f"A pending skill '{skill_name}' already exists at {dest}"
        )
    if run_session is None:
        from ncdev.claude_session import run_claude_session

        run_session = run_claude_session

    dest.mkdir(parents=True)
    prompt = _build_authoring_prompt(candidate, skill_name)
    run_session(prompt, cwd=dest)
    return dest
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_core/test_skill_author.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/core/skill_author.py tests/test_core/test_skill_author.py
git commit -m "feat(capability): author_skill — spawn a writing-skills session into pending"
```

---

## Task 5: CLI — `ncdev skill-candidates`

**Files:**
- Modify: `src/ncdev/cli.py`
- Test: `tests/test_core/test_skill_authoring_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_core/test_skill_authoring_cli.py
from ncdev.cli import build_parser, main


def test_skill_candidates_command_parses():
    args = build_parser().parse_args(["skill-candidates"])
    assert args.command == "skill-candidates"


def test_skill_candidates_runs_and_reports(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("ncdev.core.capability_ledger.Path.home", lambda: tmp_path)
    monkeypatch.setattr("ncdev.core.skill_author.Path.home", lambda: tmp_path)
    # Seed the ledger with a recurring lesson (threshold default 3).
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_core/test_skill_authoring_cli.py -k candidates -v`
Expected: FAIL — argparse rejects `skill-candidates` (unknown command)

- [ ] **Step 3: Add the subparser and dispatch**

In `src/ncdev/cli.py`, in `build_parser()`, after the `qa-update` subparser block (before `return parser`), add:

```python
    skill_candidates = sub.add_parser(
        "skill-candidates",
        help="List recurring ledger patterns + pending authored skills",
    )
    skill_candidates.add_argument(
        "--threshold", type=int, default=3,
        help="Minimum recurrences for a pattern to be a candidate",
    )
```

In `main()`, after the `qa-update` dispatch block, add:

```python
    if args.command == "skill-candidates":
        from ncdev.core.capability_ledger import read_entries
        from ncdev.core.skill_candidate import detect_skill_candidates
        from ncdev.core.skill_author import list_pending_skills

        candidates = detect_skill_candidates(read_entries(), threshold=args.threshold)
        console.print(f"[bold]Skill candidates[/bold] (>= {args.threshold} recurrences):")
        if not candidates:
            console.print("  (none)")
        for c in candidates:
            console.print(f"  - {c.pattern}  [dim](x{c.occurrences})[/dim]")
        pending = list_pending_skills()
        console.print(f"[bold]Pending authored skills[/bold]: {', '.join(pending) or '(none)'}")
        return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_core/test_skill_authoring_cli.py -k candidates -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/cli.py tests/test_core/test_skill_authoring_cli.py
git commit -m "feat(cli): skill-candidates — list ledger patterns + pending skills"
```

---

## Task 6: CLI — `ncdev skill-author` and `ncdev skill-promote`

**Files:**
- Modify: `src/ncdev/cli.py`
- Test: `tests/test_core/test_skill_authoring_cli.py` (append)

- [ ] **Step 1: Append the failing test**

```python
# Append to tests/test_core/test_skill_authoring_cli.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_core/test_skill_authoring_cli.py -k "author_and_promote or promote" -v`
Expected: FAIL — argparse rejects `skill-author` / `skill-promote`

- [ ] **Step 3: Add the subparsers and dispatch**

In `build_parser()`, after the `skill-candidates` subparser, add:

```python
    skill_author = sub.add_parser(
        "skill-author",
        help="Author a new skill for a recurring pattern (spawns a Claude session)",
    )
    skill_author.add_argument("--name", required=True, help="Name for the new skill")
    skill_author.add_argument(
        "--pattern", required=True,
        help="The recurring pattern the skill should address "
             "(copy one from `ncdev skill-candidates`)",
    )

    skill_promote = sub.add_parser(
        "skill-promote",
        help="Promote a pending authored skill into the live ~/.claude/skills library",
    )
    skill_promote.add_argument("--name", required=True, help="Pending skill name to promote")
```

In `main()`, after the `skill-candidates` dispatch block, add:

```python
    if args.command == "skill-author":
        from ncdev.core.skill_author import author_skill
        from ncdev.core.skill_candidate import SkillCandidate

        candidate = SkillCandidate(
            pattern=args.pattern, occurrences=0, example_lessons=[args.pattern],
        )
        dest = author_skill(candidate, skill_name=args.name)
        console.print(f"[green]Authored pending skill at {dest}[/green]")
        console.print(f"Review it, then run: ncdev skill-promote --name {args.name}")
        return 0

    if args.command == "skill-promote":
        from ncdev.core.skill_author import promote_skill

        try:
            dest = promote_skill(args.name)
        except (FileNotFoundError, FileExistsError) as exc:
            console.print(f"[red]{exc}[/red]")
            return 1
        console.print(f"[green]Promoted skill to {dest}[/green]")
        return 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_core/test_skill_authoring_cli.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Confirm no regression, then commit**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS — no regressions.

```bash
git add src/ncdev/cli.py tests/test_core/test_skill_authoring_cli.py
git commit -m "feat(cli): skill-author + skill-promote — gated skill authoring commands"
```

---

## Task 7: End-to-end test — ledger pattern to promoted skill

**Files:**
- Create: `tests/test_core/test_skill_authoring_e2e.py`

- [ ] **Step 1: Write the integration test**

```python
# tests/test_core/test_skill_authoring_e2e.py
"""End-to-end: a recurring ledger pattern -> detected -> authored -> promoted."""

from ncdev.core.capability_ledger import LedgerEntry, append_entry
from ncdev.core.skill_author import author_skill, list_pending_skills, promote_skill
from ncdev.core.skill_candidate import detect_skill_candidates
from ncdev.core.capability_ledger import read_entries


def test_pattern_to_promoted_skill(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.capability_ledger.Path.home", lambda: tmp_path)
    monkeypatch.setattr("ncdev.core.skill_author.Path.home", lambda: tmp_path)

    # 3 cycles record the same recurring lesson.
    for i in range(3):
        append_entry(LedgerEntry(
            timestamp="t", project_name="demo", run_id=f"r{i}", cycle=1,
            provider="openai_codex", model="gpt-5.5",
            capability_lessons=["kept hand-fixing the pagination helper"],
        ))

    # Detect.
    candidates = detect_skill_candidates(read_entries(), threshold=3)
    assert len(candidates) == 1

    # Author (session faked — writes the skill file).
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
```

- [ ] **Step 2: Run the test**

Run: `.venv/bin/python -m pytest tests/test_core/test_skill_authoring_e2e.py -v`
Expected: PASS

- [ ] **Step 3: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: PASS — no regressions.

- [ ] **Step 4: Commit**

```bash
git add tests/test_core/test_skill_authoring_e2e.py
git commit -m "test(capability): end-to-end ledger pattern to promoted skill"
```

---

## Done criteria (Phase 2c)

- `python -m pytest tests/ -q` is green.
- `ncdev skill-candidates` lists ledger patterns recurring `>= threshold` times and any pending authored skills.
- `ncdev skill-author --name X --pattern "..."` spawns a Claude session that uses `superpowers:writing-skills` and leaves an authored skill in `~/.ncdev/skill-candidates/X/`.
- `ncdev skill-promote --name X` copies a pending skill into `~/.claude/skills/X/`, refusing to overwrite an existing skill.
- Nothing reaches `~/.claude/skills/` without an explicit `skill-promote` — the human-review gate holds.

## Deferred / future work

- **Semantic clustering** of similar-but-not-identical lessons (current matching is normalised exact-equality).
- **Steward A/B promotion** — the spec's alternative gate, where the Steward evaluates a candidate skill on one slice before promotion. Human review is sufficient for now.
- **Auto-surfacing candidates** at factory-run end (currently `ncdev skill-candidates` is run on demand).

This completes the dynamic-capability-adoption effort: Phase 1 (adoption), Phase 2a (ledger), Phase 2b (live feedback), Phase 2c (skill authoring).
