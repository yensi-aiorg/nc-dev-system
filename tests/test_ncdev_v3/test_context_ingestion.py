from pathlib import Path
from unittest.mock import patch, MagicMock
import json

from ncdev.v3.context_ingestion import ingest_project_context, ingest_feature_result
from ncdev.v3.models import FeatureStep, StepResult, StepStatus, IngestionReport


def _write_artifact(run_dir: Path, name: str, data: dict) -> None:
    out = run_dir / "outputs"
    out.mkdir(parents=True, exist_ok=True)
    (out / name).write_text(json.dumps(data), encoding="utf-8")


def test_ingest_project_context_returns_report(tmp_path: Path):
    run_dir = tmp_path / "run"
    target = tmp_path / "project"
    target.mkdir()
    _write_artifact(run_dir, "design-brief.json", {"project_name": "test", "colors": {}})
    _write_artifact(run_dir, "feature-map.json", {"features": [{"name": "Auth", "description": "User auth"}]})
    _write_artifact(run_dir, "build-plan.json", {"project_name": "test", "batches": []})
    _write_artifact(run_dir, "target-project-contract.json", {"stack": {"backend": "FastAPI"}})

    from ncdev.v3.models import FeatureQueueDoc
    fq = FeatureQueueDoc(project_name="test", features=[])

    with patch("ncdev.v3.context_ingestion.CitexClient") as MockClient:
        mock_instance = MagicMock()
        mock_instance.ingest.return_value = True
        MockClient.return_value = mock_instance

        report = ingest_project_context(run_dir, target, fq, project_id="test")
        assert isinstance(report, IngestionReport)
        assert report.total_documents > 0
        assert report.successful > 0
        assert report.failed == 0


def test_ingest_feature_result_stores_in_citex(tmp_path: Path):
    feature = FeatureStep(
        feature_id="f1",
        title="User Auth",
        description="Add user authentication",
        acceptance_criteria=["Login works"],
    )
    result = StepResult(
        feature_id="f1",
        status=StepStatus.PASSED,
        files_created=["auth.py"],
        files_modified=["router.py"],
    )
    with patch("ncdev.v3.context_ingestion.CitexClient") as MockClient:
        mock_instance = MagicMock()
        mock_instance.ingest.return_value = True
        MockClient.return_value = mock_instance

        ok = ingest_feature_result(feature, result, tmp_path, project_id="test")
        assert ok is True
        mock_instance.ingest.assert_called_once()
        call_args = mock_instance.ingest.call_args
        assert call_args.kwargs["category"] == "prior_feature"
