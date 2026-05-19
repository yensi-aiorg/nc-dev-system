"""Cross-project capability ledger — NC Dev's memory.

One JSONL entry per factory cycle at ~/.ncdev/capability-ledger.jsonl,
combining objective metrics with the Steward's structured lessons.
Append-only; corrupt lines are skipped on read, never fatal.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from ncdev.pipeline.metrics import RunMetrics
from ncdev.pipeline.models import StepResult, StepStatus


class LedgerEntry(BaseModel):
    """One factory cycle's capability record."""

    timestamp: str
    project_name: str
    run_id: str
    cycle: int
    # Capability used (the builder).
    provider: str
    model: str
    skills_steered: list[str] = Field(default_factory=list)
    extra_args: list[str] = Field(default_factory=list)
    # Objective metrics.
    features_total: int = 0
    features_passed: int = 0
    first_pass_success_rate: float = 0.0
    repair_rate: float = 0.0
    broken_rate: float = 0.0
    total_cost_usd: float = 0.0
    # Steward narrative.
    steward_disposition: str = ""
    capability_lessons: list[str] = Field(default_factory=list)


def ledger_path() -> Path:
    """Absolute path to the cross-project ledger file."""
    return Path.home() / ".ncdev" / "capability-ledger.jsonl"


def append_entry(entry: LedgerEntry) -> None:
    """Append one entry as a JSONL line. Creates the ledger if absent."""
    path = ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(entry.model_dump_json() + "\n")


def read_entries() -> list[LedgerEntry]:
    """Read all valid entries in append order. Missing ledger -> []."""
    path = ledger_path()
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []
    entries: list[LedgerEntry] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(LedgerEntry.model_validate_json(line))
        except ValueError:
            continue  # skip corrupt line, never fatal
    return entries


def recent_lessons(
    *,
    project_name: str | None = None,
    limit: int = 20,
) -> list[str]:
    """Flattened `capability_lessons` from the most recent ledger entries.

    Entries are filtered to `project_name` when given, then the last
    `limit` entries are taken and their lessons concatenated in order.
    """
    entries = read_entries()
    if project_name:
        entries = [e for e in entries if e.project_name == project_name]
    lessons: list[str] = []
    for entry in entries[-limit:]:
        lessons.extend(entry.capability_lessons)
    return lessons


# Maps RunMetrics.builder_primary short names to provider registry keys.
_BUILDER_PROVIDER: dict[str, str] = {
    "codex": "openai_codex",
    "claude": "anthropic_claude_code",
}


def record_cycle(
    *,
    metrics: RunMetrics,
    steps: list[StepResult],
    cycle: int,
    steward_disposition: str,
    capability_lessons: list[str],
) -> LedgerEntry:
    """Build one LedgerEntry from a cycle's metrics + steps and append it.

    The builder capability is taken from the steps' recorded resolution
    when available, else from RunMetrics.builder_*.
    """
    provider = _BUILDER_PROVIDER.get(metrics.builder_primary, "openai_codex")
    model = metrics.builder_model
    skills_steered: list[str] = []
    for step in steps:
        if step.resolved_provider:
            provider = step.resolved_provider
        if step.resolved_model and step.resolved_model != "auto":
            model = step.resolved_model
        for skill in step.skills_steered:
            if skill not in skills_steered:
                skills_steered.append(skill)

    total = metrics.total_features or len(steps)
    broken = sum(1 for s in steps if s.status == StepStatus.FAILED)
    broken_rate = (broken / total) if total else 0.0

    entry = LedgerEntry(
        timestamp=datetime.now(timezone.utc).isoformat(),
        project_name=metrics.project_name,
        run_id=metrics.run_id,
        cycle=cycle,
        provider=provider,
        model=model,
        skills_steered=skills_steered,
        features_total=total,
        features_passed=metrics.passed_features,
        first_pass_success_rate=metrics.first_pass_success_rate,
        repair_rate=metrics.repair_rate,
        broken_rate=broken_rate,
        total_cost_usd=0.0,
        steward_disposition=steward_disposition,
        capability_lessons=list(capability_lessons),
    )
    append_entry(entry)
    return entry
