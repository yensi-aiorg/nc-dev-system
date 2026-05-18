"""Deploy a verified Sentinel fix to staging.

Auto-merge-to-staging posture: a fix that passed local verification
is pushed as a branch, opened as a PR, merged into the service's
staging branch, and the staging deploy command is run. Promotion
from staging to production stays a human action - NC Dev never
writes to prod.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ncdev.core.config import SentinelServiceConfig, validate_service_for_deploy
from ncdev.core.models import SentinelFailureReport


@dataclass
class DeployResult:
    ok: bool
    pr_url: str = ""
    fix_branch: str = ""
    merged: bool = False
    deployed: bool = False
    staging_sha_before: str = ""
    staging_sha_after: str = ""
    error: str = ""
    steps: list[str] = field(default_factory=list)


def _run_git(
    args: list[str],
    *,
    cwd: Path,
    timeout: int = 60,
) -> tuple[int, str, str]:
    """Run a git command and return returncode/stdout/stderr."""
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return 124, exc.stdout or "", exc.stderr or f"git timed out after {timeout}s"
    return completed.returncode, completed.stdout, completed.stderr


def _run_gh(
    args: list[str],
    *,
    cwd: Path,
    timeout: int = 120,
) -> tuple[int, str, str]:
    """Run a gh CLI command and return returncode/stdout/stderr."""
    try:
        completed = subprocess.run(
            ["gh", *args],
            cwd=cwd,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return 124, exc.stdout or "", exc.stderr or f"gh timed out after {timeout}s"
    return completed.returncode, completed.stdout, completed.stderr


def _run_deploy_command(command: str, cwd: Path) -> tuple[int, str, str]:
    """Run the configured staging deploy command."""
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            shell=True,
            capture_output=True,
            check=False,
            text=True,
            timeout=600,
        )
    except subprocess.TimeoutExpired as exc:
        return 124, exc.stdout or "", exc.stderr or "deploy command timed out after 600s"
    return completed.returncode, completed.stdout, completed.stderr


def build_pr_body(report: SentinelFailureReport, commit_sha: str = "") -> str:
    """Generate a PR description from the failure report."""
    location = report.error.file or "unknown"
    if report.error.line is not None:
        location = f"{location}:{report.error.line}"

    lines = [
        "## Sentinel Fix",
        "",
        "This PR was opened autonomously by NC Dev Sentinel-fix and "
        "auto-merged to staging for human promotion to production.",
        "",
        "## Failure Report",
        "",
        f"- Report ID: {report.report_id}",
        f"- Service: {report.service.name}",
        f"- Severity: {report.severity.value}",
        f"- Source: {report.source.value}",
        f"- Error type: {report.error.error_type}",
        f"- Error code: {report.error.error_code}",
        f"- Message: {report.error.message}",
        f"- Location: {location}",
    ]
    if commit_sha:
        lines.append(f"- Fix commit: {commit_sha}")
    return "\n".join(lines)


def open_and_merge_to_staging(
    repo_dir: Path,
    svc: SentinelServiceConfig,
    report: SentinelFailureReport,
    fix_branch: str,
    *,
    commit_sha: str = "",
) -> DeployResult:
    """Push the fix branch, open a PR, merge it into staging, and deploy."""
    result = DeployResult(ok=False, fix_branch=fix_branch)
    violations = validate_service_for_deploy(svc)
    if violations:
        result.error = "; ".join(violations)
        return result

    remote = svc.git_remote.strip() or "origin"
    staging_remote_ref = f"{remote}/{svc.staging_branch}"

    result.steps.append(f"push fix branch {fix_branch} to {remote}")
    code, _out, err = _run_git(
        ["push", remote, f"{fix_branch}:{fix_branch}"],
        cwd=repo_dir,
        timeout=120,
    )
    if code != 0:
        result.error = f"git push failed: {err.strip() or f'exit {code}'}"
        return result

    result.steps.append(f"fetch staging branch {svc.staging_branch}")
    code, _out, err = _run_git(
        ["fetch", remote, svc.staging_branch],
        cwd=repo_dir,
        timeout=120,
    )
    if code != 0:
        result.error = f"git fetch staging failed: {err.strip() or f'exit {code}'}"
        return result

    result.steps.append(f"record staging HEAD before merge ({staging_remote_ref})")
    code, out, err = _run_git(
        ["rev-parse", staging_remote_ref],
        cwd=repo_dir,
        timeout=60,
    )
    if code != 0:
        result.error = f"git rev-parse before merge failed: {err.strip() or f'exit {code}'}"
        return result
    result.staging_sha_before = out.strip()

    pr_title = _build_pr_title(report.error.message)
    pr_body = build_pr_body(report, commit_sha=commit_sha)
    pr_args = [
        "pr",
        "create",
        "--base",
        svc.staging_branch,
        "--head",
        fix_branch,
        "--title",
        pr_title,
        "--body",
        pr_body,
    ]
    if svc.pr_labels:
        pr_args.extend(["--label", svc.pr_labels[0]])

    result.steps.append(f"open PR from {fix_branch} to {svc.staging_branch}")
    code, out, err = _run_gh(pr_args, cwd=repo_dir, timeout=120)
    if code != 0:
        result.error = f"gh pr create failed: {err.strip() or f'exit {code}'}"
        return result
    result.pr_url = out.strip().splitlines()[-1] if out.strip() else ""
    if not result.pr_url:
        result.error = "gh pr create did not return a PR URL"
        return result

    result.steps.append(f"merge PR {result.pr_url} into {svc.staging_branch}")
    code, _out, err = _run_gh(
        ["pr", "merge", result.pr_url, "--merge", "--delete-branch=false"],
        cwd=repo_dir,
        timeout=180,
    )
    if code != 0:
        result.error = f"gh pr merge failed: {err.strip() or f'exit {code}'}"
        return result
    result.merged = True

    result.steps.append(f"fetch staging branch {svc.staging_branch} after merge")
    code, _out, err = _run_git(
        ["fetch", remote, svc.staging_branch],
        cwd=repo_dir,
        timeout=120,
    )
    if code != 0:
        result.error = f"git fetch after merge failed: {err.strip() or f'exit {code}'}"
        return result

    result.steps.append(f"record staging HEAD after merge ({staging_remote_ref})")
    code, out, err = _run_git(
        ["rev-parse", staging_remote_ref],
        cwd=repo_dir,
        timeout=60,
    )
    if code != 0:
        result.error = f"git rev-parse after merge failed: {err.strip() or f'exit {code}'}"
        return result
    result.staging_sha_after = out.strip()

    result.steps.append("run staging deploy command")
    code, _out, err = _run_deploy_command(svc.deploy_command, repo_dir)
    if code != 0:
        result.error = f"deploy command failed: {err.strip() or f'exit {code}'}"
        return result

    result.deployed = True
    result.ok = True
    return result


def _build_pr_title(message: str, max_length: int = 88) -> str:
    prefix = "[sentinel-fix] "
    clean_message = " ".join(message.split()) or "production failure"
    room = max_length - len(prefix)
    if len(clean_message) > room:
        clean_message = clean_message[: max(0, room - 3)].rstrip() + "..."
    return f"{prefix}{clean_message}"
