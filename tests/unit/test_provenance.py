from pathlib import Path
from unittest.mock import patch

from ncdev.pipeline.models import (
    CharterBundle,
    FeatureQueueDoc,
    FeatureStep,
    ProvenanceRecord,
    StepResult,
    StepStatus,
    TargetProjectContract,
    VerificationContract,
)
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


def test_engine_appends_provenance_after_each_feature(tmp_path, monkeypatch):
    """run_pipeline should write a provenance record per executed feature."""
    from ncdev.pipeline import engine as engine_mod

    bundle = CharterBundle(
        contract=TargetProjectContract(
            project_name="p", project_type="library",
            language="python", database="none", auth="none",
            ports={}, design_archetype="Developer Brutalism",
            design_system_source="claude_generated", uses_citex=False,
            is_brownfield=False, existing_repo_path="",
        ),
        verification=VerificationContract(
            backend_test_command="true",
            frontend_test_command="",
            required_files=[],
            required_screenshots=[],
            prohibited_patterns=[],
            backend_health_url="",
            start_command="",
            stop_command="",
            minimum_test_count=0,
            assets_manifest_required=False,
        ),
        feature_queue=FeatureQueueDoc(
            project_name="p",
            features=[FeatureStep(
                feature_id="f01-test", title="t", description="d",
                acceptance_criteria=[], priority=1,
            )],
        ),
    )

    def fake_generate_charter(**kwargs):
        from ncdev.claude_session import ClaudeSessionResult
        return bundle, ClaudeSessionResult(success=True, final_text="", exit_code=0)

    def fake_execute(feature, target_path, run_dir, **kwargs):
        return StepResult(
            feature_id=feature.feature_id,
            status=StepStatus.PASSED,
            commit_sha="aaa",
            files_created=["src/x.py"],
            files_modified=["src/y.py"],
            build_duration_seconds=1.0,
        )

    monkeypatch.setattr(engine_mod, "generate_charter", fake_generate_charter)
    monkeypatch.setattr(engine_mod, "execute_feature_claude_driven", fake_execute)
    monkeypatch.setattr(engine_mod, "run_design_phase",
                        lambda **kw: type("D", (), {"skipped": True, "hard_failed": False, "design_doc": None})())

    workspace = tmp_path / "ws"
    workspace.mkdir()
    source = workspace / "prd.md"
    source.write_text("# fake prd")

    state = engine_mod.run_pipeline(
        workspace=workspace,
        source_path=source,
        target_repo_path=workspace,
        skip_integration_gate=True,
    )

    from ncdev.pipeline.provenance import files_for_feature
    recorded = files_for_feature(Path(state.run_dir), "f01-test")
    assert recorded == {"src/x.py", "src/y.py"}
