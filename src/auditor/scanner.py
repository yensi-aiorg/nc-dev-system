"""Static analysis scanner for memory-leak patterns in target projects."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class Finding:
    file: str
    line: int
    pattern: str
    description: str
    severity: str  # "high" | "medium" | "low"


@dataclass
class MemoryAuditResult:
    findings: List[Finding] = field(default_factory=list)
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


# Compiled patterns for code files (.py, .js, .ts, .tsx, .jsx)
_CODE_PATTERNS: list[tuple[re.Pattern, str, str, str]] = [
    (
        re.compile(r"browser\.launch\(\)|chromium\.launch\(\)"),
        "browser.launch",
        "Playwright browser launched without explicit close — may leak browser processes",
        "high",
    ),
    (
        # gather(*tasks) at end of line with no return_exceptions keyword
        re.compile(r"asyncio\.gather\(\*\w+\)\s*$"),
        "asyncio.gather-no-return-exceptions",
        "asyncio.gather without return_exceptions=True — unhandled exceptions may abort gather and leave tasks running",
        "medium",
    ),
    (
        re.compile(r"asyncio\.gather\(\*\w+,\s*return_exceptions\s*=\s*False\)"),
        "asyncio.gather-return-exceptions-false",
        "asyncio.gather with return_exceptions=False — exceptions propagate and may leak pending tasks",
        "medium",
    ),
    (
        re.compile(r"_cache\s*:\s*dict\["),
        "dict-based cache",
        "Unbounded dict cache without maxsize — grows indefinitely under load",
        "medium",
    ),
    (
        re.compile(r"(_log|_history|_request_log)\s*:\s*list\["),
        "unbounded list accumulator",
        "Unbounded list accumulator — appends without eviction policy, leaks memory over time",
        "medium",
    ),
]

_SKIP_DIRS = {"node_modules", "__pycache__", ".git", ".venv", "venv"}
_CODE_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx"}


def _scan_code_file(path: Path) -> list[Finding]:
    findings: list[Finding] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings

    for lineno, line in enumerate(text.splitlines(), start=1):
        for pattern, name, description, severity in _CODE_PATTERNS:
            if pattern.search(line):
                findings.append(
                    Finding(
                        file=str(path),
                        line=lineno,
                        pattern=name,
                        description=description,
                        severity=severity,
                    )
                )
    return findings


def _scan_docker_compose_file(path: Path) -> list[Finding]:
    findings: list[Finding] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return findings

    if "services:" not in text:
        return findings

    if "mem_limit" not in text and "limits:" not in text:
        findings.append(
            Finding(
                file=str(path),
                line=1,
                pattern="docker-no-memory-limits",
                description="Docker Compose services defined without memory limits — containers may exhaust host RAM",
                severity="high",
            )
        )
    return findings


def scan_project(project_dir: str | Path) -> MemoryAuditResult:
    """Walk project_dir and check all relevant files for memory-leak patterns."""
    root = Path(project_dir)
    result = MemoryAuditResult()

    for path in root.rglob("*"):
        # Skip excluded directories
        if any(skip in path.parts for skip in _SKIP_DIRS):
            continue

        if not path.is_file():
            continue

        if path.suffix in _CODE_EXTENSIONS:
            result.scanned_files += 1
            result.findings.extend(_scan_code_file(path))
        elif path.name.startswith("docker-compose") and path.suffix in {".yml", ".yaml"}:
            result.scanned_files += 1
            result.findings.extend(_scan_docker_compose_file(path))

    return result
