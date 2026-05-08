"""Tests for Phase B charter generator."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from ncdev.claude_session import ClaudeSessionResult
from ncdev.pipeline.charter import (
    build_charter_prompt,
    generate_charter,
    load_charter,
    validate_charter_completeness,
    write_charter,
)
from ncdev.pipeline.models import (
    CharterBundle,
    FeatureAcceptance,
    FeatureQueueDoc,
    FeatureStep,
    TargetProjectContract,
    VerificationContract,
)


def _fake_charter_bundle() -> CharterBundle:
    return CharterBundle(
        contract=TargetProjectContract(
            project_name="myapp",
            project_type="web",
            backend_framework="fastapi",
            frontend_framework="react",
            database="mongodb",
            auth_system="keycloak",
            language_backend="python",
            language_frontend="typescript",
            deployment_target="docker",
            ports={"frontend": 23000, "backend": 23001, "mongodb": 23002},
            design_archetype="Technical Elegance",
            design_system_source="stitch",
        ),
        verification=VerificationContract(
            backend_health_url="http://localhost:23001/api/health",
            frontend_url="http://localhost:23000",
            backend_test_command="cd backend && pytest -q",
            frontend_test_command="cd frontend && npm test -- --run",
            start_command="docker compose up -d",
            stop_command="docker compose down -v",
            required_screenshots=["homepage", "login"],
            required_files=["docker-compose.yml", "backend/app/main.py"],
        ),
        feature_queue=FeatureQueueDoc(
            project_name="myapp",
            features=[
                FeatureStep(
                    feature_id="f01-scaffold",
                    title="Scaffold project",
                    description="Boot skeleton + health endpoint",
                    acceptance_criteria=["Health endpoint returns 200"],
                    acceptance=FeatureAcceptance(
                        required_files=["docker-compose.yml", "backend/app/main.py"],
                        required_tests=["backend/tests/test_health.py"],
                        required_routes=["/api/health"],
                    ),
                ),
                FeatureStep(
                    feature_id="f02-auth",
                    title="Auth",
                    description="Keycloak integration",
                    acceptance_criteria=["Login works"],
                    depends_on_features=["f01-scaffold"],
                    acceptance=FeatureAcceptance(
                        required_files=["backend/app/auth.py"],
                        required_tests=["backend/tests/test_auth_f02.py"],
                        required_routes=["/api/auth/login"],
                    ),
                ),
            ],
        ),
    )


# ---------------------------------------------------------------------------
# Prompt shape
# ---------------------------------------------------------------------------


def test_prompt_references_three_artifact_files(tmp_path: Path):
    prompt = build_charter_prompt(
        prd_path=tmp_path / "prd.md",
        target_repo=None,
        output_dir=tmp_path / "outputs",
        project_type_hint="web",
    )
    assert "target-project-contract.json" in prompt
    assert "verification-contract.json" in prompt
    assert "feature-queue.json" in prompt
    # Directs Claude to use the planning skill
    assert "writing-plans" in prompt


def test_prompt_does_not_hard_fail_on_design_concerns(tmp_path: Path):
    """Greenfield/design hard-fail is Phase C's responsibility, not the
    charter prompt. Phase B should produce the three artifacts regardless
    of whether a design system exists yet."""
    prompt = build_charter_prompt(
        prd_path=tmp_path / "prd.md",
        target_repo=None,
        output_dir=tmp_path / "outputs",
    )
    # Charter must NOT instruct Claude to write charter-error.json for
    # greenfield UI — that confuses the phase boundary.
    assert "charter-error.json" not in prompt


def test_prompt_includes_schema_excerpts(tmp_path: Path):
    prompt = build_charter_prompt(
        prd_path=tmp_path / "prd.md",
        target_repo=tmp_path,
        output_dir=tmp_path / "outputs",
    )
    # Hard-constraint fields surface in the prompt
    assert "backend_framework" in prompt
    assert "design_archetype" in prompt
    assert "required_screenshots" in prompt


# ---------------------------------------------------------------------------
# Artifact round-trip
# ---------------------------------------------------------------------------


def test_write_and_load_charter_roundtrip(tmp_path: Path):
    bundle = _fake_charter_bundle()
    out = tmp_path / "outputs"
    write_charter(bundle, out)

    assert (out / "target-project-contract.json").exists()
    assert (out / "verification-contract.json").exists()
    assert (out / "feature-queue.json").exists()

    loaded = load_charter(out)
    assert loaded.contract.project_name == "myapp"
    assert loaded.contract.design_archetype == "Technical Elegance"
    assert loaded.verification.required_screenshots == ["homepage", "login"]
    assert len(loaded.feature_queue.features) == 2
    assert loaded.feature_queue.features[0].feature_id == "f01-scaffold"


def test_load_charter_fails_when_file_missing(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_charter(tmp_path / "nonexistent")


# ---------------------------------------------------------------------------
# generate_charter — mocked Claude session
# ---------------------------------------------------------------------------


def test_generate_charter_success_loads_bundle(tmp_path: Path):
    """Simulate a successful Claude session that writes the three artifacts."""
    bundle = _fake_charter_bundle()

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        write_charter(bundle, kwargs["cwd"])
        return ClaudeSessionResult(
            success=True, final_text="charter written",
            exit_code=0, duration_seconds=1.0,
        )

    with patch("ncdev.pipeline.charter.run_ai_session", side_effect=fake_session):
        result_bundle, session = generate_charter(
            prd_path=tmp_path / "prd.md",
            output_dir=tmp_path / "outputs",
        )

    assert session.success is True
    assert result_bundle is not None
    assert result_bundle.contract.project_name == "myapp"


def test_generate_charter_hard_fails_on_charter_error_file(tmp_path: Path):
    """Greenfield UI without design system: Claude writes charter-error.json."""
    def fake_session(prompt, **kwargs):  # noqa: ARG001
        out = kwargs["cwd"]
        out.mkdir(parents=True, exist_ok=True)
        (out / "charter-error.json").write_text(json.dumps({
            "error": "greenfield UI project requires a design system",
            "fix": "run stitch setup",
        }), encoding="utf-8")
        return ClaudeSessionResult(
            success=True, final_text="hard fail: design required",
            exit_code=0, duration_seconds=0.5,
        )

    with patch("ncdev.pipeline.charter.run_ai_session", side_effect=fake_session):
        result_bundle, session = generate_charter(
            prd_path=tmp_path / "prd.md",
            output_dir=tmp_path / "outputs",
        )

    # Hard fail — no bundle returned even though session itself succeeded
    assert result_bundle is None
    assert session.success is True
    assert (tmp_path / "outputs" / "charter-error.json").exists()


def test_generate_charter_returns_none_when_session_fails(tmp_path: Path):
    def fake_session(prompt, **kwargs):  # noqa: ARG001
        return ClaudeSessionResult(
            success=False, final_text="", exit_code=1,
            error="something broke",
        )

    with patch("ncdev.pipeline.charter.run_ai_session", side_effect=fake_session):
        result_bundle, session = generate_charter(
            prd_path=tmp_path / "prd.md",
            output_dir=tmp_path / "outputs",
        )

    assert result_bundle is None
    assert session.success is False


def test_generate_charter_returns_none_on_invalid_json(tmp_path: Path):
    def fake_session(prompt, **kwargs):  # noqa: ARG001
        out = kwargs["cwd"]
        out.mkdir(parents=True, exist_ok=True)
        (out / "target-project-contract.json").write_text("{not json", encoding="utf-8")
        (out / "verification-contract.json").write_text("{}", encoding="utf-8")
        (out / "feature-queue.json").write_text("{}", encoding="utf-8")
        return ClaudeSessionResult(
            success=True, final_text="done", exit_code=0,
        )

    with patch("ncdev.pipeline.charter.run_ai_session", side_effect=fake_session):
        result_bundle, _ = generate_charter(
            prd_path=tmp_path / "prd.md",
            output_dir=tmp_path / "outputs",
        )

    assert result_bundle is None


def test_generate_charter_uses_plan_tools_only(tmp_path: Path):
    """The charter session must not have Bash or Edit — read + write only."""
    captured: dict = {}

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        captured.update(kwargs)
        write_charter(_fake_charter_bundle(), kwargs["cwd"])
        return ClaudeSessionResult(success=True, final_text="ok", exit_code=0)

    with patch("ncdev.pipeline.charter.run_ai_session", side_effect=fake_session):
        generate_charter(
            prd_path=tmp_path / "prd.md",
            output_dir=tmp_path / "outputs",
        )

    tools = list(captured["tools"])
    assert "Bash" not in tools
    assert "Edit" not in tools
    assert "Read" in tools
    assert "Write" in tools
    assert captured["include_codex_protocol"] is False


# ---------------------------------------------------------------------------
# validate_charter_completeness — production-readiness gate
# ---------------------------------------------------------------------------


def test_validate_completeness_passes_for_full_bundle() -> None:
    bundle = _fake_charter_bundle()
    assert validate_charter_completeness(bundle) == []


def test_validate_completeness_rejects_empty_test_commands() -> None:
    bundle = _fake_charter_bundle()
    bundle.verification.backend_test_command = ""
    bundle.verification.frontend_test_command = ""
    violations = validate_charter_completeness(bundle)
    assert any("backend_test_command or frontend_test_command" in v for v in violations)


def test_validate_completeness_rejects_missing_health_url_for_web() -> None:
    bundle = _fake_charter_bundle()
    bundle.contract.project_type = "web"
    bundle.verification.backend_health_url = ""
    violations = validate_charter_completeness(bundle)
    assert any("backend_health_url" in v for v in violations)


def test_validate_completeness_does_not_require_health_url_for_library() -> None:
    bundle = _fake_charter_bundle()
    bundle.contract.project_type = "library"
    bundle.verification.backend_health_url = ""
    violations = validate_charter_completeness(bundle)
    # Health URL is not required for libraries; backend_test_command is still set
    assert not any("backend_health_url" in v for v in violations)


def test_validate_completeness_rejects_feature_without_acceptance() -> None:
    bundle = _fake_charter_bundle()
    bundle.feature_queue.features.append(
        FeatureStep(
            feature_id="f99-empty",
            title="Empty",
            description="No acceptance",
            acceptance_criteria=["x"],
            # acceptance defaults to empty FeatureAcceptance
        )
    )
    violations = validate_charter_completeness(bundle)
    assert any("'f99-empty'" in v and "empty acceptance" in v for v in violations)


def test_load_charter_strict_raises_on_incomplete(tmp_path: Path) -> None:
    bundle = _fake_charter_bundle()
    bundle.feature_queue.features[0].acceptance = FeatureAcceptance()
    out = tmp_path / "outputs"
    write_charter(bundle, out)
    with pytest.raises(ValueError, match="Charter rejected"):
        load_charter(out, strict=True)


def test_load_charter_non_strict_skips_validation(tmp_path: Path) -> None:
    bundle = _fake_charter_bundle()
    bundle.feature_queue.features[0].acceptance = FeatureAcceptance()
    out = tmp_path / "outputs"
    write_charter(bundle, out)
    loaded = load_charter(out, strict=False)
    assert loaded.feature_queue.features[0].feature_id == "f01-scaffold"


def test_generate_charter_writes_error_file_on_validation_failure(tmp_path: Path) -> None:
    bundle = _fake_charter_bundle()
    bundle.feature_queue.features[0].acceptance = FeatureAcceptance()

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        write_charter(bundle, kwargs["cwd"])
        return ClaudeSessionResult(success=True, final_text="x", exit_code=0)

    with patch("ncdev.pipeline.charter.run_ai_session", side_effect=fake_session):
        result_bundle, _ = generate_charter(
            prd_path=tmp_path / "prd.md",
            output_dir=tmp_path / "outputs",
        )

    assert result_bundle is None
    err = tmp_path / "outputs" / "charter-error.json"
    assert err.exists()
    err_data = json.loads(err.read_text())
    assert "Charter rejected" in err_data["error"]


def test_charter_prompt_documents_acceptance_field() -> None:
    prompt = build_charter_prompt(
        prd_path=Path("/tmp/prd.md"),
        target_repo=None,
        output_dir=Path("/tmp/out"),
        project_type_hint="web",
    )
    # The prompt must teach Claude to populate acceptance
    assert "acceptance" in prompt
    assert "required_files" in prompt
    assert "required_tests" in prompt
    assert "MANDATORY" in prompt
