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
                "issues": [
                    {
                        "issue_id": "issue-1",
                        "title": "Route failed",
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

