"""Report generator for memory audit results."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .scanner import MemoryAuditResult


def generate_report(result: MemoryAuditResult, output_path: str | Path) -> Path:
    """Write a markdown memory-safety report to output_path and return it as a Path."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines: list[str] = [
        "# Memory Safety Audit Report",
        "",
        f"**Date:** {now}  ",
        f"**Files scanned:** {result.scanned_files}  ",
        f"**Status:** {'CLEAN' if result.is_clean else 'ISSUES FOUND'}  ",
        "",
    ]

    if result.is_clean:
        lines += [
            "## Result",
            "",
            "No memory-leak patterns detected. The project passed all checks.",
            "",
        ]
    else:
        lines += [
            "## Findings",
            "",
            f"| Severity | File | Line | Pattern | Description |",
            f"|----------|------|------|---------|-------------|",
        ]
        for f in sorted(result.findings, key=lambda x: (x.severity != "high", x.file, x.line)):
            short_file = Path(f.file).name
            lines.append(
                f"| {f.severity.upper()} | `{short_file}` | {f.line} | `{f.pattern}` | {f.description} |"
            )

        lines += [
            "",
            "## Impact",
            "",
            "Memory leaks in target projects can cause the host machine to run out of RAM during "
            "E2E test execution. Address **HIGH** severity findings before running automated tests. "
            "**MEDIUM** severity findings should be reviewed and fixed before production deployment.",
            "",
            f"**High severity:** {result.high_count}  ",
            f"**Medium severity:** {result.medium_count}  ",
            "",
        ]

    output.write_text("\n".join(lines), encoding="utf-8")
    return output
