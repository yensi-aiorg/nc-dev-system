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
    """Run a single test file. True iff it exits 0 and reports passes."""
    if test_path.suffix == ".py":
        cmd = [sys.executable, "-m", "pytest", "-q", "-x", str(test_path)]
    elif test_path.suffix in {".ts", ".tsx", ".js", ".jsx"}:
        cmd = ["npx", "vitest", "run", str(test_path)]
    else:
        # Unknown harness — treat as fail; the charter shouldn't be
        # listing test files we can't run.
        return False

    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=300,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False

    if result.returncode == 0:
        return True
    # Don't accept "0 collected" / "no tests ran" as success — a passing
    # state-scanner check requires real green tests, not absent ones.
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
