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
