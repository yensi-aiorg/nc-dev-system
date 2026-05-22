"""The Verification Gauntlet orchestrator.

``run_gauntlet`` runs an ordered ladder of layers against one feature
and returns an aggregate :class:`GauntletReport`. Layers are plain
callables ``(GauntletContext) -> GauntletLayerResult``, so the ladder
is just a list — trivially extensible and testable.

A layer that raises is caught and reported as a non-blocking ERROR: a
bug in a verification layer must never brick every build. Real check
failures are reported by the layers themselves with their own
``blocking`` flag.
"""
from __future__ import annotations

import time
from collections.abc import Callable, Sequence

from ncdev.pipeline.gauntlet.context import GauntletContext
from ncdev.pipeline.gauntlet.layers_command import (
    layer_compile,
    layer_e2e_tests,
    layer_integration_tests,
    layer_lint,
    layer_unit_tests,
)
from ncdev.pipeline.gauntlet.layers_oracle import layer_oracle
from ncdev.pipeline.gauntlet.layers_static import (
    layer_anti_bypass,
    layer_security,
)
from ncdev.pipeline.gauntlet.layers_visual import layer_visual
from ncdev.pipeline.gauntlet.models import (
    GauntletLayerResult,
    GauntletReport,
    LayerStatus,
)

Layer = Callable[[GauntletContext], GauntletLayerResult]

# The full L0-L8 ladder, in run order. Cheap/deterministic layers run
# first so an expensive AI layer (L8) is only reached once the code
# already compiles and its tests pass.
DEFAULT_LAYERS: tuple[Layer, ...] = (
    layer_compile,            # L0  typecheck + build
    layer_lint,               # L1  lint / static
    layer_unit_tests,         # L2  unit tests
    layer_integration_tests,  # L3  integration tests
    layer_e2e_tests,          # L4  end-to-end tests
    layer_visual,             # L5  visual verification
    layer_security,           # L6  multi-tool SAST
    layer_anti_bypass,        # L7  bypassed-integration scan
    layer_oracle,             # L8  independent oracle review
)

# Layers for the per-feature executor pass. The test layers (L2/L3/L4)
# are omitted: the executor's post-session verification already runs
# the project's test commands, and running them twice per feature is
# pure cost. The full L0-L8 ladder runs at the integration gate.
EXECUTOR_LAYERS: tuple[Layer, ...] = (
    layer_compile,            # L0
    layer_lint,               # L1
    layer_visual,             # L5
    layer_security,           # L6
    layer_anti_bypass,        # L7
    layer_oracle,             # L8
)


def run_gauntlet(
    ctx: GauntletContext,
    *,
    layers: Sequence[Layer] | None = None,
) -> GauntletReport:
    """Run every layer against ``ctx`` and return the aggregate report."""
    ladder = tuple(layers) if layers is not None else DEFAULT_LAYERS
    start = time.time()
    results: list[GauntletLayerResult] = []

    for layer in ladder:
        name = getattr(layer, "__name__", "unknown-layer")
        try:
            results.append(layer(ctx))
        except Exception as exc:  # noqa: BLE001
            # A crashing layer is our bug, not the feature's. Surface it
            # loudly but do not block — failing closed here would brick
            # every build on a single gauntlet defect.
            results.append(
                GauntletLayerResult(
                    layer=name,
                    status=LayerStatus.ERROR,
                    blocking=False,
                    summary=f"gauntlet layer {name!r} crashed: {exc}",
                    detail=repr(exc),
                )
            )

    return GauntletReport(
        feature_id=ctx.feature.feature_id,
        layers=results,
        duration_seconds=time.time() - start,
    )
