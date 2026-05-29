"""Tests for Phase 5b integration-gate primitives.

The end-of-run verdict now lives in
``ncdev.pipeline.grounded_verify.integration.grounded_integration_gate``
(tested under ``tests/test_grounded_verify/``). The old clause-based
``run_integration_gate`` (asset-manifest-as-verdict, ``required_files``
exact-path matching) has been retired, so the tests of that verdict
logic are gone.

What remains here are the surviving executable helpers this module still
owns and the grounded gate imports: the URL resolution helpers and the
:class:`IntegrationResult` shape.
"""
from __future__ import annotations

from ncdev.pipeline.integration_gate import (
    IntegrationResult,
    _derive_base_url,
    _resolve_url,
)


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


def test_derive_base_url_strips_path() -> None:
    assert _derive_base_url("http://localhost:23301/api/health") == "http://localhost:23301"
    assert _derive_base_url("https://api.example.com/v1/healthz") == "https://api.example.com"


def test_derive_base_url_returns_empty_when_input_empty() -> None:
    assert _derive_base_url("") == ""


def test_resolve_url_passes_through_absolute() -> None:
    assert _resolve_url("https://example.com/x", "http://localhost") == "https://example.com/x"


def test_resolve_url_joins_relative_to_base() -> None:
    assert _resolve_url("/api/auth/login", "http://localhost:23301") == "http://localhost:23301/api/auth/login"
    assert _resolve_url("api/auth/login", "http://localhost:23301/") == "http://localhost:23301/api/auth/login"


def test_resolve_url_returns_none_when_no_base() -> None:
    assert _resolve_url("/api/x", "") is None


# ---------------------------------------------------------------------------
# IntegrationResult shape (consumed by the grounded gate + the engine)
# ---------------------------------------------------------------------------


def test_integration_result_default_state() -> None:
    r = IntegrationResult()
    assert r.passed is False
    assert r.failures == []
    assert r.routes_probed == 0
