from __future__ import annotations

import json
from pathlib import Path

from ncdev.contracts.behavior_contract import (
    build_behavior_contract,
    write_behavior_contract,
)
from ncdev.pipeline.models import (
    CharterBundle,
    FeatureAcceptance,
    FeatureQueueDoc,
    FeatureStep,
    TargetProjectContract,
    VerificationContract,
)


def _bundle() -> CharterBundle:
    return CharterBundle(
        contract=TargetProjectContract(
            project_name="Pilot",
            project_type="web",
            existing_repo_path="/tmp/pilot",
        ),
        verification=VerificationContract(
            backend_health_url="http://localhost:3000/api/health",
            frontend_url="http://localhost:3000",
            backend_test_command="pytest -q",
            e2e_test_command="npx playwright test",
            prohibited_patterns=["TODO"],
            performance_budget={"/dashboard": {"lcp_ms": 2500}},
        ),
        feature_queue=FeatureQueueDoc(
            project_name="Pilot",
            assumptions=["Email delivery is represented by a local outbox."],
            features=[
                FeatureStep(
                    feature_id="f01-invites",
                    title="Team invites",
                    description="Admins invite teammates by email.",
                    acceptance_criteria=[
                        "Invite links expire after seven days.",
                        "Expired invites show a renewal path.",
                    ],
                    priority=1,
                    acceptance=FeatureAcceptance(
                        required_files=["src/invites.py"],
                        required_routes=["/invites/accept"],
                        required_tests=["tests/test_invites.py"],
                    ),
                )
            ],
        ),
    )


def test_build_behavior_contract_from_charter() -> None:
    contract = build_behavior_contract(_bundle(), source_path=Path("PRD.md"))

    assert contract.kind == "behavior-contract"
    assert contract.contract_id.startswith("bc-")
    assert contract.project_name == "Pilot"
    assert contract.target_url == "http://localhost:3000"
    assert contract.assumptions == [
        "Email delivery is represented by a local outbox."
    ]
    assert contract.required_commands["backend_test"] == "pytest -q"
    assert contract.performance_budget["/dashboard"]["lcp_ms"] == 2500

    scenario = contract.scenarios[0]
    assert scenario.scenario_id == "f01-invites-s01"
    assert scenario.required_routes == ["/invites/accept"]
    assert scenario.required_files == ["src/invites.py"]
    assert "Expired invites show a renewal path." in scenario.then


def test_write_behavior_contract_outputs_json_and_markdown(tmp_path: Path) -> None:
    contract = build_behavior_contract(_bundle())

    write_behavior_contract(contract, tmp_path)

    json_path = tmp_path / "behavior-contract.v1.json"
    markdown_path = tmp_path / "behavior-contract.md"
    assert json_path.exists()
    assert markdown_path.exists()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["contract_id"] == contract.contract_id
    assert "f01-invites-s01" in markdown_path.read_text(encoding="utf-8")

