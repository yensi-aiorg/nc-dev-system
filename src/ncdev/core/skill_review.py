"""Lightweight Steward review of an authored skill candidate.

Spawns a Claude session that reads a candidate SKILL.md and returns a
structured pass/fail verdict. Advisory - it informs the human promote
gate, it does not replace it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class SkillReview(BaseModel):
    """A Steward verdict on a candidate skill."""

    approved: bool
    reasoning: str = ""


def _build_review_prompt(skill_md: str) -> str:
    return (
        "You are reviewing a candidate Claude skill before it is promoted "
        "into the live skill library. Here is its SKILL.md:\n\n"
        f"---\n{skill_md}\n---\n\n"
        "Judge whether it is a sound, well-scoped, clearly-written skill "
        "that would genuinely help an agent. Reply with a SINGLE JSON "
        'object, no prose around it: {"approved": <true|false>, '
        '"reasoning": "<one or two sentences>"}'
    )


def review_skill_candidate(
    skill_dir: Path,
    *,
    run_session: Callable[..., Any] | None = None,
) -> SkillReview:
    """Spawn a session that reviews the SKILL.md in `skill_dir`.

    Raises FileNotFoundError if there is no SKILL.md. `run_session`
    defaults to claude_session.run_claude_session; tests inject a fake.
    """
    skill_md_path = skill_dir / "SKILL.md"
    if not skill_md_path.is_file():
        raise FileNotFoundError(f"No SKILL.md in {skill_dir}")
    if run_session is None:
        from ncdev.claude_session import run_claude_session

        run_session = run_claude_session

    prompt = _build_review_prompt(skill_md_path.read_text(encoding="utf-8"))
    result = run_session(prompt, cwd=skill_dir)
    text = getattr(result, "final_text", "") or ""
    cleaned = _FENCE_RE.sub("", text.strip()).strip()
    try:
        data = json.loads(cleaned)
        return SkillReview(approved=bool(data["approved"]),
                           reasoning=str(data.get("reasoning", "")))
    except (ValueError, KeyError, TypeError):
        return SkillReview(
            approved=False,
            reasoning="Could not parse a verdict from the review session.",
        )
