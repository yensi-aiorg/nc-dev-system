"""Detect recurring patterns in the capability ledger.

A capability lesson that the Steward records across many cycles is a
signal that NC Dev keeps hitting the same gap — a candidate for a new
skill. Matching clusters normalised lesson text by similarity so
near-identical phrasings count together.
"""

from __future__ import annotations

from difflib import SequenceMatcher
import re

from pydantic import BaseModel, Field

from ncdev.core.capability_ledger import LedgerEntry

_WS = re.compile(r"\s+")
_SIMILARITY_THRESHOLD = 0.8


class SkillCandidate(BaseModel):
    """A recurring ledger pattern worth authoring a skill for."""

    pattern: str                                    # normalised lesson text
    occurrences: int
    example_lessons: list[str] = Field(default_factory=list)  # raw lesson strings
    projects: list[str] = Field(default_factory=list)         # distinct projects


def _normalise(lesson: str) -> str:
    """Lowercase + collapse whitespace so near-identical lessons match."""
    return _WS.sub(" ", lesson.strip().lower())


def _similar(a: str, b: str) -> bool:
    return SequenceMatcher(None, a, b).ratio() >= _SIMILARITY_THRESHOLD


def detect_skill_candidates(
    entries: list[LedgerEntry],
    *,
    threshold: int = 3,
) -> list[SkillCandidate]:
    """Return ledger patterns recurring `>= threshold` times.

    Lessons are clustered by text similarity (difflib ratio >=
    _SIMILARITY_THRESHOLD), so near-identical phrasings count together.
    Each cluster keeps its first-seen normalised lesson as the pattern.
    """
    clusters: list[dict] = []  # {key, examples: list[str], projects: set[str]}
    for entry in entries:
        for lesson in entry.capability_lessons:
            key = _normalise(lesson)
            if not key:
                continue
            match = next((c for c in clusters if _similar(c["key"], key)), None)
            if match is None:
                clusters.append(
                    {"key": key, "examples": [lesson], "projects": {entry.project_name}}
                )
            else:
                match["examples"].append(lesson)
                match["projects"].add(entry.project_name)

    candidates = [
        SkillCandidate(
            pattern=c["key"],
            occurrences=len(c["examples"]),
            example_lessons=c["examples"],
            projects=sorted(c["projects"]),
        )
        for c in clusters
        if len(c["examples"]) >= threshold
    ]
    candidates.sort(key=lambda c: c.occurrences, reverse=True)
    return candidates
