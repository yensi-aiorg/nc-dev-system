"""Cross-project capability ledger — NC Dev's memory.

One JSONL entry per factory cycle at ~/.ncdev/capability-ledger.jsonl,
combining objective metrics with the Steward's structured lessons.
Append-only; corrupt lines are skipped on read, never fatal.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


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
