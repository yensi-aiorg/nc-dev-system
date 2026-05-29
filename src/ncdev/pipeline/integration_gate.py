"""Phase 5b — Integration gate primitives.

The end-of-run integration verdict now lives in
``ncdev.pipeline.grounded_verify.integration.grounded_integration_gate``,
which delegates the pass/fail decision to a grounded product judge.

This module owns the building blocks that verdict relies on:

    * :class:`IntegrationResult` — the structured outcome the engine
      consumes (``.passed`` / ``.failures`` plus observability fields).
    * the executable helpers (:func:`_run_shell`, :func:`_probe`,
      :func:`_wait_for_health`, :func:`_resolve_url`,
      :func:`_derive_base_url`, :func:`_tail`) used to gather evidence.

The old clause-based ``run_integration_gate`` (asset-manifest-as-verdict
and ``required_files`` exact-path matching) has been retired in favour of
the grounded gate.
"""
from __future__ import annotations

import subprocess
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path


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
    app_started: bool | None = None
    app_start_output_tail: str = ""
    app_stopped: bool | None = None


def _wait_for_health(url: str, *, timeout: int) -> bool:
    """Poll ``url`` until it returns 2xx or budget expires. Best-effort —
    callers don't act on the return; this is just a settle delay."""
    if not url:
        time.sleep(min(timeout, 5))
        return True
    try:
        import httpx
    except ImportError:  # pragma: no cover - runtime dependency
        return False
    deadline = time.time() + max(timeout, 5)
    while time.time() < deadline:
        try:
            r = httpx.get(url, timeout=3)
            if 200 <= r.status_code < 400:
                return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2)
    return False


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


def _probe_detail(url: str, *, timeout: int) -> tuple[bool, str]:
    """GET ``url`` and return ``(ok, detail)`` where detail is human-readable.

    ``detail`` is ``"HTTP <status>"`` on a response or ``"unreachable: <exc>"``
    on an exception — giving the judge enough signal to distinguish
    "connection refused" (env noise) from "HTTP 500" (decisive failure).
    """
    try:
        import httpx
    except ImportError:  # pragma: no cover - runtime dependency
        return False, "unreachable: httpx not installed"
    try:
        r = httpx.get(url, timeout=min(timeout, 10))
        ok = 200 <= r.status_code < 400  # 3xx redirects acceptable for routes
        return ok, f"HTTP {r.status_code}"
    except Exception as exc:  # noqa: BLE001
        return False, f"unreachable: {exc}"


def _probe(url: str, *, timeout: int) -> bool:
    return _probe_detail(url, timeout=timeout)[0]


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
