from pathlib import Path

from ncdev.pipeline.models import ProvenanceRecord
from ncdev.pipeline.provenance import (
    append_provenance,
    load_provenance,
    files_for_feature,
)


def test_append_and_load_roundtrip(tmp_path: Path) -> None:
    rec = ProvenanceRecord(
        feature_id="f02-auth",
        commit_sha="abcdef1234567890",
        files_created=["backend/app/auth.py"],
        files_modified=["backend/app/main.py"],
    )
    append_provenance(tmp_path, rec)
    loaded = load_provenance(tmp_path)
    assert len(loaded) == 1
    assert loaded[0].feature_id == "f02-auth"
    assert "backend/app/auth.py" in loaded[0].files_created


def test_files_for_feature_returns_union(tmp_path: Path) -> None:
    append_provenance(tmp_path, ProvenanceRecord(
        feature_id="f02-auth",
        commit_sha="aaa",
        files_created=["a.py"],
        files_modified=["b.py"],
    ))
    append_provenance(tmp_path, ProvenanceRecord(
        feature_id="f02-auth",
        commit_sha="bbb",
        files_created=["c.py"],
        files_modified=[],
    ))
    assert files_for_feature(tmp_path, "f02-auth") == {"a.py", "b.py", "c.py"}


def test_files_for_feature_unknown_returns_empty(tmp_path: Path) -> None:
    assert files_for_feature(tmp_path, "f99-nope") == set()
