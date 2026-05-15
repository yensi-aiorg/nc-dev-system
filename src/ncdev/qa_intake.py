from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _slug(text: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in text).strip("-")
    return "-".join(part for part in cleaned.split("-") if part)[:80] or "project"


@dataclass(frozen=True)
class ManualQAImport:
    project: str
    run_id: str
    status: str
    report_copy: str
    metadata_path: str
    fix_task_path: str


@dataclass(frozen=True)
class TestCraftrIssue:
    issue_id: str
    title: str
    severity: str = "medium"
    issue_type: str = "functionality"
    status: str = "open"
    url: str = ""
    description: str = ""
    expected_behavior: str = ""
    actual_behavior: str = ""
    evidence: list[str] | None = None
    notes: str = ""
    possible_causes: list[str] | None = None
    recommended_action: str = ""
    context: dict[str, Any] | None = None


@dataclass(frozen=True)
class TestCraftrReport:
    run_id: str
    target_url: str = ""
    date: str = ""
    status: str = ""
    summary: dict[str, str] | None = None
    issues: list[TestCraftrIssue] | None = None
    source_path: str = ""


_TEST_CRAFTR_SECTION_RE = re.compile(r"^## Issue #(?P<num>\d+): (?P<title>.+)$", re.MULTILINE)
_TEST_CRAFTR_FIELD_ROW_RE = re.compile(r"^\| \*\*(?P<key>[^*]+)\*\* \| (?P<value>.*?) \|$", re.MULTILINE)


def import_manual_qa_report(
    *,
    workspace: Path,
    report_path: Path,
    target_repo: Path,
    project: str | None = None,
    base_url: str = "",
) -> ManualQAImport:
    """Persist a manual QA report as NC-dev actionable intake.

    The report remains human-readable Markdown, while the adjacent metadata and
    generated fix task give NC-dev a stable handoff point for bugfix sessions.
    Product code still lives in the target repository.
    """
    workspace = workspace.resolve()
    report_path = report_path.resolve()
    target_repo = target_repo.resolve()

    if not report_path.exists():
        raise FileNotFoundError(f"QA report not found: {report_path}")
    if not target_repo.exists():
        raise FileNotFoundError(f"Target repo not found: {target_repo}")

    project_name = project or target_repo.name
    run_id = f"manual-qa-{_slug(project_name)}-{_utc_stamp()}"
    intake_dir = workspace / ".nc-dev" / "manual-qa" / _slug(project_name) / run_id
    intake_dir.mkdir(parents=True, exist_ok=True)

    report_copy = intake_dir / report_path.name
    shutil.copy2(report_path, report_copy)

    metadata: dict[str, Any] = {
        "schema": "manual-qa-intake.v1",
        "project": project_name,
        "run_id": run_id,
        "status": "queued",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_report": str(report_path),
        "target_repo": str(target_repo),
        "base_url": base_url,
        "report_copy": str(report_copy),
    }
    report_text = report_path.read_text(encoding="utf-8")
    test_craftr_report = load_test_craftr_report(report_path) if looks_like_test_craftr_report(report_text) else None
    if test_craftr_report:
        metadata["source_format"] = "test-craftr"
        metadata["test_craftr"] = test_craftr_to_dict(test_craftr_report)
        metadata["issue_count"] = len(test_craftr_report.issues or [])
    else:
        metadata["source_format"] = "manual-markdown"
    metadata_path = intake_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")

    issue_digest = _test_craftr_issue_digest(test_craftr_report)
    fix_task = f"""# NC-dev Manual QA Fix Task

Project: {project_name}
Target repo: {target_repo}
Base URL: {base_url or "(not specified)"}
QA report: {report_copy}
Intake run: {run_id}

## Task

Use this manual QA report as the authoritative bugfix backlog. Fix every P1/P2/P3
finding that is actionable in the target repository, then run focused automated
tests and repeat the production-style QA checks.

## Required workflow

1. Read the QA report below and inspect the target repo.
2. Convert each finding into a reproduction check or regression test where practical.
3. Fix issues in severity order without unrelated refactors.
4. Verify locally with the target repo's build/test commands.
5. Re-run route/interaction QA against the relevant local or deployed URL.
6. Update this intake status and produce a concise fix report.

{issue_digest}
## QA Report

{report_text}
"""
    fix_task_path = intake_dir / "fix-task.md"
    fix_task_path.write_text(fix_task)

    return ManualQAImport(
        project=project_name,
        run_id=run_id,
        status="queued",
        report_copy=str(report_copy),
        metadata_path=str(metadata_path),
        fix_task_path=str(fix_task_path),
    )


def list_manual_qa_imports(*, workspace: Path, project: str | None = None) -> list[dict]:
    root = workspace.resolve() / ".nc-dev" / "manual-qa"
    if project:
        roots = [root / _slug(project)]
    else:
        roots = [p for p in root.iterdir()] if root.exists() else []

    imports: list[dict] = []
    for project_root in roots:
        if not project_root.exists():
            continue
        for metadata_path in sorted(project_root.glob("*/metadata.json")):
            try:
                imports.append(json.loads(metadata_path.read_text()))
            except json.JSONDecodeError:
                imports.append({
                    "project": project_root.name,
                    "run_id": metadata_path.parent.name,
                    "status": "corrupt",
                    "metadata_path": str(metadata_path),
                })
    return imports


def update_manual_qa_status(
    *,
    workspace: Path,
    project: str,
    run_id: str,
    status: str,
    note: str = "",
) -> dict:
    metadata_path = (
        workspace.resolve()
        / ".nc-dev"
        / "manual-qa"
        / _slug(project)
        / run_id
        / "metadata.json"
    )
    if not metadata_path.exists():
        raise FileNotFoundError(f"Manual QA intake not found: {metadata_path}")

    metadata = json.loads(metadata_path.read_text())
    metadata["status"] = status
    metadata["updated_at"] = datetime.now(timezone.utc).isoformat()
    if note:
        metadata.setdefault("notes", []).append({
            "at": metadata["updated_at"],
            "note": note,
        })
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata


def import_to_dict(item: ManualQAImport) -> dict:
    return asdict(item)


def looks_like_test_craftr_report(markdown: str) -> bool:
    return "# TestCraftr Issues Report" in markdown or bool(_TEST_CRAFTR_SECTION_RE.search(markdown))


def load_test_craftr_report(path: Path) -> TestCraftrReport:
    """Load a Test Craftr report from Markdown or JSON."""
    if not path.exists():
        raise FileNotFoundError(f"Test Craftr report not found: {path}")
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return _load_test_craftr_json(text, source_path=path)
    return parse_test_craftr_markdown(text, source_path=path)


def parse_test_craftr_markdown(markdown: str, *, source_path: Path | None = None) -> TestCraftrReport:
    run_id = _metadata(markdown, "Run ID") or f"test-craftr-{_utc_stamp()}"
    target_url = _metadata(markdown, "Target URL")
    date = _metadata(markdown, "Date")
    status = _metadata(markdown, "Status")
    summary = _parse_summary(markdown)

    matches = list(_TEST_CRAFTR_SECTION_RE.finditer(markdown))
    issues: list[TestCraftrIssue] = []
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(markdown)
        block = markdown[start:end]
        fields = {
            m.group("key").strip().lower(): m.group("value").strip()
            for m in _TEST_CRAFTR_FIELD_ROW_RE.finditer(block)
        }
        issues.append(
            TestCraftrIssue(
                issue_id=f"tc-{run_id}-{match.group('num')}",
                title=match.group("title").strip(),
                severity=fields.get("severity", "medium").lower(),
                issue_type=fields.get("type", "functionality").lower(),
                status=fields.get("status", "open").lower(),
                url=fields.get("url", target_url),
                description=_section_text(block, "Description"),
                expected_behavior=_section_text(block, "Expected Behavior"),
                actual_behavior=_section_text(block, "Actual Behavior"),
                evidence=_section_list(block, "Evidence"),
                notes=_section_text(block, "Notes"),
                possible_causes=_section_numbered_list(block, "Possible Causes"),
                recommended_action=_section_text(block, "Recommended Action"),
            )
        )

    return TestCraftrReport(
        run_id=run_id,
        target_url=target_url,
        date=date,
        status=status,
        summary=summary,
        issues=issues,
        source_path=str(source_path) if source_path else "",
    )


def test_craftr_to_dict(report: TestCraftrReport) -> dict:
    return asdict(report)


def _load_test_craftr_json(text: str, *, source_path: Path) -> TestCraftrReport:
    raw = json.loads(text)
    if "issues" not in raw or "run_id" not in raw:
        raise ValueError("unsupported Test Craftr JSON report shape")
    issues = [
        TestCraftrIssue(
            issue_id=str(issue.get("issue_id", issue.get("id", f"tc-{raw['run_id']}-{idx + 1}"))),
            title=str(issue.get("title", "")),
            severity=str(issue.get("severity", "medium")).lower(),
            issue_type=str(issue.get("issue_type", issue.get("type", "functionality"))).lower(),
            status=str(issue.get("status", "open")).lower(),
            url=str(issue.get("url", _json_issue_context(issue).get("url", raw.get("target_url", "")))),
            description=str(issue.get("description", "")),
            expected_behavior=str(issue.get("expected_behavior", "")),
            actual_behavior=str(issue.get("actual_behavior", "")),
            evidence=list(issue.get("evidence") or []),
            notes=str(issue.get("notes", "")),
            possible_causes=list(issue.get("possible_causes") or []),
            recommended_action=str(issue.get("recommended_action", "")),
            context=_json_issue_context(issue),
        )
        for idx, issue in enumerate(raw.get("issues", []))
    ]
    return TestCraftrReport(
        run_id=str(raw["run_id"]),
        target_url=str(raw.get("target_url", "")),
        date=str(raw.get("date", "")),
        status=str(raw.get("status", "")),
        summary=dict(raw.get("summary", {})),
        issues=issues,
        source_path=str(source_path),
    )


def _json_issue_context(issue: dict) -> dict:
    context = issue.get("context", {})
    return context if isinstance(context, dict) else {}


def _metadata(markdown: str, label: str) -> str:
    pattern = re.compile(rf"^\*\*{re.escape(label)}\*\*: ?(.+)$", re.MULTILINE)
    match = pattern.search(markdown)
    return match.group(1).strip() if match else ""


def _parse_summary(markdown: str) -> dict[str, str]:
    summary_match = re.search(r"## Summary\s+(?P<body>.*?)(?:\n---|\n## |\Z)", markdown, re.DOTALL)
    if not summary_match:
        return {}
    summary: dict[str, str] = {}
    for line in summary_match.group("body").splitlines():
        if not line.startswith("|") or "---" in line or "Metric" in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) == 2:
            summary[cells[0]] = cells[1]
    return summary


def _section_text(block: str, heading: str) -> str:
    match = re.search(
        rf"^### {re.escape(heading)}\s*(?P<body>.*?)(?=^### |^---\s*$|^## |\Z)",
        block,
        re.DOTALL | re.MULTILINE,
    )
    if not match:
        return ""
    return _strip_code_fence(match.group("body").strip())


def _section_list(block: str, heading: str) -> list[str]:
    text = _section_text(block, heading)
    return [line[2:].strip() for line in text.splitlines() if line.startswith("- ")]


def _section_numbered_list(block: str, heading: str) -> list[str]:
    text = _section_text(block, heading)
    items: list[str] = []
    for line in text.splitlines():
        item = re.sub(r"^\d+\.\s+", "", line).strip()
        if item and item != line:
            items.append(item)
    return items


def _strip_code_fence(text: str) -> str:
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        return "\n".join(lines[1:-1]).strip()
    return text


def _test_craftr_issue_digest(report: TestCraftrReport | None) -> str:
    if not report:
        return ""
    issues = report.issues or []
    lines = [
        "## Parsed Test Craftr Issues",
        "",
        f"Run ID: {report.run_id}",
        f"Target URL: {report.target_url or '(not specified)'}",
        f"Issues found: {len(issues)}",
        "",
    ]
    for issue in issues:
        lines.append(f"- [{issue.severity.upper()}] {issue.title}")
        if issue.url:
            lines.append(f"  URL: {issue.url}")
        if issue.expected_behavior:
            lines.append(f"  Expected: {_single_line(issue.expected_behavior)}")
        if issue.actual_behavior:
            lines.append(f"  Actual: {_single_line(issue.actual_behavior)}")
        if issue.recommended_action:
            lines.append(f"  Recommended action: {_single_line(issue.recommended_action)}")
    lines.append("")
    return "\n".join(lines)


def _single_line(text: str) -> str:
    return " ".join(text.split())
