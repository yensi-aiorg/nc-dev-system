# Opus-Citex-Codex Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the static prompt builder with Opus-authored Citex ingestion so Codex pulls context on demand, and track feature effectiveness metrics.

**Architecture:** Opus reads discovery artifacts + actual project code, synthesizes structured summaries, ingests into Citex RAG (localhost:20160). Codex gets lean ~2k char prompts with HTTP query instructions for Citex. Metrics computed from existing StepResult data.

**Tech Stack:** Python 3.12+, Citex RAG API, httpx, Pydantic v2, Rich, Claude CLI (Opus), Codex CLI

---

### Task 1: Citex Client

**Files:**
- Create: `src/ncdev/v3/citex_client.py`
- Test: `tests/test_ncdev_v3/test_citex_client.py`

- [ ] **Step 1: Create test directory and init**

```bash
mkdir -p tests/test_ncdev_v3
touch tests/test_ncdev_v3/__init__.py
```

- [ ] **Step 2: Write failing tests**

```python
# tests/test_ncdev_v3/test_citex_client.py
from unittest.mock import patch, MagicMock
import pytest
from ncdev.v3.citex_client import CitexClient


def test_health_check_success():
    client = CitexClient(project_id="test-proj")
    with patch("ncdev.v3.citex_client.httpx") as mock_httpx:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_httpx.get.return_value = mock_resp
        assert client.health_check() is True
        mock_httpx.get.assert_called_once()


def test_health_check_failure():
    client = CitexClient(project_id="test-proj")
    with patch("ncdev.v3.citex_client.httpx") as mock_httpx:
        mock_httpx.get.side_effect = ConnectionError("refused")
        assert client.health_check() is False


def test_ingest_success():
    client = CitexClient(project_id="test-proj")
    with patch("ncdev.v3.citex_client.httpx") as mock_httpx:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_httpx.post.return_value = mock_resp
        assert client.ingest("some content", category="design") is True
        call_args = mock_httpx.post.call_args
        body = call_args.kwargs["json"]
        assert body["project_id"] == "test-proj"
        assert body["metadata"]["category"] == "design"


def test_ingest_failure():
    client = CitexClient(project_id="test-proj")
    with patch("ncdev.v3.citex_client.httpx") as mock_httpx:
        mock_httpx.post.side_effect = ConnectionError("refused")
        assert client.ingest("content", category="design") is False


def test_query_returns_content():
    client = CitexClient(project_id="test-proj")
    with patch("ncdev.v3.citex_client.httpx") as mock_httpx:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {"content": "User model has email, name fields"},
                {"content": "Project model has title, status fields"},
            ]
        }
        mock_httpx.post.return_value = mock_resp
        results = client.query("what data models exist?")
        assert len(results) == 2
        assert "User model" in results[0]


def test_query_returns_empty_on_failure():
    client = CitexClient(project_id="test-proj")
    with patch("ncdev.v3.citex_client.httpx") as mock_httpx:
        mock_httpx.post.side_effect = ConnectionError("refused")
        results = client.query("anything")
        assert results == []


def test_query_with_category_filter():
    client = CitexClient(project_id="test-proj")
    with patch("ncdev.v3.citex_client.httpx") as mock_httpx:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": [{"content": "color primary: #0f172a"}]}
        mock_httpx.post.return_value = mock_resp
        client.query("design tokens", category="design")
        call_args = mock_httpx.post.call_args
        body = call_args.kwargs["json"]
        assert body["filter"] == {"category": "design"}
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_ncdev_v3/test_citex_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ncdev.v3.citex_client'`

- [ ] **Step 4: Implement CitexClient**

```python
# src/ncdev/v3/citex_client.py
"""Thin HTTP client for the Citex RAG API."""
from __future__ import annotations

import httpx

CITEX_DEFAULT_URL = "http://localhost:20160"


class CitexClient:
    """Client for Citex RAG — shared context layer for all CLI agent instances."""

    def __init__(self, base_url: str = CITEX_DEFAULT_URL, project_id: str = ""):
        self.base_url = base_url.rstrip("/")
        self.project_id = project_id

    def health_check(self) -> bool:
        """Check if Citex is reachable."""
        try:
            resp = httpx.get(f"{self.base_url}/api/v1/health", timeout=5)
            return resp.status_code < 400
        except Exception:
            return False

    def ingest(self, content: str, category: str, metadata: dict | None = None) -> bool:
        """Ingest a document into Citex."""
        try:
            resp = httpx.post(
                f"{self.base_url}/api/v1/documents/ingest",
                json={
                    "project_id": self.project_id,
                    "content": content,
                    "metadata": {"category": category, **(metadata or {})},
                },
                timeout=30,
            )
            return resp.status_code < 400
        except Exception:
            return False

    def query(self, query: str, category: str | None = None, limit: int = 5) -> list[str]:
        """Query Citex for relevant context. Returns list of content strings."""
        try:
            payload: dict = {"project_id": self.project_id, "query": query, "limit": limit}
            if category:
                payload["filter"] = {"category": category}
            resp = httpx.post(
                f"{self.base_url}/api/v1/retrieval/query",
                json=payload,
                timeout=30,
            )
            if resp.status_code < 400:
                data = resp.json()
                return [
                    r.get("content", r.get("text", ""))
                    for r in data.get("results", data.get("documents", []))
                    if r.get("content") or r.get("text")
                ]
        except Exception:
            pass
        return []
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_ncdev_v3/test_citex_client.py -v`
Expected: 7 passed

- [ ] **Step 6: Commit**

```bash
git add src/ncdev/v3/citex_client.py tests/test_ncdev_v3/
git commit -m "feat(v3): add Citex RAG client"
```

---

### Task 2: Metrics Module

**Files:**
- Create: `src/ncdev/v3/metrics.py`
- Test: `tests/test_ncdev_v3/test_metrics.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_ncdev_v3/test_metrics.py
from ncdev.v3.metrics import compute_run_metrics, FeatureMetric, RunMetrics
from ncdev.v3.models import StepResult, StepStatus, StepVerification, TestResult, V3RunState


def _make_result(feature_id: str, status: StepStatus, repair_attempts: int = 0, build_s: float = 60, verify_s: float = 10) -> StepResult:
    return StepResult(
        feature_id=feature_id,
        status=status,
        build_duration_seconds=build_s,
        verify_duration_seconds=verify_s,
        repair_attempts=repair_attempts,
        files_created=["a.py", "b.py"],
        files_modified=["c.py"],
    )


def test_first_pass_success_rate_all_pass():
    state = V3RunState(run_id="test-1", total_features=3, completed_features=3)
    state.completed_steps = [
        _make_result("f1", StepStatus.PASSED, 0),
        _make_result("f2", StepStatus.PASSED, 0),
        _make_result("f3", StepStatus.PASSED, 0),
    ]
    metrics = compute_run_metrics(state)
    assert metrics.first_pass_success_rate == 1.0
    assert metrics.repair_rate == 0.0
    assert metrics.passed_features == 3
    assert metrics.failed_features == 0


def test_first_pass_success_rate_mixed():
    state = V3RunState(run_id="test-2", total_features=4, completed_features=4)
    state.completed_steps = [
        _make_result("f1", StepStatus.PASSED, 0),
        _make_result("f2", StepStatus.PASSED, 2),  # passed after repair
        _make_result("f3", StepStatus.FAILED, 2),
        _make_result("f4", StepStatus.PASSED, 0),
    ]
    metrics = compute_run_metrics(state)
    assert metrics.first_pass_success_rate == 0.5  # 2 out of 4 first-pass
    assert metrics.repair_rate == 0.5  # 2 out of 4 needed repair
    assert metrics.mean_repair_attempts == 2.0
    assert metrics.passed_features == 3
    assert metrics.failed_features == 1


def test_build_efficiency():
    state = V3RunState(run_id="test-3", total_features=2, completed_features=2)
    state.completed_steps = [
        _make_result("f1", StepStatus.PASSED, 0, build_s=80, verify_s=20),
        _make_result("f2", StepStatus.PASSED, 0, build_s=120, verify_s=30),
    ]
    metrics = compute_run_metrics(state)
    # build_efficiency = 200 / 250 = 0.8
    assert abs(metrics.build_efficiency - 0.8) < 0.01


def test_feature_metrics_populated():
    state = V3RunState(run_id="test-4", total_features=1, completed_features=1)
    state.completed_steps = [_make_result("f1", StepStatus.PASSED, 0)]
    metrics = compute_run_metrics(state)
    assert len(metrics.features) == 1
    assert metrics.features[0].feature_id == "f1"
    assert metrics.features[0].first_pass is True
    assert metrics.features[0].files_created == 2
    assert metrics.features[0].files_modified == 1


def test_empty_run():
    state = V3RunState(run_id="test-5", total_features=0, completed_features=0)
    metrics = compute_run_metrics(state)
    assert metrics.first_pass_success_rate == 0.0
    assert metrics.total_features == 0
    assert metrics.features == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_ncdev_v3/test_metrics.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement metrics module**

```python
# src/ncdev/v3/metrics.py
"""Build metrics — tracks feature effectiveness and first-pass success rate."""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from ncdev.v3.models import StepStatus, V3RunState


class FeatureMetric(BaseModel):
    feature_id: str
    title: str = ""
    status: str
    first_pass: bool
    repair_attempts: int
    build_duration_seconds: float
    verify_duration_seconds: float
    total_duration_seconds: float
    files_created: int
    files_modified: int


class RunMetrics(BaseModel):
    run_id: str
    project_name: str = ""
    started_at: str = ""
    completed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    total_duration_seconds: float = 0.0
    total_features: int = 0
    passed_features: int = 0
    failed_features: int = 0
    first_pass_success_rate: float = 0.0
    repair_rate: float = 0.0
    mean_repair_attempts: float = 0.0
    build_efficiency: float = 0.0
    feature_throughput_per_hour: float = 0.0
    features: list[FeatureMetric] = Field(default_factory=list)
    builder_primary: str = "codex"
    builder_model: str = "gpt-5.4-codex"
    citex_documents_ingested: int = 0
    citex_queries_by_codex: int = 0


def compute_run_metrics(
    state: V3RunState,
    ingestion_doc_count: int = 0,
) -> RunMetrics:
    """Compute metrics from completed step results."""
    steps = state.completed_steps
    total = len(steps)

    if total == 0:
        return RunMetrics(run_id=state.run_id, started_at=state.started_at)

    passed = [s for s in steps if s.status == StepStatus.PASSED]
    failed = [s for s in steps if s.status == StepStatus.FAILED]
    first_pass = [s for s in steps if s.status == StepStatus.PASSED and s.repair_attempts == 0]
    repaired = [s for s in steps if s.repair_attempts > 0]

    total_build = sum(s.build_duration_seconds for s in steps)
    total_verify = sum(s.verify_duration_seconds for s in steps)
    total_time = total_build + total_verify

    feature_metrics = [
        FeatureMetric(
            feature_id=s.feature_id,
            status=s.status.value,
            first_pass=(s.status == StepStatus.PASSED and s.repair_attempts == 0),
            repair_attempts=s.repair_attempts,
            build_duration_seconds=s.build_duration_seconds,
            verify_duration_seconds=s.verify_duration_seconds,
            total_duration_seconds=s.build_duration_seconds + s.verify_duration_seconds,
            files_created=len(s.files_created),
            files_modified=len(s.files_modified),
        )
        for s in steps
    ]

    hours = total_time / 3600 if total_time > 0 else 1

    return RunMetrics(
        run_id=state.run_id,
        started_at=state.started_at,
        total_duration_seconds=total_time,
        total_features=total,
        passed_features=len(passed),
        failed_features=len(failed),
        first_pass_success_rate=len(first_pass) / total,
        repair_rate=len(repaired) / total,
        mean_repair_attempts=(
            sum(s.repair_attempts for s in repaired) / len(repaired)
            if repaired else 0.0
        ),
        build_efficiency=total_build / total_time if total_time > 0 else 0.0,
        feature_throughput_per_hour=total / hours,
        features=feature_metrics,
        citex_documents_ingested=ingestion_doc_count,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_ncdev_v3/test_metrics.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/ncdev/v3/metrics.py tests/test_ncdev_v3/test_metrics.py
git commit -m "feat(v3): add build metrics module"
```

---

### Task 3: Context Ingestion Module

**Files:**
- Create: `src/ncdev/v3/context_ingestion.py`
- Modify: `src/ncdev/v3/models.py` (add IngestionReport)
- Test: `tests/test_ncdev_v3/test_context_ingestion.py`

- [ ] **Step 1: Add IngestionReport to models.py**

Add to end of `src/ncdev/v3/models.py`:

```python
class IngestionRecord(BaseModel):
    """One document ingested into Citex."""
    category: str
    char_count: int
    success: bool

class IngestionReport(BaseModel):
    """Summary of context ingestion into Citex."""
    project_id: str
    total_documents: int = 0
    successful: int = 0
    failed: int = 0
    records: list[IngestionRecord] = Field(default_factory=list)
```

- [ ] **Step 2: Write failing tests for context ingestion**

```python
# tests/test_ncdev_v3/test_context_ingestion.py
from pathlib import Path
from unittest.mock import patch, MagicMock
import json

from ncdev.v3.context_ingestion import ingest_project_context, ingest_feature_result
from ncdev.v3.models import FeatureStep, StepResult, StepStatus, IngestionReport


def _write_artifact(run_dir: Path, name: str, data: dict) -> None:
    out = run_dir / "outputs"
    out.mkdir(parents=True, exist_ok=True)
    (out / name).write_text(json.dumps(data), encoding="utf-8")


def test_ingest_project_context_returns_report(tmp_path: Path):
    run_dir = tmp_path / "run"
    target = tmp_path / "project"
    target.mkdir()
    _write_artifact(run_dir, "design-brief.json", {"project_name": "test", "colors": {}})
    _write_artifact(run_dir, "feature-map.json", {"features": [{"name": "Auth", "description": "User auth"}]})
    _write_artifact(run_dir, "build-plan.json", {"project_name": "test", "batches": []})
    _write_artifact(run_dir, "target-project-contract.json", {"stack": {"backend": "FastAPI"}})

    from ncdev.v3.models import FeatureQueueDoc
    fq = FeatureQueueDoc(project_name="test", features=[])

    with patch("ncdev.v3.context_ingestion.CitexClient") as MockClient:
        mock_instance = MagicMock()
        mock_instance.ingest.return_value = True
        MockClient.return_value = mock_instance

        report = ingest_project_context(run_dir, target, fq, project_id="test")
        assert isinstance(report, IngestionReport)
        assert report.total_documents > 0
        assert report.successful > 0
        assert report.failed == 0


def test_ingest_feature_result_stores_in_citex(tmp_path: Path):
    feature = FeatureStep(
        feature_id="f1",
        title="User Auth",
        description="Add user authentication",
        acceptance_criteria=["Login works"],
    )
    result = StepResult(
        feature_id="f1",
        status=StepStatus.PASSED,
        files_created=["auth.py"],
        files_modified=["router.py"],
    )
    with patch("ncdev.v3.context_ingestion.CitexClient") as MockClient:
        mock_instance = MagicMock()
        mock_instance.ingest.return_value = True
        MockClient.return_value = mock_instance

        ok = ingest_feature_result(feature, result, tmp_path, project_id="test")
        assert ok is True
        mock_instance.ingest.assert_called_once()
        call_args = mock_instance.ingest.call_args
        assert call_args.kwargs["category"] == "prior_feature"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_ncdev_v3/test_context_ingestion.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement context ingestion**

```python
# src/ncdev/v3/context_ingestion.py
"""Context ingestion — Opus reads project state, ingests structured summaries into Citex."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from rich.console import Console

from ncdev.v3.citex_client import CitexClient, CITEX_DEFAULT_URL
from ncdev.v3.models import (
    FeatureQueueDoc,
    FeatureStep,
    IngestionRecord,
    IngestionReport,
    StepResult,
)

console = Console()


def _read_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _read_code_files(target_path: Path, glob_pattern: str, max_files: int = 20) -> str:
    """Read source files matching a glob pattern, return concatenated content."""
    parts = []
    count = 0
    for fpath in sorted(target_path.glob(glob_pattern)):
        if fpath.is_file() and fpath.stat().st_size < 50_000:
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
                parts.append(f"### {fpath.relative_to(target_path)}\n```\n{content}\n```")
                count += 1
                if count >= max_files:
                    break
            except Exception:
                pass
    return "\n\n".join(parts)


def _synthesize_with_opus(category: str, raw_content: str) -> str:
    """Call Claude Opus to synthesize raw content into a structured summary."""
    if not raw_content.strip():
        return ""

    prompt = (
        f"You are summarizing project context for the '{category}' category.\n"
        f"Produce a concise, structured summary that another AI agent can use "
        f"to understand and build on this code. Include specific names, types, "
        f"signatures, and field definitions. No vague descriptions.\n\n"
        f"Raw content:\n{raw_content[:30000]}"
    )

    try:
        result = subprocess.run(
            [
                "claude", "-p", prompt,
                "--output-format", "text",
                "--model", "claude-opus-4-6",
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    # Fallback: return raw content truncated
    return raw_content[:5000]


def ingest_project_context(
    run_dir: Path,
    target_path: Path,
    feature_queue: FeatureQueueDoc,
    project_id: str,
    citex_api: str = CITEX_DEFAULT_URL,
) -> IngestionReport:
    """Read discovery artifacts + actual project code, ingest into Citex."""
    client = CitexClient(base_url=citex_api, project_id=project_id)
    records: list[IngestionRecord] = []
    outputs = run_dir / "outputs"

    # Category → (source description, content)
    ingestion_items: list[tuple[str, str]] = []

    # 1. Design brief
    design_brief = _read_json(outputs / "design-brief.json")
    if design_brief:
        ingestion_items.append(("design", json.dumps(design_brief, indent=2)))

    # 2. Feature specs
    for feature in feature_queue.features:
        spec_text = (
            f"Feature: {feature.title}\n"
            f"ID: {feature.feature_id}\n"
            f"Description: {feature.description}\n"
            f"Acceptance Criteria:\n" +
            "\n".join(f"- {c}" for c in feature.acceptance_criteria) +
            f"\nTest Requirements:\n" +
            "\n".join(f"- {t}" for t in feature.test_requirements)
        )
        ingestion_items.append(("feature_spec", spec_text))

    # 3. Architecture / stack / constraints
    target_contract = _read_json(outputs / "target-project-contract.json")
    build_plan = _read_json(outputs / "build-plan.json")
    arch_content = json.dumps({"target_contract": target_contract, "build_plan": build_plan}, indent=2)
    if target_contract or build_plan:
        ingestion_items.append(("architecture", arch_content))

    # 4. Existing code — read and synthesize with Opus
    code_categories = [
        ("api_contract", "backend/app/api/**/*.py"),
        ("data_model", "backend/app/models/**/*.py"),
        ("service_layer", "backend/app/services/**/*.py"),
        ("frontend_pattern", "frontend/src/stores/**/*.ts"),
        ("frontend_pattern", "frontend/src/components/**/*.tsx"),
        ("test_pattern", "backend/tests/**/*.py"),
    ]

    for category, pattern in code_categories:
        code_content = _read_code_files(target_path, pattern)
        if code_content:
            synthesized = _synthesize_with_opus(category, code_content)
            if synthesized:
                ingestion_items.append((category, synthesized))

    # Ingest all items
    for category, content in ingestion_items:
        success = client.ingest(content=content, category=category)
        records.append(IngestionRecord(
            category=category,
            char_count=len(content),
            success=success,
        ))
        status = "[green]ok[/green]" if success else "[red]fail[/red]"
        console.print(f"  Citex ingest [{category}]: {len(content)} chars — {status}")

    successful = sum(1 for r in records if r.success)
    failed = sum(1 for r in records if not r.success)

    return IngestionReport(
        project_id=project_id,
        total_documents=len(records),
        successful=successful,
        failed=failed,
        records=records,
    )


def ingest_feature_result(
    feature: FeatureStep,
    result: StepResult,
    target_path: Path,
    project_id: str,
    citex_api: str = CITEX_DEFAULT_URL,
) -> bool:
    """Ingest a completed feature result into Citex for the next feature to query."""
    client = CitexClient(base_url=citex_api, project_id=project_id)

    content = (
        f"Feature: {feature.title} ({feature.feature_id})\n"
        f"Status: {result.status.value}\n"
        f"Files created: {', '.join(result.files_created)}\n"
        f"Files modified: {', '.join(result.files_modified)}\n"
        f"Repair attempts: {result.repair_attempts}\n"
        f"Commit: {result.commit_sha}\n"
    )

    return client.ingest(
        content=content,
        category="prior_feature",
        metadata={"feature_id": feature.feature_id, "status": result.status.value},
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_ncdev_v3/test_context_ingestion.py -v`
Expected: 2 passed

- [ ] **Step 6: Commit**

```bash
git add src/ncdev/v3/context_ingestion.py src/ncdev/v3/models.py tests/test_ncdev_v3/test_context_ingestion.py
git commit -m "feat(v3): add context ingestion into Citex"
```

---

### Task 4: Rewrite Prompt Builder

**Files:**
- Modify: `src/ncdev/v3/prompt_builder.py`
- Test: `tests/test_ncdev_v3/test_prompt_builder.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_ncdev_v3/test_prompt_builder.py
from pathlib import Path
from ncdev.v3.prompt_builder import build_feature_prompt, build_repair_prompt
from ncdev.v3.models import FeatureStep


def test_lean_prompt_contains_citex_instructions():
    feature = FeatureStep(
        feature_id="f1",
        title="User Authentication",
        description="Add JWT-based user auth",
        acceptance_criteria=["Login returns JWT", "Protected routes require token"],
    )
    prompt = build_feature_prompt(
        feature=feature,
        target_path=Path("/tmp/project"),
        project_id="test-proj",
        citex_api="http://localhost:20160",
    )
    assert "localhost:20160" in prompt
    assert "test-proj" in prompt
    assert "User Authentication" in prompt
    assert "Login returns JWT" in prompt
    assert "/api/v1/retrieval/query" in prompt


def test_lean_prompt_under_5k_chars():
    feature = FeatureStep(
        feature_id="f1",
        title="Feature",
        description="Build something",
        acceptance_criteria=["It works"],
    )
    prompt = build_feature_prompt(
        feature=feature,
        target_path=Path("/tmp/project"),
        project_id="proj",
    )
    assert len(prompt) < 5000


def test_lean_prompt_has_query_examples():
    feature = FeatureStep(
        feature_id="f2",
        title="Dashboard",
        description="Build dashboard page",
        acceptance_criteria=["Shows data"],
    )
    prompt = build_feature_prompt(
        feature=feature,
        target_path=Path("/tmp/project"),
        project_id="proj",
    )
    assert "design tokens" in prompt.lower() or "design" in prompt.lower()
    assert "data model" in prompt.lower() or "models" in prompt.lower()
    assert "curl" in prompt or "httpx" in prompt


def test_repair_prompt_unchanged():
    feature = FeatureStep(
        feature_id="f1",
        title="Auth",
        description="Auth feature",
        acceptance_criteria=["Works"],
    )
    prompt = build_repair_prompt(
        feature=feature,
        target_path=Path("/tmp/project"),
        verification_output="test_login FAILED",
        error_traces="AssertionError: expected 200 got 401",
    )
    assert "REPAIR" in prompt
    assert "test_login FAILED" in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_ncdev_v3/test_prompt_builder.py -v`
Expected: FAIL — `build_feature_prompt() got unexpected keyword argument 'project_id'`

- [ ] **Step 3: Rewrite prompt_builder.py**

Replace the `build_feature_prompt` function in `src/ncdev/v3/prompt_builder.py`. Keep `build_repair_prompt`, `_get_file_tree`, `_get_recent_changes` unchanged.

New `build_feature_prompt`:

```python
def build_feature_prompt(
    feature: FeatureStep,
    target_path: Path,
    project_id: str = "",
    citex_api: str = "http://localhost:20160",
    spec_content: str = "",
    prior_results: list[StepResult] | None = None,
    stack: dict | None = None,
    design_brief: dict | None = None,
) -> str:
    """Build a lean prompt with Citex query instructions.

    Codex gets told WHAT to build and WHERE to find context.
    It pulls what it needs from Citex during its build session.
    """
    citex_curl = (
        f'curl -s -X POST {citex_api}/api/v1/retrieval/query '
        f'-H "Content-Type: application/json" '
        f'-d \'{{"project_id": "{project_id}", "query": "YOUR_QUERY", "limit": 5}}\' '
        f'| python3 -c "import sys,json; [print(d.get(\'content\',\'\')) for d in json.load(sys.stdin).get(\'results\',[])]"'
    )

    prior_summary = ""
    if prior_results:
        passed = [r for r in prior_results if r.status.value == "passed"]
        if passed:
            last = passed[-1]
            prior_summary = f"\nThe last completed feature was **{last.feature_id}** ({len(last.files_created)} files created). Query Citex for 'prior feature {last.feature_id}' to see integration points.\n"

    parts = [
        f"# Build: {feature.title}",
        "",
        "## Your Task",
        feature.description,
        "",
        "## Acceptance Criteria",
        *[f"- {c}" for c in feature.acceptance_criteria],
        "",
        "## Context Retrieval",
        f"You have access to a project knowledge base. Query it for any context you need.",
        "",
        "### How to query",
        "```bash",
        citex_curl,
        "```",
        "",
        "### What to query for",
        '- "design tokens colors typography" — before writing any UI',
        '- "existing API routes and schemas" — before adding endpoints',
        '- "data models and MongoDB schemas" — before creating models',
        '- "frontend store patterns" — before adding Zustand stores',
        '- "service layer patterns" — before adding backend services',
        '- "test patterns and fixtures" — before writing tests',
        '- "architectural constraints and conventions" — before structural decisions',
    ]

    if prior_summary:
        parts.append(prior_summary)

    parts.extend([
        "",
        "## Verification Protocol",
        "After implementing:",
        "1. Run backend tests: `cd backend && python -m pytest -q`",
        "2. Run frontend tests: `cd frontend && npx vitest run`",
        "3. Verify backend boots: `cd backend && python -c \"from app.main import app; print('OK')\"`",
        "4. Fix ALL failures before finishing.",
        "",
        "## Rules",
        "- READ existing code before writing new code",
        "- Build ON TOP of what exists — do not rewrite working code",
        "- Every file must be importable and functional",
        "- No placeholder stubs, no TODO comments",
    ])

    return "\n".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_ncdev_v3/test_prompt_builder.py -v`
Expected: 4 passed

- [ ] **Step 5: Run all tests**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add src/ncdev/v3/prompt_builder.py tests/test_ncdev_v3/test_prompt_builder.py
git commit -m "feat(v3): rewrite prompt builder with lean Citex-backed prompts"
```

---

### Task 5: Wire into Engine and Step Executor

**Files:**
- Modify: `src/ncdev/v3/engine.py`
- Modify: `src/ncdev/v3/step_executor.py`
- Modify: `src/ncdev/preflight.py`
- Modify: `src/ncdev/cli.py`

- [ ] **Step 1: Add Citex health check to preflight.py**

In `src/ncdev/preflight.py`, add after existing code:

```python
def check_citex(url: str = "http://localhost:20160") -> bool:
    """Check if Citex RAG is reachable."""
    try:
        import httpx
        resp = httpx.get(f"{url}/api/v1/health", timeout=5)
        return resp.status_code < 400
    except Exception:
        return False
```

- [ ] **Step 2: Update CLI doctor to check Citex**

In `src/ncdev/cli.py` `_doctor_report()`, add after the docker check:

```python
    from ncdev.preflight import check_citex
    citex_ok = check_citex()
    lines.append(f"- citex (localhost:20160): {'ok' if citex_ok else 'not running'}")
```

- [ ] **Step 3: Update engine.py — add ingestion phase and metrics**

In `src/ncdev/v3/engine.py`, add these changes:

After Phase 1 (discovery), before Phase 4 (feature queue), add:

```python
    # ── Phase 2.5: Context Ingestion into Citex ──────────────
    state.phase = "ingestion"
    console.print("\n[bold]Phase 2.5: Context Ingestion into Citex[/bold]")

    from ncdev.v3.citex_client import CitexClient
    from ncdev.v3.context_ingestion import ingest_project_context, ingest_feature_result

    project_id = build_plan.project_name or target_path.name
    citex = CitexClient(project_id=project_id)

    if not citex.health_check():
        console.print("[red]ERROR: Citex RAG (localhost:20160) is required but unreachable.[/red]")
        console.print("[red]Start Citex before running ncdev full.[/red]")
        state.phase = "failed"
        state.status = "failed"
        _persist_state(state, run_dir)
        return state

    ingestion_report = ingest_project_context(
        run_dir=run_dir,
        target_path=target_path,
        feature_queue=feature_queue,
        project_id=project_id,
    )
    console.print(f"  [green]✓[/green] Ingested {ingestion_report.successful}/{ingestion_report.total_documents} documents into Citex")
```

In the feature build loop, after `completed.append(result)`, add:

```python
            ingest_feature_result(feature, result, target_path, project_id=project_id)
```

Update the `execute_feature_step` call to pass `project_id`:

```python
            result = execute_feature_step(
                feature=feature,
                target_path=target_path,
                run_dir=run_dir,
                prior_results=completed,
                spec_content=spec_content,
                stack=stack if isinstance(stack, dict) else {},
                design_brief=design_brief_dict,
                max_repair_attempts=max_repair_attempts,
                builder_timeout=builder_timeout,
                builder_model=builder_model,
                project_id=project_id,
            )
```

After Phase 6 (summary), add metrics:

```python
    # ── Metrics ──────────────────���────────────────────────────
    from ncdev.v3.metrics import compute_run_metrics

    metrics = compute_run_metrics(state, ingestion_doc_count=ingestion_report.successful if ingestion_report else 0)
    write_json(run_dir / "outputs" / "metrics.json", metrics.model_dump(mode="json"))

    # Store metrics in Citex
    citex.ingest(
        content=metrics.model_dump_json(indent=2),
        category="metrics",
        metadata={"run_id": run_id},
    )

    # Display metrics panel
    from rich.panel import Panel as MetricsPanel
    console.print(MetricsPanel(
        f"[bold]First-Pass Success Rate:[/bold] {metrics.first_pass_success_rate:.0%} ({len([f for f in metrics.features if f.first_pass])}/{metrics.total_features})\n"
        f"[bold]Repair Rate:[/bold]             {metrics.repair_rate:.0%}\n"
        f"[bold]Mean Repair Attempts:[/bold]    {metrics.mean_repair_attempts:.1f}\n"
        f"[bold]Build Efficiency:[/bold]        {metrics.build_efficiency:.0%}\n"
        f"[bold]Feature Throughput:[/bold]      {metrics.feature_throughput_per_hour:.1f}/hr\n"
        f"[bold]Citex Docs Ingested:[/bold]     {metrics.citex_documents_ingested}",
        title="Build Metrics",
        border_style="cyan",
    ))
```

- [ ] **Step 4: Update step_executor.py — pass project_id through**

Add `project_id: str = ""` parameter to `execute_feature_step()` and pass it to `build_feature_prompt()`:

```python
def execute_feature_step(
    feature: FeatureStep,
    target_path: Path,
    run_dir: Path,
    prior_results: list[StepResult],
    spec_content: str = "",
    stack: dict | None = None,
    design_brief: dict | None = None,
    max_repair_attempts: int = 2,
    builder_timeout: int = 600,
    builder_model: str = "opus",
    project_id: str = "",
) -> StepResult:
```

Update the `build_feature_prompt` call:

```python
    prompt = build_feature_prompt(
        feature=feature,
        target_path=target_path,
        project_id=project_id,
        prior_results=prior_results,
        stack=stack,
        design_brief=design_brief,
    )
```

- [ ] **Step 5: Run all tests**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All pass (159 existing + new tests)

- [ ] **Step 6: Commit**

```bash
git add src/ncdev/v3/engine.py src/ncdev/v3/step_executor.py src/ncdev/preflight.py src/ncdev/cli.py
git commit -m "feat(v3): wire Citex ingestion, metrics, and lean prompts into pipeline"
```

---

### Task 6: Final Integration Test

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All pass

- [ ] **Step 2: Verify imports chain**

```bash
python -c "
from ncdev.v3.citex_client import CitexClient
from ncdev.v3.context_ingestion import ingest_project_context, ingest_feature_result
from ncdev.v3.metrics import compute_run_metrics, RunMetrics
from ncdev.v3.prompt_builder import build_feature_prompt
from ncdev.v3.engine import run_v3_full
from ncdev.preflight import check_citex
print('All imports OK')
"
```

- [ ] **Step 3: Commit and push**

```bash
git push origin main
```
