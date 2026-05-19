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


from ncdev.pipeline.models import StepResult, StepStatus


def test_step_result_has_capability_fields_with_safe_defaults():
    step = StepResult(feature_id="f1", status=StepStatus.PASSED)
    assert step.resolved_provider == ""
    assert step.resolved_model == ""
    assert step.skills_steered == []


def test_step_result_accepts_capability_fields():
    step = StepResult(
        feature_id="f1", status=StepStatus.PASSED,
        resolved_provider="openai_codex", resolved_model="gpt-5.5",
        skills_steered=["systematic-debugging"],
    )
    assert step.resolved_model == "gpt-5.5"


from ncdev.core.capability_ledger import record_cycle
from ncdev.pipeline.metrics import RunMetrics


def test_record_cycle_writes_entry_from_metrics(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.capability_ledger.Path.home", lambda: tmp_path)
    metrics = RunMetrics(
        run_id="r1", project_name="demo", total_features=4,
        passed_features=3, first_pass_success_rate=0.75, repair_rate=0.25,
        builder_primary="codex", builder_model="gpt-5.5",
    )
    steps = [
        StepResult(
            feature_id="f1", status=StepStatus.PASSED,
            resolved_provider="openai_codex", resolved_model="gpt-5.5",
            skills_steered=["systematic-debugging"],
        ),
    ]
    record_cycle(
        metrics=metrics, steps=steps, cycle=1,
        steward_disposition="continue",
        capability_lessons=["codex handled boilerplate well"],
    )
    entries = read_entries()
    assert len(entries) == 1
    e = entries[0]
    assert e.provider == "openai_codex"
    assert e.model == "gpt-5.5"
    assert e.cycle == 1
    assert e.first_pass_success_rate == 0.75
    assert e.skills_steered == ["systematic-debugging"]
    assert e.capability_lessons == ["codex handled boilerplate well"]


def test_record_cycle_no_steps_uses_metrics_builder(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.capability_ledger.Path.home", lambda: tmp_path)
    metrics = RunMetrics(run_id="r1", builder_primary="codex", builder_model="gpt-5.5")
    record_cycle(metrics=metrics, steps=[], cycle=1, steward_disposition="continue",
                 capability_lessons=[])
    e = read_entries()[0]
    assert e.provider == "openai_codex"
    assert e.model == "gpt-5.5"
    assert e.broken_rate == 0.0
