from pathlib import Path
from ncdev.v3.prompt_builder import build_feature_prompt, build_repair_prompt
from ncdev.v3.models import FeatureStep


def test_lean_prompt_contains_citex_instructions():
    feature = FeatureStep(
        feature_id="f1",
        title="User Authentication",
        description="Add JWT-based user auth",
        acceptance_criteria=["Login returns JWT", "Protected routes require token"],
    )
    prompt = build_feature_prompt(
        feature=feature,
        target_path=Path("/tmp/project"),
        project_id="test-proj",
        citex_api="http://localhost:20160",
    )
    assert "localhost:20160" in prompt
    assert "test-proj" in prompt
    assert "User Authentication" in prompt
    assert "Login returns JWT" in prompt
    assert "/api/v1/retrieval/query" in prompt


def test_lean_prompt_under_5k_chars():
    feature = FeatureStep(
        feature_id="f1",
        title="Feature",
        description="Build something",
        acceptance_criteria=["It works"],
    )
    prompt = build_feature_prompt(
        feature=feature,
        target_path=Path("/tmp/project"),
        project_id="proj",
    )
    assert len(prompt) < 5000


def test_lean_prompt_has_query_examples():
    feature = FeatureStep(
        feature_id="f2",
        title="Dashboard",
        description="Build dashboard page",
        acceptance_criteria=["Shows data"],
    )
    prompt = build_feature_prompt(
        feature=feature,
        target_path=Path("/tmp/project"),
        project_id="proj",
    )
    assert "design tokens" in prompt.lower() or "design" in prompt.lower()
    assert "data model" in prompt.lower() or "models" in prompt.lower()
    assert "curl" in prompt or "httpx" in prompt


def test_repair_prompt_unchanged():
    feature = FeatureStep(
        feature_id="f1",
        title="Auth",
        description="Auth feature",
        acceptance_criteria=["Works"],
    )
    prompt = build_repair_prompt(
        feature=feature,
        target_path=Path("/tmp/project"),
        verification_output="test_login FAILED",
        error_traces="AssertionError: expected 200 got 401",
    )
    assert "REPAIR" in prompt
    assert "test_login FAILED" in prompt
