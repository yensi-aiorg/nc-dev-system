from __future__ import annotations

from typing import Any


def _report(**overrides: Any):
    """Build a minimal valid SentinelFailureReport for tests."""
    from datetime import datetime, timezone

    from ncdev.core.models import (
        ErrorContext,
        ErrorDetail,
        ErrorFrequency,
        ErrorSeverity,
        ErrorSource,
        SentinelFailureReport,
        ServiceInfo,
    )

    base = dict(
        report_id="rep-123",
        service=ServiceInfo(
            name="citebot",
            version="1.0",
            git_sha="abc123",
            git_repo="git@github.com:org/citebot.git",
        ),
        source=ErrorSource.BACKEND,
        severity=ErrorSeverity.HIGH,
        error=ErrorDetail(
            error_type="NULL_POINTER",
            error_code="E500",
            message="NoneType has no attribute foo",
            file="app/services/doc.py",
            line=42,
            function="parse",
        ),
        frequency=ErrorFrequency(
            last_hour=5,
            last_24h=80,
            first_seen=datetime.now(timezone.utc),
            affected_users=12,
        ),
        context=ErrorContext(),
        detected_at=datetime.now(timezone.utc),
    )
    base.update(overrides)
    return SentinelFailureReport(**base)


def _service(**overrides: Any):
    from ncdev.core.config import SentinelServiceConfig

    base = dict(
        repo_path="/srv/citebot",
        repo_clone_url="git@github.com:org/citebot.git",
        language="python",
        test_commands={"backend": "pytest -q"},
    )
    base.update(overrides)
    return SentinelServiceConfig(**base)


def test_synthesize_produces_single_feature(tmp_path):
    from ncdev.sentinel_charter import synthesize_charter_from_sentinel_report

    bundle = synthesize_charter_from_sentinel_report(_report(), _service(), tmp_path)

    assert len(bundle.feature_queue.features) == 1
    assert bundle.feature_queue.features[0].feature_id == "fix-rep-123"


def test_synthesize_contract_is_brownfield(tmp_path):
    from ncdev.sentinel_charter import synthesize_charter_from_sentinel_report

    bundle = synthesize_charter_from_sentinel_report(_report(), _service(), tmp_path)

    assert bundle.contract.is_brownfield is True
    assert bundle.contract.existing_repo_path == str(tmp_path.resolve())
    assert bundle.contract.project_type == "api"


def test_synthesize_frontend_source_is_web(tmp_path):
    from ncdev.core.models import ErrorSource
    from ncdev.sentinel_charter import synthesize_charter_from_sentinel_report

    bundle = synthesize_charter_from_sentinel_report(
        _report(source=ErrorSource.FRONTEND),
        _service(),
        tmp_path,
    )

    assert bundle.contract.project_type == "web"


def test_synthesize_description_embeds_error_detail(tmp_path):
    from ncdev.sentinel_charter import synthesize_charter_from_sentinel_report

    bundle = synthesize_charter_from_sentinel_report(_report(), _service(), tmp_path)
    desc = bundle.feature_queue.features[0].description

    assert "NULL_POINTER" in desc
    assert "app/services/doc.py" in desc
    assert "NoneType has no attribute foo" in desc


def test_synthesize_verification_uses_service_test_command(tmp_path):
    from ncdev.sentinel_charter import synthesize_charter_from_sentinel_report

    bundle = synthesize_charter_from_sentinel_report(
        _report(),
        _service(test_commands={"backend": "pytest -q"}),
        tmp_path,
    )

    assert bundle.verification.backend_test_command == "pytest -q"


def test_synthesize_wires_reproduction_test_when_given(tmp_path):
    from ncdev.sentinel_charter import synthesize_charter_from_sentinel_report

    bundle = synthesize_charter_from_sentinel_report(
        _report(),
        _service(),
        tmp_path,
        reproduction_test_path="tests/test_repro_rep_123.py",
    )
    accept = bundle.feature_queue.features[0].acceptance

    assert "tests/test_repro_rep_123.py" in accept.required_tests
    assert accept.must_mention_feature_id is False


def test_synthesize_severity_drives_complexity(tmp_path):
    from ncdev.core.models import ErrorSeverity
    from ncdev.sentinel_charter import synthesize_charter_from_sentinel_report

    crit = synthesize_charter_from_sentinel_report(
        _report(severity=ErrorSeverity.CRITICAL),
        _service(),
        tmp_path,
    )
    low = synthesize_charter_from_sentinel_report(
        _report(severity=ErrorSeverity.LOW),
        _service(),
        tmp_path,
    )

    assert crit.feature_queue.features[0].estimated_complexity == "high"
    assert low.feature_queue.features[0].estimated_complexity == "medium"


def test_feature_id_for_report_is_stable():
    from ncdev.sentinel_charter import feature_id_for_report

    assert feature_id_for_report(_report()) == "fix-rep-123"
