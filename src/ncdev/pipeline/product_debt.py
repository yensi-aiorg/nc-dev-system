"""Product-level debt items.

Converts raw TestCraftr issues into typed debt the Steward can reason
about. A 'dead button' is not 'fix this selector' — it's an
unsatisfied product obligation. ProductDebt captures that framing.
"""
from __future__ import annotations

import re
from collections import defaultdict
from enum import Enum
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field


class DebtType(str, Enum):
    MISSING_FEATURE = "missing_feature"
    BROKEN_FLOW = "broken_flow"
    INCOHERENT_NAVIGATION = "incoherent_navigation"
    DEAD_CONTROL = "dead_control"
    VISUAL_POLISH = "visual_polish"
    REGRESSION = "regression"
    AMBIGUOUS_PRD = "ambiguous_prd"


class SuggestedDisposition(str, Enum):
    """Maps directly to Steward Disposition values where they overlap."""

    DIRECT_FIX = "direct_fix"
    FEATURE_RERUN = "feature_rerun"
    NEW_FEATURE_INSERTION = "new_feature_insertion"
    CHARTER_AMENDMENT = "charter_amendment"
    TEST_AMENDMENT = "test_amendment"


class ProductDebt(BaseModel):
    debt_id: str
    debt_type: DebtType
    title: str
    description: str
    source_issue_ids: list[str] = Field(default_factory=list)
    affected_feature_ids: list[str] = Field(default_factory=list)
    affected_routes: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    suggested_disposition: SuggestedDisposition = SuggestedDisposition.DIRECT_FIX
    confidence: float = 0.5


_DEBT_DISPOSITIONS: dict[DebtType, SuggestedDisposition] = {
    DebtType.MISSING_FEATURE: SuggestedDisposition.NEW_FEATURE_INSERTION,
    DebtType.BROKEN_FLOW: SuggestedDisposition.FEATURE_RERUN,
    DebtType.INCOHERENT_NAVIGATION: SuggestedDisposition.CHARTER_AMENDMENT,
    DebtType.DEAD_CONTROL: SuggestedDisposition.DIRECT_FIX,
    DebtType.VISUAL_POLISH: SuggestedDisposition.DIRECT_FIX,
    DebtType.REGRESSION: SuggestedDisposition.FEATURE_RERUN,
    DebtType.AMBIGUOUS_PRD: SuggestedDisposition.CHARTER_AMENDMENT,
}


def classify_issues_to_debt(
    tc_issues: list[dict[str, Any]],
    *,
    known_feature_ids: list[str] | None = None,
    known_routes: list[str] | None = None,
) -> list[ProductDebt]:
    """Group + classify raw TestCraftr issues into product-level debt.

    Group rules:
      - Multiple visual issues on the same URL → ONE visual_polish debt.
      - Multiple functionality issues on the same URL → ONE broken_flow
        or dead_control debt depending on context.action_attempted (if
        'click' or 'submit' → dead_control; else broken_flow).
      - An issue whose URL doesn't map to any known_feature_id/route →
        missing_feature debt (the planner didn't anticipate this URL).
      - console/network issues by URL → broken_flow if same URL has a
        functionality issue, otherwise own broken_flow debt.
      - accessibility / performance → own debt of type matching their
        category (DebtType.VISUAL_POLISH for both for now —
        accessibility is the next iteration).

    Confidence is a heuristic — 0.9 when classification is unambiguous
    (single issue type, clear URL), 0.5 when grouped, 0.3 when the
    fallback (own debt per issue) was used.
    """
    issues_by_url: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for issue in tc_issues:
        issues_by_url[_issue_path(issue)].append(issue)

    known_route_paths = (
        {_normalise_path(route) for route in known_routes}
        if known_routes is not None
        else None
    )

    debts: list[ProductDebt] = []
    for index, (url_path, issues) in enumerate(issues_by_url.items(), start=1):
        categories = [_issue_category(issue) for issue in issues]
        category_set = set(categories)
        functionality_issues = [
            issue for issue in issues if _issue_category(issue) == "functionality"
        ]
        has_functionality = bool(functionality_issues)
        fallback_used = False

        if (
            has_functionality
            and len(functionality_issues) == 1
            and _issue_action(functionality_issues[0]) in {"click", "submit"}
        ):
            debt_type = DebtType.DEAD_CONTROL
        elif has_functionality or _is_mixed_group(category_set):
            debt_type = DebtType.BROKEN_FLOW
        elif category_set == {"visual"}:
            debt_type = DebtType.VISUAL_POLISH
        elif category_set and category_set.issubset({"performance", "accessibility"}):
            debt_type = DebtType.VISUAL_POLISH
        elif category_set and category_set.issubset({"console", "network"}):
            debt_type = DebtType.BROKEN_FLOW
        else:
            debt_type = DebtType.BROKEN_FLOW
            fallback_used = True

        affected_feature_ids = _affected_feature_ids(issues, known_feature_ids)
        if (
            known_route_paths is not None
            and url_path
            and url_path not in known_route_paths
            and not affected_feature_ids
        ):
            debt_type = DebtType.MISSING_FEATURE
            fallback_used = False

        title_source = _group_title(issues, url_path, debt_type)
        slug = _slugify(title_source or url_path or "issue")
        confidence = _confidence(issues, url_path, category_set, fallback_used)
        debts.append(
            ProductDebt(
                debt_id=f"d{index:03d}-{slug}",
                debt_type=debt_type,
                title=title_source,
                description=_description(issues, url_path, debt_type),
                source_issue_ids=[str(issue.get("id", "")) for issue in issues],
                affected_feature_ids=affected_feature_ids,
                affected_routes=[url_path] if url_path else [],
                evidence=[str(issue.get("id", "")) for issue in issues],
                suggested_disposition=_DEBT_DISPOSITIONS[debt_type],
                confidence=confidence,
            )
        )

    return debts


def _issue_context(issue: dict[str, Any]) -> dict[str, Any]:
    context = issue.get("context", {})
    return context if isinstance(context, dict) else {}


def _issue_path(issue: dict[str, Any]) -> str:
    return _normalise_path(str(_issue_context(issue).get("url", "")))


def _normalise_path(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.scheme or parsed.netloc:
        path = parsed.path
    else:
        path = url.split("?", 1)[0].split("#", 1)[0]
    if not path:
        return "/"
    return path if path.startswith("/") else f"/{path}"


def _issue_category(issue: dict[str, Any]) -> str:
    return str(issue.get("category") or issue.get("type") or "").lower()


def _issue_action(issue: dict[str, Any]) -> str:
    return str(_issue_context(issue).get("action_attempted", "")).lower()


def _is_mixed_group(category_set: set[str]) -> bool:
    return len(category_set) > 1 and bool(category_set & {"console", "network", "ux"})


def _affected_feature_ids(
    issues: list[dict[str, Any]],
    known_feature_ids: list[str] | None,
) -> list[str]:
    if not known_feature_ids:
        return []
    found: list[str] = []
    for issue in issues:
        haystack = [
            str(issue.get("feature_id", "")),
            *[str(v) for v in issue.get("affected_files_hint", [])],
            *[str(v) for v in _issue_context(issue).values()],
        ]
        for feature_id in known_feature_ids:
            if feature_id in found:
                continue
            if any(feature_id in value for value in haystack):
                found.append(feature_id)
    return found


def _group_title(
    issues: list[dict[str, Any]],
    url_path: str,
    debt_type: DebtType,
) -> str:
    titles = [str(issue.get("title", "")).strip() for issue in issues]
    titles = [title for title in titles if title]
    if len(titles) == 1:
        return titles[0]
    if len(set(titles)) == 1:
        return titles[0]
    label = debt_type.value.replace("_", " ")
    return f"{label.title()} at {url_path or 'unknown route'}"


def _description(
    issues: list[dict[str, Any]],
    url_path: str,
    debt_type: DebtType,
) -> str:
    issue_count = len(issues)
    issue_label = "issue" if issue_count == 1 else "issues"
    route = url_path or "an unknown route"
    categories = ", ".join(sorted({_issue_category(issue) for issue in issues}))
    return (
        f"{issue_count} TestCraftr {issue_label} on {route} classified as "
        f"{debt_type.value}. Categories: {categories or 'unknown'}."
    )


def _confidence(
    issues: list[dict[str, Any]],
    url_path: str,
    category_set: set[str],
    fallback_used: bool,
) -> float:
    if fallback_used:
        return 0.3
    if len(issues) == 1 and len(category_set) == 1 and url_path:
        return 0.9
    return 0.5


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:48].strip("-") or "issue"
