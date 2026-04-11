"""Tests for the memory safety auditor module."""
import pytest

from src.auditor import Finding, MemoryAuditResult, generate_report, scan_project


@pytest.mark.unit
def test_empty_directory_returns_clean(tmp_path):
    result = scan_project(tmp_path)
    assert result.is_clean
    assert result.scanned_files == 0


@pytest.mark.unit
def test_detects_browser_launch_in_loop(tmp_path):
    code = "async def run():\n    browser = await playwright.chromium.launch()\n"
    (tmp_path / "test_browser.py").write_text(code)
    result = scan_project(tmp_path)
    assert not result.is_clean
    assert result.high_count >= 1
    patterns = [f.pattern for f in result.findings]
    assert "browser.launch" in patterns


@pytest.mark.unit
def test_detects_unbounded_list_append_in_loop(tmp_path):
    code = "class Agent:\n    _log: list[str] = []\n\n    def run(self):\n        self._log.append('event')\n"
    (tmp_path / "agent.py").write_text(code)
    result = scan_project(tmp_path)
    assert not result.is_clean
    patterns = [f.pattern for f in result.findings]
    assert "unbounded list accumulator" in patterns


@pytest.mark.unit
def test_detects_dict_cache_without_maxsize(tmp_path):
    code = "class Store:\n    _cache: dict[str, bytes] = {}\n"
    (tmp_path / "store.py").write_text(code)
    result = scan_project(tmp_path)
    assert not result.is_clean
    patterns = [f.pattern for f in result.findings]
    assert "dict-based cache" in patterns


@pytest.mark.unit
def test_detects_gather_without_return_exceptions(tmp_path):
    code = "async def run(tasks):\n    results = await asyncio.gather(*tasks)\n"
    (tmp_path / "runner.py").write_text(code)
    result = scan_project(tmp_path)
    assert not result.is_clean
    patterns = [f.pattern for f in result.findings]
    assert "asyncio.gather-no-return-exceptions" in patterns


@pytest.mark.unit
def test_detects_docker_without_memory_limits(tmp_path):
    compose = (
        "version: '3.8'\n"
        "services:\n"
        "  api:\n"
        "    image: myapp:latest\n"
        "    ports:\n"
        "      - '8000:8000'\n"
    )
    (tmp_path / "docker-compose.dev.yml").write_text(compose)
    result = scan_project(tmp_path)
    assert not result.is_clean
    assert result.high_count >= 1
    patterns = [f.pattern for f in result.findings]
    assert "docker-no-memory-limits" in patterns


@pytest.mark.unit
def test_clean_project_returns_clean(tmp_path):
    code = (
        "from collections import deque\n\n"
        "class SafeAgent:\n"
        "    _log = deque(maxlen=1000)\n\n"
        "    def run(self):\n"
        "        self._log.append('event')\n"
    )
    (tmp_path / "safe_agent.py").write_text(code)
    result = scan_project(tmp_path)
    assert result.is_clean
    assert result.scanned_files == 1


@pytest.mark.unit
def test_generates_markdown_file(tmp_path):
    result = MemoryAuditResult(findings=[], scanned_files=5)
    output = generate_report(result, tmp_path / "reports" / "MEMORY-SAFETY-REPORT.md")
    assert output.exists()
    assert output.suffix == ".md"


@pytest.mark.unit
def test_report_includes_findings(tmp_path):
    findings = [
        Finding(
            file="/some/project/main.py",
            line=42,
            pattern="browser.launch",
            description="Playwright browser launched without explicit close",
            severity="high",
        ),
        Finding(
            file="/some/project/store.py",
            line=7,
            pattern="dict-based cache",
            description="Unbounded dict cache without maxsize",
            severity="medium",
        ),
    ]
    result = MemoryAuditResult(findings=findings, scanned_files=10)
    output = generate_report(result, tmp_path / "MEMORY-SAFETY-REPORT.md")
    content = output.read_text()
    assert "browser.launch" in content
    assert "dict-based cache" in content
    assert "HIGH" in content
    assert "MEDIUM" in content
    assert "Impact" in content
