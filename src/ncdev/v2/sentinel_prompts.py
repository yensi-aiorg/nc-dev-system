from __future__ import annotations

from ncdev.v2.models import ErrorSource, SentinelFailureReport

_BACKEND_REPRODUCTION_TEMPLATE = """\
You are a senior software engineer. A production error has been reported by Sentinel.

## Failure Report
{report_json}

## Source Code
### {error_file}
{error_file_contents}

### Related Files
{related_file_contents}

## Existing Tests
{existing_test_contents}

## Recent Commits
{git_log}

## Your Task
Write a single test function that reproduces this exact failure.

Rules:
1. The test MUST fail with the same error type as the report ({error_type})
2. Place the test in the appropriate test file (follow existing test file conventions)
3. Name the test: test_sentinel_{report_id}_{brief_description}
4. Include a docstring: "Reproduction test for {report_id}: {error_message}"
5. Use existing test fixtures and patterns from the codebase
6. Do NOT fix the bug — only write the reproduction test
7. The test should cover the specific scenario described in the failure report
"""

_FRONTEND_REPRODUCTION_TEMPLATE = """\
You are a senior frontend engineer. A production error has been reported by Sentinel.

## Failure Report
{report_json}

## Component Code
### {error_file}
{error_file_contents}

### Related Components
{related_file_contents}

## Existing Tests
{existing_test_contents}

## User Interaction Trail
{interaction_trail}

## Your Task
Write a test that reproduces this exact failure.

Rules:
1. If this is a component error, write a Vitest + React Testing Library test
2. If this is a page-level or interaction error, write a Playwright E2E test
3. Simulate the user interaction trail from the report
4. The test MUST fail with the reported error
5. Name the test: test_sentinel_{report_id}_{brief_description}
6. Do NOT fix the bug — only write the reproduction test
"""

_FIX_TEMPLATE = """\
Your reproduction test correctly fails with:
  {test_failure_output}

Now fix the code so that the test passes.

Rules:
1. Do NOT modify the reproduction test
2. Only modify source code files
3. Make the minimal change needed to fix the issue
4. Do not refactor, restructure, or "improve" surrounding code
5. If the fix requires changes to multiple files, that's fine — make all necessary changes
"""


def _slugify(text: str) -> str:
    return text.lower().replace(" ", "_").replace("'", "")[:40]


def _format_related(related: dict[str, str]) -> str:
    if not related:
        return "(none)"
    parts: list[str] = []
    for path, content in related.items():
        parts.append(f"### {path}\n{content}")
    return "\n\n".join(parts)


def build_reproduction_prompt(
    *,
    report: SentinelFailureReport,
    error_file_contents: str,
    related_file_contents: dict[str, str],
    existing_test_contents: str,
    git_log: str,
) -> str:
    report_json = report.model_dump_json(indent=2)
    brief = _slugify(report.error.message)

    if report.source == ErrorSource.FRONTEND:
        interaction_trail = "\n".join(
            report.frontend_context.interaction_trail
        ) if report.frontend_context else "(none)"
        return _FRONTEND_REPRODUCTION_TEMPLATE.format(
            report_json=report_json,
            error_file=report.error.file or "(unknown)",
            error_file_contents=error_file_contents or "(not available)",
            related_file_contents=_format_related(related_file_contents),
            existing_test_contents=existing_test_contents or "(none)",
            interaction_trail=interaction_trail,
            error_type=report.error.error_type,
            report_id=report.report_id,
            brief_description=brief,
            error_message=report.error.message,
        )

    return _BACKEND_REPRODUCTION_TEMPLATE.format(
        report_json=report_json,
        error_file=report.error.file or "(unknown)",
        error_file_contents=error_file_contents or "(not available)",
        related_file_contents=_format_related(related_file_contents),
        existing_test_contents=existing_test_contents or "(none)",
        git_log=git_log or "(none)",
        error_type=report.error.error_type,
        report_id=report.report_id,
        brief_description=brief,
        error_message=report.error.message,
    )


def build_fix_prompt(
    *,
    report: SentinelFailureReport,
    test_failure_output: str,
) -> str:
    return _FIX_TEMPLATE.format(
        test_failure_output=test_failure_output,
    )


_VITEST_ERROR_TYPES = {
    "REACT_RENDER_ERROR",
    "REACT_EFFECT_ERROR",
    "REACT_EVENT_ERROR",
    "STATE_ERROR",
}

_PLAYWRIGHT_ERROR_TYPES = {
    "NETWORK_ERROR",
    "API_ERROR",
    "TIMEOUT_ERROR",
    "ROUTING_ERROR",
    "PERFORMANCE_LCP",
    "PERFORMANCE_CLS",
    "PERFORMANCE_INP",
}

_KNOWN_MONOREPO_PREFIXES = ("api/", "ui/", "backend/", "frontend/", "server/", "client/", "web/", "app/")


def detect_frontend_test_type(error_type: str) -> str:
    """Return 'vitest' for component/state errors, 'playwright' for page/network errors."""
    if error_type in _VITEST_ERROR_TYPES:
        return "vitest"
    return "playwright"


def detect_monorepo_subdir(file_path: str) -> str | None:
    """Detect monorepo subdirectory from a file path. Returns None if not a monorepo layout."""
    for prefix in _KNOWN_MONOREPO_PREFIXES:
        if file_path.startswith(prefix):
            return prefix.rstrip("/")
    return None
