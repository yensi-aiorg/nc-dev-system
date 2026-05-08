"""Tests for Fix 4 — dependency gating in the engine feature loop."""

from __future__ import annotations

from ncdev.pipeline.engine import _unmet_dependencies
from ncdev.pipeline.models import FeatureStep, StepResult, StepStatus


def _feat(fid: str, deps: list[str] | None = None) -> FeatureStep:
    return FeatureStep(
        feature_id=fid,
        title=fid,
        description="",
        acceptance_criteria=[],
        depends_on_features=deps or [],
    )


def test_no_deps_is_always_satisfied():
    f = _feat("f05", deps=[])
    assert _unmet_dependencies(f, completed=[]) == []


def test_dependency_not_yet_built_is_unmet():
    f = _feat("f02", deps=["f01"])
    assert _unmet_dependencies(f, completed=[]) == ["f01"]


def test_dependency_passed_is_satisfied():
    f = _feat("f02", deps=["f01"])
    completed = [StepResult(feature_id="f01", status=StepStatus.PASSED)]
    assert _unmet_dependencies(f, completed=completed) == []


def test_dependency_failed_is_unmet():
    """A failed dependency is NOT satisfied — downstream must skip."""
    f = _feat("f02", deps=["f01"])
    completed = [StepResult(feature_id="f01", status=StepStatus.FAILED)]
    assert _unmet_dependencies(f, completed=completed) == ["f01"]


def test_brownfield_skipped_dep_counts_as_satisfied():
    """Brownfield state scanner marks already-implemented features as
    SKIPPED — those count as satisfying a dep (they're really done)."""
    f = _feat("f02", deps=["f01"])
    completed = [StepResult(feature_id="f01", status=StepStatus.SKIPPED)]
    assert _unmet_dependencies(f, completed=completed) == []


def test_blocked_dep_does_NOT_count_as_satisfied():
    """Codex R2 flagged: a dependency that was BLOCKED (its own dep
    failed) must not count as met. Otherwise cascading failures break
    through the gate."""
    f = _feat("f03", deps=["f02"])
    completed = [
        StepResult(feature_id="f01", status=StepStatus.FAILED),
        StepResult(feature_id="f02", status=StepStatus.BLOCKED),
    ]
    assert _unmet_dependencies(f, completed=completed) == ["f02"]


def test_multiple_deps_partial_satisfaction():
    f = _feat("f03", deps=["f01", "f02"])
    completed = [
        StepResult(feature_id="f01", status=StepStatus.PASSED),
        StepResult(feature_id="f02", status=StepStatus.FAILED),
    ]
    assert _unmet_dependencies(f, completed=completed) == ["f02"]


def test_dep_returns_all_unmet_in_order():
    f = _feat("f05", deps=["f01", "f02", "f03", "f04"])
    completed = [
        StepResult(feature_id="f01", status=StepStatus.PASSED),
        StepResult(feature_id="f03", status=StepStatus.PASSED),
    ]
    # f02 and f04 missing entirely — both unmet, order preserved
    assert _unmet_dependencies(f, completed=completed) == ["f02", "f04"]
