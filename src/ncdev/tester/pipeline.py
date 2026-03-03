from __future__ import annotations

import subprocess
from pathlib import Path

from ncdev.models import TestResultDoc
from ncdev.utils import write_text


def _run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, check=False)
    out = (proc.stdout or "").strip() or (proc.stderr or "").strip()
    return proc.returncode, out


def run_test_pipeline(project_path: Path, dry_run: bool) -> TestResultDoc:
    commands = [
        "pytest -q",
        "npm run test",
        "npx playwright test",
    ]

    if dry_run:
        screenshots_dir = project_path / "test-results" / "screenshots"
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        desktop = screenshots_dir / "home-desktop-initial.png"
        mobile = screenshots_dir / "home-mobile-initial.png"
        write_text(desktop, "dry-run screenshot placeholder")
        write_text(mobile, "dry-run screenshot placeholder")
        return TestResultDoc(
            project_path=str(project_path),
            commands=commands,
            passed=True,
            failures=[],
            screenshots=[str(desktop), str(mobile)],
        )

    failures: list[str] = []

    rc, out = _run(["pytest", "-q"], project_path)
    if rc != 0:
        failures.append(f"pytest failed: {out[:300]}")

    if (project_path / "frontend" / "package.json").exists():
        rc, out = _run(["npm", "run", "test"], project_path / "frontend")
        if rc != 0:
            failures.append(f"frontend tests failed: {out[:300]}")

        rc, out = _run(["npx", "playwright", "test"], project_path / "frontend")
        if rc != 0:
            failures.append(f"playwright failed: {out[:300]}")

    return TestResultDoc(
        project_path=str(project_path),
        commands=commands,
        passed=len(failures) == 0,
        failures=failures,
        screenshots=[],
    )
