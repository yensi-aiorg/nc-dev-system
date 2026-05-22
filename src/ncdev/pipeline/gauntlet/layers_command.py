"""Command-driven gauntlet layers: L0-compile, L1-lint, L2/L3/L4 tests.

These five layers all share one shape: run one or more shell commands
from the verification contract and pass iff every command exits 0. A
layer whose commands are all empty reports SKIPPED (the project opted
out — a library has no e2e suite, a lint-free repo has no linter).

When ``ctx.run_commands`` is False every command layer reports SKIPPED
so the executor can run a fast, hermetic gauntlet where shelling out is
not possible.
"""
from __future__ import annotations

import time

from ncdev.pipeline.gauntlet.context import GauntletContext, run_shell, tail
from ncdev.pipeline.gauntlet.models import GauntletLayerResult, LayerStatus


def _command_layer(
    *,
    layer: str,
    label: str,
    commands: list[tuple[str, str]],
    ctx: GauntletContext,
    timeout: int = 600,
) -> GauntletLayerResult:
    """Run an ordered list of ``(name, command)`` pairs.

    Empty command strings are dropped. If nothing remains the layer is
    SKIPPED. Otherwise every command must exit 0; the first failure
    stops the layer and is reported as a blocking FAILED.
    """
    start = time.time()
    real = [(name, cmd) for name, cmd in commands if cmd.strip()]

    if not real:
        return GauntletLayerResult(
            layer=layer, status=LayerStatus.SKIPPED, blocking=False,
            summary=f"{label}: no command configured — skipped",
        )
    if not ctx.run_commands:
        return GauntletLayerResult(
            layer=layer, status=LayerStatus.SKIPPED, blocking=False,
            summary=f"{label}: command execution disabled — skipped",
        )

    findings: list[str] = []
    for name, cmd in real:
        ok, code, output = run_shell(cmd, cwd=ctx.repo, timeout=timeout)
        if not ok:
            return GauntletLayerResult(
                layer=layer, status=LayerStatus.FAILED, blocking=True,
                summary=f"{label}: {name} failed (exit {code})",
                detail=tail(output),
                duration_seconds=time.time() - start,
                findings=[f"{name}: `{cmd}` exited {code}"],
            )
        findings.append(f"{name}: ok")

    return GauntletLayerResult(
        layer=layer, status=LayerStatus.PASSED, blocking=True,
        summary=f"{label}: {len(real)} command(s) passed",
        duration_seconds=time.time() - start,
        findings=findings,
    )


def layer_compile(ctx: GauntletContext) -> GauntletLayerResult:
    """L0 — typecheck and build. Catches API misuse and signature errors."""
    v = ctx.contract
    return _command_layer(
        layer="L0-compile", label="typecheck/build", ctx=ctx,
        commands=[
            ("typecheck", v.typecheck_command),
            ("build", v.build_command),
        ],
    )


def layer_lint(ctx: GauntletContext) -> GauntletLayerResult:
    """L1 — lint and static analysis."""
    return _command_layer(
        layer="L1-lint", label="lint", ctx=ctx,
        commands=[("lint", ctx.contract.lint_command)],
    )


def layer_unit_tests(ctx: GauntletContext) -> GauntletLayerResult:
    """L2 — unit tests (backend + frontend)."""
    v = ctx.contract
    return _command_layer(
        layer="L2-unit", label="unit tests", ctx=ctx,
        commands=[
            ("backend", v.backend_test_command),
            ("frontend", v.frontend_test_command),
        ],
        timeout=900,
    )


def layer_integration_tests(ctx: GauntletContext) -> GauntletLayerResult:
    """L3 — integration tests (cross-module wiring)."""
    return _command_layer(
        layer="L3-integration", label="integration tests", ctx=ctx,
        commands=[("integration", ctx.contract.integration_test_command)],
        timeout=900,
    )


def layer_e2e_tests(ctx: GauntletContext) -> GauntletLayerResult:
    """L4 — end-to-end tests (real browser / full stack)."""
    return _command_layer(
        layer="L4-e2e", label="e2e tests", ctx=ctx,
        commands=[("e2e", ctx.contract.e2e_test_command)],
        timeout=1200,
    )
