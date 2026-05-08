"""Project state scanner — determines which features are already implemented.

Used in brownfield runs to skip features that the existing codebase already
satisfies. The scanner is intentionally STRICT: a feature is only marked
SKIPPED when its declared :class:`FeatureAcceptance` is fully satisfied on
disk and (where applicable) over the test runner. Loose keyword/stem
heuristics — the previous implementation — silently marked features done
based on tangentially-named files (e.g. ``node_modules/oauth-client/`` was
enough to "complete" a User Authentication feature). That is the failure
mode this module exists to prevent.

Skip rule:

    A feature is SKIPPED if and only if **all** of the following hold:

    1. A Conventional Commit on the current branch names the feature_id
       (``feat(<feature_id>):``, ``fix(<feature_id>):``, etc.).
    2. ``feature.acceptance.required_files`` is non-empty AND every entry
       exists in the working tree.
    3. ``feature.acceptance.required_tests`` is non-empty AND every entry
       exists AND, when ``must_mention_feature_id`` is True, references
       the feature_id literally AND runs green.
    4. The repo's smoke test (``pytest -q -x``, scoped to the test file
       set above) actually passes — "no tests" no longer counts.

Features whose acceptance bag is empty are NEVER skipped: there is no
ground truth to verify against, and silent skips are a verification
regression.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from rich.console import Console

from ncdev.pipeline.models import FeatureStep, StepResult, StepStatus

console = Console()


def scan_completed_features(
    target_path: Path,
    feature_queue: list[FeatureStep],
) -> list[str]:
    """Return feature_ids whose declared acceptance is already satisfied.

    Strict by design — see module docstring. A feature with no declared
    acceptance is never returned (we can't prove it's done).
    """
    if not (target_path / ".git").exists():
        return []

    git_log = _get_git_log(target_path)

    completed: list[str] = []
    for feature in feature_queue:
        if not _has_enforceable_acceptance(feature):
            continue
        if not _feat_commit_names_feature(feature, git_log):
            continue
        if not _required_files_present(feature, target_path):
            continue
        ok, mention_violations = _required_tests_pass(feature, target_path)
        if not ok or mention_violations:
            continue
        completed.append(feature.feature_id)

    return completed


def build_skip_results(
    feature_queue: list[FeatureStep],
    completed_ids: set[str],
) -> list[StepResult]:
    """Create SKIPPED StepResults for verified-done brownfield features.

    SKIPPED is the dependency-satisfying status: features built earlier
    runs but verified by this scanner DO unblock dependents. A FAILED or
    BLOCKED dep does not.
    """
    return [
        StepResult(
            feature_id=f.feature_id,
            status=StepStatus.SKIPPED,
            error_message=(
                "Already implemented in target repo (acceptance verified by "
                "state-scanner: commit + required_files + required_tests pass)"
            ),
        )
        for f in feature_queue
        if f.feature_id in completed_ids
    ]


# ---------------------------------------------------------------------------
# Strict acceptance checks
# ---------------------------------------------------------------------------


def _has_enforceable_acceptance(feature: FeatureStep) -> bool:
    """True if the feature has at least one required_file or required_test.

    Without one or the other we have nothing concrete to verify; the
    scanner refuses to declare such a feature done.
    """
    accept = feature.acceptance
    return bool(accept.required_files) or bool(accept.required_tests)


def _feat_commit_names_feature(feature: FeatureStep, git_log: str) -> bool:
    """True if a Conventional Commit on this branch names the feature_id.

    Looks for ``<type>(<feature_id>):`` where type is one of the
    Conventional Commit types we accept. Plain mentions of the
    feature_id elsewhere in the log don't count — those are too easy
    to hit accidentally.
    """
    fid = re.escape(feature.feature_id)
    pattern = rf"\b(feat|fix|chore|refactor|perf|test|build|ci|docs|style|revert)\({fid}\)"
    return re.search(pattern, git_log) is not None


def _required_files_present(feature: FeatureStep, target_path: Path) -> bool:
    """Every required_file must exist; with must_mention_feature_id, must
    also reference the feature_id."""
    accept = feature.acceptance
    for rel in accept.required_files:
        fp = target_path / rel
        if not fp.exists():
            return False
        if accept.must_mention_feature_id and not _file_mentions(fp, feature.feature_id):
            return False
    return True


def _required_tests_pass(
    feature: FeatureStep,
    target_path: Path,
) -> tuple[bool, bool]:
    """Run each required_test. Return (all_passed, had_mention_violation).

    When ``must_mention_feature_id`` is True, a test that exists and
    passes but doesn't mention the feature_id is a mention violation —
    we surface it as a separate signal so callers can distinguish
    "test failed" from "test passed but is generic".
    """
    accept = feature.acceptance
    if not accept.required_tests:
        return True, False

    mention_violation = False
    for rel in accept.required_tests:
        tp = target_path / rel
        if not tp.exists():
            return False, mention_violation
        if accept.must_mention_feature_id and not _file_mentions(tp, feature.feature_id):
            mention_violation = True
            continue
        if not _run_single_test(tp, target_path):
            return False, mention_violation
    return True, mention_violation


def _run_single_test(test_path: Path, cwd: Path) -> bool:
    """Run a single test file. True iff it exits 0 and reports passes.

    Resolves the right working directory for the test runner: backend
    pytest runs from the nearest pyproject.toml ancestor; frontend
    vitest runs from the nearest package.json ancestor. Without this,
    a frontend test invoked from target_path fails to find
    node_modules / vite config and reports "1/3 failed" even when the
    test passes when invoked from frontend/.
    """
    project_root, runner_cmd = _runner_for_test(test_path, cwd)
    if runner_cmd is None or project_root is None:
        return False

    try:
        result = subprocess.run(
            runner_cmd,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=300,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False

    return result.returncode == 0


def _runner_for_test(test_path: Path, target_path: Path) -> tuple[Path | None, list[str] | None]:
    """Pick the test runner + the directory to invoke it from.

    Walks up from ``test_path`` looking for a project marker
    (pyproject.toml for python, package.json for js/ts). Returns the
    marker directory + the runner command (with the test path made
    relative to that directory). Falls back to ``target_path`` and an
    absolute test path if no marker is found in the ancestor chain.

    Detects Playwright vs vitest for .ts/.tsx/.js/.jsx by inspecting
    the path: if the test sits under a ``tests/e2e/`` (or ``e2e/``)
    directory, it's a Playwright spec — invoke ``npx playwright test``
    instead of ``npx vitest run`` (vitest's default config typically
    excludes e2e/ anyway).

    For Python tests, prefers the project's own venv python (so
    project-installed packages like sqlalchemy are visible) over
    NC Dev's interpreter. Looks for .venv/bin/python or
    venv/bin/python in the marker directory and ancestors up to the
    target_path.
    """
    suffix = test_path.suffix
    if suffix == ".py":
        marker_name = "pyproject.toml"
        # Default to NC Dev's interpreter; we may switch to the project's
        # venv python below once we've located the marker directory.
        cmd_template = [sys.executable, "-m", "pytest", "-q", "-x"]
    elif suffix in {".ts", ".tsx", ".js", ".jsx"}:
        marker_name = "package.json"
        if _looks_like_playwright_test(test_path):
            cmd_template = ["npx", "playwright", "test"]
        else:
            cmd_template = ["npx", "vitest", "run"]
    else:
        return None, None

    # Walk up from the test file looking for the project marker.
    project_root = target_path
    cursor = test_path.parent
    while cursor != cursor.parent and cursor.is_relative_to(target_path):
        if (cursor / marker_name).exists():
            project_root = cursor
            break
        cursor = cursor.parent

    # If we found a python project, swap NC Dev's interpreter for the
    # project's venv python when one exists. Without this, project deps
    # (sqlalchemy, fastapi, etc.) fail to import and every test errors
    # with ModuleNotFoundError even when the project itself works.
    if suffix == ".py":
        venv_py = _find_project_python(project_root, target_path)
        if venv_py is not None:
            cmd_template = [str(venv_py), "-m", "pytest", "-q", "-x"]

    rel = test_path.relative_to(project_root) if test_path.is_relative_to(project_root) else test_path
    return project_root, [*cmd_template, str(rel)]


def _find_project_python(project_root: Path, target_path: Path) -> Path | None:
    """Look for .venv/bin/python or venv/bin/python in project_root or
    any ancestor up to target_path. Returns the first one found."""
    cursor = project_root
    while cursor.is_relative_to(target_path) or cursor == target_path:
        for venv_name in (".venv", "venv"):
            for bin_dir in ("bin", "Scripts"):
                candidate = cursor / venv_name / bin_dir / "python"
                if candidate.exists():
                    return candidate
                candidate_exe = cursor / venv_name / bin_dir / "python.exe"
                if candidate_exe.exists():
                    return candidate_exe
        if cursor == cursor.parent or cursor == target_path:
            break
        cursor = cursor.parent
    return None


def _looks_like_playwright_test(test_path: Path) -> bool:
    """True if ``test_path`` sits under an e2e/ directory or a path
    component named tests/e2e — the Playwright convention.

    Also true if a ``playwright.config.{ts,js,mjs}`` exists adjacent
    to the test or in any ancestor up to ten levels."""
    parts = {p.lower() for p in test_path.parts}
    if "e2e" in parts:
        return True
    cursor = test_path.parent
    for _ in range(10):
        for cfg in ("playwright.config.ts", "playwright.config.js", "playwright.config.mjs"):
            if (cursor / cfg).exists():
                return True
        if cursor == cursor.parent:
            break
        cursor = cursor.parent
    return False


def _file_mentions(path: Path, token: str) -> bool:
    """Cheap content scan capped at 1 MB; falls back to filename match."""
    try:
        if path.stat().st_size > 1_000_000:
            return token in path.name
        text = path.read_text(encoding="utf-8", errors="ignore")
        return token in text or token in path.name
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _get_git_log(target_path: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "log", "--pretty=%s", "--all", "-500"],
            cwd=str(target_path),
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout if result.returncode == 0 else ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""
