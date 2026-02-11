"""Error handling audit for generated projects.

Scans frontend (React/TypeScript) and backend (Python/FastAPI) source code
for common error handling omissions such as missing error boundaries,
unhandled promises, bare except clauses, and missing validation.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field
from rich.console import Console
from rich.table import Table

console = Console()


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

class AuditIssue(BaseModel):
    """A single issue discovered during the error audit."""

    severity: str = Field(
        ..., description="Severity level: 'error', 'warning', or 'info'"
    )
    category: str = Field(
        ...,
        description=(
            "Issue category, e.g. 'error-boundary', 'unhandled-promise', "
            "'bare-except', 'missing-validation'"
        ),
    )
    file: str = Field(..., description="Relative file path from project root")
    line: Optional[int] = Field(
        default=None, description="Line number where the issue was found"
    )
    description: str = Field(..., description="Human-readable description of the issue")
    suggestion: str = Field(..., description="Suggested fix for the issue")


class AuditResult(BaseModel):
    """Aggregated result of an error handling audit."""

    issues: list[AuditIssue] = Field(default_factory=list)
    warnings: list[AuditIssue] = Field(default_factory=list)
    score: float = Field(
        default=100.0,
        ge=0.0,
        le=100.0,
        description="Overall error handling score (0-100, higher is better)",
    )


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# Frontend patterns (TypeScript / React)
_RE_PROMISE_NO_CATCH = re.compile(
    r"""
    \.then\s*\(          # .then(
    [^)]*\)              # callback body
    (?!\s*\.catch)       # NOT followed by .catch
    (?!\s*\.\s*finally)  # NOT followed by .finally
    """,
    re.VERBOSE,
)

_RE_ASYNC_NO_TRY = re.compile(
    r"""
    async\s+\w+         # async functionName or async arrow
    [^{]*\{             # opening brace
    (?:(?!try\s*\{).)*? # body without try {
    await\s+            # await keyword
    """,
    re.VERBOSE | re.DOTALL,
)

_RE_AXIOS_NO_CATCH = re.compile(
    r"""
    (?:axios|api)\s*\.   # axios. or api.
    (?:get|post|put|patch|delete)\s*\(  # HTTP method
    [^;]*;               # statement end
    """,
    re.VERBOSE,
)

_RE_ZUSTAND_STORE = re.compile(
    r"create\s*<\s*\w+",
)

_RE_LOADING_STATE = re.compile(
    r"isLoading\s*:",
)

_RE_ERROR_STATE = re.compile(
    r"error\s*:\s*(?:string|null|Error)",
)

_RE_ERROR_BOUNDARY = re.compile(
    r"(?:ErrorBoundary|componentDidCatch|getDerivedStateFromError)",
)

# Backend patterns (Python / FastAPI)
_RE_BARE_EXCEPT = re.compile(
    r"^\s*except\s*:\s*$",
    re.MULTILINE,
)

_RE_EXCEPT_PASS = re.compile(
    r"except[^:]*:\s*\n\s+pass\s*$",
    re.MULTILINE,
)

_RE_ENDPOINT_DECORATOR = re.compile(
    r"@(?:router|app)\.\s*(?:get|post|put|patch|delete)\s*\(",
)

_RE_RESPONSE_MODEL = re.compile(
    r"response_model\s*=",
)

_RE_DB_QUERY_IN_LOOP = re.compile(
    r"""
    (?:for|async\s+for)\s+\w+\s+in\s+  # for x in ...
    [^:]+:\s*\n                          # colon + newline
    (?:.*\n)*?                           # intervening lines
    .*(?:find_one|find|insert|update|delete|aggregate)  # DB operation
    """,
    re.VERBOSE | re.MULTILINE,
)

_RE_PYDANTIC_VALIDATE = re.compile(
    r"(?:BaseModel|Field\(|validator|field_validator|model_validator)",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _read_file_async(path: Path) -> str:
    """Read a file's content asynchronously."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, path.read_text, "utf-8")


def _collect_files(root: Path, extensions: set[str]) -> list[Path]:
    """Recursively collect files matching the given extensions, skipping
    node_modules, __pycache__, .git, dist, and build directories."""
    skip_dirs = {"node_modules", "__pycache__", ".git", "dist", "build", ".venv", "venv"}
    results: list[Path] = []
    for child in sorted(root.iterdir()):
        if child.is_dir():
            if child.name in skip_dirs:
                continue
            results.extend(_collect_files(child, extensions))
        elif child.suffix in extensions:
            results.append(child)
    return results


def _relative(path: Path, root: Path) -> str:
    """Return *path* relative to *root* as a forward-slash string."""
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _find_line(content: str, match_start: int) -> int:
    """Return the 1-based line number for a character offset."""
    return content[:match_start].count("\n") + 1


# ---------------------------------------------------------------------------
# ErrorAuditor
# ---------------------------------------------------------------------------

class ErrorAuditor:
    """Audits a generated project for error handling issues.

    Scans both frontend (React/TypeScript) and backend (Python/FastAPI)
    source trees, producing a structured :class:`AuditResult` with
    file-and-line references for every finding.
    """

    # Weights for score deduction per severity
    _SEVERITY_WEIGHTS = {"error": 5.0, "warning": 2.0, "info": 0.5}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def audit(self, project_path: str | Path) -> AuditResult:
        """Scan *project_path* for error handling issues.

        Parameters
        ----------
        project_path:
            Root directory of the generated project.

        Returns
        -------
        AuditResult
            Structured results with file:line references.
        """
        root = Path(project_path).resolve()
        if not root.is_dir():
            return AuditResult(
                issues=[
                    AuditIssue(
                        severity="error",
                        category="project-not-found",
                        file=str(root),
                        line=None,
                        description=f"Project path does not exist: {root}",
                        suggestion="Verify the project path is correct.",
                    )
                ],
                score=0.0,
            )

        frontend_dir = root / "frontend"
        backend_dir = root / "backend"

        all_issues: list[AuditIssue] = []

        # Run frontend and backend audits concurrently.
        frontend_coro = (
            self._audit_frontend(frontend_dir, root)
            if frontend_dir.is_dir()
            else asyncio.coroutine(lambda: [])()  # type: ignore[arg-type]
        )
        backend_coro = (
            self._audit_backend(backend_dir, root)
            if backend_dir.is_dir()
            else asyncio.coroutine(lambda: [])()  # type: ignore[arg-type]
        )

        fe_issues, be_issues = await asyncio.gather(
            self._audit_frontend(frontend_dir, root) if frontend_dir.is_dir() else _empty_list(),
            self._audit_backend(backend_dir, root) if backend_dir.is_dir() else _empty_list(),
        )
        all_issues.extend(fe_issues)
        all_issues.extend(be_issues)

        errors = [i for i in all_issues if i.severity == "error"]
        warnings = [i for i in all_issues if i.severity in ("warning", "info")]

        score = self._calculate_score(all_issues)

        return AuditResult(issues=errors, warnings=warnings, score=score)

    # ------------------------------------------------------------------
    # Frontend Checks
    # ------------------------------------------------------------------

    async def _audit_frontend(self, frontend_dir: Path, root: Path) -> list[AuditIssue]:
        """Run all frontend error-handling checks."""
        if not frontend_dir.is_dir():
            return []

        ts_files = _collect_files(frontend_dir / "src", {".ts", ".tsx"}) if (frontend_dir / "src").is_dir() else []
        issues: list[AuditIssue] = []

        for fpath in ts_files:
            content = await _read_file_async(fpath)
            rel = _relative(fpath, root)
            issues.extend(self._check_unhandled_promises(content, rel))
            issues.extend(self._check_axios_without_error_handling(content, rel))
            issues.extend(self._check_store_missing_states(content, rel))

        issues.extend(await self._check_error_boundaries(frontend_dir, root))

        return issues

    def _check_unhandled_promises(self, content: str, rel_path: str) -> list[AuditIssue]:
        """Detect .then() chains missing .catch() and async functions missing try/catch around await."""
        issues: list[AuditIssue] = []

        for m in _RE_PROMISE_NO_CATCH.finditer(content):
            issues.append(
                AuditIssue(
                    severity="error",
                    category="unhandled-promise",
                    file=rel_path,
                    line=_find_line(content, m.start()),
                    description="Promise .then() chain without .catch() handler.",
                    suggestion=(
                        "Add a .catch() handler or wrap in try/catch. "
                        "Unhandled promise rejections crash the app silently."
                    ),
                )
            )

        # Check for await outside try/catch -- simplified heuristic:
        # look for lines with `await` that are NOT inside a try block.
        lines = content.split("\n")
        in_try_block = 0
        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            if stripped.startswith("try") and "{" in stripped:
                in_try_block += 1
            if in_try_block > 0:
                in_try_block += stripped.count("{") - stripped.count("}")
                if in_try_block < 0:
                    in_try_block = 0
            if "await " in stripped and in_try_block <= 0 and "catch" not in stripped:
                # Skip if the line is inside a store action (they are expected to handle
                # errors in the store pattern)
                if ".catch(" not in stripped:
                    issues.append(
                        AuditIssue(
                            severity="warning",
                            category="unhandled-promise",
                            file=rel_path,
                            line=idx,
                            description="'await' call without surrounding try/catch block.",
                            suggestion=(
                                "Wrap the await call in a try/catch block or ensure the "
                                "caller handles the rejection."
                            ),
                        )
                    )

        return issues

    def _check_axios_without_error_handling(self, content: str, rel_path: str) -> list[AuditIssue]:
        """Detect direct axios/api calls that lack error handling."""
        issues: list[AuditIssue] = []

        # Simple heuristic: look for api.get/post/... calls on lines
        # not immediately preceded by 'try' or followed by '.catch'.
        lines = content.split("\n")
        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            if re.search(r"(?:axios|api)\.\s*(?:get|post|put|patch|delete)\s*\(", stripped):
                # Check surrounding context for try/catch
                context_start = max(0, idx - 4)
                context_end = min(len(lines), idx + 3)
                context = "\n".join(lines[context_start:context_end])
                if "try" not in context and ".catch(" not in context:
                    issues.append(
                        AuditIssue(
                            severity="error",
                            category="api-no-error-handling",
                            file=rel_path,
                            line=idx,
                            description="API call without error handling (no try/catch or .catch).",
                            suggestion=(
                                "Wrap the API call in a try/catch block within a Zustand "
                                "store action and set an error state on failure."
                            ),
                        )
                    )

        return issues

    def _check_store_missing_states(self, content: str, rel_path: str) -> list[AuditIssue]:
        """Check Zustand stores for missing isLoading and error states."""
        issues: list[AuditIssue] = []

        if not _RE_ZUSTAND_STORE.search(content):
            return issues

        if not _RE_LOADING_STATE.search(content):
            issues.append(
                AuditIssue(
                    severity="warning",
                    category="missing-loading-state",
                    file=rel_path,
                    line=None,
                    description="Zustand store is missing an 'isLoading' state field.",
                    suggestion=(
                        "Add 'isLoading: boolean' to the store interface and toggle "
                        "it in async actions to drive loading indicators."
                    ),
                )
            )

        if not _RE_ERROR_STATE.search(content):
            issues.append(
                AuditIssue(
                    severity="warning",
                    category="missing-error-state",
                    file=rel_path,
                    line=None,
                    description="Zustand store is missing an 'error' state field.",
                    suggestion=(
                        "Add 'error: string | null' to the store interface and set it "
                        "in catch blocks so components can display error messages."
                    ),
                )
            )

        return issues

    async def _check_error_boundaries(self, frontend_dir: Path, root: Path) -> list[AuditIssue]:
        """Check that at least one React Error Boundary exists in the project."""
        issues: list[AuditIssue] = []
        src_dir = frontend_dir / "src"
        if not src_dir.is_dir():
            return issues

        all_tsx = _collect_files(src_dir, {".tsx", ".ts"})
        boundary_found = False
        for fpath in all_tsx:
            content = await _read_file_async(fpath)
            if _RE_ERROR_BOUNDARY.search(content):
                boundary_found = True
                break

        if not boundary_found:
            issues.append(
                AuditIssue(
                    severity="error",
                    category="error-boundary",
                    file=_relative(src_dir / "App.tsx", root),
                    line=None,
                    description=(
                        "No React Error Boundary found in the frontend. "
                        "Unhandled render errors will crash the entire app."
                    ),
                    suggestion=(
                        "Create an ErrorBoundary component using componentDidCatch or "
                        "react-error-boundary package and wrap the top-level <App /> "
                        "component with it."
                    ),
                )
            )

        return issues

    # ------------------------------------------------------------------
    # Backend Checks
    # ------------------------------------------------------------------

    async def _audit_backend(self, backend_dir: Path, root: Path) -> list[AuditIssue]:
        """Run all backend error-handling checks."""
        if not backend_dir.is_dir():
            return []

        py_files = _collect_files(backend_dir, {".py"})
        issues: list[AuditIssue] = []

        for fpath in py_files:
            content = await _read_file_async(fpath)
            rel = _relative(fpath, root)
            issues.extend(self._check_bare_excepts(content, rel))
            issues.extend(self._check_except_pass(content, rel))
            issues.extend(self._check_endpoint_error_responses(content, rel))
            issues.extend(self._check_missing_validation(content, rel))
            issues.extend(self._check_db_error_handling(content, rel))

        return issues

    def _check_bare_excepts(self, content: str, rel_path: str) -> list[AuditIssue]:
        """Detect bare 'except:' clauses (catching everything including SystemExit)."""
        issues: list[AuditIssue] = []
        for m in _RE_BARE_EXCEPT.finditer(content):
            issues.append(
                AuditIssue(
                    severity="error",
                    category="bare-except",
                    file=rel_path,
                    line=_find_line(content, m.start()),
                    description="Bare 'except:' clause catches all exceptions including SystemExit and KeyboardInterrupt.",
                    suggestion="Use 'except Exception:' or a more specific exception type.",
                )
            )
        return issues

    def _check_except_pass(self, content: str, rel_path: str) -> list[AuditIssue]:
        """Detect 'except ...: pass' patterns that silently swallow errors."""
        issues: list[AuditIssue] = []
        for m in _RE_EXCEPT_PASS.finditer(content):
            issues.append(
                AuditIssue(
                    severity="error",
                    category="silent-exception",
                    file=rel_path,
                    line=_find_line(content, m.start()),
                    description="Exception caught and silently ignored with 'pass'.",
                    suggestion=(
                        "At minimum, log the exception. Consider re-raising or "
                        "returning an appropriate error response."
                    ),
                )
            )
        return issues

    def _check_endpoint_error_responses(self, content: str, rel_path: str) -> list[AuditIssue]:
        """Check that API endpoints define error response models (responses= or raises HTTPException)."""
        issues: list[AuditIssue] = []

        if not _RE_ENDPOINT_DECORATOR.search(content):
            return issues

        lines = content.split("\n")
        for idx, line in enumerate(lines, start=1):
            if re.search(r"@(?:router|app)\.\s*(?:get|post|put|patch|delete)\s*\(", line):
                # Look at the decorator and function body for error response info
                context_end = min(len(lines), idx + 20)
                func_body = "\n".join(lines[idx - 1 : context_end])
                has_error_response = (
                    "responses=" in func_body
                    or "HTTPException" in func_body
                    or "AppException" in func_body
                    or "NotFoundException" in func_body
                    or "raise" in func_body
                )
                if not has_error_response:
                    issues.append(
                        AuditIssue(
                            severity="warning",
                            category="missing-error-response",
                            file=rel_path,
                            line=idx,
                            description="API endpoint has no explicit error handling or error response definitions.",
                            suggestion=(
                                "Add 'responses={404: ...}' to the decorator or raise "
                                "HTTPException / AppException for error cases."
                            ),
                        )
                    )

        return issues

    def _check_missing_validation(self, content: str, rel_path: str) -> list[AuditIssue]:
        """Check that endpoint files use Pydantic validation for request bodies."""
        issues: list[AuditIssue] = []

        if not _RE_ENDPOINT_DECORATOR.search(content):
            return issues

        # If there are POST/PUT/PATCH endpoints, check for Pydantic models
        has_mutation = bool(
            re.search(r"@(?:router|app)\.\s*(?:post|put|patch)\s*\(", content)
        )
        if has_mutation and not _RE_PYDANTIC_VALIDATE.search(content):
            # Check if there's a type annotation referencing a schema
            has_typed_body = bool(
                re.search(r"(?:body|data|payload|item|request)\s*:\s*\w+(?:Create|Update|Request|Schema|Input)", content)
            )
            if not has_typed_body:
                issues.append(
                    AuditIssue(
                        severity="error",
                        category="missing-validation",
                        file=rel_path,
                        line=None,
                        description=(
                            "Mutation endpoint (POST/PUT/PATCH) found without Pydantic "
                            "request body validation."
                        ),
                        suggestion=(
                            "Define a Pydantic BaseModel schema for the request body "
                            "and use it as a type annotation in the endpoint function."
                        ),
                    )
                )

        return issues

    def _check_db_error_handling(self, content: str, rel_path: str) -> list[AuditIssue]:
        """Check that database operations have error handling."""
        issues: list[AuditIssue] = []

        db_operations = [
            "find_one", "find", "insert_one", "insert_many",
            "update_one", "update_many", "delete_one", "delete_many",
            "aggregate", "replace_one",
        ]

        lines = content.split("\n")
        for idx, line in enumerate(lines, start=1):
            for op in db_operations:
                if op in line and "self.collection" in line:
                    # Check surrounding context for try/catch
                    context_start = max(0, idx - 6)
                    context_end = min(len(lines), idx + 3)
                    context = "\n".join(lines[context_start:context_end])
                    if "try:" not in context and "except" not in context:
                        issues.append(
                            AuditIssue(
                                severity="warning",
                                category="unhandled-db-error",
                                file=rel_path,
                                line=idx,
                                description=f"Database operation '{op}' without surrounding try/except block.",
                                suggestion=(
                                    "Wrap database operations in try/except to handle "
                                    "connection errors, timeouts, and duplicate key errors."
                                ),
                            )
                        )
                    break  # Only one issue per line

        return issues

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _calculate_score(self, issues: list[AuditIssue]) -> float:
        """Calculate an error handling health score from 0 to 100.

        Each issue deducts points based on severity. The floor is 0.
        """
        deductions = sum(
            self._SEVERITY_WEIGHTS.get(issue.severity, 1.0) for issue in issues
        )
        return max(0.0, round(100.0 - deductions, 1))

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def print_report(self, result: AuditResult) -> None:
        """Pretty-print an audit report to the console using Rich."""
        console.print("\n[bold]Error Handling Audit Report[/bold]\n")

        table = Table(title="Issues Found", show_lines=True)
        table.add_column("Severity", style="bold", width=10)
        table.add_column("Category", width=24)
        table.add_column("Location", width=40)
        table.add_column("Description", width=50)

        all_items = result.issues + result.warnings
        severity_styles = {
            "error": "red",
            "warning": "yellow",
            "info": "blue",
        }

        for issue in sorted(all_items, key=lambda i: ("error", "warning", "info").index(i.severity) if i.severity in ("error", "warning", "info") else 3):
            loc = issue.file
            if issue.line is not None:
                loc += f":{issue.line}"
            style = severity_styles.get(issue.severity, "white")
            table.add_row(
                f"[{style}]{issue.severity.upper()}[/{style}]",
                issue.category,
                loc,
                issue.description,
            )

        console.print(table)
        score_color = "green" if result.score >= 80 else "yellow" if result.score >= 50 else "red"
        console.print(f"\n[bold]Score:[/bold] [{score_color}]{result.score}/100[/{score_color}]")
        console.print(f"  Errors: {len(result.issues)}  |  Warnings: {len(result.warnings)}\n")


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

async def _empty_list() -> list[AuditIssue]:
    """Coroutine that returns an empty list (used as a no-op fallback)."""
    return []
