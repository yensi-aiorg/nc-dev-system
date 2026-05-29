# src/ncdev/pipeline/grounded_verify/evidence.py
"""Deterministic evidence gathering. Executes, observes, records facts.

Makes NO pass/fail decision — that is the judge's job. This guarantees
the basics were actually run so the agent cannot skip them.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ncdev.pipeline.claude_executor import _run_shell
from ncdev.pipeline.grounded_verify.models import EvidenceBundle, EvidenceItem

_DEP_MARKERS = (".venv/", "venv/", "node_modules/", "site-packages/", "/dist/", "/build/")


def _scoped_bandit_targets(changed_files: list[str]) -> list[str]:
    """Python files in the diff, excluding vendored dependencies."""
    return [
        f for f in changed_files
        if f.endswith(".py") and not any(m in f for m in _DEP_MARKERS)
    ]


def _exit_from_ok(ok: bool) -> int:
    return 0 if ok else 1


def gather_evidence(
    target_path: Path,
    *,
    backend_test_cmd: str | None,
    frontend_test_cmd: str | None,
    changed_files: list[str],
    diff: str,
    screenshots: list[str],
    timeout: int = 600,
) -> EvidenceBundle:
    items: list[EvidenceItem] = []

    if backend_test_cmd:
        ok, out = _run_shell(backend_test_cmd, cwd=target_path, timeout=timeout)
        items.append(EvidenceItem(name="backend-tests", command=backend_test_cmd,
                                  exit_code=_exit_from_ok(ok), output_tail=out[-2000:],
                                  scope="feature-tests"))
    if frontend_test_cmd:
        ok, out = _run_shell(frontend_test_cmd, cwd=target_path, timeout=timeout)
        items.append(EvidenceItem(name="frontend-tests", command=frontend_test_cmd,
                                  exit_code=_exit_from_ok(ok), output_tail=out[-2000:],
                                  scope="feature-tests"))

    targets = _scoped_bandit_targets(changed_files)
    if targets and shutil.which("bandit"):
        proc = subprocess.run(
            ["bandit", "-q", "--severity-level", "high", *targets],
            cwd=str(target_path), capture_output=True, text=True, timeout=120,
        )
        items.append(EvidenceItem(name="security-scan",
                                  command=f"bandit (diff-scoped: {len(targets)} files)",
                                  exit_code=proc.returncode,
                                  output_tail=(proc.stdout + proc.stderr)[-2000:],
                                  scope="diff"))

    return EvidenceBundle(items=items, diff=diff[-8000:],
                          changed_files=list(changed_files),
                          screenshots=list(screenshots))
