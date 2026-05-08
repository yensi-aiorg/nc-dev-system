import json

from ncdev.pipeline.context_ingestion import ingest_feature_result, ingest_project_context
from ncdev.pipeline.models import FeatureQueueDoc, FeatureStep, StepResult, StepStatus


def test_ingest_project_context_ingests_expected_categories(tmp_path, monkeypatch) -> None:
    run_dir = tmp_path / "run"
    outputs = run_dir / "outputs"
    outputs.mkdir(parents=True)
    (outputs / "design-brief.json").write_text(json.dumps({"colors": ["#111"]}), encoding="utf-8")
    (outputs / "build-plan.json").write_text(json.dumps({"stack": {"backend": "fastapi"}}), encoding="utf-8")

    target = tmp_path / "repo"
    (target / "backend/app/api/v1").mkdir(parents=True)
    (target / "backend/app/models").mkdir(parents=True)
    (target / "backend/app/services").mkdir(parents=True)
    (target / "frontend/src").mkdir(parents=True)
    (target / "tests").mkdir(parents=True)
    (target / "backend/app/api/v1/routes.py").write_text("router = object()\n", encoding="utf-8")
    (target / "backend/app/models/user.py").write_text("class User: pass\n", encoding="utf-8")
    (target / "backend/app/services/user_service.py").write_text("def fetch(): pass\n", encoding="utf-8")
    (target / "frontend/src/app.tsx").write_text("export const App = () => null;\n", encoding="utf-8")
    (target / "tests/test_app.py").write_text("def test_ok(): assert True\n", encoding="utf-8")
    (target / "CLAUDE.md").write_text("rules", encoding="utf-8")

    queue = FeatureQueueDoc(
        project_name="demo",
        features=[FeatureStep(feature_id="f1", title="Feature One", description="Do it", acceptance_criteria=["works"])],
    )

    calls = []

    class FakeClient:
        def __init__(self, project_id, base_url):
            self.project_id = project_id

        def ingest(self, content, category, metadata=None):
            calls.append((category, content, metadata))
            return True

    monkeypatch.setattr("ncdev.pipeline.context_ingestion.CitexClient", FakeClient)
    # Skip Opus synthesis in tests
    monkeypatch.setattr("ncdev.pipeline.context_ingestion._synthesize_with_opus", lambda cat, raw: raw[:500])

    report = ingest_project_context(run_dir=run_dir, target_path=target, feature_queue=queue)

    categories = {cat for cat, _, _ in calls}
    assert report.project_id == "repo"
    assert report.total_documents == len(calls)
    assert report.failed == 0
    assert "design" in categories
    assert "architecture" in categories
    assert "feature_spec" in categories


def test_ingest_feature_result_stores_prior_feature(tmp_path, monkeypatch) -> None:
    target = tmp_path / "repo"
    target.mkdir()
    captured = {}

    class FakeClient:
        def __init__(self, project_id, base_url):
            captured["project_id"] = project_id

        def ingest(self, content, category, metadata=None):
            captured["content"] = content
            captured["category"] = category
            captured["metadata"] = metadata
            return True

    monkeypatch.setattr("ncdev.pipeline.context_ingestion.CitexClient", FakeClient)

    feature = FeatureStep(feature_id="f2", title="Feature Two", description="Build it", acceptance_criteria=["done"])
    result = StepResult(feature_id="f2", status=StepStatus.PASSED, files_created=["a.py"], files_modified=["b.py"], repair_attempts=1)

    ok = ingest_feature_result(feature, result, target)
    assert ok is True
    assert captured["project_id"] == "repo"
    assert captured["category"] == "prior_feature"
    assert captured["metadata"] == {"feature_id": "f2", "status": "passed"}
    assert "Files Created:" in captured["content"]
    assert "- a.py" in captured["content"]
