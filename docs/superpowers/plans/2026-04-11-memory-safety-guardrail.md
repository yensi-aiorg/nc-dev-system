# Memory Safety Guardrail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent NC Dev System from crashing the host machine by adding memory monitoring, E2E test serialization, resource cleanup, and a pre-build memory audit for target projects.

**Architecture:** Add a `src/memory.py` module for all memory monitoring and cleanup logic. Modify `src/pipeline.py` to split Phase 3 into 3a (parallel build) and 3b (sequential E2E), add cleanup between phases, and add a Phase 3.5 memory audit. Add `psutil` dependency. Create `src/auditor/` module for static analysis of target projects.

**Tech Stack:** Python 3.12, psutil, pytest, pytest-asyncio, asyncio

**Spec:** `/Users/nrupal/dev/yensi/dev/nc-dev-system/URGENT-MEMORY-SAFETY-GUARDRAIL.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/memory.py` | Create | Memory monitoring, cleanup, pressure checks — all memory logic lives here |
| `src/auditor/__init__.py` | Create | Package init with public API |
| `src/auditor/scanner.py` | Create | Static analysis scanner for memory-leak patterns in target projects |
| `src/auditor/report.py` | Create | Generates MEMORY-SAFETY-REPORT.md from scan results |
| `src/pipeline.py` | Modify | Split phase3, add phase3.5 audit, add cleanup calls, add memory checkpoints |
| `src/builder/codex_runner.py` | Modify | Add pre-spawn memory check |
| `src/config.py` | Modify | Add memory safety config fields |
| `pyproject.toml` | Modify | Add psutil dependency |
| `templates/greenfield/docker-compose.yml.j2` | Modify | Add memory limits to services |
| `tests/test_memory.py` | Create | Tests for memory module |
| `tests/test_auditor.py` | Create | Tests for auditor scanner and report |
| `tests/test_pipeline_memory.py` | Create | Tests for pipeline memory integration |

---

## Task 1: Add psutil dependency and create `src/memory.py`

**Files:**
- Modify: `pyproject.toml:11-18` (add psutil to dependencies)
- Create: `src/memory.py`
- Create: `tests/test_memory.py`

- [ ] **Step 1: Write failing tests for memory module**

```python
# tests/test_memory.py
"""Tests for memory monitoring and resource cleanup (src.memory)."""
from __future__ import annotations

import gc
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.memory import (
    MemoryPressure,
    MemorySnapshot,
    check_memory_pressure,
    cleanup_resources,
    get_memory_snapshot,
    log_memory_checkpoint,
)


class TestGetMemorySnapshot:
    @pytest.mark.unit
    def test_returns_snapshot_with_valid_fields(self):
        snap = get_memory_snapshot()
        assert isinstance(snap, MemorySnapshot)
        assert 0 < snap.total_gb
        assert 0 <= snap.used_gb <= snap.total_gb
        assert 0 <= snap.percent <= 100

    @pytest.mark.unit
    def test_available_gb_is_positive(self):
        snap = get_memory_snapshot()
        assert snap.available_gb > 0


class TestCheckMemoryPressure:
    @pytest.mark.unit
    def test_returns_ok_when_below_80(self):
        with patch("src.memory.get_memory_snapshot") as mock:
            mock.return_value = MemorySnapshot(
                total_gb=64.0, used_gb=30.0, available_gb=34.0, percent=46.9
            )
            result = check_memory_pressure()
            assert result == MemoryPressure.OK

    @pytest.mark.unit
    def test_returns_high_between_80_and_90(self):
        with patch("src.memory.get_memory_snapshot") as mock:
            mock.return_value = MemorySnapshot(
                total_gb=64.0, used_gb=54.0, available_gb=10.0, percent=84.4
            )
            result = check_memory_pressure()
            assert result == MemoryPressure.HIGH

    @pytest.mark.unit
    def test_returns_critical_above_90(self):
        with patch("src.memory.get_memory_snapshot") as mock:
            mock.return_value = MemorySnapshot(
                total_gb=64.0, used_gb=60.0, available_gb=4.0, percent=93.8
            )
            result = check_memory_pressure()
            assert result == MemoryPressure.CRITICAL


class TestCleanupResources:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cleanup_runs_without_error(self):
        with patch("src.memory.run_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "", "")
            await cleanup_resources(project_dir=None)
            # Should call pkill for chromium and playwright at minimum
            assert mock_run.call_count >= 2

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cleanup_with_project_dir_runs_docker_down(self):
        with patch("src.memory.run_command", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = (0, "", "")
            await cleanup_resources(project_dir="/tmp/test-project")
            # Should include docker compose down
            calls_str = str(mock_run.call_args_list)
            assert "docker" in calls_str


class TestLogMemoryCheckpoint:
    @pytest.mark.unit
    def test_returns_snapshot_and_pressure(self):
        snap, pressure = log_memory_checkpoint("test-phase")
        assert isinstance(snap, MemorySnapshot)
        assert isinstance(pressure, MemoryPressure)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/test_memory.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.memory'`

- [ ] **Step 3: Add psutil to pyproject.toml**

In `pyproject.toml`, add `"psutil>=5.9,<7"` to the dependencies list:

```toml
dependencies = [
  "pydantic>=2.8,<3",
  "pyyaml>=6.0.1,<7",
  "rich>=13.7,<15",
  "jinja2>=3.1,<4",
  "httpx>=0.27,<1",
  "motor>=3.5,<4",
  "psutil>=5.9,<7",
]
```

- [ ] **Step 4: Install psutil**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && pip install psutil`

- [ ] **Step 5: Implement `src/memory.py`**

```python
# src/memory.py
"""Memory monitoring, pressure detection, and resource cleanup.

Provides the core memory safety primitives used by the pipeline:
- get_memory_snapshot() — current RAM usage
- check_memory_pressure() — OK / HIGH / CRITICAL classification
- cleanup_resources() — kill orphan browsers, stop Docker, force GC
- log_memory_checkpoint() — snapshot + log at a named checkpoint
"""
from __future__ import annotations

import asyncio
import gc
import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import psutil

from src.utils import run_command

logger = logging.getLogger(__name__)


class MemoryPressure(str, Enum):
    """Memory pressure classification."""
    OK = "ok"
    HIGH = "high"          # >80% — downgrade to sequential
    CRITICAL = "critical"  # >90% — emergency halt


@dataclass(frozen=True)
class MemorySnapshot:
    """Point-in-time memory usage reading."""
    total_gb: float
    used_gb: float
    available_gb: float
    percent: float


def get_memory_snapshot() -> MemorySnapshot:
    """Read current system memory usage via psutil."""
    mem = psutil.virtual_memory()
    return MemorySnapshot(
        total_gb=round(mem.total / (1024**3), 2),
        used_gb=round(mem.used / (1024**3), 2),
        available_gb=round(mem.available / (1024**3), 2),
        percent=round(mem.percent, 1),
    )


def check_memory_pressure(
    high_threshold: float = 80.0,
    critical_threshold: float = 90.0,
) -> MemoryPressure:
    """Classify current memory pressure.

    Returns MemoryPressure.CRITICAL if usage > critical_threshold,
    MemoryPressure.HIGH if > high_threshold, else OK.
    """
    snap = get_memory_snapshot()

    if snap.percent > critical_threshold:
        logger.critical(
            "MEMORY CRITICAL: %.1f%% used (%.1fGB / %.1fGB)",
            snap.percent, snap.used_gb, snap.total_gb,
        )
        return MemoryPressure.CRITICAL

    if snap.percent > high_threshold:
        logger.warning(
            "MEMORY HIGH: %.1f%% used (%.1fGB / %.1fGB)",
            snap.percent, snap.used_gb, snap.total_gb,
        )
        return MemoryPressure.HIGH

    logger.info(
        "Memory OK: %.1f%% used (%.1fGB / %.1fGB)",
        snap.percent, snap.used_gb, snap.total_gb,
    )
    return MemoryPressure.OK


async def cleanup_resources(project_dir: str | Path | None = None) -> None:
    """Kill orphaned processes and free memory.

    1. Kill orphaned Chromium/Playwright browser processes
    2. Stop Docker containers if project_dir is provided
    3. Force Python garbage collection
    """
    # Kill orphaned browsers
    await run_command("pkill -f chromium 2>/dev/null || true", timeout=10)
    await run_command("pkill -f playwright 2>/dev/null || true", timeout=10)

    # Stop Docker containers if we know the project directory
    if project_dir:
        project_path = Path(project_dir)
        for compose_file in [
            "docker-compose.dev.yml",
            "docker-compose.test.yml",
            "docker-compose.yml",
        ]:
            full_path = project_path / compose_file
            if full_path.exists():
                await run_command(
                    f"docker compose -f {full_path} down 2>/dev/null || true",
                    timeout=30,
                )
                break  # Only need to down once

    # Force garbage collection
    gc.collect()

    logger.info("Resource cleanup completed")


def log_memory_checkpoint(label: str) -> tuple[MemorySnapshot, MemoryPressure]:
    """Take a memory snapshot, log it, and return both snapshot and pressure level."""
    snap = get_memory_snapshot()
    pressure = check_memory_pressure()
    logger.info(
        "[%s] Memory: %.1f%% (%.1fGB / %.1fGB) — pressure=%s",
        label, snap.percent, snap.used_gb, snap.total_gb, pressure.value,
    )
    return snap, pressure
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/test_memory.py -v`
Expected: All 7 tests PASS

- [ ] **Step 7: Commit**

```bash
cd /Users/nrupal/dev/yensi/dev/nc-dev-system
git add src/memory.py tests/test_memory.py pyproject.toml
git commit -m "feat: add memory monitoring module with psutil

Adds src/memory.py with MemorySnapshot, MemoryPressure enum,
check_memory_pressure(), cleanup_resources(), and
log_memory_checkpoint(). Part of the 6th guardrail:
memory safety."
```

---

## Task 2: Add memory safety fields to `src/config.py`

**Files:**
- Modify: `src/config.py:59-89` (BuildConfig class)

- [ ] **Step 1: Add memory config fields to BuildConfig**

In `src/config.py`, add these fields to the `BuildConfig` class after `max_fix_iterations`:

```python
    # Memory safety (6th guardrail)
    memory_high_threshold: float = Field(
        default=80.0, ge=50.0, le=95.0,
        description="Memory usage % that triggers sequential downgrade",
    )
    memory_critical_threshold: float = Field(
        default=90.0, ge=60.0, le=99.0,
        description="Memory usage % that triggers emergency halt",
    )
    e2e_serial: bool = Field(
        default=True,
        description="Run E2E tests sequentially (one feature at a time)",
    )
    memory_audit_enabled: bool = Field(
        default=True,
        description="Run memory safety audit before verification",
    )
```

- [ ] **Step 2: Run existing config tests**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/ -k "config" -v`
Expected: All existing tests still PASS (new fields have defaults, so backward-compatible)

- [ ] **Step 3: Commit**

```bash
cd /Users/nrupal/dev/yensi/dev/nc-dev-system
git add src/config.py
git commit -m "feat(config): add memory safety fields to BuildConfig

Adds memory_high_threshold, memory_critical_threshold,
e2e_serial, and memory_audit_enabled fields with safe defaults."
```

---

## Task 3: Create `src/auditor/` memory audit module

**Files:**
- Create: `src/auditor/__init__.py`
- Create: `src/auditor/scanner.py`
- Create: `src/auditor/report.py`
- Create: `tests/test_auditor.py`

- [ ] **Step 1: Write failing tests for the auditor**

```python
# tests/test_auditor.py
"""Tests for memory safety auditor (src.auditor)."""
from __future__ import annotations

from pathlib import Path

import pytest

from src.auditor import MemoryAuditResult, scan_project, generate_report


class TestScanProject:
    @pytest.mark.unit
    def test_empty_directory_returns_clean(self, tmp_path):
        result = scan_project(tmp_path)
        assert isinstance(result, MemoryAuditResult)
        assert result.is_clean
        assert len(result.findings) == 0

    @pytest.mark.unit
    def test_detects_browser_launch_in_loop(self, tmp_path):
        py_file = tmp_path / "scraper.py"
        py_file.write_text(
            "async def fetch(url):\n"
            "    browser = await playwright.chromium.launch()\n"
            "    page = await browser.new_page()\n"
            "    await page.goto(url)\n"
            "    return await page.content()\n"
        )
        result = scan_project(tmp_path)
        assert not result.is_clean
        assert any("browser.launch" in f.pattern or "chromium.launch" in f.pattern for f in result.findings)

    @pytest.mark.unit
    def test_detects_unbounded_list_append_in_loop(self, tmp_path):
        py_file = tmp_path / "worker.py"
        py_file.write_text(
            "class Worker:\n"
            "    _log: list = []\n"
            "    async def _loop(self):\n"
            "        while True:\n"
            "            data = await self.fetch()\n"
            "            self._log.append(data)\n"
        )
        result = scan_project(tmp_path)
        assert not result.is_clean

    @pytest.mark.unit
    def test_detects_dict_cache_without_maxsize(self, tmp_path):
        py_file = tmp_path / "cache.py"
        py_file.write_text(
            "_cache: dict[str, bytes] = {}\n"
            "def get(key):\n"
            "    return _cache.get(key)\n"
            "def put(key, val):\n"
            "    _cache[key] = val\n"
        )
        result = scan_project(tmp_path)
        assert not result.is_clean

    @pytest.mark.unit
    def test_detects_gather_without_return_exceptions(self, tmp_path):
        py_file = tmp_path / "pipeline.py"
        py_file.write_text(
            "results = await asyncio.gather(*tasks)\n"
        )
        result = scan_project(tmp_path)
        assert not result.is_clean

    @pytest.mark.unit
    def test_detects_docker_without_memory_limits(self, tmp_path):
        compose = tmp_path / "docker-compose.dev.yml"
        compose.write_text(
            "services:\n"
            "  backend:\n"
            "    build: ./backend\n"
            "    ports:\n"
            "      - '8000:8000'\n"
        )
        result = scan_project(tmp_path)
        assert not result.is_clean
        assert any("docker" in f.pattern.lower() or "mem_limit" in f.description.lower() for f in result.findings)

    @pytest.mark.unit
    def test_clean_project_returns_clean(self, tmp_path):
        py_file = tmp_path / "app.py"
        py_file.write_text(
            "from collections import deque\n"
            "log = deque(maxlen=1000)\n"
            "def process(item):\n"
            "    log.append(item)\n"
        )
        result = scan_project(tmp_path)
        assert result.is_clean


class TestGenerateReport:
    @pytest.mark.unit
    def test_generates_markdown_file(self, tmp_path):
        result = MemoryAuditResult(findings=[], scanned_files=5)
        output_path = tmp_path / ".nc-dev" / "MEMORY-SAFETY-REPORT.md"
        generate_report(result, output_path)
        assert output_path.exists()
        content = output_path.read_text()
        assert "Memory Safety" in content

    @pytest.mark.unit
    def test_report_includes_findings(self, tmp_path):
        from src.auditor.scanner import Finding
        result = MemoryAuditResult(
            findings=[
                Finding(
                    file="scraper.py",
                    line=5,
                    pattern="browser.launch",
                    description="Browser launched without pooling",
                    severity="high",
                )
            ],
            scanned_files=1,
        )
        output_path = tmp_path / "report.md"
        generate_report(result, output_path)
        content = output_path.read_text()
        assert "scraper.py" in content
        assert "browser.launch" in content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/test_auditor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.auditor'`

- [ ] **Step 3: Implement `src/auditor/__init__.py`**

```python
# src/auditor/__init__.py
"""Memory safety auditor for target projects.

Scans a project's source code for known memory-leak patterns and generates
a safety report. Used by the pipeline before Phase 4 (VERIFY).
"""
from .report import generate_report
from .scanner import Finding, MemoryAuditResult, scan_project

__all__ = ["Finding", "MemoryAuditResult", "generate_report", "scan_project"]
```

- [ ] **Step 4: Implement `src/auditor/scanner.py`**

```python
# src/auditor/scanner.py
"""Static analysis scanner for memory-leak patterns."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# File extensions to scan
_CODE_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx"}
_COMPOSE_PATTERNS = {"docker-compose.yml", "docker-compose.dev.yml", "docker-compose.test.yml"}


@dataclass
class Finding:
    """A single memory-safety finding."""
    file: str
    line: int
    pattern: str
    description: str
    severity: str  # "high", "medium", "low"


@dataclass
class MemoryAuditResult:
    """Result of scanning a project for memory-leak patterns."""
    findings: list[Finding] = field(default_factory=list)
    scanned_files: int = 0

    @property
    def is_clean(self) -> bool:
        return len(self.findings) == 0

    @property
    def high_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "high")

    @property
    def medium_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "medium")


# Pattern definitions: (regex, pattern_name, description, severity)
_CODE_PATTERNS: list[tuple[re.Pattern, str, str, str]] = [
    (
        re.compile(r"(?:browser|chromium|firefox|webkit)\s*[=.]\s*(?:await\s+)?.*\.launch\s*\("),
        "browser.launch",
        "Browser launched per-request — may leak Chromium processes if not pooled",
        "high",
    ),
    (
        re.compile(r"asyncio\.gather\s*\(\s*\*\w+\s*\)\s*$", re.MULTILINE),
        "asyncio.gather without return_exceptions",
        "asyncio.gather without return_exceptions=True — one OOM crash hides others",
        "medium",
    ),
    (
        re.compile(r"asyncio\.gather\s*\(\s*\*\w+\s*,\s*return_exceptions\s*=\s*False"),
        "asyncio.gather return_exceptions=False",
        "asyncio.gather with return_exceptions=False — one OOM crash hides others",
        "medium",
    ),
    (
        re.compile(r"_cache\s*:\s*dict\["),
        "dict-based cache",
        "Dict-based cache without max size — grows unbounded",
        "medium",
    ),
    (
        re.compile(r"_(?:log|history|request_log)\s*:\s*list\["),
        "unbounded list accumulator",
        "List accumulator without maxlen — grows unbounded in long-running processes",
        "medium",
    ),
]

_COMPOSE_MISSING_LIMITS_RE = re.compile(r"^\s+\w+:", re.MULTILINE)


def _scan_code_file(file_path: Path, project_root: Path) -> list[Finding]:
    """Scan a single code file for memory-leak patterns."""
    findings: list[Finding] = []
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings

    rel_path = str(file_path.relative_to(project_root))
    lines = content.split("\n")

    for line_num, line in enumerate(lines, start=1):
        for pattern_re, pattern_name, description, severity in _CODE_PATTERNS:
            if pattern_re.search(line):
                findings.append(Finding(
                    file=rel_path,
                    line=line_num,
                    pattern=pattern_name,
                    description=description,
                    severity=severity,
                ))

    return findings


def _scan_compose_file(file_path: Path, project_root: Path) -> list[Finding]:
    """Scan a docker-compose file for missing memory limits."""
    findings: list[Finding] = []
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings

    rel_path = str(file_path.relative_to(project_root))

    # Check if any service lacks deploy.resources.limits.memory or mem_limit
    if "services:" in content and "mem_limit" not in content and "limits:" not in content:
        findings.append(Finding(
            file=rel_path,
            line=1,
            pattern="docker-compose without memory limits",
            description="Docker Compose services have no memory limits — containers can consume all host RAM",
            severity="high",
        ))

    return findings


def scan_project(project_dir: str | Path) -> MemoryAuditResult:
    """Scan a project directory for memory-leak patterns.

    Checks Python/JS/TS files for dangerous code patterns and
    docker-compose files for missing memory limits.
    """
    project_path = Path(project_dir)
    findings: list[Finding] = []
    scanned = 0

    # Scan code files
    for ext in _CODE_EXTENSIONS:
        for file_path in project_path.rglob(f"*{ext}"):
            # Skip node_modules, __pycache__, .git, venvs
            parts = file_path.parts
            if any(skip in parts for skip in ("node_modules", "__pycache__", ".git", ".venv", "venv")):
                continue
            findings.extend(_scan_code_file(file_path, project_path))
            scanned += 1

    # Scan docker-compose files
    for compose_name in _COMPOSE_PATTERNS:
        compose_path = project_path / compose_name
        if compose_path.exists():
            findings.extend(_scan_compose_file(compose_path, project_path))
            scanned += 1

    result = MemoryAuditResult(findings=findings, scanned_files=scanned)

    if result.is_clean:
        logger.info("Memory audit: CLEAN (%d files scanned)", scanned)
    else:
        logger.warning(
            "Memory audit: %d findings (%d high, %d medium) in %d files",
            len(findings), result.high_count, result.medium_count, scanned,
        )

    return result
```

- [ ] **Step 5: Implement `src/auditor/report.py`**

```python
# src/auditor/report.py
"""Generate a MEMORY-SAFETY-REPORT.md from audit results."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .scanner import MemoryAuditResult


def generate_report(result: MemoryAuditResult, output_path: str | Path) -> Path:
    """Write a markdown report from audit results.

    Args:
        result: The audit result to report on.
        output_path: Where to write the markdown file.

    Returns:
        The resolved path of the written report.
    """
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    lines.append("# Memory Safety Audit Report")
    lines.append("")
    lines.append(f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append(f"**Files scanned:** {result.scanned_files}")
    lines.append(f"**Findings:** {len(result.findings)}")
    lines.append(f"**Status:** {'CLEAN' if result.is_clean else 'ISSUES FOUND'}")
    lines.append("")

    if result.is_clean:
        lines.append("No memory-safety issues detected.")
    else:
        lines.append("## Findings")
        lines.append("")
        lines.append("| Severity | File | Line | Pattern | Description |")
        lines.append("|----------|------|------|---------|-------------|")
        for f in sorted(result.findings, key=lambda x: (x.severity != "high", x.file, x.line)):
            lines.append(f"| {f.severity.upper()} | `{f.file}` | {f.line} | `{f.pattern}` | {f.description} |")
        lines.append("")
        lines.append("## Impact")
        lines.append("")
        lines.append("E2E tests and verification will run with safety constraints:")
        lines.append("- E2E test concurrency downgraded to 1 (sequential)")
        lines.append("- Docker containers will have memory limits applied")
        lines.append("- Memory monitored between each test run")

    lines.append("")
    content = "\n".join(lines)
    path.write_text(content, encoding="utf-8")
    return path.resolve()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/test_auditor.py -v`
Expected: All 9 tests PASS

- [ ] **Step 7: Commit**

```bash
cd /Users/nrupal/dev/yensi/dev/nc-dev-system
git add src/auditor/ tests/test_auditor.py
git commit -m "feat: add memory safety auditor module

Scans target projects for known memory-leak patterns
(browser launches, unbounded caches, missing Docker
memory limits, unsafe asyncio.gather calls) and generates
MEMORY-SAFETY-REPORT.md. Part of the 6th guardrail."
```

---

## Task 4: Modify `src/pipeline.py` — split Phase 3, add cleanup, add memory checkpoints

This is the core change. We modify `phase3_build` to split into 3a (parallel build) and 3b (sequential E2E), add `_cleanup_resources` calls between phases, change `return_exceptions` to `True`, and add memory checkpoints.

**Files:**
- Modify: `src/pipeline.py:1-50` (imports)
- Modify: `src/pipeline.py:505-576` (phase3_build method)
- Modify: `src/pipeline.py:196-264` (run method — add cleanup between phases)
- Create: `tests/test_pipeline_memory.py`

- [ ] **Step 1: Write failing tests for pipeline memory integration**

```python
# tests/test_pipeline_memory.py
"""Tests for pipeline memory safety integration."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.config import Config
from src.pipeline import Pipeline


class TestPhase3MemoryCheckpoints:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_phase3_uses_return_exceptions_true(self, tmp_path):
        """Verify gather uses return_exceptions=True."""
        config = Config(output_dir=tmp_path)
        config.ensure_directories()
        pipeline = Pipeline(config)

        # Write a features file with one feature
        import json
        features = [{"name": "test-feature", "description": "test"}]
        config.features_path.write_text(json.dumps(features))

        with patch.object(pipeline, "_build_single_feature", new_callable=AsyncMock) as mock_build:
            mock_build.side_effect = MemoryError("simulated OOM")

            # Should NOT raise — return_exceptions=True catches it
            result = await pipeline.phase3_build()
            assert result["features_failed"] >= 1

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cleanup_called_between_phases(self, tmp_path):
        """Verify cleanup_resources is called during the run method."""
        config = Config(output_dir=tmp_path, phases=[3])
        config.ensure_directories()
        pipeline = Pipeline(config)

        with (
            patch.object(pipeline, "phase3_build", new_callable=AsyncMock) as mock_p3,
            patch("src.pipeline.cleanup_resources", new_callable=AsyncMock) as mock_cleanup,
            patch("src.pipeline.log_memory_checkpoint") as mock_checkpoint,
        ):
            mock_p3.return_value = {"features_built": 0, "features_failed": 0}
            mock_checkpoint.return_value = (MagicMock(), MagicMock(value="ok"))

            pipeline.state["requirements_path"] = str(tmp_path / "req.md")
            await pipeline.run(str(tmp_path / "req.md"))

            # cleanup_resources should have been called at least once
            assert mock_cleanup.call_count >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/test_pipeline_memory.py -v`
Expected: FAIL

- [ ] **Step 3: Add memory imports to pipeline.py**

At the top of `src/pipeline.py`, after existing imports from `src.utils`, add:

```python
from src.memory import (
    MemoryPressure,
    check_memory_pressure,
    cleanup_resources,
    log_memory_checkpoint,
)
```

- [ ] **Step 4: Modify phase3_build — use return_exceptions=True and add memory checkpoints**

Replace the `asyncio.gather` call in `phase3_build` (line 548) and add cleanup. Replace from `build_results: list[dict[str, Any]] = []` through the end of the method:

Change `return_exceptions=False` to `return_exceptions=True` on line 548:

```python
        build_results = await asyncio.gather(*tasks, return_exceptions=True)
```

Then replace the `succeeded`/`failed` counting block (lines 550-551) with:

```python
        # Handle exceptions from return_exceptions=True
        processed_results: list[dict[str, Any]] = []
        for i, r in enumerate(build_results):
            if isinstance(r, BaseException):
                feat_name = features_list[i].get("name", f"feature-{i}")
                console.print(f"  [red]Builder for {feat_name} crashed: {r}[/red]")
                processed_results.append({
                    "success": False,
                    "feature": feat_name,
                    "error": str(r),
                })
                await cleanup_resources(self.config.output_dir)
            else:
                processed_results.append(r)

        # Memory checkpoint after parallel build
        log_memory_checkpoint("post-phase3a-build")

        succeeded = sum(1 for r in processed_results if r.get("success"))
        failed = sum(1 for r in processed_results if not r.get("success"))
```

Also update the reference to `build_results` in `phase_result` to use `processed_results`:

```python
        phase_result = {
            "features_built": succeeded,
            "features_failed": failed,
            "results": processed_results,
        }
```

- [ ] **Step 5: Add cleanup between phases in the run() method**

In the `run()` method, after each phase completes (inside the `try` block, after `print_success`), add cleanup. Find the line `print_success(...)` (around line 225) and after it add:

```python
                # Memory cleanup between phases
                await cleanup_resources(self.config.output_dir)
                _, pressure = log_memory_checkpoint(f"post-phase-{phase_num}")
                if pressure == MemoryPressure.CRITICAL:
                    print_error(
                        f"  MEMORY CRITICAL after Phase {phase_num} — halting pipeline. "
                        "Free memory and run `ncdev resume`."
                    )
                    self.state["phases_failed"].append(phase_num + 1)
                    self.state[f"phase{phase_num + 1}_error"] = "Memory pressure critical"
                    break
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/test_pipeline_memory.py -v`
Expected: All tests PASS

- [ ] **Step 7: Run full test suite to check for regressions**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/ -v --timeout=60`
Expected: No regressions in existing tests

- [ ] **Step 8: Commit**

```bash
cd /Users/nrupal/dev/yensi/dev/nc-dev-system
git add src/pipeline.py tests/test_pipeline_memory.py
git commit -m "feat(pipeline): add memory checkpoints, cleanup between phases, safe gather

- phase3_build now uses return_exceptions=True
- Crashed builders trigger cleanup_resources()
- Memory checkpoint logged after Phase 3a
- cleanup_resources() runs between every phase
- Pipeline halts if memory exceeds 90% after any phase"
```

---

## Task 5: Add memory pre-check to `src/builder/codex_runner.py`

**Files:**
- Modify: `src/builder/codex_runner.py:239-270` (run method, before subprocess spawn)

- [ ] **Step 1: Add memory import to codex_runner.py**

At the top of `src/builder/codex_runner.py`, add:

```python
from src.memory import MemoryPressure, check_memory_pressure
```

- [ ] **Step 2: Add memory pre-check before spawning builder process**

In the `run()` method, right before the `try: process = await asyncio.create_subprocess_exec(...)` block (around line 363), add:

```python
        # Memory safety check before spawning builder
        pressure = check_memory_pressure()
        if pressure == MemoryPressure.CRITICAL:
            raise CodexRunnerError(
                "Cannot start builder: memory pressure critical "
                f"(>{90}% used). Free memory before retrying."
            )
```

- [ ] **Step 3: Run existing codex_runner tests**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/ -k "codex_runner or runner" -v`
Expected: All existing tests PASS (the memory check only fires when memory is actually critical)

- [ ] **Step 4: Commit**

```bash
cd /Users/nrupal/dev/yensi/dev/nc-dev-system
git add src/builder/codex_runner.py
git commit -m "feat(builder): add memory pre-check before spawning builder process

Refuses to start a builder subprocess if system memory exceeds 90%.
Prevents cascading OOM when multiple builders run in parallel."
```

---

## Task 6: Add Phase 3.5 memory audit to pipeline

**Files:**
- Modify: `src/pipeline.py` (add phase3_5_audit method and call it from run())

- [ ] **Step 1: Add phase3_5_audit method to Pipeline class**

Add this method to the Pipeline class, after `phase3_build` and before `phase4_verify`:

```python
    # ------------------------------------------------------------------
    # Phase 3.5: MEMORY AUDIT
    # ------------------------------------------------------------------

    async def phase3_5_audit(self) -> dict[str, Any]:
        """Scan the target project for memory-leak patterns.

        If findings are detected, the pipeline downgrades E2E concurrency
        and generates a MEMORY-SAFETY-REPORT.md in the project's .nc-dev/.
        """
        if not self.config.build.memory_audit_enabled:
            console.print("  [yellow]Memory audit disabled — skipping.[/yellow]")
            return {"skipped": True, "findings": 0}

        console.print("  Scanning project for memory-leak patterns...")

        from src.auditor import generate_report, scan_project

        result = scan_project(self.config.output_dir)

        if not result.is_clean:
            console.print(
                f"  [yellow]Found {len(result.findings)} memory-safety issue(s) "
                f"({result.high_count} high, {result.medium_count} medium)[/yellow]"
            )

            # Generate report
            report_path = self.config.nc_dev_path / "MEMORY-SAFETY-REPORT.md"
            generate_report(result, report_path)
            console.print(f"  Report saved to {report_path}")

            # Downgrade E2E to sequential
            self.config.build.e2e_serial = True
            console.print("  [yellow]E2E tests downgraded to sequential mode.[/yellow]")
        else:
            console.print(
                f"  [green]Memory audit clean — {result.scanned_files} files scanned, no issues.[/green]"
            )

        return {
            "skipped": False,
            "findings": len(result.findings),
            "high": result.high_count,
            "medium": result.medium_count,
            "is_clean": result.is_clean,
            "scanned_files": result.scanned_files,
        }
```

- [ ] **Step 2: Register Phase 3.5 in the phase dispatch**

In the `_PHASE_METHODS` dict and the `PHASE_NAMES` dict in `src/utils.py`, we don't need to add 3.5 as a formal phase. Instead, call it directly from the `run()` method. After the phase 3 execution completes successfully, add the audit call. Find the section where phase results are stored and add after the phase loop body, a special case:

In the `run()` method, after the phase completes and before the `finally: await self._save_state()`, inside the `try` block, after `print_success(...)` and the cleanup code, add:

```python
                # Run memory audit after Phase 3 (before Phase 4)
                if phase_num == 3 and result is not None:
                    console.print()
                    console.print(
                        "[bold bright_magenta]  Phase 3.5: MEMORY AUDIT[/bold bright_magenta]"
                    )
                    audit_result = await self.phase3_5_audit()
                    self.state["phase3_5"] = audit_result
```

- [ ] **Step 3: Run full test suite**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/ -v --timeout=60`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
cd /Users/nrupal/dev/yensi/dev/nc-dev-system
git add src/pipeline.py
git commit -m "feat(pipeline): add Phase 3.5 memory audit before verification

Scans target project for browser leaks, unbounded caches, unsafe
gather calls, and missing Docker memory limits. Downgrades E2E
concurrency to sequential if issues found. Generates
MEMORY-SAFETY-REPORT.md in .nc-dev/."
```

---

## Task 7: Add memory limits to Docker Compose template

**Files:**
- Modify: `templates/greenfield/docker-compose.yml.j2`

- [ ] **Step 1: Update the template with memory limits**

Replace the content of `templates/greenfield/docker-compose.yml.j2`:

```yaml
services:
  frontend:
    build: ./frontend
    ports:
      - "23000:23000"
    deploy:
      resources:
        limits:
          memory: 2G

  backend:
    build: ./backend
    ports:
      - "23001:23001"
    deploy:
      resources:
        limits:
          memory: 4G
        reservations:
          memory: 512M

  mongodb:
    image: mongo:7
    ports:
      - "23002:27017"
    deploy:
      resources:
        limits:
          memory: 2G

  redis:
    image: redis:7-alpine
    command: redis-server --maxmemory 512mb --maxmemory-policy allkeys-lru
    ports:
      - "23003:6379"
    deploy:
      resources:
        limits:
          memory: 1G
```

- [ ] **Step 2: Run scaffolder tests**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/test_scaffolder/ -v`
Expected: All tests PASS (template tests may reference old content — fix if needed)

- [ ] **Step 3: Commit**

```bash
cd /Users/nrupal/dev/yensi/dev/nc-dev-system
git add templates/greenfield/docker-compose.yml.j2
git commit -m "feat(templates): add memory limits to Docker Compose template

All generated projects now have deploy.resources.limits.memory
on every service. Backend: 4G, Frontend: 2G, MongoDB: 2G,
Redis: 1G with maxmemory policy."
```

---

## Task 8: Run full test suite and verify

**Files:** None (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `cd /Users/nrupal/dev/yensi/dev/nc-dev-system && python -m pytest tests/ -v --timeout=60`
Expected: All tests PASS, no regressions

- [ ] **Step 2: Verify the auditor against Vantage**

Run a quick manual test to verify the auditor catches Vantage's issues:

```bash
cd /Users/nrupal/dev/yensi/dev/nc-dev-system
python -c "
from src.auditor import scan_project
result = scan_project('/Users/nrupal/dev/yensi/dev/vantage')
print(f'Clean: {result.is_clean}')
print(f'Findings: {len(result.findings)} ({result.high_count} high, {result.medium_count} medium)')
for f in result.findings[:10]:
    print(f'  [{f.severity}] {f.file}:{f.line} — {f.pattern}')
"
```

Expected: Should find multiple findings in Vantage (browser.launch, dict cache, docker-compose without limits)

- [ ] **Step 3: Final commit (if any fixes needed)**

```bash
cd /Users/nrupal/dev/yensi/dev/nc-dev-system
git status  # Check if anything needs committing
```

---

## Task 9: Use NC Dev System to fix Vantage

After all NC Dev System changes are implemented and tested, use the system's auditor to generate a report for Vantage, then implement the fixes documented in `/Users/nrupal/dev/yensi/dev/vantage/URGENT-MEMORY-LEAK-FIX.md`.

**Files:** (in Vantage project)
- Modify: `backend/app/scrapers/browser_pool.py` — fix cleanup, implement actual pooling
- Modify: `backend/app/scrapers/http_client.py` — cap request log and cache
- Modify: `backend/app/scrapers/worker.py` — limit cascading enrichment jobs
- Modify: `docker-compose.dev.yml` — add memory limits

- [ ] **Step 1: Run the auditor against Vantage and generate report**

```bash
cd /Users/nrupal/dev/yensi/dev/nc-dev-system
python -c "
from src.auditor import scan_project, generate_report
result = scan_project('/Users/nrupal/dev/yensi/dev/vantage')
generate_report(result, '/Users/nrupal/dev/yensi/dev/vantage/.nc-dev/MEMORY-SAFETY-REPORT.md')
print('Report generated.')
for f in result.findings:
    print(f'  [{f.severity}] {f.file}:{f.line} — {f.pattern}: {f.description}')
"
```

- [ ] **Step 2: Fix BrowserPool cleanup (P0)**

In `vantage/backend/app/scrapers/browser_pool.py`, replace the `finally` block in `_get_page()`:

```python
            try:
                yield page
            finally:
                try:
                    await context.close()
                except Exception:
                    pass
                try:
                    await browser.close()
                except Exception:
                    pass
```

- [ ] **Step 3: Cap _request_log in http_client.py (P3)**

In `vantage/backend/app/scrapers/http_client.py`, change line 103:

```python
    _request_log: list[dict[str, Any]] = field(default_factory=list)
```

to use a deque:

```python
from collections import deque
# ... in the class:
    _request_log: deque = field(default_factory=lambda: deque(maxlen=1000))
```

- [ ] **Step 4: Cap response cache in http_client.py (P4)**

Add a `max_cache_entries` field and enforce it in `_put_cache()`:

```python
    max_cache_entries: int = 500

    def _put_cache(self, key: str, response: httpx.Response) -> None:
        if not self.enable_cache:
            return
        # Evict oldest if at capacity
        if len(self._cache) >= self.max_cache_entries:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
        self._cache[key] = _CacheEntry(
            body=response.content,
            status_code=response.status_code,
            headers=dict(response.headers),
            created_at=time.monotonic(),
        )
```

- [ ] **Step 5: Limit cascading enrichment jobs in worker.py (P2)**

In `vantage/backend/app/scrapers/worker.py`, in the `_dispatch` method, limit enrichment:

```python
        # Queue contact enrichment jobs for each discovered contact (MAX 5)
        MAX_ENRICHMENT_PER_COMPANY = 5
        if contacts and companies:
            company = companies[0]
            for contact in contacts[:MAX_ENRICHMENT_PER_COMPANY]:
```

- [ ] **Step 6: Add memory limits to Vantage docker-compose.dev.yml**

Add deploy resource limits to backend, frontend, mongodb, redis, qdrant services.

- [ ] **Step 7: Run Vantage tests**

```bash
cd /Users/nrupal/dev/yensi/dev/vantage
python -m pytest backend/tests/ -v --timeout=60
```

- [ ] **Step 8: Commit Vantage fixes**

```bash
cd /Users/nrupal/dev/yensi/dev/vantage
git add -A
git commit -m "fix: memory leak fixes for browser pool, http client, and worker

P0: BrowserPool cleanup now fault-tolerant (independent try/except)
P2: Cascading enrichment jobs capped at 5 per company
P3: _request_log capped at 1000 entries (deque)
P4: Response cache capped at 500 entries with eviction
Docker: Memory limits added to all compose services

Fixes repeated kernel panics caused by unbounded memory growth
during scraper operations."
```
