"""Factory loop integration test.

Drives ``run_factory`` end-to-end with mocked AI sessions and
mocked pipeline. Verifies that:

- a CONTINUE decision at cycle 1 stops the loop with success
- a REPAIR decision triggers a second cycle
- two REPAIRs followed by CONTINUE finishes successfully in cycle 3
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from ncdev import factory as fac
from ncdev.factory import FactoryStopReason, run_factory
from ncdev.pipeline.product_steward import Disposition, StewardDecision


def _make_pipeline_state(tmp_path: Path, status: str = "passed"):
    state = MagicMock()
    state.status = status
    state.run_id = "test"
    state.run_dir = str(tmp_path / "run")
    state.target_path = str(tmp_path / "target")
    state.completed_steps = []
    Path(state.run_dir).mkdir(exist_ok=True)
    Path(state.target_path).mkdir(exist_ok=True)
    return state


def test_three_cycle_repair_then_continue(monkeypatch, tmp_path):
    """REPAIR, REPAIR, CONTINUE -> success in 3 cycles."""
    pipeline_states = [
        _make_pipeline_state(tmp_path, "partial"),
        _make_pipeline_state(tmp_path, "partial"),
        _make_pipeline_state(tmp_path, "passed"),
    ]
    decisions = iter([
        StewardDecision(
            disposition=Disposition.REPAIR_CURRENT_SLICE,
            reasoning="r1",
            target_feature_ids=["f01"],
        ),
        StewardDecision(
            disposition=Disposition.REPAIR_CURRENT_SLICE,
            reasoning="r2",
            target_feature_ids=["f02"],
        ),
        StewardDecision(
            disposition=Disposition.CONTINUE,
            reasoning="done",
        ),
    ])
    pipeline_iter = iter(pipeline_states)

    monkeypatch.setattr(fac, "run_pipeline", lambda **kw: next(pipeline_iter))
    monkeypatch.setattr(
        fac,
        "load_charter_bundle_from_run",
        lambda run_dir: MagicMock(feature_queue=MagicMock(features=[])),
    )
    monkeypatch.setattr(fac, "run_product_steward", lambda **kw: next(decisions))

    prd = tmp_path / "prd.md"
    prd.write_text("# fake")
    result = run_factory(
        workspace=tmp_path,
        source_path=prd,
        max_cycles=5,
    )
    assert result.cycles_run == 3
    assert result.stop_reason == FactoryStopReason.STEWARD_CONTINUE_AT_END
    assert [d.disposition for d in result.decisions] == [
        Disposition.REPAIR_CURRENT_SLICE,
        Disposition.REPAIR_CURRENT_SLICE,
        Disposition.CONTINUE,
    ]


def test_insert_features_disposition_mutates_then_continues(monkeypatch, tmp_path):
    """INSERT_FEATURES mutates the charter and re-enters the factory loop."""
    pipeline_states = iter([
        _make_pipeline_state(tmp_path, "partial"),
        _make_pipeline_state(tmp_path, "passed"),
    ])
    decisions = iter([
        StewardDecision(
            disposition=Disposition.INSERT_FEATURES,
            reasoning="missing settings page",
        ),
        StewardDecision(
            disposition=Disposition.CONTINUE,
            reasoning="done",
        ),
    ])
    insert_features = MagicMock(return_value=0)

    monkeypatch.setattr(fac, "run_pipeline", lambda **kw: next(pipeline_states))
    monkeypatch.setattr(
        fac,
        "load_charter_bundle_from_run",
        lambda run_dir: MagicMock(feature_queue=MagicMock(features=[])),
    )
    monkeypatch.setattr(fac, "run_product_steward", lambda **kw: next(decisions))
    monkeypatch.setattr(fac, "insert_features", insert_features)

    prd = tmp_path / "prd.md"
    prd.write_text("# fake")
    result = run_factory(workspace=tmp_path, source_path=prd, max_cycles=5)
    insert_features.assert_called_once()
    assert result.stop_reason == FactoryStopReason.STEWARD_CONTINUE_AT_END
    assert result.cycles_run == 2
