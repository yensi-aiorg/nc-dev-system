"""Synthesize a CharterBundle from a Sentinel production failure report.

A production failure is just an issue. Rather than a parallel fix
engine, we manufacture a one-feature charter ("reproduce and fix
<error>") and hand it to the factory loop -- the same machinery that
builds features. The verification contract is inherited from the
registered service's test commands.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

from ncdev.core.config import SentinelServiceConfig
from ncdev.core.models import ErrorSeverity, ErrorSource, SentinelFailureReport
from ncdev.pipeline.models import (
    CharterBundle,
    FeatureAcceptance,
    FeatureQueueDoc,
    FeatureStep,
    TargetProjectContract,
    VerificationContract,
)


def synthesize_charter_from_sentinel_report(
    report: SentinelFailureReport,
    service: SentinelServiceConfig,
    repo_dir: Path,
    *,
    reproduction_test_path: str | None = None,
) -> CharterBundle:
    """Build a one-feature CharterBundle for a Sentinel fix.

    repo_dir is the local checkout of the service repo.
    reproduction_test_path, when provided (after the S16 reproduction
    step authors the failing test), is wired in as the feature's
    required_test so the verifier re-runs it.
    """
    repo_dir = repo_dir.expanduser().resolve()
    feature = _feature_for_report(
        report,
        reproduction_test_path=reproduction_test_path,
    )

    return CharterBundle(
        contract=_infer_contract(report, service, repo_dir),
        verification=_infer_verification(report, service),
        feature_queue=FeatureQueueDoc(
            generator="ncdev.sentinel_charter",
            project_name=report.service.name,
            features=[feature],
            sprint_zero_criteria=[
                "The production failure has a regression test",
                "The reported error is fixed",
                "Existing test suite still passes",
            ],
        ),
    )


def feature_id_for_report(report: SentinelFailureReport) -> str:
    """Stable feature_id for a report -- fix-<slug(report_id)>."""
    return f"fix-{_slug(report.report_id)}"


def _infer_contract(
    report: SentinelFailureReport,
    service: SentinelServiceConfig,
    repo_dir: Path,
) -> TargetProjectContract:
    package_data, package_path = _read_package_json(repo_dir)
    pyproject_data = _read_pyproject(repo_dir)

    frontend_framework = _detect_frontend_framework(package_data)
    backend_framework = _detect_backend_framework(pyproject_data, package_data)
    service_language = service.language.strip().lower()

    language_frontend = _detect_frontend_language(package_data, package_path)
    language_backend = "python" if pyproject_data else _detect_backend_language(package_data)

    if report.source == ErrorSource.BACKEND:
        language_backend = service_language or language_backend
    elif service_language in {"javascript", "typescript"}:
        language_frontend = service_language

    return TargetProjectContract(
        project_name=report.service.name,
        project_type="api" if report.source == ErrorSource.BACKEND else "web",
        is_brownfield=True,
        existing_repo_path=str(repo_dir),
        backend_framework=backend_framework,
        frontend_framework=frontend_framework,
        language_backend=language_backend,
        language_frontend=language_frontend,
        ports=_infer_ports(
            repo_dir,
            has_frontend=bool(frontend_framework),
            has_backend=bool(backend_framework),
        ),
        design_system_source="existing",
        uses_citex=True,
        uses_mock_apis=False,
    )


def _infer_verification(
    report: SentinelFailureReport,
    service: SentinelServiceConfig,
) -> VerificationContract:
    commands = service.test_commands
    backend_test_command = commands.get("backend", "")
    frontend_test_command = commands.get("frontend", "")

    if report.source == ErrorSource.BACKEND and not backend_test_command:
        backend_test_command = commands.get("unit", "")
    if report.source == ErrorSource.FRONTEND and not frontend_test_command:
        frontend_test_command = commands.get("unit", "")

    return VerificationContract(
        backend_test_command=backend_test_command,
        frontend_test_command=frontend_test_command,
        e2e_test_command=commands.get("e2e", ""),
        minimum_test_count=0,
        prohibited_patterns=["TODO", "FIXME"],
        assets_manifest_required=False,
        require_tests_in_commit=False,
    )


def _feature_for_report(
    report: SentinelFailureReport,
    *,
    reproduction_test_path: str | None,
) -> FeatureStep:
    return FeatureStep(
        feature_id=feature_id_for_report(report),
        title=f"Fix {report.error.error_type}: {report.error.message[:80]}",
        description=_description_for_report(report),
        acceptance_criteria=[
            "The reported error no longer occurs",
            "A regression test reproduces then verifies the fix",
            "The existing test suite still passes",
        ],
        test_requirements=[
            "Run the Sentinel reproduction test and the service's existing tests",
        ],
        priority=1,
        estimated_complexity=(
            "high"
            if report.severity in {ErrorSeverity.CRITICAL, ErrorSeverity.HIGH}
            else "medium"
        ),
        acceptance=FeatureAcceptance(
            required_files=[report.error.file] if report.error.file else [],
            required_tests=[reproduction_test_path] if reproduction_test_path else [],
            required_routes=[],
            required_screenshots=[],
            must_mention_feature_id=False,
            verify_app_boots=False,
        ),
    )


def _description_for_report(report: SentinelFailureReport) -> str:
    location = report.error.file or "(unknown file)"
    if report.error.line is not None:
        location = f"{location}:{report.error.line}"

    function_or_component = report.error.function or report.error.component or ""
    lines = [
        "Production Sentinel failure:",
        f"- report_id: {report.report_id}",
        f"- service: {report.service.name}",
        f"- source: {report.source.value}",
        f"- severity: {report.severity.value}",
        f"- error_type: {report.error.error_type}",
        f"- error_code: {report.error.error_code}",
        f"- message: {report.error.message}",
        f"- location: {location}",
        f"- function/component: {function_or_component or '(not provided)'}",
        (
            "- frequency: "
            f"last_hour={report.frequency.last_hour}, "
            f"last_24h={report.frequency.last_24h}, "
            f"affected_users={report.frequency.affected_users}"
        ),
    ]

    if report.context.recent_deploys:
        lines.append("- recent_deploys:")
        lines.extend(
            "  - "
            f"{deploy.sha} at {deploy.timestamp.isoformat()}: {deploy.message}"
            for deploy in report.context.recent_deploys
        )

    if report.error.stack_trace:
        lines.extend([
            "- stack_trace:",
            _truncate(report.error.stack_trace, limit=2000),
        ])

    return "\n".join(lines)


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


def _infer_ports(
    target_repo: Path,
    *,
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


def _truncate(value: str, *, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 15].rstrip() + "\n... (truncated)"


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:60].strip("-") or "report"
