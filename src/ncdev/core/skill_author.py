"""Author new Claude skills from ledger patterns, behind a human gate.

Authored skills land in a pending directory (~/.ncdev/skill-candidates/)
and only reach the live library (~/.claude/skills/) via an explicit
promote. Authoring spawns a Claude session — it is never auto-run.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ncdev.core.skill_candidate import SkillCandidate


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
