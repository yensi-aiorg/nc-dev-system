# Sentinel Integration — Full Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Sentinel fix-mode integration to NC Dev System — 8 phases from models through callback, all additive (no modifications to existing V2 pipeline code).

**Architecture:** Sentinel dispatches `SentinelFailureReport` JSON to NC Dev System via CLI (`ncdev fix`) or HTTP API (`ncdev serve`). A new `run_v2_fix()` engine function runs a 5-phase cycle (checkout → reproduce → fix → validate → submit) using existing provider adapters and job runner infrastructure. Results are reported back to Sentinel via HTTP callback.

**Tech Stack:** Python 3.12+, Pydantic v2, FastAPI (intake API), argparse (CLI), pytest

**Contract Document:** `/Users/nrupal/dev/yensi/dev/docs-only/planning/nc-dev-system/11-SENTINEL-INTEGRATION-CONTRACT.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/ncdev/v2/models.py` | Modify | Add `SENTINEL_FIX`, `SENTINEL_REPRODUCE` to `TaskType`; add all Sentinel Pydantic models |
| `src/ncdev/v2/engine.py` | Modify | Add `run_v2_fix()` function |
| `src/ncdev/v2/jobs.py` | Modify | Add `materialize_fix_from_report()` function |
| `src/ncdev/v2/sentinel_prompts.py` | Create | Reproduction and fix prompt templates |
| `src/ncdev/v2/sentinel_safety.py` | Create | Circuit breaker, scope guard, deduplication, cooldown |
| `src/ncdev/v2/sentinel_callback.py` | Create | HTTP callback client to notify Sentinel |
| `src/ncdev/intake_api.py` | Create | FastAPI HTTP intake service |
| `src/ncdev/v2/config.py` | Modify | Add sentinel config section |
| `src/ncdev/cli.py` | Modify | Add `fix` and `serve` subcommands |
| `tests/test_ncdev_v2/test_sentinel_models.py` | Create | Model serialization/deserialization tests |
| `tests/test_ncdev_v2/test_sentinel_engine.py` | Create | Engine function tests |
| `tests/test_ncdev_v2/test_sentinel_jobs.py` | Create | Job materialization tests |
| `tests/test_ncdev_v2/test_sentinel_safety.py` | Create | Safety mechanism tests |
| `tests/test_ncdev_v2/test_sentinel_callback.py` | Create | Callback client tests |
| `tests/test_ncdev_v2/test_sentinel_cli.py` | Create | CLI argument parsing tests |
| `tests/test_ncdev_v2/test_sentinel_config.py` | Create | Config extension tests |
| `tests/test_ncdev_v2/test_intake_api.py` | Create | HTTP API endpoint tests |
| `tests/fixtures/sentinel_reports/` | Create | Sample report JSON files from Appendix A |

---

## Chunk 1: Phase 1 — Models and Types

### Task 1.1: Add Sample Report Fixtures

**Files:**
- Create: `tests/fixtures/sentinel_reports/backend_error.json`
- Create: `tests/fixtures/sentinel_reports/frontend_error.json`

- [ ] **Step 1: Create backend error fixture**

Copy the exact backend sample from contract Section Appendix A into `tests/fixtures/sentinel_reports/backend_error.json`:

```json
{
  "report_id": "rpt_bk_001",
  "schema_version": "1.0",
  "service": {
    "name": "helyx-api",
    "version": "2.1.0",
    "git_sha": "a1b2c3d4e5f6",
    "git_repo": "git@github.com:yensi-solutions/helyx.git",
    "environment": "production",
    "default_branch": "main"
  },
  "source": "backend",
  "severity": "critical",
  "error": {
    "error_type": "UNHANDLED_EXCEPTION",
    "error_code": "E100",
    "message": "AttributeError: 'NoneType' object has no attribute 'total'",
    "stack_trace": "Traceback (most recent call last):\n  File \"api/app/routers/orders.py\", line 45, in create_order\n    result = await order_service.process(order)\n  File \"api/app/services/order_service.py\", line 142, in process\n    amount = order.total * 100\nAttributeError: 'NoneType' object has no attribute 'total'",
    "file": "api/app/services/order_service.py",
    "line": 142,
    "function": "process"
  },
  "chain": {
    "chain_id": "ch_xyz789",
    "nodes": [
      {"service": "helyx-api", "endpoint": "POST /api/orders", "method": "POST", "status_code": 500, "duration_ms": 234},
      {"service": "inventory-service", "endpoint": "GET /stock/check", "method": "GET", "status_code": 200, "duration_ms": 45}
    ],
    "failed_node_index": 0
  },
  "frequency": {
    "last_hour": 47,
    "last_24h": 312,
    "first_seen": "2026-03-15T10:15:00Z",
    "affected_users": 23
  },
  "context": {
    "request": {"method": "POST", "path": "/api/orders", "body_redacted": {"items": "[REDACTED]"}},
    "environment": {"python_version": "3.12.1", "fastapi_version": "0.115.0"},
    "recent_deploys": [
      {"sha": "a1b2c3d4e5f6", "timestamp": "2026-03-15T09:00:00Z", "message": "Add coupon support to checkout"}
    ],
    "related_files": ["api/app/models/order.py", "api/app/routers/orders.py"]
  },
  "triage": {
    "ticket_id": "SEN-042",
    "priority": 1,
    "notes": "Likely caused by the coupon support deploy 1 hour before first occurrence",
    "auto_deploy": false,
    "max_attempts": 3
  },
  "detected_at": "2026-03-15T10:15:00Z",
  "approved_at": "2026-03-15T10:20:00Z"
}
```

- [ ] **Step 2: Create frontend error fixture**

Copy the exact frontend sample from contract Appendix A into `tests/fixtures/sentinel_reports/frontend_error.json`.

- [ ] **Step 3: Commit fixtures**

```bash
git add tests/fixtures/sentinel_reports/
git commit -m "test(sentinel): add sample failure report fixtures from contract"
```

---

### Task 1.2: Add TaskType Enum Members

**Files:**
- Modify: `src/ncdev/v2/models.py` (line 30-45, `TaskType` enum)
- Test: `tests/test_ncdev_v2/test_sentinel_models.py`

- [ ] **Step 1: Write failing test for new TaskType members**

Create `tests/test_ncdev_v2/test_sentinel_models.py`:

```python
from ncdev.v2.models import TaskType


def test_sentinel_task_types_exist() -> None:
    assert TaskType.SENTINEL_FIX == "sentinel_fix"
    assert TaskType.SENTINEL_REPRODUCE == "sentinel_reproduce"


def test_sentinel_task_types_in_values() -> None:
    values = [t.value for t in TaskType]
    assert "sentinel_fix" in values
    assert "sentinel_reproduce" in values
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/test_ncdev_v2/test_sentinel_models.py -v`
Expected: FAIL with `AttributeError: SENTINEL_FIX`

- [ ] **Step 3: Add enum members to TaskType**

In `src/ncdev/v2/models.py`, add two new members at the end of the `TaskType` enum (after `DELIVERY_PACK`):

```python
    SENTINEL_FIX = "sentinel_fix"
    SENTINEL_REPRODUCE = "sentinel_reproduce"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/test_ncdev_v2/test_sentinel_models.py -v`
Expected: PASS

- [ ] **Step 5: Run full existing test suite to confirm no regression**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/ -v --tb=short`
Expected: All existing tests still pass

- [ ] **Step 6: Commit**

```bash
git add src/ncdev/v2/models.py tests/test_ncdev_v2/test_sentinel_models.py
git commit -m "feat(sentinel): add SENTINEL_FIX and SENTINEL_REPRODUCE to TaskType"
```

---

### Task 1.3: Add FixOutcome Enum and Sub-Models

**Files:**
- Modify: `src/ncdev/v2/models.py`
- Modify: `tests/test_ncdev_v2/test_sentinel_models.py`

- [ ] **Step 1: Write failing tests for FixOutcome and sub-models**

Append to `tests/test_ncdev_v2/test_sentinel_models.py`:

```python
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
    ServiceInfo,
    TriageInfo,
)


def test_fix_outcome_values() -> None:
    assert FixOutcome.FIXED == "fixed"
    assert FixOutcome.CANNOT_REPRODUCE == "cannot_reproduce"
    assert FixOutcome.FIX_FAILED == "fix_failed"
    assert FixOutcome.VALIDATION_FAILED == "validation_failed"
    assert FixOutcome.CHECKOUT_FAILED == "checkout_failed"
    assert FixOutcome.BLOCKED == "blocked"


def test_error_source_values() -> None:
    assert ErrorSource.BACKEND == "backend"
    assert ErrorSource.FRONTEND == "frontend"


def test_error_severity_values() -> None:
    assert ErrorSeverity.CRITICAL == "critical"
    assert ErrorSeverity.HIGH == "high"
    assert ErrorSeverity.MEDIUM == "medium"
    assert ErrorSeverity.LOW == "low"


def test_service_info_construction() -> None:
    info = ServiceInfo(
        name="helyx-api",
        version="2.1.0",
        git_sha="abc123",
        git_repo="git@github.com:org/repo.git",
    )
    assert info.environment == "production"
    assert info.default_branch == "main"


def test_error_detail_optional_fields() -> None:
    detail = ErrorDetail(
        error_type="UNHANDLED_EXCEPTION",
        error_code="E100",
        message="something broke",
    )
    assert detail.stack_trace is None
    assert detail.file is None
    assert detail.line is None
    assert detail.function is None
    assert detail.component is None


def test_chain_node_construction() -> None:
    node = ChainNode(
        service="helyx-api",
        endpoint="POST /api/orders",
        method="POST",
        status_code=500,
        duration_ms=234,
    )
    assert node.status_code == 500


def test_request_chain_construction() -> None:
    chain = RequestChain(
        chain_id="ch_xyz",
        nodes=[
            ChainNode(service="svc", endpoint="/ep", method="GET", status_code=200, duration_ms=10),
        ],
        failed_node_index=0,
    )
    assert len(chain.nodes) == 1


def test_network_failure_construction() -> None:
    nf = NetworkFailure(url="/api/test", method="GET", error="Failed to fetch")
    assert nf.status_code is None
    assert nf.duration_ms is None


def test_frontend_context_defaults() -> None:
    ctx = FrontendContext(url="https://example.com/page")
    assert ctx.interaction_trail == []
    assert ctx.console_errors == []
    assert ctx.network_failures == []
    assert ctx.component_stack is None
    assert ctx.core_web_vitals is None


def test_error_frequency_defaults() -> None:
    from datetime import datetime, timezone

    freq = ErrorFrequency(
        last_hour=10,
        last_24h=50,
        first_seen=datetime(2026, 3, 15, tzinfo=timezone.utc),
    )
    assert freq.affected_users == 0


def test_error_context_defaults() -> None:
    ctx = ErrorContext()
    assert ctx.request is None
    assert ctx.environment == {}
    assert ctx.recent_deploys == []
    assert ctx.related_files == []


def test_deploy_info_construction() -> None:
    from datetime import datetime, timezone

    di = DeployInfo(
        sha="abc123",
        timestamp=datetime(2026, 3, 15, tzinfo=timezone.utc),
        message="Deploy message",
    )
    assert di.sha == "abc123"


def test_triage_info_defaults() -> None:
    ti = TriageInfo(ticket_id="SEN-042")
    assert ti.assignee == "ncdev"
    assert ti.priority == 1
    assert ti.notes == ""
    assert ti.auto_deploy is False
    assert ti.max_attempts == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/test_ncdev_v2/test_sentinel_models.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Add enums and sub-models to models.py**

Add the following to `src/ncdev/v2/models.py`, **after the `TaskType` enum and before `ArtifactEnvelope`**. Follow the existing pattern: `str, Enum` for enums, `BaseModel` with `Field(default_factory=...)` for lists/dicts:

```python
class ErrorSource(str, Enum):
    BACKEND = "backend"
    FRONTEND = "frontend"


class ErrorSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FixOutcome(str, Enum):
    FIXED = "fixed"
    CANNOT_REPRODUCE = "cannot_reproduce"
    FIX_FAILED = "fix_failed"
    VALIDATION_FAILED = "validation_failed"
    CHECKOUT_FAILED = "checkout_failed"
    BLOCKED = "blocked"


class ServiceInfo(BaseModel):
    name: str
    version: str
    git_sha: str
    git_repo: str
    environment: str = "production"
    default_branch: str = "main"


class ErrorDetail(BaseModel):
    error_type: str
    error_code: str
    message: str
    stack_trace: str | None = None
    file: str | None = None
    line: int | None = None
    function: str | None = None
    component: str | None = None


class ChainNode(BaseModel):
    service: str
    endpoint: str
    method: str
    status_code: int
    duration_ms: int


class RequestChain(BaseModel):
    chain_id: str
    nodes: list[ChainNode]
    failed_node_index: int


class NetworkFailure(BaseModel):
    url: str
    method: str
    status_code: int | None = None
    error: str
    duration_ms: int | None = None


class FrontendContext(BaseModel):
    url: str
    user_agent: str | None = None
    viewport: str | None = None
    interaction_trail: list[str] = Field(default_factory=list)
    console_errors: list[str] = Field(default_factory=list)
    network_failures: list[NetworkFailure] = Field(default_factory=list)
    component_stack: str | None = None
    core_web_vitals: dict[str, float] | None = None


class ErrorFrequency(BaseModel):
    last_hour: int
    last_24h: int
    first_seen: datetime
    affected_users: int = 0


class ErrorContext(BaseModel):
    request: dict[str, Any] | None = None
    environment: dict[str, str] = Field(default_factory=dict)
    recent_deploys: list[DeployInfo] = Field(default_factory=list)
    similar_successful_request: dict[str, Any] | None = None
    recent_log_lines: list[str] = Field(default_factory=list)
    related_files: list[str] = Field(default_factory=list)


class DeployInfo(BaseModel):
    sha: str
    timestamp: datetime
    message: str


class TriageInfo(BaseModel):
    ticket_id: str
    assignee: str = "ncdev"
    priority: int = 1
    notes: str = ""
    auto_deploy: bool = False
    max_attempts: int = 3
```

**Important:** `DeployInfo` must be defined **before** `ErrorContext` since `ErrorContext` references it. Order the classes with dependencies first.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/test_ncdev_v2/test_sentinel_models.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/v2/models.py tests/test_ncdev_v2/test_sentinel_models.py
git commit -m "feat(sentinel): add FixOutcome enum and all sub-models"
```

---

### Task 1.4: Add SentinelFailureReport Model

**Files:**
- Modify: `src/ncdev/v2/models.py`
- Modify: `tests/test_ncdev_v2/test_sentinel_models.py`

- [ ] **Step 1: Write failing test for SentinelFailureReport**

Append to `tests/test_ncdev_v2/test_sentinel_models.py`:

```python
import json
from pathlib import Path

from pydantic import ConfigDict

from ncdev.v2.models import SentinelFailureReport


FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "sentinel_reports"


def test_sentinel_failure_report_from_backend_fixture() -> None:
    raw = json.loads((FIXTURES_DIR / "backend_error.json").read_text())
    report = SentinelFailureReport.model_validate(raw)
    assert report.report_id == "rpt_bk_001"
    assert report.schema_version == "1.0"
    assert report.source == ErrorSource.BACKEND
    assert report.severity == ErrorSeverity.CRITICAL
    assert report.service.name == "helyx-api"
    assert report.service.git_sha == "a1b2c3d4e5f6"
    assert report.error.error_type == "UNHANDLED_EXCEPTION"
    assert report.error.error_code == "E100"
    assert report.error.file == "api/app/services/order_service.py"
    assert report.error.line == 142
    assert report.chain is not None
    assert len(report.chain.nodes) == 2
    assert report.chain.failed_node_index == 0
    assert report.frontend_context is None
    assert report.frequency.last_24h == 312
    assert report.frequency.affected_users == 23
    assert report.triage is not None
    assert report.triage.ticket_id == "SEN-042"
    assert report.approved_at is not None


def test_sentinel_failure_report_from_frontend_fixture() -> None:
    raw = json.loads((FIXTURES_DIR / "frontend_error.json").read_text())
    report = SentinelFailureReport.model_validate(raw)
    assert report.report_id == "rpt_fe_001"
    assert report.source == ErrorSource.FRONTEND
    assert report.severity == ErrorSeverity.HIGH
    assert report.frontend_context is not None
    assert report.frontend_context.url == "https://helyx.local/projects"
    assert len(report.frontend_context.interaction_trail) == 3
    assert len(report.frontend_context.network_failures) == 1
    assert report.chain is None


def test_sentinel_failure_report_roundtrip() -> None:
    raw = json.loads((FIXTURES_DIR / "backend_error.json").read_text())
    report = SentinelFailureReport.model_validate(raw)
    dumped = json.loads(report.model_dump_json())
    reloaded = SentinelFailureReport.model_validate(dumped)
    assert reloaded.report_id == report.report_id
    assert reloaded.error.message == report.error.message


def test_sentinel_failure_report_ignores_extra_fields() -> None:
    raw = json.loads((FIXTURES_DIR / "backend_error.json").read_text())
    raw["unknown_future_field"] = "should be ignored"
    report = SentinelFailureReport.model_validate(raw)
    assert report.report_id == "rpt_bk_001"


def test_sentinel_failure_report_minimal() -> None:
    """Report with only required fields, no optional data."""
    from datetime import datetime, timezone

    report = SentinelFailureReport(
        report_id="rpt_minimal",
        service=ServiceInfo(
            name="test-svc",
            version="1.0.0",
            git_sha="abc123",
            git_repo="git@github.com:org/repo.git",
        ),
        source=ErrorSource.BACKEND,
        severity=ErrorSeverity.LOW,
        error=ErrorDetail(
            error_type="UNHANDLED_EXCEPTION",
            error_code="E100",
            message="test error",
        ),
        frequency=ErrorFrequency(
            last_hour=1,
            last_24h=1,
            first_seen=datetime(2026, 3, 15, tzinfo=timezone.utc),
        ),
        context=ErrorContext(),
        detected_at=datetime(2026, 3, 15, tzinfo=timezone.utc),
    )
    assert report.chain is None
    assert report.frontend_context is None
    assert report.triage is None
    assert report.approved_at is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/test_ncdev_v2/test_sentinel_models.py::test_sentinel_failure_report_from_backend_fixture -v`
Expected: FAIL with `ImportError: cannot import name 'SentinelFailureReport'`

- [ ] **Step 3: Add SentinelFailureReport model**

Add to `src/ncdev/v2/models.py`, after all the sub-models and before `ArtifactEnvelope`:

```python
class SentinelFailureReport(BaseModel):
    model_config = ConfigDict(extra="ignore")

    report_id: str
    schema_version: str = "1.0"
    service: ServiceInfo
    source: ErrorSource
    severity: ErrorSeverity
    error: ErrorDetail
    chain: RequestChain | None = None
    frontend_context: FrontendContext | None = None
    frequency: ErrorFrequency
    context: ErrorContext
    triage: TriageInfo | None = None
    detected_at: datetime
    approved_at: datetime | None = None
```

Also add the `ConfigDict` import at the top of the file:

```python
from pydantic import BaseModel, ConfigDict, Field
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/test_ncdev_v2/test_sentinel_models.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/v2/models.py tests/test_ncdev_v2/test_sentinel_models.py
git commit -m "feat(sentinel): add SentinelFailureReport model with extra=ignore"
```

---

### Task 1.5: Add SentinelFixResult Model

**Files:**
- Modify: `src/ncdev/v2/models.py`
- Modify: `tests/test_ncdev_v2/test_sentinel_models.py`

- [ ] **Step 1: Write failing test for SentinelFixResult**

Append to `tests/test_ncdev_v2/test_sentinel_models.py`:

```python
from ncdev.v2.models import SentinelFixResult


def test_sentinel_fix_result_fixed() -> None:
    from datetime import datetime, timezone

    now = datetime(2026, 3, 15, 14, 30, 0, tzinfo=timezone.utc)
    result = SentinelFixResult(
        report_id="rpt_bk_001",
        run_id="fix-rpt_bk_001-20260315-143000",
        outcome=FixOutcome.FIXED,
        outcome_detail="Fixed null check in order_service.py",
        pr_url="https://github.com/org/repo/pull/42",
        fix_branch="sentinel/fix/rpt_bk_001",
        commit_sha="deadbeef",
        files_changed=["api/app/services/order_service.py"],
        reproduction_test="tests/test_order_service.py::test_sentinel_rpt_bk_001",
        agent_reasoning="The order.total was None when coupon reduced price to zero",
        fix_description="Added null check before accessing total attribute",
        attempts_used=1,
        duration_seconds=145,
        started_at=now,
        completed_at=now,
    )
    assert result.outcome == FixOutcome.FIXED
    assert result.pr_url == "https://github.com/org/repo/pull/42"
    assert len(result.files_changed) == 1


def test_sentinel_fix_result_cannot_reproduce() -> None:
    from datetime import datetime, timezone

    now = datetime(2026, 3, 15, tzinfo=timezone.utc)
    result = SentinelFixResult(
        report_id="rpt_bk_002",
        run_id="fix-rpt_bk_002-20260315-150000",
        outcome=FixOutcome.CANNOT_REPRODUCE,
        outcome_detail="Reproduction test passed — bug not reproducible",
        started_at=now,
        completed_at=now,
    )
    assert result.outcome == FixOutcome.CANNOT_REPRODUCE
    assert result.pr_url is None
    assert result.files_changed == []
    assert result.attempts_used == 0


def test_sentinel_fix_result_roundtrip() -> None:
    from datetime import datetime, timezone

    now = datetime(2026, 3, 15, tzinfo=timezone.utc)
    result = SentinelFixResult(
        report_id="rpt_bk_001",
        run_id="fix-rpt_bk_001-20260315-143000",
        outcome=FixOutcome.FIXED,
        outcome_detail="Fixed",
        started_at=now,
        completed_at=now,
    )
    dumped = json.loads(result.model_dump_json())
    reloaded = SentinelFixResult.model_validate(dumped)
    assert reloaded.report_id == result.report_id
    assert reloaded.outcome == result.outcome
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/test_ncdev_v2/test_sentinel_models.py::test_sentinel_fix_result_fixed -v`
Expected: FAIL with `ImportError: cannot import name 'SentinelFixResult'`

- [ ] **Step 3: Add SentinelFixResult model**

Add to `src/ncdev/v2/models.py`, right after `SentinelFailureReport`:

```python
class SentinelFixResult(BaseModel):
    report_id: str
    run_id: str
    schema_version: str = "1.0"
    outcome: FixOutcome
    outcome_detail: str
    pr_url: str | None = None
    fix_branch: str | None = None
    commit_sha: str | None = None
    files_changed: list[str] = Field(default_factory=list)
    reproduction_test: str | None = None
    agent_reasoning: str | None = None
    fix_description: str | None = None
    attempts_used: int = 0
    max_attempts: int = 3
    duration_seconds: int = 0
    started_at: datetime
    completed_at: datetime
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/test_ncdev_v2/test_sentinel_models.py -v`
Expected: All tests PASS

- [ ] **Step 5: Run full test suite to confirm no regressions**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/ncdev/v2/models.py tests/test_ncdev_v2/test_sentinel_models.py
git commit -m "feat(sentinel): add SentinelFixResult model and FixOutcome enum"
```

---

## Chunk 2: Phase 2 — Engine and Jobs

### Task 2.1: Add Sentinel Prompt Templates

**Files:**
- Create: `src/ncdev/v2/sentinel_prompts.py`
- Create: `tests/test_ncdev_v2/test_sentinel_prompts.py`

- [ ] **Step 1: Write failing test for prompt templates**

Create `tests/test_ncdev_v2/test_sentinel_prompts.py`:

```python
import json
from pathlib import Path

from ncdev.v2.models import SentinelFailureReport
from ncdev.v2.sentinel_prompts import build_fix_prompt, build_reproduction_prompt

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "sentinel_reports"


def test_build_reproduction_prompt_backend() -> None:
    raw = json.loads((FIXTURES_DIR / "backend_error.json").read_text())
    report = SentinelFailureReport.model_validate(raw)
    prompt = build_reproduction_prompt(
        report=report,
        error_file_contents="def process(order):\n    amount = order.total * 100\n",
        related_file_contents={"api/app/models/order.py": "class Order: ..."},
        existing_test_contents="def test_process(): ...",
        git_log="abc123 Add coupon support",
    )
    assert "rpt_bk_001" in prompt
    assert "UNHANDLED_EXCEPTION" in prompt
    assert "order_service.py" in prompt
    assert "test_sentinel_rpt_bk_001" in prompt
    assert "Do NOT fix the bug" in prompt


def test_build_reproduction_prompt_frontend() -> None:
    raw = json.loads((FIXTURES_DIR / "frontend_error.json").read_text())
    report = SentinelFailureReport.model_validate(raw)
    prompt = build_reproduction_prompt(
        report=report,
        error_file_contents="export function ProjectList() { ... }",
        related_file_contents={},
        existing_test_contents="",
        git_log="abc123 Refactor project list",
    )
    assert "rpt_fe_001" in prompt
    assert "REACT_RENDER_ERROR" in prompt
    assert "Vitest" in prompt or "Playwright" in prompt
    assert "Do NOT fix the bug" in prompt


def test_build_fix_prompt() -> None:
    raw = json.loads((FIXTURES_DIR / "backend_error.json").read_text())
    report = SentinelFailureReport.model_validate(raw)
    prompt = build_fix_prompt(
        report=report,
        test_failure_output="FAILED test_sentinel_rpt_bk_001 - AttributeError",
    )
    assert "test_failure_output" not in prompt or "FAILED" in prompt
    assert "Do NOT modify the reproduction test" in prompt
    assert "minimal change" in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/test_ncdev_v2/test_sentinel_prompts.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement prompt templates**

Create `src/ncdev/v2/sentinel_prompts.py`:

```python
from __future__ import annotations

from ncdev.v2.models import ErrorSource, SentinelFailureReport

_BACKEND_REPRODUCTION_TEMPLATE = """\
You are a senior software engineer. A production error has been reported by Sentinel.

## Failure Report
{report_json}

## Source Code
### {error_file}
{error_file_contents}

### Related Files
{related_file_contents}

## Existing Tests
{existing_test_contents}

## Recent Commits
{git_log}

## Your Task
Write a single test function that reproduces this exact failure.

Rules:
1. The test MUST fail with the same error type as the report ({error_type})
2. Place the test in the appropriate test file (follow existing test file conventions)
3. Name the test: test_sentinel_{report_id}_{brief_description}
4. Include a docstring: "Reproduction test for {report_id}: {error_message}"
5. Use existing test fixtures and patterns from the codebase
6. Do NOT fix the bug — only write the reproduction test
7. The test should cover the specific scenario described in the failure report
"""

_FRONTEND_REPRODUCTION_TEMPLATE = """\
You are a senior frontend engineer. A production error has been reported by Sentinel.

## Failure Report
{report_json}

## Component Code
### {error_file}
{error_file_contents}

### Related Components
{related_file_contents}

## Existing Tests
{existing_test_contents}

## User Interaction Trail
{interaction_trail}

## Your Task
Write a test that reproduces this exact failure.

Rules:
1. If this is a component error, write a Vitest + React Testing Library test
2. If this is a page-level or interaction error, write a Playwright E2E test
3. Simulate the user interaction trail from the report
4. The test MUST fail with the reported error
5. Name the test: test_sentinel_{report_id}_{brief_description}
6. Do NOT fix the bug — only write the reproduction test
"""

_FIX_TEMPLATE = """\
Your reproduction test correctly fails with:
  {test_failure_output}

Now fix the code so that the test passes.

Rules:
1. Do NOT modify the reproduction test
2. Only modify source code files
3. Make the minimal change needed to fix the issue
4. Do not refactor, restructure, or "improve" surrounding code
5. If the fix requires changes to multiple files, that's fine — make all necessary changes
"""


def _slugify(text: str) -> str:
    return text.lower().replace(" ", "_").replace("'", "")[:40]


def _format_related(related: dict[str, str]) -> str:
    if not related:
        return "(none)"
    parts: list[str] = []
    for path, content in related.items():
        parts.append(f"### {path}\n{content}")
    return "\n\n".join(parts)


def build_reproduction_prompt(
    *,
    report: SentinelFailureReport,
    error_file_contents: str,
    related_file_contents: dict[str, str],
    existing_test_contents: str,
    git_log: str,
) -> str:
    report_json = report.model_dump_json(indent=2)
    brief = _slugify(report.error.message)

    if report.source == ErrorSource.FRONTEND:
        interaction_trail = "\n".join(
            report.frontend_context.interaction_trail
        ) if report.frontend_context else "(none)"
        return _FRONTEND_REPRODUCTION_TEMPLATE.format(
            report_json=report_json,
            error_file=report.error.file or "(unknown)",
            error_file_contents=error_file_contents or "(not available)",
            related_file_contents=_format_related(related_file_contents),
            existing_test_contents=existing_test_contents or "(none)",
            interaction_trail=interaction_trail,
            error_type=report.error.error_type,
            report_id=report.report_id,
            brief_description=brief,
            error_message=report.error.message,
        )

    return _BACKEND_REPRODUCTION_TEMPLATE.format(
        report_json=report_json,
        error_file=report.error.file or "(unknown)",
        error_file_contents=error_file_contents or "(not available)",
        related_file_contents=_format_related(related_file_contents),
        existing_test_contents=existing_test_contents or "(none)",
        git_log=git_log or "(none)",
        error_type=report.error.error_type,
        report_id=report.report_id,
        brief_description=brief,
        error_message=report.error.message,
    )


def build_fix_prompt(
    *,
    report: SentinelFailureReport,
    test_failure_output: str,
) -> str:
    return _FIX_TEMPLATE.format(
        test_failure_output=test_failure_output,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/test_ncdev_v2/test_sentinel_prompts.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/v2/sentinel_prompts.py tests/test_ncdev_v2/test_sentinel_prompts.py
git commit -m "feat(sentinel): add reproduction and fix prompt templates"
```

---

### Task 2.2: Add materialize_fix_from_report() to jobs.py

**Files:**
- Modify: `src/ncdev/v2/jobs.py`
- Create: `tests/test_ncdev_v2/test_sentinel_jobs.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_ncdev_v2/test_sentinel_jobs.py`:

```python
import json
from pathlib import Path

from ncdev.v2.models import (
    ExecutionJob,
    JobQueueDoc,
    SentinelFailureReport,
    TaskType,
)
from ncdev.v2.jobs import materialize_fix_from_report

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "sentinel_reports"


def test_materialize_fix_creates_two_jobs(tmp_path: Path) -> None:
    raw = json.loads((FIXTURES_DIR / "backend_error.json").read_text())
    report = SentinelFailureReport.model_validate(raw)

    run_dir = tmp_path / "run"
    (run_dir / "outputs" / "task-requests").mkdir(parents=True)
    (run_dir / "outputs" / "sentinel-report.json").write_text(
        report.model_dump_json(indent=2), encoding="utf-8"
    )

    queue = materialize_fix_from_report(
        run_dir=run_dir,
        report=report,
        target_path=str(tmp_path / "repo"),
        registry={},
    )

    assert isinstance(queue, JobQueueDoc)
    assert len(queue.jobs) == 2

    reproduce_job = queue.jobs[0]
    assert reproduce_job.task_type == TaskType.SENTINEL_REPRODUCE
    assert reproduce_job.job_id == "reproduce-rpt_bk_001"
    assert reproduce_job.depends_on == []
    assert reproduce_job.metadata["report_id"] == "rpt_bk_001"

    fix_job = queue.jobs[1]
    assert fix_job.task_type == TaskType.SENTINEL_FIX
    assert fix_job.job_id == "fix-rpt_bk_001"
    assert fix_job.depends_on == ["reproduce-rpt_bk_001"]
    assert fix_job.metadata["report_id"] == "rpt_bk_001"


def test_materialize_fix_persists_task_requests(tmp_path: Path) -> None:
    raw = json.loads((FIXTURES_DIR / "backend_error.json").read_text())
    report = SentinelFailureReport.model_validate(raw)

    run_dir = tmp_path / "run"
    (run_dir / "outputs" / "task-requests").mkdir(parents=True)
    (run_dir / "outputs" / "sentinel-report.json").write_text(
        report.model_dump_json(indent=2), encoding="utf-8"
    )

    queue = materialize_fix_from_report(
        run_dir=run_dir,
        report=report,
        target_path=str(tmp_path / "repo"),
        registry={},
    )

    for job in queue.jobs:
        artifact_path = run_dir / job.request_artifact
        assert artifact_path.exists(), f"Missing request artifact: {job.request_artifact}"


def test_materialize_fix_frontend_report(tmp_path: Path) -> None:
    raw = json.loads((FIXTURES_DIR / "frontend_error.json").read_text())
    report = SentinelFailureReport.model_validate(raw)

    run_dir = tmp_path / "run"
    (run_dir / "outputs" / "task-requests").mkdir(parents=True)
    (run_dir / "outputs" / "sentinel-report.json").write_text(
        report.model_dump_json(indent=2), encoding="utf-8"
    )

    queue = materialize_fix_from_report(
        run_dir=run_dir,
        report=report,
        target_path=str(tmp_path / "repo"),
        registry={},
    )

    assert len(queue.jobs) == 2
    assert queue.jobs[0].task_type == TaskType.SENTINEL_REPRODUCE
    assert queue.jobs[1].task_type == TaskType.SENTINEL_FIX
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/test_ncdev_v2/test_sentinel_jobs.py -v`
Expected: FAIL with `ImportError: cannot import name 'materialize_fix_from_report'`

- [ ] **Step 3: Implement materialize_fix_from_report()**

Add to `src/ncdev/v2/jobs.py` (at the end of the file, following the existing pattern of `materialize_job_queue` and `materialize_repair_job_queue`):

```python
def materialize_fix_from_report(
    run_dir: Path,
    report: SentinelFailureReport,
    target_path: str,
    registry: dict[str, Any],
) -> JobQueueDoc:
    """Create a job queue for fixing a Sentinel-reported error.

    Jobs created:
    1. SENTINEL_REPRODUCE — write reproduction test (Claude)
    2. SENTINEL_FIX — write code fix (Codex, with Claude fallback)

    Validation and submission are handled by the engine directly,
    not as agent jobs (they're deterministic operations).
    """
    outputs_dir = run_dir / "outputs"
    requests_dir = outputs_dir / "task-requests"
    requests_dir.mkdir(parents=True, exist_ok=True)

    jobs: list[ExecutionJob] = []

    reproduce_id = f"reproduce-{report.report_id}"
    reproduce_request = TaskRequestDoc(
        generator="ncdev.v2.jobs.materialize_fix_from_report",
        schema_id="task-request.v2",
        task_type=TaskType.SENTINEL_REPRODUCE,
        provider="anthropic_claude_code",
        model="opus",
        title=f"Reproduce: {report.error.error_code} in {report.error.file or 'unknown'}:{report.error.line or '?'}",
        prompt="(prompt will be built at execution time with file contents)",
        input_artifacts=["outputs/sentinel-report.json"],
        metadata={
            "report_id": report.report_id,
            "error_file": report.error.file,
            "error_line": report.error.line,
        },
    )
    reproduce_path = _persist_request(
        requests_dir / "sentinel_reproduce.json", reproduce_request
    )
    jobs.append(
        ExecutionJob(
            job_id=reproduce_id,
            task_type=TaskType.SENTINEL_REPRODUCE,
            provider="anthropic_claude_code",
            model="opus",
            title=reproduce_request.title,
            request_artifact=f"outputs/task-requests/sentinel_reproduce.json",
            target_path=target_path,
            input_artifacts=["outputs/sentinel-report.json"],
            depends_on=[],
            metadata={
                "report_id": report.report_id,
                "error_file": report.error.file,
                "error_line": report.error.line,
                "attempt": 1,
                "max_attempts": report.triage.max_attempts if report.triage else 3,
            },
        )
    )

    fix_id = f"fix-{report.report_id}"
    fix_request = TaskRequestDoc(
        generator="ncdev.v2.jobs.materialize_fix_from_report",
        schema_id="task-request.v2",
        task_type=TaskType.SENTINEL_FIX,
        provider="openai_codex",
        model="gpt-5.2-codex",
        title=f"Fix: {report.error.error_code} in {report.error.file or 'unknown'}:{report.error.line or '?'}",
        prompt="(prompt will be built at execution time with test failure output)",
        input_artifacts=[
            "outputs/sentinel-report.json",
            "outputs/reproduction-test-result.json",
        ],
        metadata={
            "report_id": report.report_id,
        },
    )
    _persist_request(requests_dir / "sentinel_fix.json", fix_request)
    jobs.append(
        ExecutionJob(
            job_id=fix_id,
            task_type=TaskType.SENTINEL_FIX,
            provider="openai_codex",
            model="gpt-5.2-codex",
            title=fix_request.title,
            request_artifact="outputs/task-requests/sentinel_fix.json",
            target_path=target_path,
            input_artifacts=[
                "outputs/sentinel-report.json",
                "outputs/reproduction-test-result.json",
            ],
            depends_on=[reproduce_id],
            metadata={
                "report_id": report.report_id,
                "attempt": 1,
                "max_attempts": report.triage.max_attempts if report.triage else 3,
            },
        )
    )

    queue = JobQueueDoc(
        generator="ncdev.v2.jobs.materialize_fix_from_report",
        project_name=report.service.name,
        jobs=jobs,
    )
    _persist_request(outputs_dir / "job-queue.json", queue)
    return queue
```

Also add the necessary imports at the top of `jobs.py`:

```python
from ncdev.v2.models import SentinelFailureReport
```

(Add to existing imports — `TaskRequestDoc`, `ExecutionJob`, `JobQueueDoc`, `TaskType` should already be imported.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/test_ncdev_v2/test_sentinel_jobs.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/v2/jobs.py tests/test_ncdev_v2/test_sentinel_jobs.py
git commit -m "feat(sentinel): add materialize_fix_from_report() to jobs.py"
```

---

### Task 2.3: Add run_v2_fix() Engine Function

**Files:**
- Modify: `src/ncdev/v2/engine.py`
- Create: `tests/test_ncdev_v2/test_sentinel_engine.py`

- [ ] **Step 1: Write failing test for run_v2_fix()**

Create `tests/test_ncdev_v2/test_sentinel_engine.py`:

```python
import json
from pathlib import Path

from ncdev.v2.engine import run_v2_fix
from ncdev.v2.models import V2TaskStatus

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "sentinel_reports"


def test_run_v2_fix_dry_run_loads_report(tmp_path: Path) -> None:
    report_path = FIXTURES_DIR / "backend_error.json"
    target_repo = tmp_path / "repo"
    target_repo.mkdir()

    state = run_v2_fix(
        workspace=tmp_path,
        report_path=report_path,
        target_repo_path=target_repo,
        dry_run=True,
    )

    assert state.command == "fix"
    assert state.metadata["mode"] == "sentinel_fix"
    assert state.metadata["report_id"] == "rpt_bk_001"
    assert state.metadata["service_name"] == "helyx-api"
    assert state.metadata["git_sha"] == "a1b2c3d4e5f6"
    assert state.metadata["error_code"] == "E100"
    assert state.metadata["severity"] == "critical"
    assert state.metadata["source"] == "backend"

    task_names = [t.name for t in state.tasks]
    assert task_names == [
        "load_report",
        "checkout_version",
        "reproduce",
        "fix",
        "validate",
        "submit",
    ]

    load_task = next(t for t in state.tasks if t.name == "load_report")
    assert load_task.status == V2TaskStatus.PASSED


def test_run_v2_fix_dry_run_persists_report_artifact(tmp_path: Path) -> None:
    report_path = FIXTURES_DIR / "backend_error.json"
    target_repo = tmp_path / "repo"
    target_repo.mkdir()

    state = run_v2_fix(
        workspace=tmp_path,
        report_path=report_path,
        target_repo_path=target_repo,
        dry_run=True,
    )

    run_dir = Path(state.run_dir)
    sentinel_report = run_dir / "outputs" / "sentinel-report.json"
    assert sentinel_report.exists()
    raw = json.loads(sentinel_report.read_text())
    assert raw["report_id"] == "rpt_bk_001"


def test_run_v2_fix_invalid_report_blocks(tmp_path: Path) -> None:
    bad_report = tmp_path / "bad.json"
    bad_report.write_text('{"not": "a valid report"}', encoding="utf-8")
    target_repo = tmp_path / "repo"
    target_repo.mkdir()

    state = run_v2_fix(
        workspace=tmp_path,
        report_path=bad_report,
        target_repo_path=target_repo,
        dry_run=True,
    )

    load_task = next(t for t in state.tasks if t.name == "load_report")
    assert load_task.status == V2TaskStatus.BLOCKED
    assert state.status == V2TaskStatus.BLOCKED


def test_run_v2_fix_missing_report_blocks(tmp_path: Path) -> None:
    target_repo = tmp_path / "repo"
    target_repo.mkdir()

    state = run_v2_fix(
        workspace=tmp_path,
        report_path=tmp_path / "nonexistent.json",
        target_repo_path=target_repo,
        dry_run=True,
    )

    load_task = next(t for t in state.tasks if t.name == "load_report")
    assert load_task.status == V2TaskStatus.BLOCKED


def test_run_v2_fix_dry_run_stops_after_load(tmp_path: Path) -> None:
    """In dry_run mode, only load_report runs. Other tasks stay pending."""
    report_path = FIXTURES_DIR / "backend_error.json"
    target_repo = tmp_path / "repo"
    target_repo.mkdir()

    state = run_v2_fix(
        workspace=tmp_path,
        report_path=report_path,
        target_repo_path=target_repo,
        dry_run=True,
    )

    checkout_task = next(t for t in state.tasks if t.name == "checkout_version")
    assert checkout_task.status == V2TaskStatus.PENDING
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/test_ncdev_v2/test_sentinel_engine.py -v`
Expected: FAIL with `ImportError: cannot import name 'run_v2_fix'`

- [ ] **Step 3: Implement run_v2_fix()**

Add to `src/ncdev/v2/engine.py`. This is the initial implementation that handles report loading and dry-run mode. The full execution phases (checkout, reproduce, fix, validate, submit) will be fleshed out in later tasks when they can be integration-tested:

```python
def run_v2_fix(
    workspace: Path,
    report_path: Path,
    target_repo_path: Path,
    dry_run: bool,
    *,
    auto_deploy: bool = False,
    max_attempts: int = 3,
    command: str = "fix",
    run_id: str | None = None,
) -> V2RunState:
    """Fix a production error reported by Sentinel.

    Unlike the full V2 pipeline (discover -> deliver), this is a focused
    5-phase cycle: checkout -> reproduce -> fix -> validate -> submit.
    """
    import json as _json
    from ncdev.v2.models import SentinelFailureReport

    rid = run_id or f"fix-{report_path.stem}-{_utc_now().strftime('%Y%m%d-%H%M%S')}"
    run_dir = init_v2_run_dirs(workspace, rid)
    state = _base_fix_state(rid, workspace, run_dir, command)
    persist_v2_run_state(state)

    # --- Phase: load_report ---
    _set_task(state, "load_report", V2TaskStatus.RUNNING, "Loading Sentinel report")
    persist_v2_run_state(state)

    if not report_path.exists():
        _set_task(state, "load_report", V2TaskStatus.BLOCKED, f"Report not found: {report_path}")
        state.status = V2TaskStatus.BLOCKED
        persist_v2_run_state(state)
        return state

    try:
        raw = _json.loads(report_path.read_text(encoding="utf-8"))
        report = SentinelFailureReport.model_validate(raw)
    except Exception as exc:
        _set_task(state, "load_report", V2TaskStatus.BLOCKED, f"Invalid report: {exc}")
        state.status = V2TaskStatus.BLOCKED
        persist_v2_run_state(state)
        return state

    # Persist report as artifact
    outputs_dir = run_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    (outputs_dir / "sentinel-report.json").write_text(
        report.model_dump_json(indent=2), encoding="utf-8"
    )

    # Populate metadata
    state.metadata.update({
        "mode": "sentinel_fix",
        "report_id": report.report_id,
        "service_name": report.service.name,
        "git_sha": report.service.git_sha,
        "error_code": report.error.error_code,
        "severity": report.severity.value,
        "source": report.source.value,
        "attempts": 0,
        "max_attempts": max_attempts,
        "auto_deploy": auto_deploy,
        "fix_branch": f"sentinel/fix/{report.report_id}",
    })

    _set_task(state, "load_report", V2TaskStatus.PASSED, f"Loaded report {report.report_id}")
    state.artifacts.append("outputs/sentinel-report.json")
    persist_v2_run_state(state)

    if dry_run:
        return state

    # Phases 2-5 (checkout, reproduce, fix, validate, submit) require
    # git operations and agent invocations. They will be implemented in
    # subsequent tasks with proper integration test infrastructure.
    # For now, the state is returned after report loading.
    return state


def _base_fix_state(
    run_id: str,
    workspace: Path,
    run_dir: Path,
    command: str,
) -> V2RunState:
    """Create initial V2RunState for a Sentinel fix run."""
    fix_tasks = [
        V2TaskState(name="load_report"),
        V2TaskState(name="checkout_version"),
        V2TaskState(name="reproduce"),
        V2TaskState(name="fix"),
        V2TaskState(name="validate"),
        V2TaskState(name="submit"),
    ]
    return V2RunState(
        run_id=run_id,
        command=command,
        workspace=str(workspace),
        run_dir=str(run_dir),
        tasks=fix_tasks,
    )
```

Add the necessary imports at the top of `engine.py` (only add what's not already imported):
- `V2TaskState` should already be imported
- `_utc_now` from `ncdev.v2.models` should already be imported
- `init_v2_run_dirs` and `persist_v2_run_state` from `ncdev.artifacts.state` should already be imported

Check the existing imports before adding — avoid duplicates.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/test_ncdev_v2/test_sentinel_engine.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/ncdev/v2/engine.py tests/test_ncdev_v2/test_sentinel_engine.py
git commit -m "feat(sentinel): add run_v2_fix() engine function with report loading"
```

---

## Chunk 3: Phase 3 — CLI

### Task 3.1: Add `fix` Subcommand to CLI

**Files:**
- Modify: `src/ncdev/cli.py`
- Create: `tests/test_ncdev_v2/test_sentinel_cli.py`

- [ ] **Step 1: Write failing tests for fix command parsing**

Create `tests/test_ncdev_v2/test_sentinel_cli.py`:

```python
from ncdev.cli import build_parser


def test_cli_fix_parses_report() -> None:
    parser = build_parser()
    args = parser.parse_args(["fix", "--report", "/tmp/rpt.json", "--target", "/tmp/repo"])
    assert args.command == "fix"
    assert args.report == "/tmp/rpt.json"
    assert args.target == "/tmp/repo"
    assert args.dry_run is False
    assert args.auto_deploy is False
    assert args.max_attempts == 3
    assert args.ui == "headless"


def test_cli_fix_parses_report_dir() -> None:
    parser = build_parser()
    args = parser.parse_args(["fix", "--report-dir", "/tmp/reports/", "--target", "/tmp/repo", "--batch"])
    assert args.report_dir == "/tmp/reports/"
    assert args.batch is True


def test_cli_fix_dry_run() -> None:
    parser = build_parser()
    args = parser.parse_args(["fix", "--report", "/tmp/rpt.json", "--target", "/tmp/repo", "--dry-run"])
    assert args.dry_run is True


def test_cli_fix_auto_deploy() -> None:
    parser = build_parser()
    args = parser.parse_args(["fix", "--report", "/tmp/rpt.json", "--target", "/tmp/repo", "--auto-deploy"])
    assert args.auto_deploy is True


def test_cli_fix_max_attempts() -> None:
    parser = build_parser()
    args = parser.parse_args(["fix", "--report", "/tmp/rpt.json", "--target", "/tmp/repo", "--max-attempts", "5"])
    assert args.max_attempts == 5


def test_cli_fix_resume_run_id() -> None:
    parser = build_parser()
    args = parser.parse_args(["fix", "--report", "/tmp/rpt.json", "--target", "/tmp/repo", "--run-id", "fix-123"])
    assert args.run_id == "fix-123"


def test_cli_serve_parses() -> None:
    parser = build_parser()
    args = parser.parse_args(["serve"])
    assert args.command == "serve"
    assert args.port == 16650
    assert args.workers == 1


def test_cli_serve_custom_port() -> None:
    parser = build_parser()
    args = parser.parse_args(["serve", "--port", "9999", "--workers", "4"])
    assert args.port == 9999
    assert args.workers == 4
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/test_ncdev_v2/test_sentinel_cli.py -v`
Expected: FAIL (argparse errors — `fix` and `serve` subcommands don't exist yet)

- [ ] **Step 3: Add fix and serve subcommands to build_parser()**

In `src/ncdev/cli.py`, inside `build_parser()`, add the `fix` and `serve` subparsers after the existing V2 subparsers. Follow the existing argparse pattern:

```python
    # --- Sentinel Fix Mode ---
    fix_parser = subparsers.add_parser("fix", help="Fix a production error from a Sentinel report")
    fix_parser.add_argument("--report", help="Path to SentinelFailureReport JSON file")
    fix_parser.add_argument("--report-dir", help="Path to directory of report JSON files (batch mode)")
    fix_parser.add_argument("--target", required=True, help="Path to the target repository to fix")
    fix_parser.add_argument("--dry-run", action="store_true", default=False)
    fix_parser.add_argument("--auto-deploy", action="store_true", default=False, help="Auto-create PR if fix passes")
    fix_parser.add_argument("--max-attempts", type=int, default=3, help="Max fix attempts")
    fix_parser.add_argument("--batch", action="store_true", default=False, help="Process multiple reports")
    fix_parser.add_argument("--run-id", default=None, help="Resume a previous fix run")
    fix_parser.add_argument("--workspace", default=None)
    fix_parser.add_argument("--ui", choices=["headless", "headed"], default="headless")

    # --- Sentinel HTTP Intake ---
    serve_parser = subparsers.add_parser("serve", help="Start HTTP intake API for Sentinel reports")
    serve_parser.add_argument("--port", type=int, default=16650)
    serve_parser.add_argument("--workers", type=int, default=1)
    serve_parser.add_argument("--api-key", default=None, help="API key for authentication")
    serve_parser.add_argument("--workspace", default=None)
```

- [ ] **Step 4: Add fix command dispatch in main()**

In `src/ncdev/cli.py`, inside `main()`, add the `fix` and `serve` command handling in the dispatch section:

```python
    elif args.command == "fix":
        from ncdev.v2.engine import run_v2_fix

        workspace = _workspace(args.workspace)
        report_path = Path(args.report) if args.report else None
        target = Path(args.target)

        if report_path is None and args.report_dir is None:
            print("Error: --report or --report-dir is required")
            return 1

        if report_path:
            state = run_v2_fix(
                workspace=workspace,
                report_path=report_path,
                target_repo_path=target,
                dry_run=args.dry_run,
                auto_deploy=args.auto_deploy,
                max_attempts=args.max_attempts,
                run_id=args.run_id,
            )
            print(summarize_v2_status(state))
        return 0

    elif args.command == "serve":
        print(f"Starting intake API on port {args.port} with {args.workers} worker(s)...")
        # Full implementation in Phase 5
        return 0
```

Import `summarize_v2_status` from `ncdev.v2.engine` if not already imported.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/test_ncdev_v2/test_sentinel_cli.py -v`
Expected: PASS

- [ ] **Step 6: Run full test suite**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/ncdev/cli.py tests/test_ncdev_v2/test_sentinel_cli.py
git commit -m "feat(sentinel): add ncdev fix and ncdev serve CLI commands"
```

---

## Chunk 4: Phase 4 — Configuration

### Task 4.1: Extend V2 Config with Sentinel Section

**Files:**
- Modify: `src/ncdev/v2/config.py`
- Create: `tests/test_ncdev_v2/test_sentinel_config.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_ncdev_v2/test_sentinel_config.py`:

```python
from pathlib import Path

from ncdev.v2.config import ensure_default_v2_config, load_v2_config


def test_sentinel_config_defaults(tmp_path: Path) -> None:
    config = ensure_default_v2_config(tmp_path)
    assert config.sentinel is not None
    assert config.sentinel.intake.enabled is True
    assert config.sentinel.intake.port == 16650
    assert config.sentinel.intake.max_concurrent_runs == 3
    assert config.sentinel.intake.queue_max_size == 50
    assert config.sentinel.rate_limits.max_fixes_per_hour == 10
    assert config.sentinel.rate_limits.max_fixes_per_service_per_hour == 5
    assert config.sentinel.rate_limits.cooldown_after_failure_seconds == 300
    assert config.sentinel.callback.enabled is True
    assert config.sentinel.callback.retry_count == 3
    assert config.sentinel.callback.retry_delay_seconds == 5
    assert config.sentinel.git.branch_prefix == "sentinel/fix/"
    assert config.sentinel.git.commit_prefix == "[sentinel-fix]"
    assert config.sentinel.git.pr_label == "sentinel-auto"


def test_sentinel_config_service_registry(tmp_path: Path) -> None:
    config = ensure_default_v2_config(tmp_path)
    assert config.sentinel.services == {}


def test_sentinel_config_roundtrip(tmp_path: Path) -> None:
    config = ensure_default_v2_config(tmp_path)
    loaded = load_v2_config(tmp_path)
    assert loaded.sentinel.intake.port == config.sentinel.intake.port
    assert loaded.sentinel.rate_limits.max_fixes_per_hour == 10


def test_sentinel_routing_extension(tmp_path: Path) -> None:
    from ncdev.v2.models import TaskType

    config = ensure_default_v2_config(tmp_path)
    assert config.routing.providers_for(TaskType.SENTINEL_REPRODUCE) == ["anthropic_claude_code"]
    assert config.routing.providers_for(TaskType.SENTINEL_FIX) == ["openai_codex"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/test_ncdev_v2/test_sentinel_config.py -v`
Expected: FAIL (no `sentinel` attribute on `NCDevV2Config`)

- [ ] **Step 3: Add Sentinel config models and extend NCDevV2Config**

In `src/ncdev/v2/config.py`, add the following new config models before `NCDevV2Config`:

```python
class SentinelServiceConfig(BaseModel):
    repo_path: str = ""
    git_remote: str = ""
    default_branch: str = "main"
    language: str = "python"
    test_commands: dict[str, str] = Field(default_factory=dict)
    pr_labels: list[str] = Field(default_factory=lambda: ["sentinel-auto", "bug"])
    auto_deploy: bool = False


class SentinelIntakeConfig(BaseModel):
    enabled: bool = True
    port: int = 16650
    api_key: str = ""
    max_concurrent_runs: int = 3
    queue_max_size: int = 50


class SentinelRateLimitConfig(BaseModel):
    max_fixes_per_hour: int = 10
    max_fixes_per_service_per_hour: int = 5
    cooldown_after_failure_seconds: int = 300


class SentinelCallbackConfig(BaseModel):
    enabled: bool = True
    url: str = ""
    api_key: str = ""
    retry_count: int = 3
    retry_delay_seconds: int = 5


class SentinelGitConfig(BaseModel):
    branch_prefix: str = "sentinel/fix/"
    commit_prefix: str = "[sentinel-fix]"
    pr_label: str = "sentinel-auto"


class SentinelConfig(BaseModel):
    intake: SentinelIntakeConfig = Field(default_factory=SentinelIntakeConfig)
    rate_limits: SentinelRateLimitConfig = Field(default_factory=SentinelRateLimitConfig)
    services: dict[str, SentinelServiceConfig] = Field(default_factory=dict)
    callback: SentinelCallbackConfig = Field(default_factory=SentinelCallbackConfig)
    git: SentinelGitConfig = Field(default_factory=SentinelGitConfig)
```

Add `sentinel` field to `NCDevV2Config`:

```python
class NCDevV2Config(BaseModel):
    # ... existing fields ...
    sentinel: SentinelConfig = Field(default_factory=SentinelConfig)
```

Also extend `RoutingConfig` with sentinel routing fields and update `providers_for()`:

```python
class RoutingConfig(BaseModel):
    # ... existing fields ...
    sentinel_reproduce: list[str] = Field(default_factory=lambda: ["anthropic_claude_code"])
    sentinel_fix: list[str] = Field(default_factory=lambda: ["openai_codex"])

    def providers_for(self, task_type: TaskType) -> list[str]:
        mapping = {
            # ... existing mappings ...
            TaskType.SENTINEL_REPRODUCE: self.sentinel_reproduce,
            TaskType.SENTINEL_FIX: self.sentinel_fix,
        }
        return mapping.get(task_type, self.review)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/test_ncdev_v2/test_sentinel_config.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/ncdev/v2/config.py tests/test_ncdev_v2/test_sentinel_config.py
git commit -m "feat(sentinel): add sentinel config section with service registry, rate limits, callback"
```

---

## Chunk 5: Phase 5 — HTTP Intake API

### Task 5.1: Implement Intake API

**Files:**
- Create: `src/ncdev/intake_api.py`
- Create: `tests/test_ncdev_v2/test_intake_api.py`

- [ ] **Step 1: Write failing tests for intake API endpoints**

Create `tests/test_ncdev_v2/test_intake_api.py`:

```python
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from ncdev.intake_api import create_app

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "sentinel_reports"


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    app = create_app(workspace=tmp_path, api_key="test-key")
    return TestClient(app)


def test_health_endpoint(client: TestClient) -> None:
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"


def test_post_report_requires_auth(client: TestClient) -> None:
    raw = json.loads((FIXTURES_DIR / "backend_error.json").read_text())
    resp = client.post("/api/v1/reports", json=raw)
    assert resp.status_code == 401


def test_post_report_accepts_valid_report(client: TestClient) -> None:
    raw = json.loads((FIXTURES_DIR / "backend_error.json").read_text())
    resp = client.post(
        "/api/v1/reports",
        json=raw,
        headers={"Authorization": "Bearer test-key"},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["accepted"] is True
    assert "run_id" in data
    assert data["status"] == "queued"


def test_post_report_rejects_invalid_schema(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/reports",
        json={"not": "valid"},
        headers={"Authorization": "Bearer test-key"},
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data["accepted"] is False


def test_get_run_status_not_found(client: TestClient) -> None:
    resp = client.get("/api/v1/runs/nonexistent")
    assert resp.status_code == 404


def test_get_run_result_not_found(client: TestClient) -> None:
    resp = client.get("/api/v1/runs/nonexistent/result")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/test_ncdev_v2/test_intake_api.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement intake_api.py**

Create `src/ncdev/intake_api.py`:

```python
"""Minimal HTTP API for receiving Sentinel failure reports.

Start: ncdev serve --port 16650
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from ncdev.v2.models import SentinelFailureReport, V2RunState, _utc_now


def create_app(
    *,
    workspace: Path,
    api_key: str = "",
) -> FastAPI:
    app = FastAPI(title="NC Dev System — Sentinel Intake API")
    run_registry: dict[str, dict[str, Any]] = {}
    lock = threading.Lock()

    def _check_auth(request: Request) -> None:
        if not api_key:
            return
        auth = request.headers.get("Authorization", "")
        if auth != f"Bearer {api_key}":
            raise HTTPException(status_code=401, detail="Unauthorized")

    @app.get("/api/v1/health")
    def health() -> dict[str, Any]:
        with lock:
            active = sum(1 for r in run_registry.values() if r.get("status") == "running")
            queued = sum(1 for r in run_registry.values() if r.get("status") == "queued")
        return {
            "status": "healthy",
            "active_runs": active,
            "queued": queued,
        }

    @app.post("/api/v1/reports", status_code=202)
    def post_report(request: Request, body: dict[str, Any]) -> JSONResponse:
        _check_auth(request)
        try:
            report = SentinelFailureReport.model_validate(body)
        except ValidationError as exc:
            return JSONResponse(
                status_code=400,
                content={
                    "accepted": False,
                    "error": "Invalid report schema",
                    "details": [str(e["msg"]) for e in exc.errors()],
                },
            )

        run_id = f"fix-{report.report_id}-{_utc_now().strftime('%Y%m%d-%H%M%S')}"
        with lock:
            run_registry[run_id] = {
                "run_id": run_id,
                "report_id": report.report_id,
                "status": "queued",
                "queued_at": _utc_now().isoformat(),
            }

        return JSONResponse(
            status_code=202,
            content={
                "accepted": True,
                "run_id": run_id,
                "status": "queued",
                "status_url": f"/api/v1/runs/{run_id}",
            },
        )

    @app.get("/api/v1/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        with lock:
            entry = run_registry.get(run_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return entry

    @app.get("/api/v1/runs/{run_id}/result")
    def get_run_result(run_id: str) -> dict[str, Any]:
        with lock:
            entry = run_registry.get(run_id)
        if entry is None:
            raise HTTPException(status_code=404, detail="Run not found")
        if entry.get("status") != "complete":
            raise HTTPException(status_code=404, detail="Run not complete")
        return entry.get("result", {})

    return app
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/test_ncdev_v2/test_intake_api.py -v`
Expected: PASS

- [ ] **Step 5: Wire serve command to intake API**

In `src/ncdev/cli.py`, update the `serve` command handler:

```python
    elif args.command == "serve":
        import uvicorn
        from ncdev.intake_api import create_app

        workspace = _workspace(args.workspace)
        app = create_app(workspace=workspace, api_key=args.api_key or "")
        uvicorn.run(app, host="0.0.0.0", port=args.port, workers=args.workers)
        return 0
```

- [ ] **Step 6: Run full test suite**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/ncdev/intake_api.py src/ncdev/cli.py tests/test_ncdev_v2/test_intake_api.py
git commit -m "feat(sentinel): add HTTP intake API with /reports, /runs, /health endpoints"
```

---

## Chunk 6: Phase 6 — Safety

### Task 6.1: Implement Safety Mechanisms

**Files:**
- Create: `src/ncdev/v2/sentinel_safety.py`
- Create: `tests/test_ncdev_v2/test_sentinel_safety.py`

- [ ] **Step 1: Write failing tests for circuit breaker, scope guard, dedup, cooldown**

Create `tests/test_ncdev_v2/test_sentinel_safety.py`:

```python
import time
from pathlib import Path

from ncdev.v2.sentinel_safety import (
    CircuitBreaker,
    CooldownTracker,
    DeduplicationTracker,
    ScopeGuard,
)


def test_circuit_breaker_trips_after_three_failures() -> None:
    cb = CircuitBreaker(threshold=3, reset_seconds=3600)
    cb.record_failure("helyx-api")
    cb.record_failure("helyx-api")
    assert not cb.is_tripped("helyx-api")
    cb.record_failure("helyx-api")
    assert cb.is_tripped("helyx-api")


def test_circuit_breaker_resets_on_success() -> None:
    cb = CircuitBreaker(threshold=3, reset_seconds=3600)
    cb.record_failure("helyx-api")
    cb.record_failure("helyx-api")
    cb.record_success("helyx-api")
    cb.record_failure("helyx-api")
    assert not cb.is_tripped("helyx-api")


def test_circuit_breaker_manual_reset() -> None:
    cb = CircuitBreaker(threshold=3, reset_seconds=3600)
    for _ in range(3):
        cb.record_failure("helyx-api")
    assert cb.is_tripped("helyx-api")
    cb.reset("helyx-api")
    assert not cb.is_tripped("helyx-api")


def test_circuit_breaker_independent_services() -> None:
    cb = CircuitBreaker(threshold=3, reset_seconds=3600)
    for _ in range(3):
        cb.record_failure("helyx-api")
    assert cb.is_tripped("helyx-api")
    assert not cb.is_tripped("vantage-api")


def test_scope_guard_accepts_small_change() -> None:
    sg = ScopeGuard(max_files=10, max_lines=200)
    ok, msg = sg.check(files_changed=2, lines_changed=50, changed_paths=["src/svc.py", "tests/test_svc.py"])
    assert ok is True


def test_scope_guard_rejects_too_many_files() -> None:
    sg = ScopeGuard(max_files=10, max_lines=200)
    paths = [f"src/file_{i}.py" for i in range(11)]
    ok, msg = sg.check(files_changed=11, lines_changed=50, changed_paths=paths)
    assert ok is False
    assert "files" in msg.lower()


def test_scope_guard_rejects_too_many_lines() -> None:
    sg = ScopeGuard(max_files=10, max_lines=200)
    ok, msg = sg.check(files_changed=1, lines_changed=201, changed_paths=["src/svc.py"])
    assert ok is False
    assert "lines" in msg.lower()


def test_scope_guard_rejects_protected_files() -> None:
    sg = ScopeGuard(max_files=10, max_lines=200)
    ok, msg = sg.check(files_changed=1, lines_changed=5, changed_paths=["Dockerfile"])
    assert ok is False
    assert "protected" in msg.lower() or "Dockerfile" in msg


def test_dedup_tracker_detects_duplicate() -> None:
    dt = DeduplicationTracker()
    key = dt.make_key("helyx-api", "src/svc.py", "process", "UNHANDLED_EXCEPTION")
    assert not dt.is_active(key)
    dt.mark_active(key, "run-1")
    assert dt.is_active(key)


def test_dedup_tracker_clears_after_completion() -> None:
    dt = DeduplicationTracker()
    key = dt.make_key("helyx-api", "src/svc.py", "process", "UNHANDLED_EXCEPTION")
    dt.mark_active(key, "run-1")
    dt.mark_complete(key)
    assert not dt.is_active(key)


def test_cooldown_tracker_blocks_during_cooldown() -> None:
    ct = CooldownTracker(cooldown_seconds=1)
    ct.record_failure("helyx-api")
    assert ct.is_cooling_down("helyx-api")


def test_cooldown_tracker_allows_after_cooldown() -> None:
    ct = CooldownTracker(cooldown_seconds=0)
    ct.record_failure("helyx-api")
    assert not ct.is_cooling_down("helyx-api")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/test_ncdev_v2/test_sentinel_safety.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement sentinel_safety.py**

Create `src/ncdev/v2/sentinel_safety.py`:

```python
"""Safety mechanisms for Sentinel fix mode: circuit breaker, scope guard, deduplication, cooldown."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

_PROTECTED_PATTERNS = (
    "Dockerfile",
    "docker-compose",
    ".github/",
    ".gitlab-ci",
    "Jenkinsfile",
    "Makefile",
    ".env",
)


@dataclass
class CircuitBreaker:
    threshold: int = 3
    reset_seconds: int = 3600
    _failures: dict[str, int] = field(default_factory=dict)
    _tripped_at: dict[str, float] = field(default_factory=dict)

    def record_failure(self, service: str) -> None:
        self._failures[service] = self._failures.get(service, 0) + 1
        if self._failures[service] >= self.threshold:
            self._tripped_at[service] = time.monotonic()

    def record_success(self, service: str) -> None:
        self._failures.pop(service, None)
        self._tripped_at.pop(service, None)

    def is_tripped(self, service: str) -> bool:
        if service not in self._tripped_at:
            return False
        elapsed = time.monotonic() - self._tripped_at[service]
        if elapsed >= self.reset_seconds:
            self.reset(service)
            return False
        return True

    def reset(self, service: str) -> None:
        self._failures.pop(service, None)
        self._tripped_at.pop(service, None)


@dataclass
class ScopeGuard:
    max_files: int = 10
    max_lines: int = 200

    def check(
        self,
        files_changed: int,
        lines_changed: int,
        changed_paths: list[str],
    ) -> tuple[bool, str]:
        if files_changed > self.max_files:
            return False, f"Too many files changed: {files_changed} > {self.max_files}"
        if lines_changed > self.max_lines:
            return False, f"Too many lines changed: {lines_changed} > {self.max_lines}"
        for path in changed_paths:
            for pattern in _PROTECTED_PATTERNS:
                if pattern in path:
                    return False, f"Protected file modified: {path}"
        return True, ""


@dataclass
class DeduplicationTracker:
    _active: dict[str, str] = field(default_factory=dict)

    @staticmethod
    def make_key(service: str, file: str | None, function: str | None, error_type: str) -> str:
        return f"{service}:{file or ''}:{function or ''}:{error_type}"

    def is_active(self, key: str) -> bool:
        return key in self._active

    def mark_active(self, key: str, run_id: str) -> None:
        self._active[key] = run_id

    def mark_complete(self, key: str) -> None:
        self._active.pop(key, None)


@dataclass
class CooldownTracker:
    cooldown_seconds: int = 300
    _last_failure: dict[str, float] = field(default_factory=dict)

    def record_failure(self, service: str) -> None:
        self._last_failure[service] = time.monotonic()

    def is_cooling_down(self, service: str) -> bool:
        if service not in self._last_failure:
            return False
        elapsed = time.monotonic() - self._last_failure[service]
        return elapsed < self.cooldown_seconds
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/test_ncdev_v2/test_sentinel_safety.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/v2/sentinel_safety.py tests/test_ncdev_v2/test_sentinel_safety.py
git commit -m "feat(sentinel): add circuit breaker, scope guard, deduplication, cooldown"
```

---

## Chunk 7: Phase 7 — Frontend Support

### Task 7.1: Frontend Detection and Templates

**Files:**
- Modify: `src/ncdev/v2/sentinel_prompts.py`
- Modify: `tests/test_ncdev_v2/test_sentinel_prompts.py`

- [ ] **Step 1: Write failing tests for frontend-specific prompt variations**

Append to `tests/test_ncdev_v2/test_sentinel_prompts.py`:

```python
from ncdev.v2.sentinel_prompts import detect_frontend_test_type, detect_monorepo_subdir


def test_detect_frontend_test_type_component_error() -> None:
    assert detect_frontend_test_type("REACT_RENDER_ERROR") == "vitest"


def test_detect_frontend_test_type_interaction_error() -> None:
    assert detect_frontend_test_type("NETWORK_ERROR") == "playwright"


def test_detect_frontend_test_type_page_error() -> None:
    assert detect_frontend_test_type("ROUTING_ERROR") == "playwright"


def test_detect_frontend_test_type_state_error() -> None:
    assert detect_frontend_test_type("STATE_ERROR") == "vitest"


def test_detect_monorepo_subdir_backend() -> None:
    assert detect_monorepo_subdir("api/app/services/order_service.py") == "api"


def test_detect_monorepo_subdir_frontend() -> None:
    assert detect_monorepo_subdir("ui/src/components/Cart.tsx") == "ui"


def test_detect_monorepo_subdir_src_direct() -> None:
    assert detect_monorepo_subdir("src/services/order.py") is None


def test_detect_monorepo_subdir_no_slash() -> None:
    assert detect_monorepo_subdir("order.py") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/test_ncdev_v2/test_sentinel_prompts.py::test_detect_frontend_test_type_component_error -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: Add detection functions to sentinel_prompts.py**

Add to `src/ncdev/v2/sentinel_prompts.py`:

```python
_VITEST_ERROR_TYPES = {
    "REACT_RENDER_ERROR",
    "REACT_EFFECT_ERROR",
    "REACT_EVENT_ERROR",
    "STATE_ERROR",
}

_PLAYWRIGHT_ERROR_TYPES = {
    "NETWORK_ERROR",
    "API_ERROR",
    "TIMEOUT_ERROR",
    "ROUTING_ERROR",
    "PERFORMANCE_LCP",
    "PERFORMANCE_CLS",
    "PERFORMANCE_INP",
}

_KNOWN_MONOREPO_PREFIXES = ("api/", "ui/", "backend/", "frontend/", "server/", "client/", "web/", "app/")


def detect_frontend_test_type(error_type: str) -> str:
    """Return 'vitest' for component/state errors, 'playwright' for page/network errors."""
    if error_type in _VITEST_ERROR_TYPES:
        return "vitest"
    return "playwright"


def detect_monorepo_subdir(file_path: str) -> str | None:
    """Detect monorepo subdirectory from a file path. Returns None if not a monorepo layout."""
    for prefix in _KNOWN_MONOREPO_PREFIXES:
        if file_path.startswith(prefix):
            return prefix.rstrip("/")
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/test_ncdev_v2/test_sentinel_prompts.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/v2/sentinel_prompts.py tests/test_ncdev_v2/test_sentinel_prompts.py
git commit -m "feat(sentinel): add frontend test type detection and monorepo subdir detection"
```

---

## Chunk 8: Phase 8 — Callback

### Task 8.1: Implement Callback Client

**Files:**
- Create: `src/ncdev/v2/sentinel_callback.py`
- Create: `tests/test_ncdev_v2/test_sentinel_callback.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_ncdev_v2/test_sentinel_callback.py`:

```python
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from ncdev.v2.models import FixOutcome, SentinelFixResult
from ncdev.v2.sentinel_callback import send_fix_result


def _make_result() -> SentinelFixResult:
    now = datetime(2026, 3, 15, 14, 30, 0, tzinfo=timezone.utc)
    return SentinelFixResult(
        report_id="rpt_bk_001",
        run_id="fix-rpt_bk_001-20260315-143000",
        outcome=FixOutcome.FIXED,
        outcome_detail="Fixed null check",
        pr_url="https://github.com/org/repo/pull/42",
        started_at=now,
        completed_at=now,
    )


@patch("ncdev.v2.sentinel_callback.httpx")
def test_send_fix_result_success(mock_httpx: MagicMock) -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_httpx.post.return_value = mock_response

    result = _make_result()
    success = send_fix_result(
        result=result,
        callback_url="http://sentinel.local/api/v1/fix-results",
        api_key="test-key",
        retry_count=1,
        retry_delay_seconds=0,
    )
    assert success is True
    mock_httpx.post.assert_called_once()
    call_kwargs = mock_httpx.post.call_args
    assert "Authorization" in call_kwargs.kwargs["headers"]


@patch("ncdev.v2.sentinel_callback.httpx")
def test_send_fix_result_retries_on_failure(mock_httpx: MagicMock) -> None:
    mock_response_fail = MagicMock()
    mock_response_fail.status_code = 500
    mock_response_ok = MagicMock()
    mock_response_ok.status_code = 200
    mock_httpx.post.side_effect = [mock_response_fail, mock_response_ok]

    result = _make_result()
    success = send_fix_result(
        result=result,
        callback_url="http://sentinel.local/api/v1/fix-results",
        api_key="test-key",
        retry_count=2,
        retry_delay_seconds=0,
    )
    assert success is True
    assert mock_httpx.post.call_count == 2


@patch("ncdev.v2.sentinel_callback.httpx")
def test_send_fix_result_gives_up_after_retries(mock_httpx: MagicMock) -> None:
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_httpx.post.return_value = mock_response

    result = _make_result()
    success = send_fix_result(
        result=result,
        callback_url="http://sentinel.local/api/v1/fix-results",
        api_key="test-key",
        retry_count=2,
        retry_delay_seconds=0,
    )
    assert success is False
    assert mock_httpx.post.call_count == 2


@patch("ncdev.v2.sentinel_callback.httpx")
def test_send_fix_result_handles_connection_error(mock_httpx: MagicMock) -> None:
    mock_httpx.post.side_effect = Exception("Connection refused")

    result = _make_result()
    success = send_fix_result(
        result=result,
        callback_url="http://sentinel.local/api/v1/fix-results",
        api_key="test-key",
        retry_count=1,
        retry_delay_seconds=0,
    )
    assert success is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/test_ncdev_v2/test_sentinel_callback.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement sentinel_callback.py**

Create `src/ncdev/v2/sentinel_callback.py`:

```python
"""HTTP callback client to notify Sentinel of fix results."""
from __future__ import annotations

import logging
import time

import httpx

from ncdev.v2.models import SentinelFixResult

logger = logging.getLogger(__name__)


def send_fix_result(
    *,
    result: SentinelFixResult,
    callback_url: str,
    api_key: str,
    retry_count: int = 3,
    retry_delay_seconds: int = 5,
) -> bool:
    """Send a SentinelFixResult to the Sentinel callback URL.

    Returns True if Sentinel acknowledged the result (200 OK), False otherwise.
    Retries up to retry_count times with retry_delay_seconds between attempts.
    """
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "X-NCDev-Run-ID": result.run_id,
    }
    payload = result.model_dump_json()

    for attempt in range(retry_count):
        try:
            response = httpx.post(
                callback_url,
                content=payload,
                headers=headers,
                timeout=30.0,
            )
            if response.status_code == 200:
                logger.info("Callback succeeded for run %s", result.run_id)
                return True
            logger.warning(
                "Callback attempt %d/%d failed with status %d for run %s",
                attempt + 1,
                retry_count,
                response.status_code,
                result.run_id,
            )
        except Exception:
            logger.warning(
                "Callback attempt %d/%d raised exception for run %s",
                attempt + 1,
                retry_count,
                result.run_id,
                exc_info=True,
            )

        if attempt < retry_count - 1 and retry_delay_seconds > 0:
            time.sleep(retry_delay_seconds)

    logger.error("Callback exhausted all %d retries for run %s", retry_count, result.run_id)
    return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/test_ncdev_v2/test_sentinel_callback.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/ncdev/v2/sentinel_callback.py tests/test_ncdev_v2/test_sentinel_callback.py
git commit -m "feat(sentinel): add callback HTTP client with retry logic"
```

---

## Final Verification

- [ ] **Run full test suite one final time**

```bash
cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/ -v --tb=short
```

All tests must pass, including all existing tests (no regressions).

- [ ] **Verify no existing files were modified beyond additions**

Check that existing V2 pipeline functions in `engine.py` were not modified — only new functions were added. Check that existing tests still pass unchanged.
