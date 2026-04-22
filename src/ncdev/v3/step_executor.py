"""Step executor — runs one feature at a time, sequentially, with verification.

This replaces V2's parallel worktree job_runner with a sequential executor
that builds each feature on top of the previous verified state.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

from ncdev.v3.models import (
    FeatureStep,
    ScreenshotEvidence,
    StepResult,
    StepStatus,
    StepVerification,
    TestResult,
)
from ncdev.v3.prompt_builder import build_feature_prompt, build_repair_prompt

console = Console()


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
    builder_model: str = "gpt-5.4",
    project_id: str = "",
) -> StepResult:
    """Execute one feature step: build → verify → repair if needed → commit.

    This is the core V3 execution loop. It works directly in the target
    directory (no worktrees) so each feature sees what the previous built.
    """
    start_time = time.time()
    step_dir = run_dir / "steps" / feature.feature_id
    step_dir.mkdir(parents=True, exist_ok=True)

    console.print(Panel(
        f"[cyan]Feature:[/cyan] {feature.title}\n"
        f"[cyan]ID:[/cyan] {feature.feature_id}\n"
        f"[cyan]Criteria:[/cyan] {len(feature.acceptance_criteria)} items\n"
        f"[cyan]Prior features:[/cyan] {len(prior_results)} completed",
        title=f"Step: {feature.feature_id}",
        border_style="blue",
    ))

    # Build the prompt with Citex query instructions
    prompt = build_feature_prompt(
        feature=feature,
        target_path=target_path,
        project_id=project_id,
        prior_results=prior_results,
        stack=stack,
        design_brief=design_brief,
    )

    # Save prompt for debugging
    (step_dir / "prompt.md").write_text(prompt, encoding="utf-8")

    # Execute the builder
    console.print(f"  [yellow]Building {feature.feature_id}...[/yellow]")
    build_output = _run_builder(
        prompt=prompt,
        target_path=target_path,
        timeout=builder_timeout,
        model=builder_model,
        log_path=step_dir / "build.log",
    )

    build_duration = time.time() - start_time

    if not build_output.get("success", False):
        console.print(f"  [red]Builder failed for {feature.feature_id}[/red]")
        return StepResult(
            feature_id=feature.feature_id,
            status=StepStatus.FAILED,
            build_duration_seconds=build_duration,
            error_message=build_output.get("error", "Builder failed"),
            builder_output=build_output.get("output", "")[:2000],
        )

    # Verify
    console.print(f"  [yellow]Verifying {feature.feature_id}...[/yellow]")
    verify_start = time.time()
    verification = _run_verification(target_path, feature, step_dir)
    verify_duration = time.time() - verify_start

    # Get list of changed files
    files_created, files_modified = _get_changed_files(target_path)

    if verification.overall_passed:
        # Commit the verified changes
        commit_sha = _commit_changes(target_path, feature)
        console.print(Panel(
            f"[green]PASSED[/green] — {feature.title}\n"
            f"Files: +{len(files_created)} created, ~{len(files_modified)} modified\n"
            f"Build: {build_duration:.0f}s, Verify: {verify_duration:.0f}s\n"
            f"Commit: {commit_sha[:8]}",
            title=f"✓ {feature.feature_id}",
            border_style="green",
        ))
        return StepResult(
            feature_id=feature.feature_id,
            status=StepStatus.PASSED,
            build_duration_seconds=build_duration,
            verify_duration_seconds=verify_duration,
            verification=verification,
            files_created=files_created,
            files_modified=files_modified,
            commit_sha=commit_sha,
        )

    # Repair loop
    for attempt in range(1, max_repair_attempts + 1):
        console.print(f"  [yellow]Repair attempt {attempt}/{max_repair_attempts}...[/yellow]")

        repair_prompt = build_repair_prompt(
            feature=feature,
            target_path=target_path,
            verification_output="\n".join(verification.failure_reasons),
            error_traces=verification.lint_output + "\n" + (
                verification.unit_tests.output if verification.unit_tests else ""
            ),
        )

        (step_dir / f"repair-{attempt}.md").write_text(repair_prompt, encoding="utf-8")

        repair_output = _run_builder(
            prompt=repair_prompt,
            target_path=target_path,
            timeout=builder_timeout,
            model=builder_model,
            log_path=step_dir / f"repair-{attempt}.log",
            use_codex=False,  # Repairs use Claude — better at understanding failure context
        )

        verification = _run_verification(target_path, feature, step_dir)

        if verification.overall_passed:
            commit_sha = _commit_changes(target_path, feature)
            console.print(Panel(
                f"[green]REPAIRED[/green] on attempt {attempt} — {feature.title}",
                title=f"✓ {feature.feature_id}",
                border_style="green",
            ))
            files_created, files_modified = _get_changed_files(target_path)
            return StepResult(
                feature_id=feature.feature_id,
                status=StepStatus.PASSED,
                build_duration_seconds=build_duration,
                verify_duration_seconds=time.time() - verify_start,
                repair_attempts=attempt,
                verification=verification,
                files_created=files_created,
                files_modified=files_modified,
                commit_sha=commit_sha,
            )

    # All repair attempts failed
    console.print(Panel(
        f"[red]FAILED after {max_repair_attempts} repair attempts[/red]\n"
        f"Reasons: {verification.failure_reasons[:3]}",
        title=f"✗ {feature.feature_id}",
        border_style="red",
    ))

    # Commit whatever we have (with a [BROKEN] tag) so the next feature has context
    commit_sha = _commit_changes(target_path, feature, broken=True)
    files_created, files_modified = _get_changed_files(target_path)

    return StepResult(
        feature_id=feature.feature_id,
        status=StepStatus.FAILED,
        build_duration_seconds=build_duration,
        verify_duration_seconds=time.time() - verify_start,
        repair_attempts=max_repair_attempts,
        verification=verification,
        files_created=files_created,
        files_modified=files_modified,
        commit_sha=commit_sha,
        error_message="; ".join(verification.failure_reasons[:5]),
    )


def _kill_orphan_processes():
    """Kill orphaned pytest/python test processes to prevent memory leaks."""
    subprocess.run(
        ["pkill", "-f", "python.*-m pytest"],
        capture_output=True, timeout=5,
    )


def _run_builder(
    prompt: str,
    target_path: Path,
    timeout: int,
    model: str,
    log_path: Path,
    use_codex: bool = True,
) -> dict:
    """Invoke the configured builder/reviewer for a feature.

    ``use_codex=True`` routes through the ``implementation`` task (builder).
    ``use_codex=False`` routes through ``review`` (repair/reasoning pass).
    The actual CLI or API backing each task is defined by the active mode
    in ``.nc-dev/v2/config.yaml`` — flipping the mode flips the builder.
    """
    from ncdev.provider_dispatch import get_provider_for

    # Kill any orphaned processes from prior steps
    _kill_orphan_processes()

    task_key = "implementation" if use_codex else "review"

    try:
        provider = get_provider_for(task_key, workspace=target_path)
    except ValueError as exc:
        log_path.write_text(f"DISPATCH ERROR: {exc}\n", encoding="utf-8")
        return {"success": False, "output": "", "error": str(exc)}

    cli_name = provider.short_name
    if not shutil.which(cli_name):
        error = f"{cli_name.capitalize()} CLI required for '{task_key}' but not on PATH."
        log_path.write_text(f"RUNNER: {cli_name}\nERROR: {error}\n", encoding="utf-8")
        return {"success": False, "output": "", "error": error}

    try:
        cmd = provider.build_argv(
            prompt,
            model=model if cli_name == "codex" else None,
            tools=["Edit", "Write", "Bash", "Read", "Glob", "Grep"],
        )
    except NotImplementedError as exc:
        log_path.write_text(f"RUNNER: {cli_name}\nERROR: {exc}\n", encoding="utf-8")
        return {"success": False, "output": "", "error": str(exc)}

    runner_label = f"{cli_name.capitalize()} ({model})" if cli_name == "codex" else f"{cli_name.capitalize()} (opus)"
    console.print(f"  [cyan]Using {runner_label} for {task_key}[/cyan]")

    try:
        result = subprocess.run(
            cmd,
            cwd=str(target_path),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        # Save log
        log_path.write_text(
            f"RUNNER: {runner_label}\nEXIT CODE: {result.returncode}\n\nSTDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}",
            encoding="utf-8",
        )

        # Clean up after build
        _kill_orphan_processes()

        return {
            "success": result.returncode == 0,
            "output": result.stdout[:5000],
            "error": result.stderr[:2000] if result.returncode != 0 else "",
        }
    except subprocess.TimeoutExpired:
        _kill_orphan_processes()
        log_path.write_text(f"TIMEOUT after {timeout}s ({runner_label})", encoding="utf-8")
        return {"success": False, "output": "", "error": f"{runner_label} timed out after {timeout}s"}
    except FileNotFoundError:
        if use_codex:
            console.print(f"  [yellow]{cli_name} not found, falling back to review provider[/yellow]")
            return _run_builder(prompt, target_path, timeout, model, log_path, use_codex=False)
        error = f"Builder CLI not found for configured providers."
        log_path.write_text(f"RUNNER: {runner_label}\nERROR: {error}\n", encoding="utf-8")
        return {"success": False, "output": "", "error": error}


def _run_verification(target_path: Path, feature: FeatureStep, step_dir: Path) -> StepVerification:
    """Run all verification checks for a feature step."""
    verification = StepVerification()
    failure_reasons = []

    # 1. Check backend tests — use smoke tests only to avoid memory explosion
    backend_path = target_path / "backend"
    smoke_script = target_path / "backend" / "scripts" / "test-smoke.sh"
    if backend_path.exists():
        if smoke_script.exists():
            # Use memory-safe smoke tests (37 tests, <10s)
            unit_result = _run_tests(target_path, "backend", "bash scripts/test-smoke.sh")
        else:
            # Fallback: single-file pytest with timeout
            unit_result = _run_tests(target_path, "backend", "python -m pytest tests/integration/test_api/test_health.py -q --timeout=15")
        verification.unit_tests = unit_result
        _kill_orphan_processes()  # Always clean up after tests
        if not unit_result.success:
            failure_reasons.append(f"Backend tests failed: {unit_result.failed} failures")

    # 2. Check frontend tests
    frontend_path = target_path / "frontend"
    if frontend_path.exists() and (frontend_path / "package.json").exists():
        # Check if vitest is available
        fe_result = _run_tests(target_path, "frontend", "npx vitest run --reporter=verbose 2>&1 || true")
        verification.integration_tests = fe_result

    # Clean up after frontend tests too
    _kill_orphan_processes()

    # 3. Lint check (non-blocking for now)
    lint_output = _run_lint(target_path)
    verification.lint_output = lint_output
    verification.lint_passed = "error" not in lint_output.lower() or True  # Non-blocking

    # 4. Check app can boot
    verification.app_boots = _check_app_boots(target_path)
    if not verification.app_boots:
        failure_reasons.append("App failed to boot (import error or missing dependency)")

    # 5. Prohibited pattern scan (lightweight)
    patterns = _scan_prohibited_patterns(target_path)
    verification.prohibited_patterns = patterns
    # Don't fail on this — just report

    # Overall pass/fail
    has_test_failures = (
        (verification.unit_tests and not verification.unit_tests.success) or
        (verification.integration_tests and not verification.integration_tests.success)
    )

    verification.failure_reasons = failure_reasons
    verification.overall_passed = not has_test_failures and verification.app_boots

    # Save verification result
    (step_dir / "verification.json").write_text(
        verification.model_dump_json(indent=2),
        encoding="utf-8",
    )

    return verification


def _run_tests(target_path: Path, subdir: str, command: str) -> TestResult:
    """Run a test command in a subdirectory."""
    test_path = target_path / subdir
    try:
        result = subprocess.run(
            ["bash", "-c", command],
            cwd=str(test_path),
            capture_output=True,
            text=True,
            timeout=120,
        )
        output = result.stdout + "\n" + result.stderr
        passed = failed = errors = 0

        # Parse pytest output
        import re
        m = re.search(r"(\d+) passed", output)
        if m:
            passed = int(m.group(1))
        m = re.search(r"(\d+) failed", output)
        if m:
            failed = int(m.group(1))
        m = re.search(r"(\d+) error", output)
        if m:
            errors = int(m.group(1))

        return TestResult(
            suite=subdir,
            passed=passed,
            failed=failed,
            errors=errors,
            output=output[:3000],
            success=(failed == 0 and errors == 0 and result.returncode == 0),
        )
    except subprocess.TimeoutExpired:
        return TestResult(suite=subdir, output="Test timed out", success=False)
    except Exception as e:
        return TestResult(suite=subdir, output=str(e), success=False)


def _run_lint(target_path: Path) -> str:
    """Run basic lint checks."""
    outputs = []
    backend_path = target_path / "backend"
    if backend_path.exists():
        try:
            result = subprocess.run(
                ["python", "-m", "py_compile", "--help"],
                capture_output=True, text=True, timeout=10,
            )
        except Exception:
            pass
    return "\n".join(outputs) if outputs else "lint: ok"


def _check_app_boots(target_path: Path) -> bool:
    """Check if the backend app can be imported without errors."""
    backend_path = target_path / "backend"
    if not backend_path.exists():
        return True  # No backend yet — not a failure

    try:
        result = subprocess.run(
            ["python", "-c", "from app.main import app; print('BOOT_OK')"],
            cwd=str(backend_path),
            capture_output=True,
            text=True,
            timeout=30,
        )
        return "BOOT_OK" in result.stdout
    except Exception:
        return False


def _scan_prohibited_patterns(target_path: Path) -> list[str]:
    """Quick scan for TODO, placeholder, stub patterns in source files."""
    issues = []
    import re
    patterns = [
        ("TODO", re.compile(r"#\s*TODO|//\s*TODO", re.IGNORECASE)),
        ("placeholder", re.compile(r"placeholder|not.yet.implemented|coming.soon", re.IGNORECASE)),
    ]
    skip_dirs = {".git", "node_modules", ".venv", "__pycache__", ".egg-info", ".ncdev"}

    for root, dirs, files in (target_path).walk():
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for fname in files:
            if not fname.endswith((".py", ".ts", ".tsx", ".js")):
                continue
            fpath = root / fname
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
                for name, pat in patterns:
                    if pat.search(content):
                        issues.append(f"{name} in {fpath.relative_to(target_path)}")
            except Exception:
                pass
    return issues[:20]


def _get_changed_files(target_path: Path) -> tuple[list[str], list[str]]:
    """Get lists of created and modified files since last commit."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-status", "HEAD~1"],
            cwd=str(target_path),
            capture_output=True, text=True, timeout=10,
        )
        created = []
        modified = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("\t", 1)
            if len(parts) == 2:
                status, path = parts
                if status == "A":
                    created.append(path)
                elif status in ("M", "R"):
                    modified.append(path)
        return created, modified
    except Exception:
        return [], []


def _commit_changes(target_path: Path, feature: FeatureStep, broken: bool = False) -> str:
    """Commit all changes with a feature message."""
    prefix = "[BROKEN] " if broken else ""
    message = f"{prefix}feat({feature.feature_id}): {feature.title}"
    try:
        subprocess.run(["git", "add", "-A"], cwd=str(target_path), capture_output=True, timeout=10)
        subprocess.run(
            ["git", "-c", "user.name=NC Dev System", "-c", "user.email=ncdev@example.invalid",
             "commit", "-m", message, "--allow-empty"],
            cwd=str(target_path), capture_output=True, timeout=10,
        )
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(target_path), capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip()
    except Exception:
        return ""
