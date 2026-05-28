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


_BANDIT_EXCLUDE_DIRS = (
    ".venv",
    "venv",
    "env",
    "node_modules",
    "tests",
    "test",
    ".tox",
    ".git",
    "build",
    "dist",
    "site-packages",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "migrations",
)


def _scanners_for(repo: Path) -> tuple[tuple[str, list[str], str], ...]:
    """SAST scanners applicable to ``repo`` — (name, argv, probe binary).

    bandit and semgrep scan the repo's own source, so they always
    apply. pip-audit audits *declared dependencies* — but with no
    target it audits the ambient environment (NC Dev's own venv, not
    the project). It is therefore included only when the repo ships a
    ``requirements.txt``, and pointed explicitly at that file.

    Bandit policy (set in this function):

    - ``--severity-level high`` — only block on findings bandit is
      reasonably confident describe a real security flaw (eval, exec,
      pickle.loads, SSL no-verify, etc.). Low / Medium severity
      findings (assert in tests, ``import subprocess``, hardcoded
      strings that look like passwords) are well-known sources of
      noise and would block every initial build.
    - ``--confidence-level low`` — keep low-confidence matches in
      scope so we don't miss legitimate-but-fuzzy detections at the
      High severity tier; ``--severity-level high`` is doing the
      filtering.
    - ``-x`` exclusions cover venvs, tests, caches, build artifacts,
      migrations. Tests in particular are noisy — ``assert`` (B101),
      ``random`` (B311), subprocess imports — none of which are
      production risks.
    - ``-f txt`` (no ``-q``) prints the per-finding detail so that
      when bandit DOES block, the repair session has the file +
      line + cwe to act on. The Gauntlet captures the tail of this
      output.

    Project teams that want a tighter gate can drop a ``bandit.yaml``
    or ``[tool.bandit]`` block into ``pyproject.toml``; bandit reads
    those automatically.
    """
    # bandit's -x matches each candidate path with fnmatch, so a bare
    # "./.venv" only excludes a TOP-LEVEL .venv — it misses nested
    # virtualenvs like backend/.venv (where pymongo/httpx live and trip
    # MD5/SHA1 findings). Emit glob patterns that match the directory at
    # any depth: both "*/<name>/*" (nested) and "./<name>" (top-level).
    _patterns: list[str] = []
    for name in _BANDIT_EXCLUDE_DIRS:
        _patterns.append(f"./{name}")
        _patterns.append(f"*/{name}/*")
        _patterns.append(f"*/{name}")
    excludes = ",".join(_patterns)
    scanners: list[tuple[str, list[str], str]] = [
        (
            "bandit",
            [
                "bandit",
                "-r",
                ".",
                "--severity-level",
                "high",
                "--confidence-level",
                "low",
                "-x",
                excludes,
                "-f",
                "txt",
            ],
            "bandit",
        ),
        ("semgrep", ["semgrep", "--error", "--quiet", "--config", "auto"], "semgrep"),
    ]
    if (repo / "requirements.txt").is_file():
        scanners.append((
            "pip-audit",
            ["pip-audit", "--progress-spinner", "off", "-r", "requirements.txt"],
            "pip-audit",
        ))
    return tuple(scanners)


def _which(binary: str) -> str | None:
    """Resolve a scanner binary to a runnable path, or None.

    Checks PATH first, then the directory of the current interpreter —
    pip-installed console scripts (bandit, pip-audit) land next to
    ``sys.executable`` and are missed by a bare PATH lookup when the
    venv is not activated.
    """
    import shutil
    import sys

    found = shutil.which(binary)
    if found:
        return found
    candidate = Path(sys.executable).parent / binary
    return str(candidate) if candidate.exists() else None


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

    # Resolve each applicable scanner to a runnable path; drop the
    # ones not installed.
    available: list[tuple[str, list[str]]] = []
    for name, argv, probe in _scanners_for(ctx.repo):
        resolved = _which(probe)
        if resolved:
            available.append((name, [resolved, *argv[1:]]))
    if not available:
        return GauntletLayerResult(
            layer="L6-security", status=LayerStatus.SKIPPED, blocking=False,
            summary="security: no SAST scanner installed — skipped",
            findings=["install bandit / pip-audit / semgrep to enable L6"],
        )

    findings: list[str] = []
    ran: list[str] = []
    for name, argv in available:
        ok, code, output = run_shell(" ".join(argv), cwd=ctx.repo, timeout=600)
        ran.append(name)
        if not ok:
            # Capture more output for security scanners (bandit prints
            # per-finding detail — file:line + Issue/CWE/Code snippet,
            # ~6-10 lines each) so repair sessions have actionable
            # context. 20 lines used to cut off after the metrics
            # block, hiding the actual findings.
            findings.append(f"{name}: reported issues (exit {code})\n{tail(output, 80)}")

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
