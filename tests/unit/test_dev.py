"""Tests for the thin ``ncdev dev`` orchestrator."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from ncdev import dev
from ncdev.claude_session import ClaudeSessionResult


def _init_git(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=str(path), check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=str(path), check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=str(path), check=True)
    (path / "README.md").write_text("init")
    subprocess.run(["git", "add", "-A"], cwd=str(path), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(path), check=True)


@pytest.fixture(autouse=True)
def _patch_citex(monkeypatch):
    """Bypass Citex health checks in tests."""
    monkeypatch.setattr(dev, "require_citex", lambda url=None: None)
    monkeypatch.setattr(dev, "citex_store", lambda *a, **k: True)


# ---------------------------------------------------------------------------
# Prompt shape
# ---------------------------------------------------------------------------


def test_task_prompt_references_project_and_skills(tmp_path: Path):
    prompt = dev._build_task_prompt(
        "refactor the auth flow",
        project_path=tmp_path,
        project_id="myapp",
        mode="bugfix",
    )
    assert "refactor the auth flow" in prompt
    assert "myapp" in prompt
    assert str(tmp_path) in prompt
    # References the Codex protocol and skill machinery but does not inline them
    assert "Codex protocol" in prompt
    assert "test-driven-development" in prompt
    assert "verification-before-completion" in prompt
    assert "systematic-debugging" in prompt
    # Explicit Codex exec command shape appears as guidance
    assert "codex exec --full-auto" in prompt


def test_task_prompt_is_short():
    prompt = dev._build_task_prompt("X", Path("/p"), "pid", "auto")
    # Keep it tight — this is the whole point of the rewrite
    assert len(prompt) < 2500, f"prompt is {len(prompt)} chars, should stay lean"


# ---------------------------------------------------------------------------
# Successful run
# ---------------------------------------------------------------------------


def test_run_dev_passes_when_session_commits_cleanly(tmp_path: Path):
    project = tmp_path / "app"
    project.mkdir()
    _init_git(project)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        # Simulate Claude committing a clean change
        (project / "foo.py").write_text("x = 1")
        subprocess.run(["git", "add", "-A"], cwd=str(project), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "feat: foo"],
                       cwd=str(project), check=True)
        return ClaudeSessionResult(
            success=True, final_text="built foo", exit_code=0,
            duration_seconds=1.0, total_cost_usd=0.05,
            skills_invoked=["test-driven-development"],
        )

    with patch("ncdev.dev.run_ai_session", side_effect=fake_session):
        result = dev.run_dev(project, task="add foo", mode="auto")

    assert result["status"] == "passed"
    assert result["commit_sha"] != ""
    assert "test-driven-development" in result["skills_invoked"]


# ---------------------------------------------------------------------------
# Broken-tag recovery
# ---------------------------------------------------------------------------


def test_dirty_working_tree_gets_broken_commit(tmp_path: Path):
    project = tmp_path / "app"
    project.mkdir()
    _init_git(project)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        # Claude left changes uncommitted
        (project / "halfdone.py").write_text("# WIP")
        return ClaudeSessionResult(success=False, final_text="stuck", exit_code=1)

    with patch("ncdev.dev.run_ai_session", side_effect=fake_session):
        result = dev.run_dev(project, task="try something", mode="auto")

    assert result["status"] == "failed"
    # A [BROKEN] commit exists so we can recover
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=str(project),
        capture_output=True, text=True, check=True,
    )
    assert "[BROKEN]" in log.stdout


def test_dirty_tree_after_successful_session_is_auto_committed_not_broken(tmp_path: Path):
    """A successful session that forgets to commit should be auto-committed
    with a neutral chore(ncdev): message, status=passed, no [BROKEN] tag."""
    project = tmp_path / "app"
    project.mkdir()
    _init_git(project)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        # Claude finished the work, tests pass in its session, but it
        # neglected to run `git commit`.
        (project / "feature.py").write_text("def feature():\n    return 42\n")
        return ClaudeSessionResult(
            success=True,
            final_text="All tests pass.",
            exit_code=0,
            files_touched=["feature.py"],
        )

    with patch("ncdev.dev.run_ai_session", side_effect=fake_session):
        result = dev.run_dev(project, task="add feature", mode="auto")

    assert result["status"] == "passed"
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=str(project),
        capture_output=True, text=True, check=True,
    )
    assert "[BROKEN]" not in log.stdout
    assert "chore(ncdev)" in log.stdout
    # Working tree should be clean after the auto-commit
    status_out = subprocess.run(
        ["git", "status", "--porcelain"], cwd=str(project),
        capture_output=True, text=True, check=True,
    )
    assert status_out.stdout.strip() == ""


def test_successful_session_with_autocommit_failure_is_not_marked_passed(tmp_path: Path):
    """If _commit_session_leftovers returns '' (e.g. nothing staged because
    everything is gitignored, or git identity missing), the run must NOT be
    marked passed — that would be the same false-positive-success the fix
    was meant to prevent."""
    project = tmp_path / "app"
    project.mkdir()
    _init_git(project)
    (project / ".gitignore").write_text("*.ignored\n")
    subprocess.run(["git", "add", ".gitignore"], cwd=str(project), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add gitignore"],
                   cwd=str(project), check=True)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        # Only write to an ignored path — git add -A stages nothing, commit fails.
        (project / "scratch.ignored").write_text("whatever")
        return ClaudeSessionResult(
            success=True, final_text="done", exit_code=0,
            files_touched=["scratch.ignored"],
        )

    with patch("ncdev.dev.run_ai_session", side_effect=fake_session):
        result = dev.run_dev(project, task="try to do a thing", mode="auto")

    assert result["status"] == "failed"
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=str(project),
        capture_output=True, text=True, check=True,
    )
    assert "chore(ncdev)" not in log.stdout
    assert "[BROKEN]" not in log.stdout


def test_failed_session_with_clean_tree_is_failed_without_broken_commit(tmp_path: Path):
    """Complementary gap: session.success=False + clean tree. No broken commit
    should be created (nothing to preserve), and status is failed."""
    project = tmp_path / "app"
    project.mkdir()
    _init_git(project)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        return ClaudeSessionResult(
            success=False, final_text="crashed", exit_code=1,
        )

    with patch("ncdev.dev.run_ai_session", side_effect=fake_session):
        result = dev.run_dev(project, task="do x", mode="auto")

    assert result["status"] == "failed"
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=str(project),
        capture_output=True, text=True, check=True,
    )
    assert "[BROKEN]" not in log.stdout


def test_empty_task_yields_fallback_autocommit_subject(tmp_path: Path):
    """Guard: an empty or all-whitespace task must still produce a readable
    commit subject, not 'chore(ncdev): ' with a trailing space."""
    project = tmp_path / "app"
    project.mkdir()
    _init_git(project)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        (project / "f.py").write_text("# x\n")
        return ClaudeSessionResult(
            success=True, final_text="ok", exit_code=0, files_touched=["f.py"],
        )

    with patch("ncdev.dev.run_ai_session", side_effect=fake_session):
        dev.run_dev(project, task="   \n  ", mode="auto")

    subject = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"], cwd=str(project),
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert subject == "chore(ncdev): uncommitted session work"


def test_no_work_done_is_failed(tmp_path: Path):
    project = tmp_path / "app"
    project.mkdir()
    _init_git(project)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        return ClaudeSessionResult(
            success=True, final_text="nothing to do", exit_code=0,
        )

    with patch("ncdev.dev.run_ai_session", side_effect=fake_session):
        result = dev.run_dev(project, task="x", mode="auto")

    assert result["status"] == "failed"


# ---------------------------------------------------------------------------
# Session options flow through
# ---------------------------------------------------------------------------


def test_max_budget_propagates_to_session(tmp_path: Path):
    project = tmp_path / "app"
    project.mkdir()
    _init_git(project)
    captured: dict = {}

    def fake_session(prompt, **kwargs):
        captured.update(kwargs)
        (project / "x").write_text("x")
        subprocess.run(["git", "add", "-A"], cwd=str(project), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "feat: x"],
                       cwd=str(project), check=True)
        return ClaudeSessionResult(success=True, final_text="ok", exit_code=0)

    with patch("ncdev.dev.run_ai_session", side_effect=fake_session):
        dev.run_dev(project, task="x", max_budget_usd=1.25)

    assert captured["max_budget_usd"] == 1.25
    # Must include Bash/Skill/Task so Claude can shell to Codex + invoke skills
    tools = list(captured["tools"])
    assert "Bash" in tools and "Skill" in tools and "Task" in tools
    # The mode-aware config must be forwarded to the dispatcher — it
    # decides whether to inject the Codex protocol based on mode.
    assert captured["config"] is not None


# ---------------------------------------------------------------------------
# Citex summary ingestion
# ---------------------------------------------------------------------------


def test_run_summary_ingested_to_citex(tmp_path: Path, monkeypatch):
    project = tmp_path / "app"
    project.mkdir()
    _init_git(project)

    calls = []
    monkeypatch.setattr(dev, "citex_store",
                        lambda pid, content, metadata: calls.append((pid, content, metadata)) or True)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        (project / "a").write_text("a")
        subprocess.run(["git", "add", "-A"], cwd=str(project), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "feat: a"],
                       cwd=str(project), check=True)
        return ClaudeSessionResult(
            success=True, final_text="done", exit_code=0,
            skills_invoked=["verification-before-completion"],
        )

    with patch("ncdev.dev.run_ai_session", side_effect=fake_session):
        dev.run_dev(project, task="do a thing", mode="enhance")

    assert len(calls) == 1
    pid, content, metadata = calls[0]
    assert pid == "app"
    assert "do a thing" in content
    assert metadata["status"] == "passed"
    assert metadata["mode"] == "enhance"
    assert "verification-before-completion" in metadata["skills_invoked"]
