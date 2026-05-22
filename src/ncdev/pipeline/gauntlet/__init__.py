"""The Verification Gauntlet — NC Dev v4's layered correctness ladder.

"Tests pass" is necessary, not sufficient. The Gauntlet runs a ladder
of independent checks (L0-L8: compile, lint, unit, integration, e2e,
visual, security, anti-bypass, oracle review) per feature and decides
whether the work may be committed.

Public surface:

    from ncdev.pipeline.gauntlet import run_gauntlet, GauntletContext
    report = run_gauntlet(ctx)
    if not report.passed:
        ...  # report.blocking_failures explains why
"""
from ncdev.pipeline.gauntlet.context import (
    GauntletContext,
    extract_json_object,
    run_shell,
    tail,
)
from ncdev.pipeline.gauntlet.models import (
    GauntletLayerResult,
    GauntletReport,
    LayerStatus,
)
from ncdev.pipeline.gauntlet.orchestrator import (
    DEFAULT_LAYERS,
    EXECUTOR_LAYERS,
    run_gauntlet,
)

__all__ = [
    "run_gauntlet",
    "DEFAULT_LAYERS",
    "EXECUTOR_LAYERS",
    "GauntletContext",
    "GauntletReport",
    "GauntletLayerResult",
    "LayerStatus",
    "run_shell",
    "tail",
    "extract_json_object",
]
