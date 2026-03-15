from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ncdev.v2.models import (
    ChainNode,
    DeployInfo,
    ErrorContext,
    ErrorDetail,
    ErrorFrequency,
    ErrorSeverity,
    ErrorSource,
    FixOutcome,
    FrontendContext,
    NetworkFailure,
    RequestChain,
    SentinelFailureReport,
    SentinelFixResult,
    ServiceInfo,
    TaskType,
    TriageInfo,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "sentinel_reports"


# ---------------------------------------------------------------------------
# TaskType enum
# ---------------------------------------------------------------------------
class TestTaskTypeEnumExtensions:
    def test_sentinel_fix_exists(self):
        assert TaskType.SENTINEL_FIX.value == "sentinel_fix"

    def test_sentinel_reproduce_exists(self):
        assert TaskType.SENTINEL_REPRODUCE.value == "sentinel_reproduce"

    def test_sentinel_members_are_last(self):
        members = list(TaskType)
        assert members[-2] == TaskType.SENTINEL_FIX
        assert members[-1] == TaskType.SENTINEL_REPRODUCE


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class TestErrorSource:
    def test_values(self):
        assert ErrorSource.BACKEND.value == "backend"
        assert ErrorSource.FRONTEND.value == "frontend"

    def test_membership(self):
        assert len(ErrorSource) == 2


class TestErrorSeverity:
    def test_values(self):
        assert ErrorSeverity.CRITICAL.value == "critical"
        assert ErrorSeverity.HIGH.value == "high"
        assert ErrorSeverity.MEDIUM.value == "medium"
        assert ErrorSeverity.LOW.value == "low"

    def test_membership(self):
        assert len(ErrorSeverity) == 4


class TestFixOutcome:
    def test_values(self):
        expected = {
            "fixed",
            "cannot_reproduce",
            "fix_failed",
            "validation_failed",
            "checkout_failed",
            "blocked",
        }
        assert {m.value for m in FixOutcome} == expected

    def test_membership(self):
        assert len(FixOutcome) == 6


# ---------------------------------------------------------------------------
# Sub-models with defaults
# ---------------------------------------------------------------------------
class TestSubModelDefaults:
    def test_service_info_defaults(self):
        si = ServiceInfo(
            name="svc", version="1.0", git_sha="abc", git_repo="repo"
        )
        assert si.environment == "production"
        assert si.default_branch == "main"

    def test_error_detail_optional_fields(self):
        ed = ErrorDetail(error_type="E", error_code="1", message="msg")
        assert ed.stack_trace is None
        assert ed.file is None
        assert ed.line is None
        assert ed.function is None
        assert ed.component is None

    def test_chain_node(self):
        cn = ChainNode(
            service="s", endpoint="/e", method="GET", status_code=200, duration_ms=10
        )
        assert cn.status_code == 200

    def test_request_chain(self):
        rc = RequestChain(
            chain_id="c1",
            nodes=[
                ChainNode(
                    service="s",
                    endpoint="/e",
                    method="GET",
                    status_code=200,
                    duration_ms=10,
                )
            ],
            failed_node_index=0,
        )
        assert len(rc.nodes) == 1

    def test_network_failure_defaults(self):
        nf = NetworkFailure(url="/x", method="GET", error="fail")
        assert nf.status_code is None
        assert nf.duration_ms is None

    def test_frontend_context_defaults(self):
        fc = FrontendContext(url="http://localhost")
        assert fc.interaction_trail == []
        assert fc.console_errors == []
        assert fc.network_failures == []
        assert fc.component_stack is None
        assert fc.core_web_vitals is None

    def test_error_frequency(self):
        ef = ErrorFrequency(
            last_hour=5,
            last_24h=20,
            first_seen=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        assert ef.affected_users == 0

    def test_deploy_info(self):
        di = DeployInfo(
            sha="abc",
            timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            message="deploy",
        )
        assert di.sha == "abc"

    def test_error_context_defaults(self):
        ec = ErrorContext()
        assert ec.request is None
        assert ec.environment == {}
        assert ec.recent_deploys == []
        assert ec.similar_successful_request is None
        assert ec.recent_log_lines == []
        assert ec.related_files == []

    def test_triage_info_defaults(self):
        ti = TriageInfo(ticket_id="T-1")
        assert ti.assignee == "ncdev"
        assert ti.priority == 1
        assert ti.notes == ""
        assert ti.auto_deploy is False
        assert ti.max_attempts == 3


# ---------------------------------------------------------------------------
# SentinelFailureReport from fixtures
# ---------------------------------------------------------------------------
class TestSentinelFailureReportDeserialization:
    def test_backend_fixture(self):
        data = json.loads((FIXTURES / "backend_error.json").read_text())
        report = SentinelFailureReport.model_validate(data)
        assert report.report_id == "rpt_bk_001"
        assert report.source == ErrorSource.BACKEND
        assert report.severity == ErrorSeverity.CRITICAL
        assert report.service.name == "helyx-api"
        assert report.error.line == 142
        assert report.chain is not None
        assert len(report.chain.nodes) == 2
        assert report.chain.failed_node_index == 0
        assert report.frequency.last_hour == 47
        assert report.frequency.affected_users == 23
        assert report.context.related_files == [
            "api/app/models/order.py",
            "api/app/routers/orders.py",
        ]
        assert report.triage is not None
        assert report.triage.ticket_id == "SEN-042"
        assert report.frontend_context is None

    def test_frontend_fixture(self):
        data = json.loads((FIXTURES / "frontend_error.json").read_text())
        report = SentinelFailureReport.model_validate(data)
        assert report.report_id == "rpt_fe_001"
        assert report.source == ErrorSource.FRONTEND
        assert report.severity == ErrorSeverity.HIGH
        assert report.error.component == "ProjectList"
        assert report.frontend_context is not None
        assert report.frontend_context.url == "https://helyx.local/projects"
        assert len(report.frontend_context.network_failures) == 1
        assert report.frontend_context.network_failures[0].status_code == 500
        assert report.frontend_context.component_stack == "ProjectList > ProjectsPage > Layout > App"
        assert report.chain is None
        assert report.triage is not None
        assert report.triage.ticket_id == "SEN-043"


class TestSentinelFailureReportRoundtrip:
    def test_roundtrip_backend(self):
        data = json.loads((FIXTURES / "backend_error.json").read_text())
        report = SentinelFailureReport.model_validate(data)
        serialized = json.loads(report.model_dump_json())
        report2 = SentinelFailureReport.model_validate(serialized)
        assert report == report2

    def test_roundtrip_frontend(self):
        data = json.loads((FIXTURES / "frontend_error.json").read_text())
        report = SentinelFailureReport.model_validate(data)
        serialized = json.loads(report.model_dump_json())
        report2 = SentinelFailureReport.model_validate(serialized)
        assert report == report2


class TestSentinelFailureReportExtraFields:
    def test_extra_fields_ignored(self):
        data = json.loads((FIXTURES / "backend_error.json").read_text())
        data["unknown_field"] = "should be ignored"
        data["another_extra"] = 42
        report = SentinelFailureReport.model_validate(data)
        assert report.report_id == "rpt_bk_001"
        assert not hasattr(report, "unknown_field")


class TestSentinelFailureReportMinimal:
    def test_minimal_required_fields(self):
        now = datetime(2026, 3, 15, tzinfo=timezone.utc)
        report = SentinelFailureReport(
            report_id="rpt_min",
            service=ServiceInfo(
                name="svc", version="1.0", git_sha="abc", git_repo="repo"
            ),
            source=ErrorSource.BACKEND,
            severity=ErrorSeverity.LOW,
            error=ErrorDetail(error_type="E", error_code="1", message="msg"),
            frequency=ErrorFrequency(
                last_hour=1, last_24h=1, first_seen=now
            ),
            context=ErrorContext(),
            detected_at=now,
        )
        assert report.schema_version == "1.0"
        assert report.chain is None
        assert report.frontend_context is None
        assert report.triage is None
        assert report.approved_at is None


# ---------------------------------------------------------------------------
# SentinelFixResult
# ---------------------------------------------------------------------------
class TestSentinelFixResult:
    def test_fixed_outcome(self):
        now = datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc)
        later = datetime(2026, 3, 15, 10, 5, 0, tzinfo=timezone.utc)
        result = SentinelFixResult(
            report_id="rpt_bk_001",
            run_id="run_001",
            outcome=FixOutcome.FIXED,
            outcome_detail="Patched null guard in order_service.py",
            pr_url="https://github.com/org/repo/pull/42",
            fix_branch="nc-dev/sentinel-fix-rpt_bk_001",
            commit_sha="deadbeef",
            files_changed=["api/app/services/order_service.py"],
            reproduction_test="tests/test_order_null.py",
            fix_description="Added null check before accessing order.total",
            attempts_used=1,
            duration_seconds=120,
            started_at=now,
            completed_at=later,
        )
        assert result.outcome == FixOutcome.FIXED
        assert result.pr_url is not None
        assert len(result.files_changed) == 1

    def test_cannot_reproduce_outcome(self):
        now = datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc)
        later = datetime(2026, 3, 15, 10, 2, 0, tzinfo=timezone.utc)
        result = SentinelFixResult(
            report_id="rpt_bk_002",
            run_id="run_002",
            outcome=FixOutcome.CANNOT_REPRODUCE,
            outcome_detail="Could not trigger the error in test environment",
            attempts_used=3,
            max_attempts=3,
            duration_seconds=300,
            started_at=now,
            completed_at=later,
        )
        assert result.outcome == FixOutcome.CANNOT_REPRODUCE
        assert result.pr_url is None
        assert result.files_changed == []

    def test_roundtrip(self):
        now = datetime(2026, 3, 15, 10, 0, 0, tzinfo=timezone.utc)
        later = datetime(2026, 3, 15, 10, 5, 0, tzinfo=timezone.utc)
        result = SentinelFixResult(
            report_id="rpt_bk_001",
            run_id="run_001",
            outcome=FixOutcome.FIXED,
            outcome_detail="Fixed",
            started_at=now,
            completed_at=later,
        )
        serialized = json.loads(result.model_dump_json())
        result2 = SentinelFixResult.model_validate(serialized)
        assert result == result2
