from ncdev.pipeline.product_debt import (
    DebtType,
    SuggestedDisposition,
    check_performance_budget,
    classify_issues_to_debt,
)


def _issue(
    issue_id: str,
    *,
    url: str = "http://localhost:3000/settings",
    category: str = "visual",
    action: str = "",
    title: str = "Issue",
    affected_files_hint: list[str] | None = None,
    metric_name: str | None = None,
    metric_value: float | None = None,
    threshold: float | None = None,
) -> dict:
    issue = {
        "id": issue_id,
        "severity": "medium",
        "category": category,
        "type": category,
        "title": title,
        "context": {
            "url": url,
            "action_attempted": action,
            "actual": "actual result",
            "expected": "expected result",
        },
        "affected_files_hint": affected_files_hint or [],
    }
    if metric_name is not None:
        issue["metric_name"] = metric_name
    if metric_value is not None:
        issue["metric_value"] = metric_value
    if threshold is not None:
        issue["threshold"] = threshold
    return issue


def test_classify_single_visual_issue_is_visual_polish():
    debts = classify_issues_to_debt([
        _issue("i001", title="Button color is wrong"),
    ])

    assert len(debts) == 1
    assert debts[0].debt_type == DebtType.VISUAL_POLISH
    assert debts[0].suggested_disposition == SuggestedDisposition.DIRECT_FIX
    assert debts[0].confidence == 0.9
    assert debts[0].source_issue_ids == ["i001"]
    assert debts[0].evidence == ["i001"]


def test_classify_groups_visual_issues_per_url():
    debts = classify_issues_to_debt([
        _issue("i001", title="Spacing is wrong"),
        _issue("i002", title="Text contrast is low"),
    ])

    assert len(debts) == 1
    assert debts[0].debt_type == DebtType.VISUAL_POLISH
    assert debts[0].source_issue_ids == ["i001", "i002"]
    assert debts[0].confidence == 0.5


def test_classify_functionality_click_is_dead_control():
    debts = classify_issues_to_debt([
        _issue(
            "i001",
            category="functionality",
            action="click",
            title="Save button does nothing",
        ),
    ])

    assert len(debts) == 1
    assert debts[0].debt_type == DebtType.DEAD_CONTROL
    assert debts[0].suggested_disposition == SuggestedDisposition.DIRECT_FIX


def test_classify_functionality_multi_is_broken_flow():
    debts = classify_issues_to_debt([
        _issue("i001", category="functionality", action="click"),
        _issue("i002", category="functionality", action="click"),
    ])

    assert len(debts) == 1
    assert debts[0].debt_type == DebtType.BROKEN_FLOW
    assert debts[0].suggested_disposition == SuggestedDisposition.FEATURE_RERUN


def test_classify_unknown_url_is_missing_feature_when_routes_given():
    debts = classify_issues_to_debt(
        [_issue("i001", title="Settings page does not exist")],
        known_routes=["/dashboard"],
    )

    assert len(debts) == 1
    assert debts[0].debt_type == DebtType.MISSING_FEATURE
    assert debts[0].suggested_disposition == SuggestedDisposition.NEW_FEATURE_INSERTION
    assert debts[0].affected_routes == ["/settings"]


def test_classify_known_url_is_not_missing_feature():
    debts = classify_issues_to_debt(
        [_issue("i001", title="Settings page visual issue")],
        known_routes=["/settings"],
    )

    assert len(debts) == 1
    assert debts[0].debt_type == DebtType.VISUAL_POLISH


def test_classify_performance_routes_to_perf_type():
    debts = classify_issues_to_debt([
        _issue(
            "i001",
            category="performance",
            title="Slow load",
            url="/dashboard",
        )
    ])
    assert len(debts) == 1
    assert debts[0].debt_type == DebtType.PERFORMANCE
    assert debts[0].suggested_disposition == SuggestedDisposition.DIRECT_FIX


def test_classify_perf_evidence_includes_metric_strings():
    """Issue with metric_name/value/threshold -> evidence has formatted string."""
    issue = _issue("i001", category="performance", url="/x")
    issue["metric_name"] = "lcp_ms"
    issue["metric_value"] = 4200
    issue["threshold"] = 2500
    debts = classify_issues_to_debt([issue])
    assert any(
        "lcp_ms" in e and "4200" in e and "2500" in e
        for e in debts[0].evidence
    )


def test_accessibility_still_visual_polish_for_now():
    debts = classify_issues_to_debt([
        _issue(
            "i001",
            category="accessibility",
            title="Missing alt text",
        )
    ])
    assert debts[0].debt_type == DebtType.VISUAL_POLISH


def test_suggested_disposition_matches_debt_type():
    debts = classify_issues_to_debt([
        _issue("i001", category="visual", title="Visual issue", url="/visual"),
        _issue(
            "i002",
            category="functionality",
            action="click",
            title="Dead control",
            url="/dead-control",
        ),
        _issue(
            "i003",
            category="functionality",
            action="navigate",
            title="Broken flow",
            url="/broken-flow",
        ),
        _issue(
            "i004",
            category="visual",
            title="Missing route",
            url="/missing-route",
        ),
    ], known_routes=["/visual", "/dead-control", "/broken-flow"])
    dispositions = {
        debt.debt_type: debt.suggested_disposition
        for debt in debts
    }

    assert dispositions[DebtType.VISUAL_POLISH] == SuggestedDisposition.DIRECT_FIX
    assert dispositions[DebtType.DEAD_CONTROL] == SuggestedDisposition.DIRECT_FIX
    assert dispositions[DebtType.BROKEN_FLOW] == SuggestedDisposition.FEATURE_RERUN
    assert (
        dispositions[DebtType.MISSING_FEATURE]
        == SuggestedDisposition.NEW_FEATURE_INSERTION
    )


def test_debt_id_is_unique_and_slugged():
    debts = classify_issues_to_debt([
        _issue("i001", title="Save Button Does Nothing!", url="/settings"),
        _issue("i002", title="Save Button Does Nothing!", url="/profile"),
    ])

    assert [debt.debt_id for debt in debts] == [
        "d001-save-button-does-nothing",
        "d002-save-button-does-nothing",
    ]


def test_check_performance_budget_finds_violation():
    measured = {"/dashboard": {"lcp_ms": 4200}}
    budget = {"/dashboard": {"lcp_ms": 2500}}
    violations = check_performance_budget(measured, budget)
    assert len(violations) == 1
    assert violations[0]["metric"] == "lcp_ms"
    assert violations[0]["observed"] == 4200
    assert violations[0]["severity"] == "high"


def test_check_performance_budget_critical_when_2x():
    v = check_performance_budget(
        {"/x": {"lcp_ms": 6000}},
        {"/x": {"lcp_ms": 2500}},
    )
    assert v[0]["severity"] == "critical"


def test_check_performance_budget_returns_empty_when_under_budget():
    v = check_performance_budget(
        {"/x": {"lcp_ms": 1800}},
        {"/x": {"lcp_ms": 2500}},
    )
    assert v == []
