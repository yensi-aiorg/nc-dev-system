from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from ncdev.v2.models import (
    ErrorContext,
    ErrorDetail,
    ErrorFrequency,
    ErrorSeverity,
    ErrorSource,
    FrontendContext,
    SentinelFailureReport,
    ServiceInfo,
)
from ncdev.v2.sentinel_prompts import build_fix_prompt, build_reproduction_prompt

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "sentinel_reports"


def _load_report(name: str) -> SentinelFailureReport:
    data = json.loads((FIXTURES / name).read_text())
    return SentinelFailureReport.model_validate(data)


# ---------------------------------------------------------------------------
# build_reproduction_prompt — backend
# ---------------------------------------------------------------------------
class TestBuildReproductionPromptBackend:
    def test_contains_report_id(self):
        report = _load_report("backend_error.json")
        prompt = build_reproduction_prompt(
            report=report,
            error_file_contents="def process(order): ...",
            related_file_contents={},
            existing_test_contents="",
            git_log="abc123 Add coupon support",
        )
        assert report.report_id in prompt

    def test_contains_error_type(self):
        report = _load_report("backend_error.json")
        prompt = build_reproduction_prompt(
            report=report,
            error_file_contents="def process(order): ...",
            related_file_contents={},
            existing_test_contents="",
            git_log="",
        )
        assert report.error.error_type in prompt

    def test_contains_error_file(self):
        report = _load_report("backend_error.json")
        prompt = build_reproduction_prompt(
            report=report,
            error_file_contents="def process(order): ...",
            related_file_contents={},
            existing_test_contents="",
            git_log="",
        )
        assert report.error.file in prompt

    def test_contains_do_not_fix(self):
        report = _load_report("backend_error.json")
        prompt = build_reproduction_prompt(
            report=report,
            error_file_contents="",
            related_file_contents={},
            existing_test_contents="",
            git_log="",
        )
        assert "Do NOT fix the bug" in prompt

    def test_contains_related_files(self):
        report = _load_report("backend_error.json")
        prompt = build_reproduction_prompt(
            report=report,
            error_file_contents="code here",
            related_file_contents={"models/order.py": "class Order: ..."},
            existing_test_contents="",
            git_log="",
        )
        assert "models/order.py" in prompt
        assert "class Order: ..." in prompt

    def test_contains_git_log(self):
        report = _load_report("backend_error.json")
        prompt = build_reproduction_prompt(
            report=report,
            error_file_contents="",
            related_file_contents={},
            existing_test_contents="",
            git_log="abc123 Add coupon support",
        )
        assert "abc123 Add coupon support" in prompt


# ---------------------------------------------------------------------------
# build_reproduction_prompt — frontend
# ---------------------------------------------------------------------------
class TestBuildReproductionPromptFrontend:
    def test_contains_report_id(self):
        report = _load_report("frontend_error.json")
        prompt = build_reproduction_prompt(
            report=report,
            error_file_contents="export function ProjectList() { ... }",
            related_file_contents={},
            existing_test_contents="",
            git_log="",
        )
        assert report.report_id in prompt

    def test_contains_error_type(self):
        report = _load_report("frontend_error.json")
        prompt = build_reproduction_prompt(
            report=report,
            error_file_contents="",
            related_file_contents={},
            existing_test_contents="",
            git_log="",
        )
        assert report.error.error_type in prompt

    def test_contains_vitest_or_playwright(self):
        report = _load_report("frontend_error.json")
        prompt = build_reproduction_prompt(
            report=report,
            error_file_contents="",
            related_file_contents={},
            existing_test_contents="",
            git_log="",
        )
        assert "Vitest" in prompt or "Playwright" in prompt

    def test_contains_do_not_fix(self):
        report = _load_report("frontend_error.json")
        prompt = build_reproduction_prompt(
            report=report,
            error_file_contents="",
            related_file_contents={},
            existing_test_contents="",
            git_log="",
        )
        assert "Do NOT fix the bug" in prompt

    def test_contains_interaction_trail(self):
        report = _load_report("frontend_error.json")
        prompt = build_reproduction_prompt(
            report=report,
            error_file_contents="",
            related_file_contents={},
            existing_test_contents="",
            git_log="",
        )
        assert "navigate /dashboard" in prompt
        assert "click .sidebar-link" in prompt


# ---------------------------------------------------------------------------
# build_fix_prompt
# ---------------------------------------------------------------------------
class TestBuildFixPrompt:
    def test_contains_failure_output(self):
        report = _load_report("backend_error.json")
        prompt = build_fix_prompt(
            report=report,
            test_failure_output="FAILED test_sentinel_rpt_bk_001 - AttributeError",
        )
        assert "FAILED test_sentinel_rpt_bk_001 - AttributeError" in prompt

    def test_contains_do_not_modify_test(self):
        report = _load_report("backend_error.json")
        prompt = build_fix_prompt(
            report=report,
            test_failure_output="some failure output",
        )
        assert "Do NOT modify the reproduction test" in prompt

    def test_contains_minimal_change_rule(self):
        report = _load_report("backend_error.json")
        prompt = build_fix_prompt(
            report=report,
            test_failure_output="some failure output",
        )
        assert "minimal change" in prompt


from ncdev.v2.sentinel_prompts import detect_frontend_test_type, detect_monorepo_subdir


def test_detect_frontend_test_type_component_error() -> None:
    assert detect_frontend_test_type("REACT_RENDER_ERROR") == "vitest"


def test_detect_frontend_test_type_effect_error() -> None:
    assert detect_frontend_test_type("REACT_EFFECT_ERROR") == "vitest"


def test_detect_frontend_test_type_event_error() -> None:
    assert detect_frontend_test_type("REACT_EVENT_ERROR") == "vitest"


def test_detect_frontend_test_type_state_error() -> None:
    assert detect_frontend_test_type("STATE_ERROR") == "vitest"


def test_detect_frontend_test_type_network_error() -> None:
    assert detect_frontend_test_type("NETWORK_ERROR") == "playwright"


def test_detect_frontend_test_type_api_error() -> None:
    assert detect_frontend_test_type("API_ERROR") == "playwright"


def test_detect_frontend_test_type_routing_error() -> None:
    assert detect_frontend_test_type("ROUTING_ERROR") == "playwright"


def test_detect_frontend_test_type_unknown_defaults_playwright() -> None:
    assert detect_frontend_test_type("SOME_UNKNOWN_ERROR") == "playwright"


def test_detect_monorepo_subdir_api() -> None:
    assert detect_monorepo_subdir("api/app/services/order_service.py") == "api"


def test_detect_monorepo_subdir_ui() -> None:
    assert detect_monorepo_subdir("ui/src/components/Cart.tsx") == "ui"


def test_detect_monorepo_subdir_backend() -> None:
    assert detect_monorepo_subdir("backend/src/main.py") == "backend"


def test_detect_monorepo_subdir_frontend() -> None:
    assert detect_monorepo_subdir("frontend/src/App.tsx") == "frontend"


def test_detect_monorepo_subdir_src_direct() -> None:
    assert detect_monorepo_subdir("src/services/order.py") is None


def test_detect_monorepo_subdir_no_slash() -> None:
    assert detect_monorepo_subdir("order.py") is None
