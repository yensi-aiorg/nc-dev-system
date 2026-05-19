"""Author new Claude skills from ledger patterns, behind a human gate.

Authored skills land in a pending directory (~/.ncdev/skill-candidates/)
and only reach the live library (~/.claude/skills/) via an explicit
promote. Authoring spawns a Claude session — it is never auto-run.
"""

from __future__ import annotations

import shutil
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
