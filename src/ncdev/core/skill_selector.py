"""Pick skills per work type from the probed inventory and render a
steering block. Replaces a hand-written, never-updated skill list with
a selection driven by what is actually installed.
"""

from __future__ import annotations

# Preferred skills per work type, in priority order. Only skills also
# present in the probed inventory are selected — security: NC Dev steers
# toward this vetted set, never toward arbitrary on-disk skills.
_WORK_TYPE_SKILLS: dict[str, list[str]] = {
    "greenfield_ui": [
        "writing-plans", "test-driven-development", "frontend-design",
        "goal", "verification-before-completion",
    ],
    "greenfield_backend": [
        "writing-plans", "test-driven-development",
        "goal", "verification-before-completion",
    ],
    "brownfield": [
        "writing-plans", "test-driven-development",
        "systematic-debugging", "verification-before-completion",
    ],
    "bugfix": [
        "systematic-debugging", "test-driven-development",
        "verification-before-completion",
    ],
}


def work_type_for(*, is_brownfield: bool, touches_frontend: bool) -> str:
    """Classify a feature build into a work type.

    Bugfix sessions pass the literal "bugfix" directly and do not call
    this — see Task 12.
    """
    if is_brownfield:
        return "brownfield"
    return "greenfield_ui" if touches_frontend else "greenfield_backend"


def select_skills(work_type: str, inventory: list[str]) -> list[str]:
    """Return the preferred skills for `work_type` that are installed."""
    preferred = _WORK_TYPE_SKILLS.get(work_type, _WORK_TYPE_SKILLS["brownfield"])
    installed = set(inventory)
    return [s for s in preferred if s in installed]


def render_skill_block(skills: list[str]) -> str:
    """Render a system-prompt block steering the session toward `skills`."""
    if not skills:
        return ""
    lines = [
        "## Available skills for this session",
        "",
        "These skills are installed and relevant to this work. Invoke "
        "the ones that apply:",
        "",
    ]
    lines += [f"- `{name}`" for name in skills]
    return "\n".join(lines)
