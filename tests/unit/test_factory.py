from pathlib import Path
from unittest.mock import MagicMock


from ncdev.factory import (
    FactoryStopReason,
    run_factory,
)
from ncdev.pipeline.models import FeatureAcceptance, FeatureStep
from ncdev.pipeline.product_steward import (
    Disposition,
    FeatureAmendment,
    StewardDecision,
)


def _make_pipeline_state(tmp_path: Path, cycle: int, status: str = "passed"):
    state = MagicMock()
    state.status = status
    state.run_id = f"test-run-{cycle}"
    state.run_dir = str(tmp_path / f"run-{cycle}")
    state.target_path = str(tmp_path / "target")
    state.completed_steps = []
    Path(state.run_dir).mkdir()
    Path(state.target_path).mkdir(exist_ok=True)
    return state


def _new_feature() -> FeatureStep:
    return FeatureStep(
        feature_id="f02-settings",
        title="Settings",
        description="Add settings",
        acceptance_criteria=["Settings work"],
        acceptance=FeatureAcceptance(
            required_files=["src/settings.py"],
            required_tests=["tests/test_settings.py"],
        ),
    )


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


def test_factory_inserts_features_then_continues(monkeypatch, tmp_path):
    from ncdev import factory as fac

    pipeline_states = iter([
        _make_pipeline_state(tmp_path, 1, "passed"),
        _make_pipeline_state(tmp_path, 2, "passed"),
    ])
    new_feature = _new_feature()
    decisions = iter([
        StewardDecision(
            disposition=Disposition.INSERT_FEATURES,
            reasoning="Missing settings",
            new_features=[new_feature],
        ),
        StewardDecision(
            disposition=Disposition.CONTINUE,
            reasoning="done",
        ),
    ])
    insert_features = MagicMock(return_value=1)

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
    result = run_factory(workspace=tmp_path, source_path=prd, max_cycles=3)

    insert_features.assert_called_once_with(
        tmp_path / "run-1" / "outputs",
        [new_feature],
    )
    assert result.stop_reason == FactoryStopReason.STEWARD_CONTINUE_AT_END
    assert result.cycles_run == 2


def test_factory_applies_amendments_then_continues(monkeypatch, tmp_path):
    from ncdev import factory as fac

    pipeline_states = iter([
        _make_pipeline_state(tmp_path, 1, "passed"),
        _make_pipeline_state(tmp_path, 2, "passed"),
    ])
    amendments = [
        FeatureAmendment(
            feature_id="f01-scaffold",
            field="acceptance.required_files",
            new_value=["src/revised.py"],
            reason="Tighter target",
        ),
    ]
    decisions = iter([
        StewardDecision(
            disposition=Disposition.REWRITE_ACCEPTANCE,
            reasoning="Acceptance needs tightening",
            amendments=amendments,
        ),
        StewardDecision(
            disposition=Disposition.CONTINUE,
            reasoning="done",
        ),
    ])
    apply_amendments = MagicMock(return_value=1)

    monkeypatch.setattr(fac, "run_pipeline", lambda **kw: next(pipeline_states))
    monkeypatch.setattr(
        fac,
        "load_charter_bundle_from_run",
        lambda run_dir: MagicMock(feature_queue=MagicMock(features=[])),
    )
    monkeypatch.setattr(fac, "run_product_steward", lambda **kw: next(decisions))
    monkeypatch.setattr(fac, "apply_amendments", apply_amendments)

    prd = tmp_path / "prd.md"
    prd.write_text("# fake")
    result = run_factory(workspace=tmp_path, source_path=prd, max_cycles=3)

    apply_amendments.assert_called_once_with(
        tmp_path / "run-1" / "outputs",
        amendments,
    )
    assert result.stop_reason == FactoryStopReason.STEWARD_CONTINUE_AT_END
    assert result.cycles_run == 2


def test_factory_reruns_charter_then_continues(monkeypatch, tmp_path):
    from ncdev import factory as fac

    pipeline_states = iter([
        _make_pipeline_state(tmp_path, 1, "passed"),
        _make_pipeline_state(tmp_path, 2, "passed"),
    ])
    decisions = iter([
        StewardDecision(
            disposition=Disposition.RERUN_CHARTER,
            reasoning="Planning is off",
        ),
        StewardDecision(
            disposition=Disposition.CONTINUE,
            reasoning="done",
        ),
    ])
    archive_and_clear_charter = MagicMock(
        return_value=tmp_path / "run-1" / "outputs" / ".attempt-1",
    )
    generate_charter = MagicMock(return_value=(MagicMock(), MagicMock()))

    monkeypatch.setattr(fac, "run_pipeline", lambda **kw: next(pipeline_states))
    monkeypatch.setattr(
        fac,
        "load_charter_bundle_from_run",
        lambda run_dir: MagicMock(feature_queue=MagicMock(features=[])),
    )
    monkeypatch.setattr(fac, "run_product_steward", lambda **kw: next(decisions))
    monkeypatch.setattr(fac, "archive_and_clear_charter", archive_and_clear_charter)
    monkeypatch.setattr(fac, "generate_charter", generate_charter)

    prd = tmp_path / "prd.md"
    prd.write_text("# fake")
    result = run_factory(
        workspace=tmp_path,
        source_path=prd,
        target_repo_path=tmp_path / "target",
        builder_model="test-model",
        max_budget_usd=12.5,
        max_cycles=3,
    )

    archive_and_clear_charter.assert_called_once_with(tmp_path / "run-1" / "outputs")
    generate_charter.assert_called_once_with(
        prd_path=prd,
        output_dir=tmp_path / "run-1" / "outputs",
        target_repo=tmp_path / "target",
        model="test-model",
        max_budget_usd=12.5,
        log_path=tmp_path / "run-1" / "logs" / "charter-rerun-cycle-1.jsonl",
        config=None,
    )
    assert result.stop_reason == FactoryStopReason.STEWARD_CONTINUE_AT_END
    assert result.cycles_run == 2


def test_factory_probe_test_craftr_passes_debt_to_steward(monkeypatch, tmp_path):
    """When probe_test_craftr=True, the factory calls TC, classifies, and
    hands ProductDebt to the Steward."""
    from ncdev import factory as fac
    from ncdev.pipeline.product_debt import (
        DebtType,
        ProductDebt,
        SuggestedDisposition,
    )

    fake_state = MagicMock()
    fake_state.status = "passed"
    fake_state.run_id = "test"
    fake_state.run_dir = str(tmp_path / "run")
    fake_state.target_path = str(tmp_path / "target")
    fake_state.completed_steps = []
    Path(fake_state.run_dir).mkdir()
    Path(fake_state.target_path).mkdir()

    captured_steward_kwargs = {}

    def fake_steward(**kwargs):
        captured_steward_kwargs.update(kwargs)
        return StewardDecision(disposition=Disposition.CONTINUE, reasoning="ok")

    fake_debt = [
        ProductDebt(
            debt_id="d001-test",
            debt_type=DebtType.VISUAL_POLISH,
            title="t",
            description="d",
            suggested_disposition=SuggestedDisposition.DIRECT_FIX,
        )
    ]
    monkeypatch.setattr(fac, "run_pipeline", lambda **kw: fake_state)
    monkeypatch.setattr(
        fac,
        "load_charter_bundle_from_run",
        lambda run_dir: MagicMock(feature_queue=MagicMock(features=[])),
    )
    monkeypatch.setattr(fac, "run_product_steward", fake_steward)
    monkeypatch.setattr(
        fac,
        "_probe_test_craftr",
        lambda **kw: ("tc-run-1", [{"id": "i1"}], {"core_flow": 80}),
    )
    monkeypatch.setattr(
        fac,
        "classify_issues_to_debt",
        lambda issues, known_routes=None: fake_debt,
    )

    prd = tmp_path / "prd.md"
    prd.write_text("# fake")
    result = run_factory(
        workspace=tmp_path,
        source_path=prd,
        max_cycles=1,
        probe_test_craftr=True,
    )
    assert "tc-run-1" in result.test_craftr_runs
    assert result.last_product_debt == fake_debt
    assert captured_steward_kwargs["product_debt"] == fake_debt
    assert captured_steward_kwargs["last_test_craftr_scores"] == {"core_flow": 80}


def test_factory_probe_disabled_default(monkeypatch, tmp_path):
    """Without probe_test_craftr=True, no TC call is made and Steward gets no debt."""
    from ncdev import factory as fac

    fake_state = MagicMock()
    fake_state.status = "passed"
    fake_state.run_id = "test"
    fake_state.run_dir = str(tmp_path / "run")
    fake_state.target_path = str(tmp_path / "target")
    fake_state.completed_steps = []
    Path(fake_state.run_dir).mkdir()
    Path(fake_state.target_path).mkdir()

    probe_called = []
    captured = {}

    def fake_steward(**kwargs):
        captured.update(kwargs)
        return StewardDecision(disposition=Disposition.CONTINUE, reasoning="ok")

    monkeypatch.setattr(fac, "run_pipeline", lambda **kw: fake_state)
    monkeypatch.setattr(
        fac,
        "load_charter_bundle_from_run",
        lambda run_dir: MagicMock(feature_queue=MagicMock(features=[])),
    )
    monkeypatch.setattr(fac, "run_product_steward", fake_steward)
    monkeypatch.setattr(
        fac,
        "_probe_test_craftr",
        lambda **kw: probe_called.append(1) or ("x", [], {}),
    )

    prd = tmp_path / "prd.md"
    prd.write_text("# fake")
    result = run_factory(workspace=tmp_path, source_path=prd, max_cycles=1)
    assert probe_called == []
    assert result.test_craftr_runs == []
    assert captured.get("product_debt") in (None, [])
