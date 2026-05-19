from ncdev.core.capability_ledger import (
    LedgerEntry,
    append_entry,
    ledger_path,
    read_entries,
)


def _entry(**over):
    base = dict(
        timestamp="2026-05-19T00:00:00+00:00",
        project_name="demo", run_id="r1", cycle=1,
        provider="openai_codex", model="gpt-5.5",
        skills_steered=["systematic-debugging"], extra_args=[],
        features_total=4, features_passed=3,
        first_pass_success_rate=0.75, repair_rate=0.25, broken_rate=0.0,
        total_cost_usd=1.5, steward_disposition="continue",
        capability_lessons=[],
    )
    base.update(over)
    return LedgerEntry(**base)


def test_ledger_path_is_under_home_ncdev(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.capability_ledger.Path.home", lambda: tmp_path)
    p = ledger_path()
    assert p == tmp_path / ".ncdev" / "capability-ledger.jsonl"


def test_append_then_read_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.capability_ledger.Path.home", lambda: tmp_path)
    append_entry(_entry(run_id="r1"))
    append_entry(_entry(run_id="r2"))
    entries = read_entries()
    assert [e.run_id for e in entries] == ["r1", "r2"]


def test_read_entries_missing_ledger_returns_empty(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.capability_ledger.Path.home", lambda: tmp_path)
    assert read_entries() == []


def test_read_entries_skips_corrupt_lines(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.capability_ledger.Path.home", lambda: tmp_path)
    append_entry(_entry(run_id="good"))
    ledger_path().write_text(
        ledger_path().read_text(encoding="utf-8") + "{bad json\n", encoding="utf-8"
    )
    entries = read_entries()
    assert [e.run_id for e in entries] == ["good"]
