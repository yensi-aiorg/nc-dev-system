"""Reproduction-first gate for Sentinel fixes.

Before any fix is attempted, the production failure must be
reproduced as a *failing test* in the cloned repo. A fix you can't
verify against a failing test is a guess -- so if reproduction fails,
the whole fix is halted with CANNOT_REPRODUCE.
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from ncdev.ai_session import run_ai_session
from ncdev.claude_session import DEFAULT_BUILD_TOOLS
from ncdev.core.config import NCDevConfig
from ncdev.core.models import SentinelFailureReport
from ncdev.core.sentinel_prompts import build_reproduction_prompt

_MAX_FILE_CHARS = 16_000
_TEST_TIMEOUT_SECONDS = 300


@dataclass
class ReproductionResult:
    reproduced: bool
    test_path: str = ""          # repo-relative path to the test the session wrote
    test_output: str = ""        # captured output of the failing run
    reason: str = ""             # human-readable explanation
    session_cost_usd: float = 0.0


def reproduce_failure(
    report: SentinelFailureReport,
    repo_dir: Path,
    *,
    config: NCDevConfig | None = None,
    model: str | None = None,
    timeout: int = 1800,
    max_budget_usd: float | None = None,
) -> ReproductionResult:
    """Author and verify a failing reproduction test for a Sentinel report."""
    repo_dir = repo_dir.resolve()
    context = _gather_repro_context(report, repo_dir)
    prompt = build_reproduction_prompt(report=report, **context)

    pre_session_files = _git_changed_files(repo_dir)
    from ncdev.core.capability_probe import scan_installed_skills
    from ncdev.core.capability_ledger import recent_lessons
    from ncdev.core.skill_selector import render_skill_block, select_skills

    # Bugfix sessions always use the "bugfix" work type -- they most need
    # systematic-debugging + reproduction skills.
    _skill_block = render_skill_block(
        select_skills(
            "bugfix",
            scan_installed_skills(repo_dir),
            lessons=recent_lessons(),
        )
    )

    session = run_ai_session(
        prompt,
        cwd=repo_dir,
        config=config,
        tools=DEFAULT_BUILD_TOOLS,
        model=model,
        timeout=timeout,
        max_budget_usd=max_budget_usd,
        append_system_prompt=_skill_block or None,
    )
    session_cost = float(session.total_cost_usd or 0.0)

    if not session.success:
        reason = session.error or session.final_text or "reproduction session failed"
        return ReproductionResult(
            reproduced=False,
            reason=reason,
            session_cost_usd=session_cost,
        )

    test_files = _detect_new_test_files(repo_dir, pre_session_files)
    if not test_files:
        return ReproductionResult(
            reproduced=False,
            reason="no new or changed test file was written by the reproduction session",
            session_cost_usd=session_cost,
        )

    passing: list[str] = []
    errors: list[str] = []
    for test_rel_path in test_files:
        passed, output = _run_test_file(repo_dir, test_rel_path)
        if not passed:
            if _looks_like_unrelated_test_error(output):
                return ReproductionResult(
                    reproduced=False,
                    test_path=test_rel_path,
                    test_output=output,
                    reason=f"test run failed for an unrelated runner/setup reason: {test_rel_path}",
                    session_cost_usd=session_cost,
                )
            return ReproductionResult(
                reproduced=True,
                test_path=test_rel_path,
                test_output=output,
                reason="reproduction test fails as required",
                session_cost_usd=session_cost,
            )
        if output:
            passing.append(f"{test_rel_path}: {output}")
        else:
            passing.append(test_rel_path)

    if passing:
        errors.append("all reproduction tests passed; no production failure was reproduced")
        errors.extend(passing)
    return ReproductionResult(
        reproduced=False,
        test_path=test_files[0],
        test_output="\n\n".join(passing),
        reason="\n".join(errors) or "reproduction test passed instead of failing",
        session_cost_usd=session_cost,
    )


def _gather_repro_context(report: SentinelFailureReport, repo_dir: Path) -> dict:
    error_file_contents = _read_repo_file(repo_dir, report.error.file)

    related_file_contents: dict[str, str] = {}
    for rel in report.context.related_files:
        related_file_contents[rel] = _read_repo_file(repo_dir, rel)

    return {
        "error_file_contents": error_file_contents,
        "related_file_contents": related_file_contents,
        "existing_test_contents": _existing_test_contents(report, repo_dir),
        "git_log": _git_log(repo_dir),
    }


def _detect_new_test_files(repo_dir: Path, pre_session_files: set[str]) -> list[str]:
    candidates = sorted(_git_changed_files(repo_dir) - pre_session_files)
    return [rel for rel in candidates if _looks_like_test_path(rel) and (repo_dir / rel).is_file()]


def _run_test_file(repo_dir: Path, test_rel_path: str) -> tuple[bool, str]:
    test_path = repo_dir / test_rel_path
    project_root, runner_cmd = _runner_for_test_file(repo_dir, test_path)
    if project_root is None or runner_cmd is None:
        return False, f"no supported test runner for {test_rel_path}"

    try:
        result = subprocess.run(
            runner_cmd,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=_TEST_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        output = "\n".join(part for part in (exc.stdout, exc.stderr) if part)
        return False, f"test timed out after {_TEST_TIMEOUT_SECONDS}s\n{output}".strip()
    except FileNotFoundError as exc:
        return False, f"test runner not found: {exc}"

    return result.returncode == 0, _combined_output(result.stdout, result.stderr)


def _read_repo_file(repo_dir: Path, rel_path: str | None) -> str:
    path = _safe_repo_path(repo_dir, rel_path)
    if path is None or not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:_MAX_FILE_CHARS]
    except OSError:
        return ""


def _existing_test_contents(report: SentinelFailureReport, repo_dir: Path) -> str:
    error_path = Path(report.error.file or "")
    stem = error_path.stem
    if not stem:
        return ""

    candidates = sorted(
        path
        for path in repo_dir.rglob("*")
        if path.is_file()
        and _looks_like_test_path(_rel(path, repo_dir))
        and (
            stem in path.stem
            or (path.parent.name == "tests" and path.suffix in {".py", ".js", ".jsx", ".ts", ".tsx"})
        )
    )

    parts: list[str] = []
    for path in candidates[:5]:
        rel = _rel(path, repo_dir)
        content = _read_repo_file(repo_dir, rel)
        if content:
            parts.append(f"### {rel}\n{content}")
    return "\n\n".join(parts)


def _git_log(repo_dir: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-20"],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""
    return result.stdout if result.returncode == 0 else ""


def _git_changed_files(repo_dir: Path) -> set[str]:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return set()
    if result.returncode != 0:
        return set()

    files: set[str] = set()
    entries = [entry for entry in result.stdout.split("\0") if entry]
    skip_next = False
    for entry in entries:
        if skip_next:
            skip_next = False
            continue
        status = entry[:2]
        path = entry[3:]
        if not path:
            continue
        files.add(path)
        if "R" in status or "C" in status:
            skip_next = True
    return files


def _runner_for_test_file(repo_dir: Path, test_path: Path) -> tuple[Path | None, list[str] | None]:
    try:
        from ncdev.pipeline.state_scanner import _runner_for_test

        return _runner_for_test(test_path, repo_dir)
    except Exception:  # noqa: BLE001
        return _local_runner_for_test(test_path, repo_dir)


def _local_runner_for_test(test_path: Path, repo_dir: Path) -> tuple[Path | None, list[str] | None]:
    suffix = test_path.suffix
    if suffix == ".py":
        return repo_dir, [_python_runner(), "-m", "pytest", "-q", "-x", str(test_path.relative_to(repo_dir))]
    if suffix in {".ts", ".tsx", ".js", ".jsx"}:
        rel = str(test_path.relative_to(repo_dir))
        if _looks_like_playwright_path(test_path):
            return repo_dir, ["npx", "playwright", "test", rel]
        return repo_dir, ["npx", "vitest", "run", rel]
    return None, None


def _looks_like_test_path(rel_path: str) -> bool:
    path = Path(rel_path)
    parts = {part.lower() for part in path.parts}
    name = path.name.lower()
    stem = path.stem.lower()
    return (
        "tests" in parts
        or "test" in parts
        or "e2e" in parts
        or name.startswith("test_")
        or stem.endswith("_test")
        or ".test." in name
        or ".spec." in name
    )


def _looks_like_playwright_path(test_path: Path) -> bool:
    parts = {part.lower() for part in test_path.parts}
    return "e2e" in parts


def _safe_repo_path(repo_dir: Path, rel_path: str | None) -> Path | None:
    if not rel_path:
        return None
    raw = Path(rel_path)
    if raw.is_absolute():
        candidate = raw.resolve()
    else:
        candidate = (repo_dir / raw).resolve()
    try:
        candidate.relative_to(repo_dir)
    except ValueError:
        return None
    return candidate


def _rel(path: Path, repo_dir: Path) -> str:
    try:
        return path.relative_to(repo_dir).as_posix()
    except ValueError:
        return path.as_posix()


def _python_runner() -> str:
    return sys.executable


def _combined_output(stdout: str, stderr: str) -> str:
    return "\n".join(part for part in (stdout.strip(), stderr.strip()) if part).strip()


def _looks_like_unrelated_test_error(output: str) -> bool:
    lower = output.lower()
    unrelated_markers = (
        "no supported test runner",
        "test runner not found",
        "test timed out",
        "no tests ran",
        "collected 0 items",
        "modulenotfounderror",
        "importerror",
        "syntaxerror",
        "configuration error",
    )
    return any(marker in lower for marker in unrelated_markers)
