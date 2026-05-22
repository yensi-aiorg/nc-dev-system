"""Data shapes for the Verification Gauntlet.

The Gauntlet replaces "tests pass = done" with a layered ladder of
independent checks (L0-L8). Each layer runs in isolation, has one job,
and emits exactly one :class:`GauntletLayerResult`. The aggregate
:class:`GauntletReport` decides whether a feature may be committed.

A layer's *status* and whether it *blocks* are orthogonal: a layer can
fail without blocking (advisory) or be skipped because it does not
apply to this project (a backend-only feature skips visual checks).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class LayerStatus(str, Enum):
    """Outcome of a single gauntlet layer."""

    PASSED = "passed"      # the check ran and the code satisfied it
    FAILED = "failed"      # the check ran and the code did not satisfy it
    SKIPPED = "skipped"    # the check does not apply (no command, no UI, ...)
    ERROR = "error"        # the check itself could not run (tool missing, crash)


@dataclass
class GauntletLayerResult:
    """The result of one gauntlet layer.

    ``blocking`` records whether a non-pass status should block the
    commit. ``findings`` is a structured list of specific problems
    (one string each) for layers that surface more than a pass/fail.
    """

    layer: str                       # stable id, e.g. "L0-typecheck"
    status: LayerStatus
    blocking: bool
    summary: str                     # one-line human summary
    detail: str = ""                 # output tail / extended explanation
    duration_seconds: float = 0.0
    findings: list[str] = field(default_factory=list)

    @property
    def is_blocking_failure(self) -> bool:
        """True when this layer should stop the feature from committing."""
        return self.blocking and self.status in (
            LayerStatus.FAILED,
            LayerStatus.ERROR,
        )


@dataclass
class GauntletReport:
    """Aggregate result of running every layer for one feature."""

    feature_id: str
    layers: list[GauntletLayerResult] = field(default_factory=list)
    duration_seconds: float = 0.0

    @property
    def passed(self) -> bool:
        """The feature clears the gauntlet iff no blocking layer failed."""
        return not any(layer.is_blocking_failure for layer in self.layers)

    @property
    def blocking_failures(self) -> list[GauntletLayerResult]:
        return [layer for layer in self.layers if layer.is_blocking_failure]

    @property
    def advisory_failures(self) -> list[GauntletLayerResult]:
        """Layers that failed but were not configured to block."""
        return [
            layer
            for layer in self.layers
            if not layer.blocking and layer.status == LayerStatus.FAILED
        ]

    def summary_line(self) -> str:
        passed = sum(1 for l in self.layers if l.status == LayerStatus.PASSED)
        failed = sum(1 for l in self.layers if l.status == LayerStatus.FAILED)
        skipped = sum(1 for l in self.layers if l.status == LayerStatus.SKIPPED)
        errored = sum(1 for l in self.layers if l.status == LayerStatus.ERROR)
        verdict = "PASS" if self.passed else "BLOCKED"
        return (
            f"gauntlet {verdict} [{self.feature_id}] — "
            f"{passed} passed, {failed} failed, {skipped} skipped, "
            f"{errored} errored"
        )
