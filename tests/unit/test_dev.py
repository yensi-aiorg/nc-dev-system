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

    with patch("ncdev.dev.run_claude_session", side_effect=fake_session):
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

    with patch("ncdev.dev.run_claude_session", side_effect=fake_session):
        result = dev.run_dev(project, task="try something", mode="auto")

    assert result["status"] == "failed"
    # A [BROKEN] commit exists so we can recover
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=str(project),
        capture_output=True, text=True, check=True,
    )
    assert "[BROKEN]" in log.stdout


def test_no_work_done_is_failed(tmp_path: Path):
    project = tmp_path / "app"
    project.mkdir()
    _init_git(project)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        return ClaudeSessionResult(
            success=True, final_text="nothing to do", exit_code=0,
        )

    with patch("ncdev.dev.run_claude_session", side_effect=fake_session):
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

    with patch("ncdev.dev.run_claude_session", side_effect=fake_session):
        dev.run_dev(project, task="x", max_budget_usd=1.25)

    assert captured["max_budget_usd"] == 1.25
    # Must include Bash/Skill/Task so Claude can shell to Codex + invoke skills
    tools = list(captured["tools"])
    assert "Bash" in tools and "Skill" in tools and "Task" in tools
    # Codex protocol must be injected — no opt-out for dev mode
    assert captured["include_codex_protocol"] is True


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

    with patch("ncdev.dev.run_claude_session", side_effect=fake_session):
        dev.run_dev(project, task="do a thing", mode="enhance")

    assert len(calls) == 1
    pid, content, metadata = calls[0]
    assert pid == "app"
    assert "do a thing" in content
    assert metadata["status"] == "passed"
    assert metadata["mode"] == "enhance"
    assert "verification-before-completion" in metadata["skills_invoked"]
