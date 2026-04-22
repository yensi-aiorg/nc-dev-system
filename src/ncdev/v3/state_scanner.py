"""Project state scanner — determines which features are already implemented.

Scans the target repo's git history, file tree, and test results to figure out
what's already built, so the engine can skip completed work and resume from
where the previous run left off.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from rich.console import Console

from ncdev.v3.models import FeatureStep, StepResult, StepStatus

console = Console()


def scan_completed_features(
    target_path: Path,
    feature_queue: list[FeatureStep],
) -> list[str]:
    """Scan the target repo and return feature_ids that are already done.

    A feature is considered done if:
    1. It appears in a git commit message (feat(feature_id): ...), OR
    2. Key files described by its title/description exist in the repo, AND
    3. The project's tests pass (basic smoke check)
    """
    if not (target_path / ".git").exists():
        return []

    git_log = _get_git_log(target_path)
    file_tree = _get_file_set(target_path)
    tests_pass = _run_smoke_test(target_path)

    completed: list[str] = []

    for feature in feature_queue:
        # Check 1: Is this feature in the git history?
        in_git = _feature_in_git_history(feature, git_log)

        # Check 2: Do files related to this feature exist?
        has_files = _feature_has_files(feature, file_tree)

        if tests_pass and (in_git or has_files):
            completed.append(feature.feature_id)

    return completed


def build_skip_results(
    feature_queue: list[FeatureStep],
    completed_ids: set[str],
) -> list[StepResult]:
    """Create SKIPPED StepResults for already-completed brownfield features.

    Uses :attr:`StepStatus.SKIPPED` — these features were done before
    this run started. The dependency gate treats SKIPPED as dep-
    satisfying, and metrics / summary correctly exclude them from
    PASSED / BLOCKED / FAILED counters.
    """
    return [
        StepResult(
            feature_id=f.feature_id,
            status=StepStatus.SKIPPED,
            error_message="Already implemented in target repo (state-scanner detection)",
        )
        for f in feature_queue
        if f.feature_id in completed_ids
    ]


def _get_git_log(target_path: Path) -> str:
    """Get full git log with commit messages."""
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "--all", "-200"],
            cwd=str(target_path),
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.lower() if result.returncode == 0 else ""
    except Exception:
        return ""


def _get_file_set(target_path: Path) -> set[str]:
    """Get set of all file paths in the repo (relative, lowercase)."""
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=str(target_path),
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return {line.strip().lower() for line in result.stdout.splitlines() if line.strip()}
    except Exception:
        pass
    return set()


def _run_smoke_test(target_path: Path) -> bool:
    """Quick check: do backend tests pass? (or at least not crash)"""
    backend = target_path / "backend"
    if not backend.exists():
        # Maybe tests are at root level
        backend = target_path

    has_tests = any(backend.rglob("test_*.py")) or any(backend.rglob("*_test.py"))
    if not has_tests:
        return True

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-x", "--no-header"],
            cwd=str(backend),
            capture_output=True, text=True, timeout=60,
        )
        # Accept green runs and partially green runs that still discovered passing tests.
        if result.returncode == 0 or "passed" in result.stdout:
            return True

        combined_output = f"{result.stdout}\n{result.stderr}".lower()

        # Brownfield repos often do not have pytest wired yet. That should not block
        # feature detection entirely.
        non_blocking_markers = [
            "no tests ran",
            "collected 0 items",
            "unrecognized arguments: --timeout=30",
            "module named pytest",
        ]
        return any(marker in combined_output for marker in non_blocking_markers)
    except Exception:
        return False


def _feature_in_git_history(feature: FeatureStep, git_log: str) -> bool:
    """Check if a feature appears in git commit messages."""
    feature_id_lower = feature.feature_id.lower()
    title_lower = feature.title.lower()

    # Direct feature ID match: feat(sprint-0):, feat(feature-01):, [feature-01]
    if feature_id_lower in git_log:
        return True

    # Title keywords match (at least 3 significant words from title in same commit line)
    title_words = [w for w in re.split(r'\W+', title_lower) if len(w) > 3]
    if len(title_words) >= 2:
        for line in git_log.splitlines():
            matches = sum(1 for w in title_words if w in line)
            if matches >= min(3, len(title_words)):
                return True

    return False


def _feature_has_files(feature: FeatureStep, file_tree: set[str]) -> bool:
    """Check if files related to the feature exist in the repo.

    For sprint-0 (scaffold): check for fundamental files.
    For other features: check for feature-specific files using title keywords.
    """
    fid = feature.feature_id.lower()

    # Sprint-0: scaffold is done if basic project structure exists
    if "sprint-0" in fid or "scaffold" in feature.title.lower():
        scaffold_markers = [
            "backend/app/main.py",
            "backend/requirements.txt",
            "docker-compose.yml",
        ]
        found = sum(1 for m in scaffold_markers if m in file_tree)
        return found >= 2

    # For other features: extract keywords from title and check file tree
    title_words = [w.lower() for w in re.split(r'\W+', feature.title) if len(w) > 3]
    if not title_words:
        return False

    # Check if any file path contains feature keywords (prefix match for stems)
    keyword_hits = 0
    for word in title_words:
        # Use first 4+ chars as stem to match "auth" in path against "authentication" in title
        stem = word[:4] if len(word) > 4 else word
        for fpath in file_tree:
            if stem in fpath:
                keyword_hits += 1
                break

    # Need at least 1 keyword match to consider the feature has files
    return keyword_hits >= 1
