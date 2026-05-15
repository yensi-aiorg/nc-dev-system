import json

from ncdev.claude_session import ClaudeSessionResult
from ncdev.pipeline.product_steward import (
    Disposition,
    parse_steward_response,
)


def test_disposition_enum_values():
    assert Disposition.CONTINUE.value == "continue"
    assert Disposition.REPAIR_CURRENT_SLICE.value == "repair_current_slice"
    assert Disposition.INSERT_FEATURES.value == "insert_features"
    assert Disposition.REWRITE_ACCEPTANCE.value == "rewrite_acceptance"
    assert Disposition.RERUN_CHARTER.value == "rerun_charter"
    assert Disposition.STOP_AS_UNRECOVERABLE.value == "stop_as_unrecoverable"


def test_parse_steward_response_happy_path():
    payload = json.dumps({
        "disposition": "repair_current_slice",
        "reasoning": "f02-auth left the dashboard route 500ing",
        "target_feature_ids": ["f02-auth"],
        "new_features": [],
        "amendments": [],
    })
    decision = parse_steward_response(payload)
    assert decision.disposition == Disposition.REPAIR_CURRENT_SLICE
    assert decision.target_feature_ids == ["f02-auth"]


def test_parse_steward_response_strips_markdown_fences():
    payload = "```json\n" + json.dumps({
        "disposition": "continue",
        "reasoning": "looking good",
    }) + "\n```"
    decision = parse_steward_response(payload)
    assert decision.disposition == Disposition.CONTINUE


def test_parse_steward_response_invalid_disposition_raises():
    import pytest

    with pytest.raises(ValueError):
        parse_steward_response(json.dumps({
            "disposition": "yolo",
            "reasoning": "n/a",
        }))


def _bundle():
    from ncdev.pipeline.models import (
        CharterBundle, FeatureQueueDoc, FeatureStep,
        TargetProjectContract, VerificationContract,
    )
    return CharterBundle(
        contract=TargetProjectContract(
            project_name="salon", project_type="web",
            language="python", database="postgres", auth="keycloak",
            ports={"frontend": 23000}, design_archetype="Warm Playfulness",
            design_system_source="claude_generated", uses_citex=False,
            is_brownfield=False, existing_repo_path="",
        ),
        verification=VerificationContract(
            backend_test_command="pytest", frontend_test_command="npm test",
            backend_health_url="http://localhost:23001/health",
            start_command="docker compose up -d",
            stop_command="docker compose down",
        ),
        feature_queue=FeatureQueueDoc(
            project_name="salon",
            features=[
                FeatureStep(feature_id="f01-scaffold", title="Scaffold",
                            description="boot", acceptance_criteria=[]),
                FeatureStep(feature_id="f02-auth", title="Auth",
                            description="login", acceptance_criteria=[]),
            ],
        ),
    )


def test_prompt_includes_prd_and_failed_feature(tmp_path):
    from ncdev.pipeline.product_steward import build_steward_prompt
    from ncdev.pipeline.models import StepResult, StepStatus

    prd = tmp_path / "prd.md"
    prd.write_text("# Salon PRD\nUsers should manage appointments.")
    prompt = build_steward_prompt(
        prd_path=prd,
        bundle=_bundle(),
        completed=[StepResult(
            feature_id="f01-scaffold", status=StepStatus.PASSED,
            commit_sha="aaa",
        ), StepResult(
            feature_id="f02-auth", status=StepStatus.FAILED,
            error_message="login route returned 500",
        )],
        target_path=tmp_path,
        last_test_craftr_scores=None,
    )
    assert "Salon PRD" in prompt
    assert "f02-auth" in prompt
    assert "FAILED" in prompt
    for v in ("continue", "repair_current_slice", "stop_as_unrecoverable"):
        assert v in prompt


def test_steward_prompt_includes_product_debt_section(tmp_path):
    from ncdev.pipeline.product_debt import (
        DebtType,
        ProductDebt,
        SuggestedDisposition,
    )
    from ncdev.pipeline.product_steward import build_steward_prompt

    prd = tmp_path / "prd.md"
    prd.write_text("# Salon PRD\nUsers should configure settings.")
    prompt = build_steward_prompt(
        prd_path=prd,
        bundle=_bundle(),
        completed=[],
        target_path=tmp_path,
        product_debt=[
            ProductDebt(
                debt_id="d001-settings-page",
                debt_type=DebtType.MISSING_FEATURE,
                title="Settings page missing",
                description="The PRD mentions settings but no feature handles it.",
                affected_routes=["/settings"],
                suggested_disposition=SuggestedDisposition.NEW_FEATURE_INSERTION,
                confidence=0.9,
            )
        ],
    )

    assert "### Detected product debt" in prompt
    assert "missing_feature" in prompt
    assert "d001-settings-page" in prompt
    assert "new_feature_insertion" in prompt


def test_steward_prompt_includes_perf_budget_section_when_perf_debt_present(tmp_path):
    from ncdev.pipeline.product_debt import (
        DebtType,
        ProductDebt,
        SuggestedDisposition,
    )
    from ncdev.pipeline.product_steward import build_steward_prompt

    debt = [
        ProductDebt(
            debt_id="d001-slow",
            debt_type=DebtType.PERFORMANCE,
            title="LCP regression on /dashboard",
            description="LCP exceeded budget",
            evidence=["lcp_ms=4200ms (budget 2500ms)"],
            suggested_disposition=SuggestedDisposition.DIRECT_FIX,
        )
    ]
    prd = tmp_path / "prd.md"
    prd.write_text("# x")
    prompt = build_steward_prompt(
        prd_path=prd,
        bundle=_bundle(),
        completed=[],
        target_path=tmp_path,
        product_debt=debt,
    )
    assert "Performance budget status" in prompt
    assert "lcp_ms=4200ms" in prompt


def test_steward_prompt_omits_debt_section_when_none(tmp_path):
    from ncdev.pipeline.product_steward import build_steward_prompt

    prd = tmp_path / "prd.md"
    prd.write_text("# Salon PRD")
    prompt = build_steward_prompt(
        prd_path=prd,
        bundle=_bundle(),
        completed=[],
        target_path=tmp_path,
        product_debt=None,
    )

    assert "Detected product debt" not in prompt


def test_steward_prompt_includes_provenance_section(tmp_path):
    from ncdev.pipeline.product_steward import build_steward_prompt

    prd = tmp_path / "prd.md"
    prd.write_text("# x")
    prompt = build_steward_prompt(
        prd_path=prd,
        bundle=_bundle(),
        completed=[],
        target_path=tmp_path,
        feature_provenance={
            "f01-scaffold": ["backend/app/main.py", "frontend/src/App.tsx"],
            "f02-auth": ["backend/app/auth.py", "frontend/src/pages/Login.tsx"],
        },
    )
    assert "Feature provenance" in prompt
    assert "backend/app/auth.py" in prompt
    assert "frontend/src/pages/Login.tsx" in prompt


def test_steward_prompt_omits_provenance_when_empty(tmp_path):
    from ncdev.pipeline.product_steward import build_steward_prompt

    prd = tmp_path / "prd.md"
    prd.write_text("# x")
    prompt = build_steward_prompt(
        prd_path=prd,
        bundle=_bundle(),
        completed=[],
        target_path=tmp_path,
        feature_provenance=None,
    )
    assert "Feature provenance" not in prompt


def test_steward_prompt_truncates_long_file_lists(tmp_path):
    from ncdev.pipeline.product_steward import build_steward_prompt

    prd = tmp_path / "prd.md"
    prd.write_text("# x")
    files = [f"src/file_{i}.py" for i in range(50)]
    prompt = build_steward_prompt(
        prd_path=prd,
        bundle=_bundle(),
        completed=[],
        target_path=tmp_path,
        feature_provenance={"f01": files},
    )
    assert "more" in prompt
    assert "src/file_0.py" in prompt
    assert "src/file_49.py" not in prompt


def test_run_product_steward_returns_decision(monkeypatch, tmp_path):
    from ncdev.pipeline import product_steward as ps

    fake_response = '{"disposition": "continue", "reasoning": "all green"}'

    def fake_session(prompt, **kwargs):
        return ClaudeSessionResult(
            success=True,
            final_text=fake_response,
            exit_code=0,
        )

    monkeypatch.setattr(ps, "run_ai_session", fake_session)
    prd = tmp_path / "prd.md"
    prd.write_text("# fake")

    decision = ps.run_product_steward(
        prd_path=prd,
        bundle=_bundle(),
        completed=[],
        target_path=tmp_path,
        run_dir=tmp_path / ".run",
        config=None,
    )
    assert decision.disposition == Disposition.CONTINUE


def test_run_steward_loads_provenance_from_disk(monkeypatch, tmp_path):
    """run_product_steward reads provenance.jsonl from a sibling/ancestor."""
    from ncdev.pipeline import product_steward as ps
    from ncdev.pipeline.models import ProvenanceRecord
    from ncdev.pipeline.provenance import append_provenance

    run_dir = tmp_path / "run-1"
    run_dir.mkdir()
    append_provenance(run_dir, ProvenanceRecord(
        feature_id="f01",
        commit_sha="aaa",
        files_created=["a.py"],
        files_modified=["b.py"],
    ))

    steward_dir = run_dir / "steward" / "cycle-1"
    captured_prompts = []

    def fake_session(prompt, **kwargs):
        captured_prompts.append(prompt)
        return ClaudeSessionResult(
            success=True,
            final_text='{"disposition":"continue","reasoning":"ok"}',
            exit_code=0,
        )

    monkeypatch.setattr(ps, "run_ai_session", fake_session)
    prd = tmp_path / "prd.md"
    prd.write_text("# x")
    decision = ps.run_product_steward(
        prd_path=prd,
        bundle=_bundle(),
        completed=[],
        target_path=tmp_path,
        run_dir=steward_dir,
        config=None,
    )
    assert "Feature provenance" in captured_prompts[0]
    assert "a.py" in captured_prompts[0]
    assert decision.disposition.value == "continue"


def test_run_product_steward_falls_back_to_stop_on_invalid_response(monkeypatch, tmp_path):
    from ncdev.pipeline import product_steward as ps

    def fake_session(prompt, **kwargs):
        return ClaudeSessionResult(
            success=True,
            final_text="not json",
            exit_code=0,
        )

    monkeypatch.setattr(ps, "run_ai_session", fake_session)
    prd = tmp_path / "prd.md"
    prd.write_text("# fake")

    decision = ps.run_product_steward(
        prd_path=prd,
        bundle=_bundle(),
        completed=[],
        target_path=tmp_path,
        run_dir=tmp_path / ".run",
        config=None,
    )
    assert decision.disposition == Disposition.STOP_AS_UNRECOVERABLE


def test_run_steward_consults_capability_router(monkeypatch, tmp_path):
    """When config has a capability chain for product_coherence_review,
    run_product_steward picks up the chain's model name."""
    from ncdev.core.config import (
        CapabilityChoice,
        CapabilityMatrixConfig,
        NCDevConfig,
        ProviderPreferenceConfig,
    )
    from ncdev.pipeline import product_steward as ps

    cfg = NCDevConfig(
        mode="custom",
        providers={"anthropic_claude_code": ProviderPreferenceConfig(enabled=True)},
        capabilities=CapabilityMatrixConfig(
            chains={
                "product_coherence_review": [
                    CapabilityChoice(
                        provider="anthropic_claude_code",
                        model="opus-5",
                    )
                ],
            }
        ),
    )
    captured_model = []

    def fake_session(prompt, **kwargs):
        captured_model.append(kwargs.get("model"))
        return ClaudeSessionResult(
            success=True,
            final_text='{"disposition":"continue","reasoning":"ok"}',
            exit_code=0,
        )

    monkeypatch.setattr(ps, "run_ai_session", fake_session)
    prd = tmp_path / "prd.md"
    prd.write_text("# fake")
    decision = ps.run_product_steward(
        prd_path=prd,
        bundle=_bundle(),
        completed=[],
        target_path=tmp_path,
        run_dir=tmp_path / ".run",
        config=cfg,
    )
    assert captured_model == ["opus-5"]
    assert decision.disposition.value == "continue"
