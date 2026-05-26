from __future__ import annotations

import json
from pathlib import Path

from ncdev.contracts.verification_report import (
    load_verification_report,
    summarize_verification_report,
)


def test_load_and_summarize_testcraftr_verification_report(tmp_path: Path) -> None:
    path = tmp_path / "verification-report.v1.json"
    path.write_text(
        json.dumps(
            {
                "run_id": "tc-local-1",
                "contract_id": "bc-1",
                "target_url": "http://localhost:3000",
                "verdict": "fail",
                "suggested_action": "repair",
                "coverage": {"scenarios_total": 2, "scenarios_failed": 1},
                "scenario_results": [
                    {
                        "scenario_id": "s1",
                        "verdict": "fail",
                        "route_probes": [{"url": "/x", "ok": False}],
                        "file_checks": [{"path": "missing.py", "exists": False}],
                        "browser_smokes": [{"url": "/x", "ok": False}],
                        "interaction_steps": [{"action": "click", "ok": False}],
                        "visual_checks": [
                            {"baseline_path": "base.png", "ok": False}
                        ],
                    }
                ],
                "command_results": [{"name": "unit", "ok": False}],
                "persona_results": [{"persona": "inspector", "verdict": "fail"}],
                "issues": [
                    {
                        "issue_id": "issue-1",
                        "title": "Route failed",
                        "issue_type": "behavior",
                        "blocking": True,
                    },
                    {
                        "issue_id": "issue-2",
                        "title": "Advisory polish",
                        "blocking": False,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    report = load_verification_report(path)
    summary = summarize_verification_report(report)

    assert report.passed is False
    assert len(report.blocking_issues) == 1
    assert summary["verdict"] == "fail"
    assert summary["blocking_issue_count"] == 1
    assert summary["coverage"] == {"scenarios_total": 2, "scenarios_failed": 1}
    assert summary["failure_categories"] == {
        "route": 1,
        "file": 1,
        "browser": 1,
        "interaction": 1,
        "visual": 1,
        "command": 1,
        "persona": 1,
    }
    assert summary["issue_types"] == {"behavior": 2}
    assert summary["persona_results"] == [
        {"persona": "inspector", "verdict": "fail", "finding_count": 0}
    ]
