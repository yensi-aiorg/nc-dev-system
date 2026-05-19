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
