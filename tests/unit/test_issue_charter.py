from __future__ import annotations

import json
from pathlib import Path

from ncdev.pipeline.issue_charter import (
    _infer_contract,
    synthesize_charter_from_report,
)


def _write_report(path: Path, issues: list[dict]) -> None:
    path.write_text(
        json.dumps({
            "run_id": "tc-test-1",
            "target_url": "http://localhost:23000",
            "issues": issues,
        }),
        encoding="utf-8",
    )


def test_synthesize_returns_brownfield_contract(tmp_path: Path) -> None:
    target_repo = tmp_path / "app"
    target_repo.mkdir()
    report = tmp_path / "tc-report.json"
    _write_report(report, [])

    bundle = synthesize_charter_from_report(report, target_repo)

    assert bundle.contract.is_brownfield is True
    assert bundle.contract.existing_repo_path == str(target_repo.resolve())
    assert bundle.contract.project_name == "app"


def test_synthesize_one_feature_per_debt(tmp_path: Path) -> None:
    target_repo = tmp_path / "app"
    target_repo.mkdir()
    report = tmp_path / "tc-report.json"
    _write_report(
        report,
        [
            {
                "id": "v001",
                "title": "Hero text is clipped",
                "issue_type": "visual",
                "context": {"url": "/"},
            },
            {
                "id": "v002",
                "title": "CTA spacing is off",
                "issue_type": "visual",
                "context": {"url": "/"},
            },
            {
                "id": "f001",
                "title": "Settings page crashes",
                "issue_type": "functionality",
                "context": {"url": "/settings", "action_attempted": "navigate"},
            },
        ],
    )

    bundle = synthesize_charter_from_report(report, target_repo)

    assert len(bundle.feature_queue.features) == 2


def test_synthesize_orders_features_by_priority(tmp_path: Path) -> None:
    target_repo = tmp_path / "app"
    target_repo.mkdir()
    report = tmp_path / "tc-report.json"
    _write_report(
        report,
        [
            {
                "id": "v001",
                "title": "Card alignment is uneven",
                "issue_type": "visual",
                "context": {"url": "/"},
            },
            {
                "id": "f001",
                "title": "Checkout flow fails",
                "issue_type": "functionality",
                "context": {"url": "/checkout", "action_attempted": "navigate"},
            },
        ],
    )

    bundle = synthesize_charter_from_report(report, target_repo)

    assert bundle.feature_queue.features[0].title == "Checkout flow fails"
    assert bundle.feature_queue.features[0].priority < bundle.feature_queue.features[1].priority


def test_synthesize_feature_acceptance_has_routes(tmp_path: Path) -> None:
    target_repo = tmp_path / "app"
    target_repo.mkdir()
    report = tmp_path / "tc-report.json"
    _write_report(
        report,
        [
            {
                "id": "i001",
                "title": "Dashboard 500s",
                "issue_type": "functionality",
                "context": {"url": "/dashboard"},
            }
        ],
    )

    bundle = synthesize_charter_from_report(report, target_repo)

    assert "/dashboard" in bundle.feature_queue.features[0].acceptance.required_routes


def test_synthesize_must_mention_false(tmp_path: Path) -> None:
    target_repo = tmp_path / "app"
    target_repo.mkdir()
    report = tmp_path / "tc-report.json"
    _write_report(
        report,
        [
            {
                "id": "i001",
                "title": "Dashboard 500s",
                "issue_type": "functionality",
                "context": {"url": "/dashboard"},
            }
        ],
    )

    bundle = synthesize_charter_from_report(report, target_repo)

    assert all(
        feature.acceptance.must_mention_feature_id is False
        for feature in bundle.feature_queue.features
    )


def test_infer_contract_reads_pyproject(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        """
[tool.poetry]
name = "api"
version = "0.1.0"

[tool.poetry.dependencies]
python = "^3.12"
fastapi = "^0.115.0"
""".strip(),
        encoding="utf-8",
    )

    contract = _infer_contract(tmp_path, "api")

    assert contract.backend_framework == "fastapi"
    assert contract.language_backend == "python"


def test_infer_contract_reads_package_json(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"react": "18.0.0"}}),
        encoding="utf-8",
    )

    contract = _infer_contract(tmp_path, "web")

    assert contract.frontend_framework == "react"
    assert contract.language_frontend in {"typescript", "javascript"}
