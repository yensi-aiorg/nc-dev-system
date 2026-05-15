"""Synthesize a CharterBundle from a TestCraftr issue report.

The factory loop's normal input is a PRD that gets fed to charter
generation. Bug-fix mode bypasses that: we already know what's wrong
(the issues), so we manufacture a charter whose features are
'resolve debt X' and 'resolve debt Y'. The verification contract
inherits from the existing brownfield target_repo where possible.
"""
from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any, Iterable

from ncdev.qa_intake import TestCraftrIssue, TestCraftrReport, load_test_craftr_report
from ncdev.pipeline.models import (
    CharterBundle,
    FeatureAcceptance,
    FeatureQueueDoc,
    FeatureStep,
    TargetProjectContract,
    VerificationContract,
)
from ncdev.pipeline.product_debt import (
    DebtType,
    ProductDebt,
    SuggestedDisposition,
    classify_issues_to_debt,
)


def synthesize_charter_from_report(
    report_path: Path,
    target_repo: Path,
    *,
    project_name: str | None = None,
) -> CharterBundle:
    """Build a CharterBundle whose features are 'fix each debt item'."""
    report = load_test_craftr_report(report_path)
    target_repo = target_repo.expanduser().resolve()
    resolved_project_name = project_name or target_repo.name

    issue_dicts = [_issue_to_classifier_dict(issue) for issue in report.issues or []]
    known_routes = sorted({
        str(issue.get("context", {}).get("url", ""))
        for issue in issue_dicts
        if issue.get("context", {}).get("url")
    })
    debts = classify_issues_to_debt(
        issue_dicts,
        known_routes=known_routes or None,
    )
    issues_by_id = {issue.issue_id: issue for issue in report.issues or []}

    return CharterBundle(
        contract=_infer_contract(target_repo, resolved_project_name),
        verification=_infer_verification(target_repo),
        feature_queue=FeatureQueueDoc(
            generator="ncdev.pipeline.issue_charter",
            project_name=resolved_project_name,
            features=sorted(
                [
                    _feature_for_debt(
                        debt,
                        issues_by_id=issues_by_id,
                        report=report,
                    )
                    for debt in debts
                ],
                key=lambda feature: (feature.priority, feature.feature_id),
            ),
            sprint_zero_criteria=[
                "Existing test suite still passes",
                "Each listed TestCraftr debt item is fixed or made non-reproducible",
            ],
        ),
    )


def _infer_contract(target_repo: Path, project_name: str) -> TargetProjectContract:
    """Infer a minimal brownfield target contract from common project files."""
    target_repo = target_repo.expanduser().resolve()
    package_data, package_path = _read_package_json(target_repo)
    pyproject_data = _read_pyproject(target_repo)

    frontend_framework = _detect_frontend_framework(package_data)
    backend_framework = _detect_backend_framework(pyproject_data, package_data)
    language_frontend = _detect_frontend_language(package_data, package_path)
    language_backend = "python" if pyproject_data else _detect_backend_language(package_data)
    ports = _infer_ports(target_repo, bool(frontend_framework), bool(backend_framework))

    return TargetProjectContract(
        project_name=project_name,
        project_type=_project_type(frontend_framework, backend_framework),
        is_brownfield=True,
        existing_repo_path=str(target_repo),
        backend_framework=backend_framework,
        frontend_framework=frontend_framework,
        language_backend=language_backend,
        language_frontend=language_frontend,
        ports=ports,
        design_system_source="existing",
        uses_citex=True,
        uses_mock_apis=False,
    )


def _infer_verification(target_repo: Path) -> VerificationContract:
    """Infer minimal brownfield verification commands from project markers."""
    target_repo = target_repo.expanduser().resolve()
    package_data, package_path = _read_package_json(target_repo)
    has_pyproject = (target_repo / "pyproject.toml").exists()

    return VerificationContract(
        backend_test_command="pytest" if has_pyproject else "",
        frontend_test_command=_npm_test_command(package_data, package_path, target_repo),
        minimum_test_count=0,
        required_files=[],
        prohibited_patterns=["TODO", "FIXME"],
        assets_manifest_required=False,
        require_tests_in_commit=False,
    )


def _priority_for_debt(debt: ProductDebt) -> int:
    """Return 1=highest priority for factory issue repair ordering."""
    if debt.suggested_disposition == SuggestedDisposition.NEW_FEATURE_INSERTION:
        return 1

    debt_rank = {
        DebtType.BROKEN_FLOW: 2,
        DebtType.DEAD_CONTROL: 3,
        DebtType.PERFORMANCE: 4,
        DebtType.REGRESSION: 5,
        DebtType.VISUAL_POLISH: 6,
        DebtType.INCOHERENT_NAVIGATION: 7,
        DebtType.AMBIGUOUS_PRD: 8,
        DebtType.MISSING_FEATURE: 1,
    }
    priority = debt_rank.get(debt.debt_type, 8)
    if len(debt.evidence) >= 3 and priority > 2:
        priority -= 1
    return priority


def _feature_for_debt(
    debt: ProductDebt,
    *,
    issues_by_id: dict[str, TestCraftrIssue],
    report: TestCraftrReport,
) -> FeatureStep:
    related_issues = [
        issues_by_id[issue_id]
        for issue_id in debt.source_issue_ids
        if issue_id in issues_by_id
    ]
    evidence_lines = _evidence_lines(debt, related_issues)
    recommendations = _recommendations(related_issues)

    description = debt.description
    if evidence_lines:
        description += "\n\nEvidence:\n" + "\n".join(f"- {line}" for line in evidence_lines)
    if report.target_url:
        description += f"\n\nTestCraftr target URL: {report.target_url}"

    criteria = [
        debt.title,
        "Existing behavior not related to this debt remains intact",
        *recommendations,
    ]

    return FeatureStep(
        feature_id=f"fix-{_slug(debt.debt_id)}",
        title=debt.title,
        description=description,
        acceptance_criteria=_dedupe(criteria),
        test_requirements=["Run the target repository's existing relevant tests"],
        priority=_priority_for_debt(debt),
        estimated_complexity=_complexity_for_debt(debt),
        acceptance=FeatureAcceptance(
            required_routes=list(debt.affected_routes),
            must_mention_feature_id=False,
        ),
    )


def _issue_to_classifier_dict(issue: TestCraftrIssue) -> dict[str, Any]:
    evidence = issue.evidence or []
    context = dict(issue.context or {})
    context.setdefault("url", issue.url)
    return {
        "id": issue.issue_id,
        "title": issue.title,
        "severity": issue.severity,
        "type": issue.issue_type,
        "category": issue.issue_type,
        "status": issue.status,
        "description": issue.description,
        "expected_behavior": issue.expected_behavior,
        "actual_behavior": issue.actual_behavior,
        "evidence": list(evidence),
        "recommended_action": issue.recommended_action,
        "context": context,
    }


def _read_package_json(target_repo: Path) -> tuple[dict[str, Any], Path | None]:
    candidates = [
        target_repo / "package.json",
        target_repo / "frontend" / "package.json",
        target_repo / "web" / "package.json",
        target_repo / "app" / "package.json",
    ]
    for path in candidates:
        if not path.exists():
            continue
        try:
            return json.loads(path.read_text(encoding="utf-8")), path
        except json.JSONDecodeError:
            return {}, path
    return {}, None


def _read_pyproject(target_repo: Path) -> dict[str, Any]:
    path = target_repo / "pyproject.toml"
    if not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError:
        return {}


def _detect_frontend_framework(package_data: dict[str, Any]) -> str:
    deps = _package_deps(package_data)
    if "next" in deps:
        return "next"
    if "react" in deps:
        return "react"
    if "vue" in deps:
        return "vue"
    if "svelte" in deps:
        return "svelte"
    return ""


def _detect_backend_framework(
    pyproject_data: dict[str, Any],
    package_data: dict[str, Any],
) -> str:
    py_deps = _python_deps(pyproject_data)
    if "fastapi" in py_deps:
        return "fastapi"
    if "django" in py_deps:
        return "django"
    if "flask" in py_deps:
        return "flask"

    js_deps = _package_deps(package_data)
    if "express" in js_deps:
        return "express"
    return ""


def _detect_frontend_language(
    package_data: dict[str, Any],
    package_path: Path | None,
) -> str:
    if not package_data:
        return ""
    deps = _package_deps(package_data)
    package_dir = package_path.parent if package_path else None
    if "typescript" in deps or (package_dir and (package_dir / "tsconfig.json").exists()):
        return "typescript"
    return "javascript"


def _detect_backend_language(package_data: dict[str, Any]) -> str:
    return "javascript" if _detect_backend_framework({}, package_data) else ""


def _project_type(frontend_framework: str, backend_framework: str) -> str:
    if frontend_framework:
        return "web"
    if backend_framework:
        return "api"
    return "web"


def _infer_ports(
    target_repo: Path,
    has_frontend: bool,
    has_backend: bool,
) -> dict[str, int]:
    ports: dict[str, int] = {}
    compose_ports = _ports_from_compose(target_repo)
    if compose_ports:
        return compose_ports
    if has_frontend:
        ports["frontend"] = 23000
    if has_backend:
        ports["backend"] = 23001
    return ports


def _ports_from_compose(target_repo: Path) -> dict[str, int]:
    for name in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
        path = target_repo / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        matches = re.findall(r"['\"]?(\d{2,5}):(\d{2,5})['\"]?", text)
        if matches:
            return {
                f"port_{index}": int(host)
                for index, (host, _container) in enumerate(matches, start=1)
            }
    return {}


def _package_deps(package_data: dict[str, Any]) -> set[str]:
    deps: set[str] = set()
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        value = package_data.get(key, {})
        if isinstance(value, dict):
            deps.update(str(name).lower() for name in value)
    return deps


def _python_deps(pyproject_data: dict[str, Any]) -> set[str]:
    deps: set[str] = set()
    project_deps = pyproject_data.get("project", {}).get("dependencies", [])
    if isinstance(project_deps, list):
        deps.update(_dependency_name(dep) for dep in project_deps)

    poetry_deps = (
        pyproject_data.get("tool", {})
        .get("poetry", {})
        .get("dependencies", {})
    )
    if isinstance(poetry_deps, dict):
        deps.update(str(dep).lower() for dep in poetry_deps)
    return {dep for dep in deps if dep}


def _dependency_name(value: str) -> str:
    return re.split(r"[<>=~!;\[]", str(value).lower(), maxsplit=1)[0].strip()


def _npm_test_command(
    package_data: dict[str, Any],
    package_path: Path | None,
    target_repo: Path,
) -> str:
    if not package_data or "test" not in package_data.get("scripts", {"test": ""}):
        return "npm test" if package_data else ""
    if package_path and package_path.parent != target_repo:
        rel = package_path.parent.relative_to(target_repo)
        return f"cd {rel} && npm test"
    return "npm test"


def _evidence_lines(
    debt: ProductDebt,
    issues: Iterable[TestCraftrIssue],
) -> list[str]:
    lines = list(debt.evidence)
    for issue in issues:
        if issue.expected_behavior:
            lines.append(f"{issue.issue_id} expected: {issue.expected_behavior}")
        if issue.actual_behavior:
            lines.append(f"{issue.issue_id} actual: {issue.actual_behavior}")
        for item in issue.evidence or []:
            lines.append(f"{issue.issue_id}: {item}")
    return _dedupe(lines)


def _recommendations(issues: Iterable[TestCraftrIssue]) -> list[str]:
    return _dedupe(
        issue.recommended_action
        for issue in issues
        if issue.recommended_action
    )


def _complexity_for_debt(debt: ProductDebt) -> str:
    if debt.suggested_disposition == SuggestedDisposition.NEW_FEATURE_INSERTION:
        return "high"
    if debt.debt_type in {DebtType.BROKEN_FLOW, DebtType.REGRESSION}:
        return "medium"
    return "low"


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = " ".join(str(value).split())
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:64].strip("-") or "issue"
