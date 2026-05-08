"""Phase 5b — Integration gate.

Runs after the per-feature build loop completes. Without this gate, a
"passed" run only proves each feature individually verified — it does
NOT prove the resulting product works as a whole. The integration
gate enforces the run-wide invariants:

    1. Asset manifest is fully covered (no feature-touched code
       references an asset the manifest doesn't list).
    2. Every required_file from the global verification contract
       exists.
    3. Every required_route from every feature's acceptance bag
       responds 2xx when the app is booted (when a health URL is
       configured — for non-web projects this clause is a no-op).
    4. The full backend test command passes.
    5. The full frontend test command passes (when configured).
    6. The e2e test command passes (when configured).

If any clause fails, the run status is downgraded to
``integration_failed`` regardless of how many individual features
PASSED. This is the "the whole product must work" rail.
"""
from __future__ import annotations

import subprocess
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console

from ncdev.pipeline.asset_manifest import (
    aggregate_manifests,
    verify_manifest_covers_references,
)
from ncdev.pipeline.models import CharterBundle, StepResult, StepStatus

console = Console()


@dataclass
class IntegrationResult:
    """Outcome of the end-of-run integration gate."""

    passed: bool = False
    duration_seconds: float = 0.0
    failures: list[str] = field(default_factory=list)
    asset_coverage_ok: bool = True
    contract_files_ok: bool = True
    routes_probed: int = 0
    routes_failed: list[str] = field(default_factory=list)
    backend_tests_ok: bool | None = None
    frontend_tests_ok: bool | None = None
    e2e_tests_ok: bool | None = None
    backend_test_output_tail: str = ""
    frontend_test_output_tail: str = ""
    e2e_test_output_tail: str = ""
    lint_ok: bool | None = None
    lint_output_tail: str = ""
    build_ok: bool | None = None
    build_output_tail: str = ""


def run_integration_gate(
    bundle: CharterBundle,
    target_path: Path,
    completed: list[StepResult],
    *,
    probe_health: bool = True,
    run_test_commands: bool = True,
) -> IntegrationResult:
    """Run every clause and return a structured result.

    The function is side-effect-free with respect to the repo: it does
    not commit, does not mutate state. Its only output is the
    :class:`IntegrationResult` — callers (the engine) decide how to
    surface it.
    """
    start = time.time()
    result = IntegrationResult()

    # Clause 1 — asset manifest aggregate coverage. We only care about
    # features that actually PASSED this run; SKIPPED brownfield
    # features get a pass since they predate the manifest contract.
    feature_ids_built = {
        r.feature_id for r in completed if r.status == StepStatus.PASSED
    }
    for fid in feature_ids_built:
        ok, missing = verify_manifest_covers_references(target_path, fid)
        if not ok:
            result.asset_coverage_ok = False
            result.failures.append(
                f"asset manifest missing entries for {fid}: {missing[:5]}"
            )

    # Aggregate manifest must be valid even if every feature was already
    # individually verified — paranoid belt-and-braces against a feature
    # session that wrote its manifest but corrupted the aggregate.
    try:
        aggregate_manifests(target_path)
    except Exception as exc:  # noqa: BLE001
        result.asset_coverage_ok = False
        result.failures.append(f"asset manifest aggregate failed: {exc}")

    # Clause 2 — global required_files
    for req in bundle.verification.required_files:
        if not (target_path / req).exists():
            result.contract_files_ok = False
            result.failures.append(f"required file missing: {req}")

    # Clause 3 — required_routes from every feature's acceptance bag
    if probe_health:
        base_url = bundle.verification.frontend_url or _derive_base_url(
            bundle.verification.backend_health_url
        )
        for feat in bundle.feature_queue.features:
            if feat.feature_id not in feature_ids_built:
                # Don't probe routes for SKIPPED / FAILED / BLOCKED — they
                # didn't pass per-feature, so route enforcement noise is
                # not our job here.
                continue
            for route in feat.acceptance.required_routes:
                full = _resolve_url(route, base_url)
                if not full:
                    result.failures.append(
                        f"required_route {route!r} for {feat.feature_id} cannot "
                        "be resolved — no base URL configured in the contract"
                    )
                    result.routes_failed.append(route)
                    continue
                result.routes_probed += 1
                if not _probe(full, timeout=bundle.verification.boot_timeout_seconds):
                    result.routes_failed.append(full)
                    result.failures.append(
                        f"required_route unreachable: {full} "
                        f"(feature {feat.feature_id})"
                    )

    # Clause 4 — backend test command
    if run_test_commands and bundle.verification.backend_test_command:
        ok, out = _run_shell(
            bundle.verification.backend_test_command,
            cwd=target_path,
            timeout=900,
        )
        result.backend_tests_ok = ok
        result.backend_test_output_tail = _tail(out)
        if not ok:
            result.failures.append(
                f"backend test suite failed: {result.backend_test_output_tail}"
            )

    # Clause 5 — frontend test command
    if run_test_commands and bundle.verification.frontend_test_command:
        ok, out = _run_shell(
            bundle.verification.frontend_test_command,
            cwd=target_path,
            timeout=900,
        )
        result.frontend_tests_ok = ok
        result.frontend_test_output_tail = _tail(out)
        if not ok:
            result.failures.append(
                f"frontend test suite failed: {result.frontend_test_output_tail}"
            )

    # Clause 6 — e2e test command
    if run_test_commands and bundle.verification.e2e_test_command:
        ok, out = _run_shell(
            bundle.verification.e2e_test_command,
            cwd=target_path,
            timeout=1800,
        )
        result.e2e_tests_ok = ok
        result.e2e_test_output_tail = _tail(out)
        if not ok:
            result.failures.append(
                f"e2e test suite failed: {result.e2e_test_output_tail}"
            )

    # Clause 7 — lint command. A passing test suite with broken types
    # or unused-import / unsafe-fallback warnings still ships a
    # half-baked product; lint is part of "production complete".
    if run_test_commands and bundle.verification.lint_command:
        ok, out = _run_shell(
            bundle.verification.lint_command,
            cwd=target_path,
            timeout=600,
        )
        result.lint_ok = ok
        result.lint_output_tail = _tail(out)
        if not ok:
            result.failures.append(
                f"lint failed: {result.lint_output_tail}"
            )

    # Clause 8 — build command. The product must actually build —
    # passing tests against unbuildable code is a frequent silent-skip
    # mode (frontend bundles in particular).
    if run_test_commands and bundle.verification.build_command:
        ok, out = _run_shell(
            bundle.verification.build_command,
            cwd=target_path,
            timeout=1800,
        )
        result.build_ok = ok
        result.build_output_tail = _tail(out)
        if not ok:
            result.failures.append(
                f"build failed: {result.build_output_tail}"
            )

    result.duration_seconds = time.time() - start
    result.passed = not result.failures
    return result


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


def _derive_base_url(health_url: str) -> str:
    """Strip the path off a health URL to get a base for relative routes."""
    if not health_url:
        return ""
    parsed = urllib.parse.urlsplit(health_url)
    if not parsed.scheme:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def _resolve_url(route: str, base_url: str) -> str | None:
    """Resolve a route to a fully-qualified URL.

    Accepts absolute URLs (returned as-is) or path-only routes that
    are joined to ``base_url``. Returns None if the route is path-only
    AND no base_url is configured.
    """
    if route.startswith(("http://", "https://")):
        return route
    if not base_url:
        return None
    return base_url.rstrip("/") + "/" + route.lstrip("/")


def _probe(url: str, *, timeout: int) -> bool:
    try:
        import httpx
    except ImportError:  # pragma: no cover - runtime dependency
        return False
    try:
        r = httpx.get(url, timeout=min(timeout, 10))
        return 200 <= r.status_code < 400  # 3xx redirects acceptable for routes
    except Exception:  # noqa: BLE001
        return False


def _run_shell(cmd: str, *, cwd: Path, timeout: int) -> tuple[bool, str]:
    try:
        r = subprocess.run(
            cmd, shell=True, cwd=str(cwd),
            capture_output=True, text=True, timeout=timeout,
        )
        return r.returncode == 0, (r.stdout + "\n" + r.stderr)
    except subprocess.TimeoutExpired as exc:
        return False, f"timed out after {timeout}s: {exc}"
    except Exception as exc:  # noqa: BLE001
        return False, f"exec error: {exc}"


def _tail(text: str, n: int = 400) -> str:
    """Return the last n chars of text — last lines are usually most useful."""
    text = text.strip()
    if len(text) <= n:
        return text
    return "..." + text[-n:]
