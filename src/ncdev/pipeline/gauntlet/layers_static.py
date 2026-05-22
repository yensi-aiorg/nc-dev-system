"""Static, deterministic gauntlet layers: L6 security, L7 anti-bypass.

Neither layer needs an AI call or a running app — they read the
feature's diff and the repo's dependency manifests. Both are precise
by design: a verification layer that cries wolf gets ignored.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from ncdev.pipeline.gauntlet.context import GauntletContext, run_shell, tail
from ncdev.pipeline.gauntlet.models import GauntletLayerResult, LayerStatus

# --- diff parsing ----------------------------------------------------------

_DIFF_FILE_HEADER = re.compile(r"^\+\+\+ b/(.+)$")

_TEST_PATH_MARKERS = ("test_", "_test.", "/test", "/tests/", ".test.", ".spec.", "conftest")


def _is_test_path(path: str) -> bool:
    low = path.lower()
    return any(marker in low for marker in _TEST_PATH_MARKERS)


def _added_lines_by_file(diff: str) -> dict[str, list[str]]:
    """Map each file in a unified diff to the lines it ADDED.

    Only ``+`` lines (not the ``+++`` header) count as added.
    """
    by_file: dict[str, list[str]] = {}
    current: str | None = None
    for line in diff.splitlines():
        header = _DIFF_FILE_HEADER.match(line)
        if header:
            current = header.group(1)
            by_file.setdefault(current, [])
            continue
        if current and line.startswith("+") and not line.startswith("+++"):
            by_file[current].append(line[1:])
    return by_file


# --- L7 anti-bypass --------------------------------------------------------

# High-precision markers of a bypassed integration. Each almost never
# appears in legitimate *production* (non-test) code. Test code may
# legitimately mock, so test files are excluded before scanning.
_BYPASS_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("NotImplementedError", re.compile(r"\braise\s+NotImplementedError")),
    ("stub comment", re.compile(r"#\s*(stub|placeholder|not\s*implemented|bypass|fake\s*impl|hack\b)", re.I)),
    ("mock in production code", re.compile(r"\b(unittest\.mock|MagicMock|from\s+mock\s+import)\b")),
    ("hardcoded TODO/FIXME", re.compile(r"#\s*(TODO|FIXME)\b")),
    ("JS not-implemented throw", re.compile(r"throw\s+new\s+Error\(\s*['\"](not implemented|TODO)", re.I)),
)


def layer_anti_bypass(ctx: GauntletContext) -> GauntletLayerResult:
    """L7 — detect a stubbed / mocked / bypassed integration.

    The dominant failure mode of autonomous coders (Replit's own
    confession): the agent makes the tests green by faking the
    integration it was told to build. This layer scans the feature's
    diff — production files only — for high-precision bypass markers.
    """
    start = time.time()

    if not ctx.diff.strip():
        return GauntletLayerResult(
            layer="L7-anti-bypass", status=LayerStatus.SKIPPED, blocking=False,
            summary="anti-bypass: no diff provided — skipped",
        )

    findings: list[str] = []
    for path, added in _added_lines_by_file(ctx.diff).items():
        if _is_test_path(path):
            continue
        for lineno, text in enumerate(added, start=1):
            for label, pattern in _BYPASS_PATTERNS:
                if pattern.search(text):
                    findings.append(f"{path}: {label} — `{text.strip()[:80]}`")

    duration = time.time() - start
    if findings:
        return GauntletLayerResult(
            layer="L7-anti-bypass", status=LayerStatus.FAILED, blocking=True,
            summary=(
                f"anti-bypass: {len(findings)} bypassed-integration "
                "marker(s) in production code"
            ),
            detail="\n".join(findings[:25]),
            duration_seconds=duration,
            findings=findings,
        )
    return GauntletLayerResult(
        layer="L7-anti-bypass", status=LayerStatus.PASSED, blocking=True,
        summary="anti-bypass: no stubbed/mocked integrations in production code",
        duration_seconds=duration,
    )


# --- L6 security -----------------------------------------------------------

# Each scanner: (name, argv, "available?" probe binary). A scanner whose
# binary is absent is skipped, not failed — absence is not a vuln.
_SAST_SCANNERS: tuple[tuple[str, list[str], str], ...] = (
    ("bandit", ["bandit", "-r", ".", "-ll", "-q"], "bandit"),
    ("pip-audit", ["pip-audit", "--progress-spinner", "off"], "pip-audit"),
    ("semgrep", ["semgrep", "--error", "--quiet", "--config", "auto"], "semgrep"),
)


def _which(binary: str) -> bool:
    import shutil

    return shutil.which(binary) is not None


def layer_security(ctx: GauntletContext) -> GauntletLayerResult:
    """L6 — multi-tool SAST + dependency-existence scan.

    Runs whichever of bandit / pip-audit / semgrep are installed. A
    confirmed finding from any scanner is a blocking failure (research:
    a single scanner misses ~78% of vulns — breadth matters). If no
    scanner is installed the layer is SKIPPED with a loud finding
    rather than silently passing.
    """
    start = time.time()

    if not ctx.run_commands:
        return GauntletLayerResult(
            layer="L6-security", status=LayerStatus.SKIPPED, blocking=False,
            summary="security: command execution disabled — skipped",
        )

    available = [s for s in _SAST_SCANNERS if _which(s[2])]
    if not available:
        return GauntletLayerResult(
            layer="L6-security", status=LayerStatus.SKIPPED, blocking=False,
            summary="security: no SAST scanner installed — skipped",
            findings=["install bandit / pip-audit / semgrep to enable L6"],
        )

    findings: list[str] = []
    ran: list[str] = []
    for name, argv, _ in available:
        ok, code, output = run_shell(" ".join(argv), cwd=ctx.repo, timeout=600)
        ran.append(name)
        if not ok:
            findings.append(f"{name}: reported issues (exit {code})\n{tail(output, 20)}")

    duration = time.time() - start
    if findings:
        return GauntletLayerResult(
            layer="L6-security", status=LayerStatus.FAILED, blocking=True,
            summary=f"security: {len(findings)} of {len(ran)} scanner(s) flagged issues",
            detail="\n\n".join(findings),
            duration_seconds=duration,
            findings=findings,
        )
    return GauntletLayerResult(
        layer="L6-security", status=LayerStatus.PASSED, blocking=True,
        summary=f"security: clean across {len(ran)} scanner(s) ({', '.join(ran)})",
        duration_seconds=duration,
    )
