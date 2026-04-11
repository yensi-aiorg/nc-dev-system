from pathlib import Path

from ncdev.v3.models import FeatureStep
from ncdev.v3.prompt_builder import build_feature_prompt, build_repair_prompt


def test_prompt_contains_citex_instructions() -> None:
    feature = FeatureStep(
        feature_id="f1", title="User Authentication",
        description="Add JWT-based user auth",
        acceptance_criteria=["Login returns JWT", "Protected routes require token"],
    )
    prompt = build_feature_prompt(feature=feature, target_path=Path("/tmp/project"), project_id="test-proj")
    assert "localhost:20161" in prompt
    assert "test-proj" in prompt
    assert "User Authentication" in prompt
    assert "Login returns JWT" in prompt
    assert "/api/retrieval/query" in prompt


def test_prompt_under_5k_chars() -> None:
    feature = FeatureStep(feature_id="f1", title="Feature", description="Build something", acceptance_criteria=["It works"])
    prompt = build_feature_prompt(feature=feature, target_path=Path("/tmp/p"), project_id="proj")
    assert len(prompt) < 5000


def test_prompt_includes_test_requirements() -> None:
    feature = FeatureStep(
        feature_id="f1", title="Dashboard",
        description="Build dashboard page",
        acceptance_criteria=["Shows data"],
        test_requirements=["adds regression tests"],
    )
    prompt = build_feature_prompt(feature=feature, target_path=Path("/tmp/p"), project_id="proj")
    assert "adds regression tests" in prompt
    assert "Test Requirements" in prompt


def test_prompt_has_query_examples() -> None:
    feature = FeatureStep(feature_id="f2", title="X", description="Y", acceptance_criteria=["Z"])
    prompt = build_feature_prompt(feature=feature, target_path=Path("/tmp/p"), project_id="proj")
    assert "design tokens" in prompt.lower()
    assert "data model" in prompt.lower()
    assert "curl" in prompt


def test_repair_prompt_includes_failures() -> None:
    feature = FeatureStep(feature_id="f1", title="Auth", description="Auth feature", acceptance_criteria=["Works"])
    prompt = build_repair_prompt(
        feature=feature, target_path=Path("/tmp/project"),
        verification_output="test_login FAILED",
        error_traces="AssertionError: expected 200 got 401",
    )
    assert "REPAIR" in prompt
    assert "test_login FAILED" in prompt
    assert "AssertionError" in prompt
