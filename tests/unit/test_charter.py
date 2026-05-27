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
            ports={"frontend": 23300, "backend": 23301, "mongodb": 23302},
            design_archetype="Technical Elegance",
            design_system_source="stitch",
        ),
        verification=VerificationContract(
            backend_health_url="http://localhost:23301/api/health",
            frontend_url="http://localhost:23300",
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
# Stack-resolution rules — PRD wins, house defaults fill silence
# ---------------------------------------------------------------------------


def test_prompt_documents_keystone_vs_standalone_auth(tmp_path: Path):
    """Charter must instruct the LLM to detect Keystone in the PRD and
    fall back to standalone Keycloak otherwise. Without this the LLM
    has no way to know about the in-house Keystone platform and will
    default to whatever it has seen most often (raw Keycloak)."""
    prompt = build_charter_prompt(
        prd_path=tmp_path / "prd.md", target_repo=None, output_dir=tmp_path,
    )
    assert "keystone" in prompt.lower()
    assert "keystone-sdk" in prompt
    assert "@keystone/react" in prompt
    assert "keycloak_standalone" in prompt
    # Standalone mode is the mock layer — not a hand-written stub
    assert "standalone_mode" in prompt
    assert "dev_users" in prompt


def test_prompt_documents_app_owns_auth_ui_invariant(tmp_path: Path):
    """The application always renders auth UI; Keycloak's hosted login
    page is never shown. This invariant must be stated in the prompt so
    the LLM doesn't default to redirecting users to Keycloak's UI."""
    prompt = build_charter_prompt(
        prd_path=tmp_path / "prd.md", target_repo=None, output_dir=tmp_path,
    )
    assert "auth_ui_owner" in prompt
    assert "application" in prompt
    # Direct-grant guidance must appear for both Keystone and standalone
    # paths — the LLM needs to know to configure clients accordingly.
    assert "standardFlowEnabled" in prompt
    assert "directAccessGrantsEnabled" in prompt
    # Must explicitly warn against the Keycloak login page
    assert "Keycloak's hosted login page" in prompt or "Keycloak login page" in prompt


def test_prompt_documents_social_auth_off_by_default(tmp_path: Path):
    """Social auth is opt-in via PRD only. The prompt must instruct the
    LLM not to enable Google/etc unless the PRD explicitly asks."""
    prompt = build_charter_prompt(
        prd_path=tmp_path / "prd.md", target_repo=None, output_dir=tmp_path,
    )
    assert "social_auth_providers" in prompt
    assert "OFF by default" in prompt
    # Keystone's BFF flow paths must be referenced so the LLM knows
    # the integration surface
    assert "/api/auth/google/start" in prompt


def test_prompt_documents_frontend_state_house_default(tmp_path: Path):
    """When the PRD is silent on frontend state / data-fetching, the
    house default (Zustand + Axios with interceptors) is used instead
    of guessing React Query."""
    prompt = build_charter_prompt(
        prd_path=tmp_path / "prd.md", target_repo=None, output_dir=tmp_path,
    )
    assert "frontend_state" in prompt
    assert "frontend_data_fetching" in prompt
    assert "'zustand'" in prompt
    assert "'axios_with_interceptors'" in prompt
    # PRD-wins instruction must be present (line wrapping may insert
    # whitespace between words — check for the distinctive token)
    assert "verbatim" in prompt
    assert "PRD names" in prompt


def test_prompt_uses_house_default_port_base(tmp_path: Path):
    """Port allocation guidance in the prompt must reflect the configured
    house_defaults.port_base (23300 by default)."""
    prompt = build_charter_prompt(
        prd_path=tmp_path / "prd.md", target_repo=None, output_dir=tmp_path,
    )
    assert "23300" in prompt
    assert "23301" in prompt
    assert "23304" in prompt
    assert "23305" in prompt


def test_prompt_port_base_honours_config_override(tmp_path: Path):
    """A non-default house_defaults.port_base must flow through to the
    prompt — confirms the budget-lever character of the config."""
    from ncdev.core.config import (
        HouseDefaultsConfig,
        NCDevConfig,
    )

    cfg = NCDevConfig(
        house_defaults=HouseDefaultsConfig(port_base=24500),
    )
    prompt = build_charter_prompt(
        prd_path=tmp_path / "prd.md",
        target_repo=None,
        output_dir=tmp_path,
        config=cfg,
    )
    assert "24500" in prompt
    assert "24505" in prompt
    # Old base must not leak through
    assert "23300" not in prompt
    assert "23304" not in prompt


def test_prompt_frontend_state_fallback_honours_config_override(tmp_path: Path):
    """If a project shop changes the house default state library, the
    prompt must reflect that — not the original Zustand text."""
    from ncdev.core.config import (
        HouseDefaultsConfig,
        HouseDefaultsFrontendConfig,
        NCDevConfig,
    )

    cfg = NCDevConfig(
        house_defaults=HouseDefaultsConfig(
            frontend=HouseDefaultsFrontendConfig(
                state_fallback="jotai",
                data_fetching_fallback="tanstack_query",
            ),
        ),
    )
    prompt = build_charter_prompt(
        prd_path=tmp_path / "prd.md",
        target_repo=None,
        output_dir=tmp_path,
        config=cfg,
    )
    assert "'jotai'" in prompt
    assert "'tanstack_query'" in prompt


# ---------------------------------------------------------------------------
# Contract model — new auth/frontend stack fields
# ---------------------------------------------------------------------------


def test_contract_defaults_for_new_stack_fields():
    """The new stack fields default to safe empty / invariant values."""
    contract = TargetProjectContract(project_name="myapp")
    assert contract.auth_provider == ""
    assert contract.auth_ui_owner == "application"
    assert contract.social_auth_providers == []
    assert contract.frontend_state == ""
    assert contract.frontend_data_fetching == ""


def test_contract_accepts_keystone_auth_provider():
    """The charter LLM populates auth_provider with the resolved value;
    "keystone" must round-trip through the model."""
    contract = TargetProjectContract(
        project_name="myapp",
        auth_provider="keystone",
        social_auth_providers=["google"],
        frontend_state="zustand",
        frontend_data_fetching="axios_with_interceptors",
    )
    payload = json.loads(contract.model_dump_json())
    assert payload["auth_provider"] == "keystone"
    assert payload["auth_ui_owner"] == "application"
    assert payload["social_auth_providers"] == ["google"]
    assert payload["frontend_state"] == "zustand"
    assert payload["frontend_data_fetching"] == "axios_with_interceptors"


# ---------------------------------------------------------------------------
# HouseDefaultsConfig — config wiring
# ---------------------------------------------------------------------------


def test_house_defaults_config_safe_defaults():
    """The defaults must match the documented contract — Keycloak
    standalone + Zustand + Axios + port base 23300 + app-owned auth UI."""
    from ncdev.core.config import NCDevConfig

    cfg = NCDevConfig()
    house = cfg.house_defaults
    assert house.auth.fallback == "keycloak_standalone"
    assert house.auth.ui_owner == "application"
    assert house.frontend.state_fallback == "zustand"
    assert house.frontend.data_fetching_fallback == "axios_with_interceptors"
    assert house.port_base == 23300


def test_house_defaults_config_parses_from_yaml_dict():
    """A YAML-loaded config (the live .nc-dev/config.yaml round-trip)
    must accept overrides for every house_defaults field."""
    from ncdev.core.config import NCDevConfig

    cfg = NCDevConfig.model_validate({
        "house_defaults": {
            "auth": {"fallback": "keystone", "ui_owner": "application"},
            "frontend": {
                "state_fallback": "redux_toolkit",
                "data_fetching_fallback": "rtk_query",
            },
            "port_base": 24000,
        },
    })
    assert cfg.house_defaults.auth.fallback == "keystone"
    assert cfg.house_defaults.frontend.state_fallback == "redux_toolkit"
    assert cfg.house_defaults.frontend.data_fetching_fallback == "rtk_query"
    assert cfg.house_defaults.port_base == 24000


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
    assert (out / "behavior-contract.v1.json").exists()
    assert (out / "behavior-contract.md").exists()

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


# --- semantic validation (v4 defect #10) -----------------------------------


def test_validate_completeness_rejects_blank_feature_id() -> None:
    bundle = _fake_charter_bundle()
    bundle.feature_queue.features[0].feature_id = "   "
    violations = validate_charter_completeness(bundle)
    assert any("blank feature_id" in v for v in violations)


def test_validate_completeness_rejects_duplicate_feature_ids() -> None:
    bundle = _fake_charter_bundle()
    bundle.feature_queue.features[1].feature_id = "f01-scaffold"
    violations = validate_charter_completeness(bundle)
    assert any("duplicate feature_id" in v and "f01-scaffold" in v for v in violations)


def test_validate_completeness_rejects_blank_title_or_description() -> None:
    bundle = _fake_charter_bundle()
    bundle.feature_queue.features[0].title = ""
    bundle.feature_queue.features[1].description = "   "
    violations = validate_charter_completeness(bundle)
    assert any("blank title" in v for v in violations)
    assert any("blank description" in v for v in violations)


def test_validate_completeness_rejects_empty_acceptance_criteria() -> None:
    bundle = _fake_charter_bundle()
    bundle.feature_queue.features[0].acceptance_criteria = []
    violations = validate_charter_completeness(bundle)
    assert any("acceptance_criteria" in v and "f01-scaffold" in v for v in violations)


def test_validate_completeness_rejects_unknown_dependency() -> None:
    bundle = _fake_charter_bundle()
    bundle.feature_queue.features[1].depends_on_features = ["does-not-exist"]
    violations = validate_charter_completeness(bundle)
    assert any("does-not-exist" in v and "depends_on" in v for v in violations)


def test_validate_completeness_rejects_empty_feature_queue() -> None:
    bundle = _fake_charter_bundle()
    bundle.feature_queue.features = []
    violations = validate_charter_completeness(bundle)
    assert any("feature queue is empty" in v for v in violations)


def test_validate_completeness_passes_clean_bundle_semantically() -> None:
    """A well-formed bundle yields no semantic violations."""
    bundle = _fake_charter_bundle()
    assert validate_charter_completeness(bundle) == []


# --- assumptions surface (v4 Pillar C) -------------------------------------


def test_charter_prompt_instructs_recording_assumptions() -> None:
    from ncdev.pipeline.charter import CHARTER_PROMPT_TEMPLATE

    assert "assumptions" in CHARTER_PROMPT_TEMPLATE
    assert "ambiguous" in CHARTER_PROMPT_TEMPLATE.lower()


def test_charter_roundtrip_preserves_assumptions(tmp_path: Path) -> None:
    from ncdev.pipeline.charter import load_charter, write_charter

    bundle = _fake_charter_bundle()
    bundle.feature_queue.assumptions = [
        "PRD does not specify auth — assuming Keycloak email/password.",
        "Multi-tenancy not mentioned — assuming single-tenant for v1.",
    ]
    write_charter(bundle, tmp_path)
    reloaded = load_charter(tmp_path, strict=False)
    assert reloaded.feature_queue.assumptions == bundle.feature_queue.assumptions


def test_assumptions_default_to_empty_list() -> None:
    bundle = _fake_charter_bundle()
    assert bundle.feature_queue.assumptions == []


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
