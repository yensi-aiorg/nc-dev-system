"""End-to-end: a recorded cycle feeds back into the next resolution."""

from ncdev.core.capability_ledger import read_entries, record_cycle
from ncdev.core.capability_policy import resolve_model
from ncdev.core.capability_probe import probe_claude
from ncdev.pipeline.metrics import RunMetrics
from ncdev.pipeline.models import StepResult, StepStatus


def _claude_snapshot(monkeypatch):
    monkeypatch.setattr(
        "ncdev.core.capability_probe.shutil.which", lambda _: "/usr/bin/claude"
    )
    monkeypatch.setattr("ncdev.core.capability_probe._run_version", lambda _b: "1.2.3")
    return probe_claude()


def test_bad_cycles_demote_the_model_on_next_resolve(monkeypatch, tmp_path):
    monkeypatch.setattr("ncdev.core.capability_ledger.Path.home", lambda: tmp_path)
    snap = _claude_snapshot(monkeypatch)

    # Record 4 bad cycles for the claude builder ("opus", low success).
    for i in range(4):
        metrics = RunMetrics(
            run_id=f"r{i}",
            project_name="demo",
            total_features=4,
            passed_features=1,
            first_pass_success_rate=0.2,
            builder_primary="claude",
            builder_model="opus",
        )
        steps = [
            StepResult(
                feature_id="f1",
                status=StepStatus.FAILED,
                resolved_provider="anthropic_claude_code",
                resolved_model="opus",
            )
        ]
        record_cycle(
            metrics=metrics,
            steps=steps,
            cycle=i + 1,
            steward_disposition="repair_current_slice",
            capability_lessons=[],
        )

    ledger = read_entries()
    assert len(ledger) == 4

    # Phase-1 resolution (no ledger) still yields the default alias.
    assert resolve_model("anthropic_claude_code", "auto", snap) == "opus"
    # Ledger-aware resolution demotes after the bad track record.
    assert (
        resolve_model("anthropic_claude_code", "auto", snap, ledger_entries=ledger)
        == "sonnet"
    )
