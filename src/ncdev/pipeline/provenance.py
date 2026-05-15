"""Engine-side feature provenance.

Records which files each feature session touched, persisted as
``<run_dir>/provenance.jsonl``. Downstream verifiers and the Steward
query this instead of demanding string markers in the source files.
"""
from __future__ import annotations

import json
from pathlib import Path

from ncdev.pipeline.models import ProvenanceRecord

_FILENAME = "provenance.jsonl"


def append_provenance(run_dir: Path, record: ProvenanceRecord) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / _FILENAME
    with path.open("a", encoding="utf-8") as f:
        f.write(record.model_dump_json() + "\n")


def load_provenance(run_dir: Path) -> list[ProvenanceRecord]:
    path = run_dir / _FILENAME
    if not path.exists():
        return []
    out: list[ProvenanceRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(ProvenanceRecord.model_validate_json(line))
    return out


def files_for_feature(run_dir: Path, feature_id: str) -> set[str]:
    """Return the union of all files touched by any session for this feature."""
    files: set[str] = set()
    for rec in load_provenance(run_dir):
        if rec.feature_id != feature_id:
            continue
        files.update(rec.files_created)
        files.update(rec.files_modified)
    return files
