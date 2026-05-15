from pathlib import Path
from unittest.mock import MagicMock


from ncdev.factory import (
    FactoryStopReason,
    run_factory,
)
from ncdev.pipeline.product_steward import Disposition, StewardDecision


def test_factory_stops_when_steward_says_continue_at_end_of_queue(monkeypatch, tmp_path):
    """End-of-queue + Steward says continue -> factory exits with status=passed."""
    from ncdev import factory as fac

    # Stub the inner build pass: pretend run_pipeline ran and all features passed.
    fake_state = MagicMock()
    fake_state.status = "passed"
    fake_state.run_id = "test-run"
    fake_state.run_dir = str(tmp_path / "run")
    fake_state.target_path = str(tmp_path / "target")
    fake_state.completed_steps = []
    Path(fake_state.run_dir).mkdir()
    Path(fake_state.target_path).mkdir()

    monkeypatch.setattr(fac, "run_pipeline", lambda **kw: fake_state)
    monkeypatch.setattr(fac, "load_charter_bundle_from_run",
                        lambda run_dir: MagicMock(feature_queue=MagicMock(features=[])))
    monkeypatch.setattr(fac, "run_product_steward",
                        lambda **kw: StewardDecision(
                            disposition=Disposition.CONTINUE,
                            reasoning="all done",
                        ))

    prd = tmp_path / "prd.md"
    prd.write_text("# fake")
    result = run_factory(
        workspace=tmp_path,
        source_path=prd,
        max_cycles=3,
    )
    assert result.stop_reason == FactoryStopReason.STEWARD_CONTINUE_AT_END
    assert result.cycles_run == 1


def test_factory_exhausts_budget(monkeypatch, tmp_path):
    """If the Steward keeps asking for repairs, the factory stops at max_cycles."""
    from ncdev import factory as fac

    fake_state = MagicMock()
    fake_state.status = "failed"
    fake_state.run_id = "test-run"
    fake_state.run_dir = str(tmp_path / "run")
    fake_state.target_path = str(tmp_path / "target")
    Path(fake_state.run_dir).mkdir()
    Path(fake_state.target_path).mkdir()

    monkeypatch.setattr(fac, "run_pipeline", lambda **kw: fake_state)
    monkeypatch.setattr(fac, "load_charter_bundle_from_run",
                        lambda run_dir: MagicMock(feature_queue=MagicMock(features=[])))
    monkeypatch.setattr(fac, "run_product_steward",
                        lambda **kw: StewardDecision(
                            disposition=Disposition.REPAIR_CURRENT_SLICE,
                            reasoning="still broken",
                            target_feature_ids=["f01"],
                        ))

    prd = tmp_path / "prd.md"
    prd.write_text("# fake")
    result = run_factory(
        workspace=tmp_path,
        source_path=prd,
        max_cycles=3,
    )
    assert result.stop_reason == FactoryStopReason.BUDGET_EXHAUSTED
    assert result.cycles_run == 3


def test_factory_stops_on_unrecoverable(monkeypatch, tmp_path):
    from ncdev import factory as fac

    fake_state = MagicMock()
    fake_state.status = "failed"
    fake_state.run_id = "test-run"
    fake_state.run_dir = str(tmp_path / "run")
    fake_state.target_path = str(tmp_path / "target")
    Path(fake_state.run_dir).mkdir()
    Path(fake_state.target_path).mkdir()

    monkeypatch.setattr(fac, "run_pipeline", lambda **kw: fake_state)
    monkeypatch.setattr(fac, "load_charter_bundle_from_run",
                        lambda run_dir: MagicMock(feature_queue=MagicMock(features=[])))
    monkeypatch.setattr(fac, "run_product_steward",
                        lambda **kw: StewardDecision(
                            disposition=Disposition.STOP_AS_UNRECOVERABLE,
                            reasoning="unrecoverable: missing infra",
                        ))

    prd = tmp_path / "prd.md"
    prd.write_text("# fake")
    result = run_factory(
        workspace=tmp_path,
        source_path=prd,
        max_cycles=5,
    )
    assert result.stop_reason == FactoryStopReason.STEWARD_UNRECOVERABLE
    assert result.cycles_run == 1
