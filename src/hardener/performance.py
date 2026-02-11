"""Basic performance audit for generated projects.

Analyses both frontend and backend source code for common performance
anti-patterns such as large bundles, excessive dependencies, N+1 query
patterns, missing indexes, and missing pagination.
"""

from __future__ import annotations

import asyncio
import json
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

class PerformanceIssue(BaseModel):
    """A single performance concern."""

    severity: str = Field(
        ..., description="Severity level: 'error', 'warning', or 'info'"
    )
    category: str = Field(
        ...,
        description=(
            "Issue category: 'bundle-size', 'dependency-count', 'lazy-load', "
            "'n-plus-one', 'missing-index', 'missing-pagination', etc."
        ),
    )
    description: str = Field(...)
    file: Optional[str] = Field(
        default=None, description="Relative file path (if applicable)"
    )
    line: Optional[int] = Field(
        default=None, description="Line number (if applicable)"
    )
    suggestion: str = Field(...)


class PerformanceResult(BaseModel):
    """Aggregated performance audit results."""

    issues: list[PerformanceIssue] = Field(default_factory=list)
    bundle_size_kb: Optional[float] = Field(
        default=None, description="Estimated or actual frontend bundle size in KB"
    )
    dependency_count: int = Field(
        default=0, description="Number of production dependencies"
    )
    score: float = Field(default=100.0, ge=0.0, le=100.0)


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

# Heavy imports that are often better code-split / lazy-loaded
_HEAVY_IMPORTS = {
    "moment": ("moment", "date-fns or dayjs (smaller alternatives)"),
    "lodash": ("lodash (full)", "lodash-es with tree-shaking or individual lodash/ imports"),
    "chart.js": ("chart.js", "dynamic import() to lazy-load chart library"),
    "three": ("three.js", "dynamic import() to lazy-load 3D library"),
    "d3": ("d3 (full)", "individual d3-* modules"),
    "@mui/material": ("Material UI (full)", "selective imports from @mui/material/Button etc."),
    "antd": ("Ant Design (full)", "selective imports with babel-plugin-import"),
    "firebase": ("Firebase SDK (full)", "modular Firebase v9+ imports"),
    "aws-sdk": ("AWS SDK v2 (full)", "@aws-sdk/* v3 modular clients"),
}

# N+1 query pattern: DB call inside a for loop
_RE_N_PLUS_ONE = re.compile(
    r"""
    (?:for|async\s+for)\s+\w+\s+in\s+.*:\s*\n   # loop header
    (?:[ \t]+.*\n)*?                              # loop body
    [ \t]+.*(?:                                   # line with DB operation
        \.find_one|\.find\(|\.aggregate|\.count_documents|
        \.insert_one|\.update_one|\.delete_one|
        \.replace_one|\.find_one_and
    )
    """,
    re.VERBOSE | re.MULTILINE,
)

# get_all / list endpoints missing skip/limit
_RE_LIST_ENDPOINT = re.compile(
    r"""
    @(?:router|app)\.\s*get\s*\(       # GET endpoint
    [^)]*\)\s*\n                         # end of decorator
    (?:.*\n)*?                           # function body
    async\s+def\s+(\w+)                 # function name
    """,
    re.VERBOSE | re.MULTILINE,
)

_RE_PAGINATION_PARAMS = re.compile(
    r"(?:skip|offset|limit|page|per_page|page_size)",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _read_file(path: Path) -> str:
    """Read file content asynchronously."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, path.read_text, "utf-8")


def _collect_files(root: Path, extensions: set[str]) -> list[Path]:
    """Recursively collect files, skipping common non-source directories."""
    skip = {"node_modules", "__pycache__", ".git", "dist", "build", ".venv", "venv", ".next"}
    results: list[Path] = []
    if not root.is_dir():
        return results
    for child in sorted(root.iterdir()):
        if child.is_dir():
            if child.name not in skip:
                results.extend(_collect_files(child, extensions))
        elif child.suffix in extensions:
            results.append(child)
    return results


def _relative(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _find_line(content: str, offset: int) -> int:
    return content[:offset].count("\n") + 1


# ---------------------------------------------------------------------------
# PerformanceAuditor
# ---------------------------------------------------------------------------

class PerformanceAuditor:
    """Basic performance audit for generated projects.

    Checks:
    - Frontend bundle size (measured from ``dist/`` or estimated from source)
    - Number of production dependencies in ``package.json``
    - Heavy imports that should be lazy-loaded or replaced
    - Backend N+1 query patterns
    - Missing database indexes
    - List endpoints without pagination
    """

    # Thresholds
    MAX_RECOMMENDED_DEPS = 25
    MAX_BUNDLE_KB = 500  # 500 KB warning threshold
    CRITICAL_BUNDLE_KB = 1000  # 1 MB error threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def audit(self, project_path: str | Path) -> PerformanceResult:
        """Run performance checks on *project_path*.

        Parameters
        ----------
        project_path:
            Root directory of the generated project.

        Returns
        -------
        PerformanceResult
        """
        root = Path(project_path).resolve()
        if not root.is_dir():
            return PerformanceResult(
                issues=[
                    PerformanceIssue(
                        severity="error",
                        category="project-not-found",
                        description=f"Project path does not exist: {root}",
                        suggestion="Verify the project path is correct.",
                    )
                ],
                score=0.0,
            )

        issues: list[PerformanceIssue] = []
        bundle_size_kb: float | None = None
        dep_count = 0

        frontend_dir = root / "frontend"
        backend_dir = root / "backend"

        # Run frontend and backend checks concurrently
        fe_result, be_result = await asyncio.gather(
            self._audit_frontend(frontend_dir, root) if frontend_dir.is_dir() else _empty_fe_result(),
            self._audit_backend(backend_dir, root) if backend_dir.is_dir() else _empty_list(),
        )

        fe_issues, bundle_size_kb, dep_count = fe_result
        issues.extend(fe_issues)
        issues.extend(be_result)

        score = self._calculate_score(issues)

        return PerformanceResult(
            issues=issues,
            bundle_size_kb=bundle_size_kb,
            dependency_count=dep_count,
            score=score,
        )

    # ------------------------------------------------------------------
    # Frontend Checks
    # ------------------------------------------------------------------

    async def _audit_frontend(
        self,
        frontend_dir: Path,
        root: Path,
    ) -> tuple[list[PerformanceIssue], float | None, int]:
        """Run frontend performance checks.

        Returns a tuple of (issues, bundle_size_kb, dependency_count).
        """
        issues: list[PerformanceIssue] = []
        bundle_size_kb: float | None = None
        dep_count = 0

        # ---- Bundle size ----
        dist_dir = frontend_dir / "dist"
        if dist_dir.is_dir():
            bundle_size_kb = await self._measure_bundle_size(dist_dir)
            if bundle_size_kb is not None:
                if bundle_size_kb > self.CRITICAL_BUNDLE_KB:
                    issues.append(
                        PerformanceIssue(
                            severity="error",
                            category="bundle-size",
                            description=(
                                f"Frontend bundle size is {bundle_size_kb:.0f} KB "
                                f"(threshold: {self.CRITICAL_BUNDLE_KB} KB)."
                            ),
                            suggestion=(
                                "Enable code splitting with React.lazy() and dynamic "
                                "import(). Check for large dependencies that can be "
                                "replaced with lighter alternatives."
                            ),
                        )
                    )
                elif bundle_size_kb > self.MAX_BUNDLE_KB:
                    issues.append(
                        PerformanceIssue(
                            severity="warning",
                            category="bundle-size",
                            description=(
                                f"Frontend bundle size is {bundle_size_kb:.0f} KB "
                                f"(recommended: <{self.MAX_BUNDLE_KB} KB)."
                            ),
                            suggestion=(
                                "Consider code splitting for routes and lazy-loading "
                                "heavy components."
                            ),
                        )
                    )

        # ---- Dependency count ----
        pkg_json_path = frontend_dir / "package.json"
        if pkg_json_path.is_file():
            dep_count = await self._count_dependencies(pkg_json_path)
            if dep_count > self.MAX_RECOMMENDED_DEPS:
                issues.append(
                    PerformanceIssue(
                        severity="warning",
                        category="dependency-count",
                        description=(
                            f"Project has {dep_count} production dependencies "
                            f"(recommended: <{self.MAX_RECOMMENDED_DEPS})."
                        ),
                        file=_relative(pkg_json_path, root),
                        suggestion=(
                            "Audit dependencies with 'npx depcheck' and remove unused "
                            "packages. Consider lighter alternatives for large libraries."
                        ),
                    )
                )

        # ---- Heavy imports ----
        src_dir = frontend_dir / "src"
        if src_dir.is_dir():
            ts_files = _collect_files(src_dir, {".ts", ".tsx", ".js", ".jsx"})
            for fpath in ts_files:
                content = await _read_file(fpath)
                issues.extend(
                    self._check_heavy_imports(content, _relative(fpath, root))
                )
                issues.extend(
                    self._check_missing_lazy_routes(content, _relative(fpath, root))
                )

        return issues, bundle_size_kb, dep_count

    async def _measure_bundle_size(self, dist_dir: Path) -> float | None:
        """Measure total JS + CSS bundle size in the dist directory."""
        total_bytes = 0
        js_css_files = _collect_files(dist_dir, {".js", ".css", ".mjs"})
        if not js_css_files:
            return None
        for fpath in js_css_files:
            total_bytes += fpath.stat().st_size
        return round(total_bytes / 1024, 1)

    async def _count_dependencies(self, pkg_json_path: Path) -> int:
        """Count production dependencies in package.json."""
        content = await _read_file(pkg_json_path)
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return 0
        deps = data.get("dependencies", {})
        return len(deps)

    def _check_heavy_imports(self, content: str, rel_path: str) -> list[PerformanceIssue]:
        """Detect imports of known heavy libraries that should be code-split."""
        issues: list[PerformanceIssue] = []
        lines = content.split("\n")

        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()
            if not (stripped.startswith("import ") or stripped.startswith("from ")):
                continue

            for pkg_key, (lib_name, alternative) in _HEAVY_IMPORTS.items():
                # Match import from 'moment' or import from "lodash"
                if re.search(rf"""['"]({re.escape(pkg_key)})(?:/|['"])""", stripped):
                    issues.append(
                        PerformanceIssue(
                            severity="warning",
                            category="lazy-load",
                            description=f"Static import of {lib_name} adds significant bundle weight.",
                            file=rel_path,
                            line=idx,
                            suggestion=f"Consider using {alternative}.",
                        )
                    )
                    break

        return issues

    def _check_missing_lazy_routes(self, content: str, rel_path: str) -> list[PerformanceIssue]:
        """Check for route definitions that use static imports instead of React.lazy()."""
        issues: list[PerformanceIssue] = []

        # Heuristic: if a file imports Route/Routes from react-router and
        # imports page components statically, suggest lazy loading.
        has_routes = bool(re.search(r"(?:from\s+['\"]react-router|<Route\s)", content))
        if not has_routes:
            return issues

        # Count static page imports
        page_imports = re.findall(
            r"import\s+\w+\s+from\s+['\"].*(?:Page|View|Screen)['\"]", content
        )
        if len(page_imports) > 3:
            issues.append(
                PerformanceIssue(
                    severity="info",
                    category="lazy-load",
                    description=(
                        f"{len(page_imports)} page components imported statically in "
                        f"router definition."
                    ),
                    file=rel_path,
                    suggestion=(
                        "Use React.lazy(() => import('./pages/XxxPage')) with "
                        "<Suspense> to code-split each route."
                    ),
                )
            )

        return issues

    # ------------------------------------------------------------------
    # Backend Checks
    # ------------------------------------------------------------------

    async def _audit_backend(
        self,
        backend_dir: Path,
        root: Path,
    ) -> list[PerformanceIssue]:
        """Run backend performance checks."""
        issues: list[PerformanceIssue] = []
        py_files = _collect_files(backend_dir, {".py"})

        for fpath in py_files:
            content = await _read_file(fpath)
            rel = _relative(fpath, root)
            issues.extend(self._check_n_plus_one(content, rel))
            issues.extend(self._check_missing_pagination(content, rel))
            issues.extend(self._check_missing_indexes(content, rel))
            issues.extend(self._check_sync_in_async(content, rel))

        return issues

    def _check_n_plus_one(self, content: str, rel_path: str) -> list[PerformanceIssue]:
        """Detect N+1 query patterns (DB calls inside loops)."""
        issues: list[PerformanceIssue] = []

        for m in _RE_N_PLUS_ONE.finditer(content):
            issues.append(
                PerformanceIssue(
                    severity="error",
                    category="n-plus-one",
                    description="Database query inside a loop (potential N+1 query pattern).",
                    file=rel_path,
                    line=_find_line(content, m.start()),
                    suggestion=(
                        "Batch the query using $in or aggregate pipeline. Fetch all "
                        "needed documents in a single query before the loop."
                    ),
                )
            )

        return issues

    def _check_missing_pagination(self, content: str, rel_path: str) -> list[PerformanceIssue]:
        """Check that list/GET endpoints include pagination parameters."""
        issues: list[PerformanceIssue] = []

        # Find GET endpoint functions
        lines = content.split("\n")
        for idx, line in enumerate(lines, start=1):
            if re.search(r'@(?:router|app)\.\s*get\s*\(\s*["\']/?["\']', line):
                # This is a root GET on a resource (likely a list endpoint)
                # Look at the function signature for skip/limit/page params
                func_start = idx
                func_end = min(len(lines), idx + 10)
                func_block = "\n".join(lines[func_start - 1 : func_end])

                # Check for collection-style names (list_, get_all, etc.)
                is_list = bool(
                    re.search(r"def\s+(?:list_|get_all|get_\w+s\b|index|fetch_all)", func_block)
                )
                if not is_list:
                    # Also check for find() without limit
                    if ".find(" in func_block and ".to_list()" in func_block:
                        is_list = True

                if is_list and not _RE_PAGINATION_PARAMS.search(func_block):
                    issues.append(
                        PerformanceIssue(
                            severity="warning",
                            category="missing-pagination",
                            description="List endpoint appears to return all documents without pagination.",
                            file=rel_path,
                            line=idx,
                            suggestion=(
                                "Add skip/limit or page/page_size query parameters "
                                "to prevent unbounded result sets."
                            ),
                        )
                    )

        return issues

    def _check_missing_indexes(self, content: str, rel_path: str) -> list[PerformanceIssue]:
        """Check for queries that filter on fields without obvious index setup."""
        issues: list[PerformanceIssue] = []

        # Look for find() calls with filter dictionaries
        filter_fields: list[str] = []
        for m in re.finditer(r'\.find(?:_one)?\s*\(\s*\{([^}]+)\}', content):
            # Extract field names from the filter dict
            filter_text = m.group(1)
            field_matches = re.findall(r'["\'](\w+)["\']', filter_text)
            for field in field_matches:
                if field not in ("_id", "$or", "$and", "$in", "$regex"):
                    filter_fields.append(field)

        # If we see queries on specific fields, check if there's an indexes file nearby
        if filter_fields and "indexes" not in rel_path:
            # Check if file mentions create_index
            if "create_index" not in content and "ensure_index" not in content:
                unique_fields = sorted(set(filter_fields))
                if unique_fields:
                    issues.append(
                        PerformanceIssue(
                            severity="warning",
                            category="missing-index",
                            description=(
                                f"Queries filter on fields [{', '.join(unique_fields)}] "
                                f"but no index creation found in this file."
                            ),
                            file=rel_path,
                            suggestion=(
                                "Ensure indexes are defined in db/indexes.py for fields "
                                "used in query filters. Missing indexes cause full "
                                "collection scans."
                            ),
                        )
                    )

        return issues

    def _check_sync_in_async(self, content: str, rel_path: str) -> list[PerformanceIssue]:
        """Detect synchronous blocking calls inside async functions."""
        issues: list[PerformanceIssue] = []

        blocking_calls = {
            "time.sleep(": "Use asyncio.sleep() instead of time.sleep() in async code.",
            "open(": "Use aiofiles.open() instead of synchronous file I/O in async code.",
            "requests.get(": "Use httpx.AsyncClient instead of synchronous requests library.",
            "requests.post(": "Use httpx.AsyncClient instead of synchronous requests library.",
            "requests.put(": "Use httpx.AsyncClient instead of synchronous requests library.",
            "subprocess.run(": "Use asyncio.create_subprocess_exec() for non-blocking subprocess calls.",
            "subprocess.call(": "Use asyncio.create_subprocess_exec() for non-blocking subprocess calls.",
        }

        lines = content.split("\n")
        in_async = False

        for idx, line in enumerate(lines, start=1):
            stripped = line.strip()

            if stripped.startswith("async def "):
                in_async = True
            elif stripped.startswith("def ") and not stripped.startswith("def _"):
                in_async = False
            elif stripped.startswith("class "):
                in_async = False

            if not in_async:
                continue

            for call_pattern, suggestion in blocking_calls.items():
                if call_pattern in stripped:
                    # Avoid false positives for open() used in non-file contexts
                    if call_pattern == "open(" and ("aiofiles" in content or "json.load" not in stripped):
                        if "with open(" not in stripped:
                            continue
                    issues.append(
                        PerformanceIssue(
                            severity="warning",
                            category="blocking-call",
                            description=f"Synchronous blocking call '{call_pattern.rstrip('(')}' inside async function.",
                            file=rel_path,
                            line=idx,
                            suggestion=suggestion,
                        )
                    )
                    break

        return issues

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _calculate_score(self, issues: list[PerformanceIssue]) -> float:
        """Calculate performance health score from 0 to 100."""
        weights = {"error": 8.0, "warning": 3.0, "info": 1.0}
        deductions = sum(weights.get(i.severity, 1.0) for i in issues)
        return max(0.0, round(100.0 - deductions, 1))

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def print_report(self, result: PerformanceResult) -> None:
        """Pretty-print a performance report to the console."""
        console.print("\n[bold]Performance Audit Report[/bold]\n")

        # Summary
        if result.bundle_size_kb is not None:
            size_color = (
                "green" if result.bundle_size_kb < self.MAX_BUNDLE_KB
                else "yellow" if result.bundle_size_kb < self.CRITICAL_BUNDLE_KB
                else "red"
            )
            console.print(
                f"  Bundle size: [{size_color}]{result.bundle_size_kb:.0f} KB[/{size_color}]"
            )

        dep_color = "green" if result.dependency_count <= self.MAX_RECOMMENDED_DEPS else "yellow"
        console.print(
            f"  Dependencies: [{dep_color}]{result.dependency_count}[/{dep_color}]"
        )

        if not result.issues:
            console.print("\n[green]No performance issues found.[/green]")
        else:
            table = Table(title="Performance Issues", show_lines=True)
            table.add_column("Severity", width=10)
            table.add_column("Category", width=22)
            table.add_column("Location", width=30)
            table.add_column("Description", width=50)

            severity_styles = {"error": "red", "warning": "yellow", "info": "blue"}
            for issue in result.issues:
                loc = issue.file or "-"
                if issue.line:
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
        console.print(f"\n[bold]Score:[/bold] [{score_color}]{result.score}/100[/{score_color}]\n")


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

async def _empty_list() -> list[PerformanceIssue]:
    """Async no-op returning an empty list."""
    return []


async def _empty_fe_result() -> tuple[list[PerformanceIssue], float | None, int]:
    """Async no-op returning an empty frontend result tuple."""
    return [], None, 0
