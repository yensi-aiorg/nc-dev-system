"""Unit tests for git worktree management (src.builder.worktree).

Tests cover:
- WorktreeManager initialisation and validation
- Worktree creation (mock git commands)
- Worktree cleanup and branch deletion
- Worktree merge into target branch
- Listing worktrees from porcelain output
- cleanup_all for bulk removal
- get_worktree and worktree_exists helpers
- _sanitize_feature_name edge cases
- Error handling when git commands fail
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.builder.worktree import (
    WorktreeError,
    WorktreeInfo,
    WorktreeManager,
    _run_git,
    _sanitize_feature_name,
)


# ---------------------------------------------------------------------------
# Local fixture -- avoids real git commits (which fail in some CI envs)
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_git_repo(tmp_path: Path) -> Path:
    """Create a directory with a `.git` dir so WorktreeManager accepts it.

    All git operations are mocked, so we don't need a real repo.
    """
    (tmp_path / ".git").mkdir()
    return tmp_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_run_git_success(stdout: str = "", stderr: str = ""):
    """Return an AsyncMock that resolves to (stdout, stderr)."""
    return AsyncMock(return_value=(stdout, stderr))


def _mock_run_git_failure(message: str = "fail", command: str = "git ...", stderr: str = "error"):
    """Return an AsyncMock that raises WorktreeError."""
    async def _raise(*args, **kwargs):
        raise WorktreeError(message, command=command, stderr=stderr)
    return _raise


# ---------------------------------------------------------------------------
# _sanitize_feature_name
# ---------------------------------------------------------------------------

class TestSanitizeFeatureName:
    @pytest.mark.unit
    def test_simple_name(self):
        assert _sanitize_feature_name("user-auth") == "user-auth"

    @pytest.mark.unit
    def test_spaces_converted_to_hyphens(self):
        assert _sanitize_feature_name("User Authentication") == "user-authentication"

    @pytest.mark.unit
    def test_special_characters_stripped(self):
        assert _sanitize_feature_name("feat: create (task)") == "feat-create-task"

    @pytest.mark.unit
    def test_consecutive_hyphens_collapsed(self):
        assert _sanitize_feature_name("a---b") == "a-b"

    @pytest.mark.unit
    def test_leading_trailing_hyphens_stripped(self):
        assert _sanitize_feature_name("--feature--") == "feature"

    @pytest.mark.unit
    def test_uppercase_lowered(self):
        assert _sanitize_feature_name("MyFeature") == "myfeature"

    @pytest.mark.unit
    def test_empty_name_raises(self):
        with pytest.raises(WorktreeError, match="empty sanitized name"):
            _sanitize_feature_name("!!!!")


# ---------------------------------------------------------------------------
# _run_git
# ---------------------------------------------------------------------------

class TestRunGit:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_success_returns_stdout_stderr(self, mock_subprocess):
        proc = mock_subprocess(stdout="branch-output", stderr="", returncode=0)
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            stdout, stderr = await _run_git("branch", "-a")
            assert stdout == "branch-output"
            assert stderr == ""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_nonzero_exit_raises_worktree_error(self, mock_subprocess):
        proc = mock_subprocess(stdout="", stderr="fatal: bad revision", returncode=128)
        with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
            with pytest.raises(WorktreeError, match="Git command failed"):
                await _run_git("log", "--oneline")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_timeout_raises_worktree_error(self):
        async def _mock_exec(*args, **kwargs):
            proc = AsyncMock()
            async def _communicate():
                await asyncio.sleep(10)
                return (b"", b"")
            proc.communicate = _communicate
            proc.kill = MagicMock()
            proc.returncode = -1
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=_mock_exec):
            with pytest.raises(WorktreeError, match="timed out"):
                await _run_git("status", timeout=0.01)


# ---------------------------------------------------------------------------
# WorktreeManager.__init__
# ---------------------------------------------------------------------------

class TestWorktreeManagerInit:
    @pytest.mark.unit
    def test_valid_repo_initialises(self, tmp_path: Path):
        # Create a fake .git directory so WorktreeManager sees a repo
        (tmp_path / ".git").mkdir()
        mgr = WorktreeManager(tmp_path)
        assert mgr.repo_path == tmp_path.resolve()
        assert mgr.worktrees_dir == tmp_path.resolve() / ".worktrees"

    @pytest.mark.unit
    def test_non_git_dir_raises(self, tmp_path: Path):
        with pytest.raises(WorktreeError, match="Not a git repository"):
            WorktreeManager(tmp_path)


# ---------------------------------------------------------------------------
# WorktreeManager.create
# ---------------------------------------------------------------------------

class TestWorktreeManagerCreate:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_worktree_success(self, fake_git_repo: Path):
        mgr = WorktreeManager(fake_git_repo)

        with patch("src.builder.worktree._run_git", _mock_run_git_success()):
            info = await mgr.create("user-auth")

        assert isinstance(info, WorktreeInfo)
        assert info.name == "user-auth"
        assert info.branch == "nc-dev/user-auth"
        assert info.feature == "user-auth"
        assert info.path == mgr.worktrees_dir / "user-auth"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_sanitizes_feature_name(self, fake_git_repo: Path):
        mgr = WorktreeManager(fake_git_repo)

        with patch("src.builder.worktree._run_git", _mock_run_git_success()):
            info = await mgr.create("User Authentication Feature")

        assert info.name == "user-authentication-feature"
        assert info.branch == "nc-dev/user-authentication-feature"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_existing_worktree_raises(self, fake_git_repo: Path):
        mgr = WorktreeManager(fake_git_repo)
        # Pre-create the worktree directory
        wt_dir = mgr.worktrees_dir / "user-auth"
        wt_dir.mkdir(parents=True)

        with pytest.raises(WorktreeError, match="already exists"):
            await mgr.create("user-auth")

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_with_custom_base_branch(self, fake_git_repo: Path):
        mgr = WorktreeManager(fake_git_repo)
        calls = []

        async def _capture_run_git(*args, cwd=None, timeout=60.0):
            calls.append(args)
            return ("", "")

        with patch("src.builder.worktree._run_git", side_effect=_capture_run_git):
            await mgr.create("my-feature", base_branch="develop")

        # Check the base_branch was passed to the git worktree add command
        assert any("develop" in call for call in calls)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_git_failure_propagates(self, fake_git_repo: Path):
        mgr = WorktreeManager(fake_git_repo)

        with patch("src.builder.worktree._run_git", side_effect=_mock_run_git_failure("worktree add failed")):
            with pytest.raises(WorktreeError, match="worktree add failed"):
                await mgr.create("fail-feature")


# ---------------------------------------------------------------------------
# WorktreeManager.cleanup
# ---------------------------------------------------------------------------

class TestWorktreeManagerCleanup:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cleanup_removes_worktree_and_branch(self, fake_git_repo: Path):
        mgr = WorktreeManager(fake_git_repo)
        # Pre-create the worktree directory
        wt_dir = mgr.worktrees_dir / "user-auth"
        wt_dir.mkdir(parents=True)

        calls = []

        async def _track(*args, cwd=None, timeout=60.0):
            calls.append(list(args))
            return ("", "")

        with patch("src.builder.worktree._run_git", side_effect=_track):
            await mgr.cleanup("user-auth")

        # Should have called worktree remove and branch -D
        cmd_strings = [" ".join(c) for c in calls]
        assert any("worktree remove" in s for s in cmd_strings)
        assert any("branch -D" in s for s in cmd_strings)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cleanup_missing_worktree_still_deletes_branch(self, fake_git_repo: Path):
        mgr = WorktreeManager(fake_git_repo)
        # Don't create the worktree directory

        calls = []

        async def _track(*args, cwd=None, timeout=60.0):
            calls.append(list(args))
            return ("", "")

        with patch("src.builder.worktree._run_git", side_effect=_track):
            await mgr.cleanup("user-auth")

        # Should still attempt to delete the branch
        cmd_strings = [" ".join(c) for c in calls]
        assert any("branch -D" in s for s in cmd_strings)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cleanup_branch_not_found_tolerated(self, fake_git_repo: Path):
        mgr = WorktreeManager(fake_git_repo)

        call_count = 0

        async def _mock(*args, cwd=None, timeout=60.0):
            nonlocal call_count
            call_count += 1
            if "branch" in args and "-D" in args:
                raise WorktreeError("branch not found", command="git branch -D", stderr="not found")
            return ("", "")

        with patch("src.builder.worktree._run_git", side_effect=_mock):
            # Should not raise
            await mgr.cleanup("user-auth")

        assert call_count > 0


# ---------------------------------------------------------------------------
# WorktreeManager.merge
# ---------------------------------------------------------------------------

class TestWorktreeManagerMerge:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_merge_success_returns_true(self, fake_git_repo: Path):
        mgr = WorktreeManager(fake_git_repo)

        async def _mock(*args, cwd=None, timeout=60.0):
            if "rev-parse" in args:
                return ("main", "")
            return ("", "")

        with patch("src.builder.worktree._run_git", side_effect=_mock):
            result = await mgr.merge("user-auth")

        assert result is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_merge_failure_returns_false(self, fake_git_repo: Path):
        mgr = WorktreeManager(fake_git_repo)

        async def _mock(*args, cwd=None, timeout=60.0):
            if "rev-parse" in args:
                return ("feature-branch", "")
            if "merge" in args and "--abort" not in args and "checkout" not in args:
                raise WorktreeError("merge conflict")
            return ("", "")

        with patch("src.builder.worktree._run_git", side_effect=_mock):
            result = await mgr.merge("user-auth")

        assert result is False

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_merge_custom_commit_message(self, fake_git_repo: Path):
        mgr = WorktreeManager(fake_git_repo)
        merge_args = []

        async def _mock(*args, cwd=None, timeout=60.0):
            if "rev-parse" in args:
                return ("main", "")
            if "merge" in args:
                merge_args.extend(args)
            return ("", "")

        with patch("src.builder.worktree._run_git", side_effect=_mock):
            await mgr.merge("user-auth", commit_message="custom msg")

        assert "custom msg" in merge_args

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_merge_restores_original_branch(self, fake_git_repo: Path):
        mgr = WorktreeManager(fake_git_repo)
        checkout_calls = []

        async def _mock(*args, cwd=None, timeout=60.0):
            if "rev-parse" in args:
                return ("my-dev-branch", "")
            if "checkout" in args:
                checkout_calls.append(list(args))
            return ("", "")

        with patch("src.builder.worktree._run_git", side_effect=_mock):
            await mgr.merge("user-auth", target_branch="main")

        # Should restore original branch (my-dev-branch)
        flat = [item for sublist in checkout_calls for item in sublist]
        assert "my-dev-branch" in flat


# ---------------------------------------------------------------------------
# WorktreeManager.list_worktrees
# ---------------------------------------------------------------------------

class TestWorktreeManagerListWorktrees:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_list_parses_porcelain_output(self, fake_git_repo: Path):
        mgr = WorktreeManager(fake_git_repo)
        worktrees_prefix = str(mgr.worktrees_dir)

        porcelain = (
            f"worktree {fake_git_repo}\n"
            f"HEAD abc123\n"
            f"branch refs/heads/main\n"
            f"\n"
            f"worktree {worktrees_prefix}/user-auth\n"
            f"HEAD def456\n"
            f"branch refs/heads/nc-dev/user-auth\n"
            f"\n"
        )

        with patch("src.builder.worktree._run_git", _mock_run_git_success(porcelain)):
            result = await mgr.list_worktrees()

        assert len(result) == 1
        assert result[0].name == "user-auth"
        assert result[0].branch == "nc-dev/user-auth"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_list_empty_when_no_worktrees(self, fake_git_repo: Path):
        mgr = WorktreeManager(fake_git_repo)

        porcelain = (
            f"worktree {fake_git_repo}\n"
            f"HEAD abc123\n"
            f"branch refs/heads/main\n"
            f"\n"
        )

        with patch("src.builder.worktree._run_git", _mock_run_git_success(porcelain)):
            result = await mgr.list_worktrees()

        assert result == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_list_git_error_returns_empty(self, fake_git_repo: Path):
        mgr = WorktreeManager(fake_git_repo)

        with patch("src.builder.worktree._run_git", side_effect=_mock_run_git_failure()):
            result = await mgr.list_worktrees()

        assert result == []

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_list_handles_no_trailing_blank_line(self, fake_git_repo: Path):
        mgr = WorktreeManager(fake_git_repo)
        worktrees_prefix = str(mgr.worktrees_dir)

        porcelain = (
            f"worktree {worktrees_prefix}/task-crud\n"
            f"HEAD aaa111\n"
            f"branch refs/heads/nc-dev/task-crud"
        )

        with patch("src.builder.worktree._run_git", _mock_run_git_success(porcelain)):
            result = await mgr.list_worktrees()

        assert len(result) == 1
        assert result[0].name == "task-crud"


# ---------------------------------------------------------------------------
# WorktreeManager.cleanup_all
# ---------------------------------------------------------------------------

class TestWorktreeManagerCleanupAll:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cleanup_all_cleans_each_worktree(self, fake_git_repo: Path):
        mgr = WorktreeManager(fake_git_repo)
        worktrees_prefix = str(mgr.worktrees_dir)

        porcelain = (
            f"worktree {worktrees_prefix}/feat-a\n"
            f"HEAD aaa\n"
            f"branch refs/heads/nc-dev/feat-a\n"
            f"\n"
            f"worktree {worktrees_prefix}/feat-b\n"
            f"HEAD bbb\n"
            f"branch refs/heads/nc-dev/feat-b\n"
            f"\n"
        )

        cleaned = []

        async def _mock_cleanup(name):
            cleaned.append(name)

        with patch("src.builder.worktree._run_git", _mock_run_git_success(porcelain)):
            mgr.cleanup = AsyncMock(side_effect=_mock_cleanup)
            await mgr.cleanup_all()

        assert "feat-a" in cleaned
        assert "feat-b" in cleaned

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_cleanup_all_no_active_worktrees(self, fake_git_repo: Path):
        mgr = WorktreeManager(fake_git_repo)

        with patch("src.builder.worktree._run_git", _mock_run_git_success("")):
            # Should not raise
            await mgr.cleanup_all()


# ---------------------------------------------------------------------------
# WorktreeManager.get_worktree / worktree_exists
# ---------------------------------------------------------------------------

class TestWorktreeManagerGet:
    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_worktree_found(self, fake_git_repo: Path):
        mgr = WorktreeManager(fake_git_repo)
        worktrees_prefix = str(mgr.worktrees_dir)

        porcelain = (
            f"worktree {worktrees_prefix}/user-auth\n"
            f"HEAD abc123\n"
            f"branch refs/heads/nc-dev/user-auth\n"
            f"\n"
        )

        with patch("src.builder.worktree._run_git", _mock_run_git_success(porcelain)):
            wt = await mgr.get_worktree("user-auth")

        assert wt is not None
        assert wt.name == "user-auth"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_worktree_not_found(self, fake_git_repo: Path):
        mgr = WorktreeManager(fake_git_repo)

        with patch("src.builder.worktree._run_git", _mock_run_git_success("")):
            wt = await mgr.get_worktree("nonexistent")

        assert wt is None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_worktree_exists_true(self, fake_git_repo: Path):
        mgr = WorktreeManager(fake_git_repo)
        worktrees_prefix = str(mgr.worktrees_dir)

        porcelain = (
            f"worktree {worktrees_prefix}/user-auth\n"
            f"HEAD abc123\n"
            f"branch refs/heads/nc-dev/user-auth\n"
            f"\n"
        )

        with patch("src.builder.worktree._run_git", _mock_run_git_success(porcelain)):
            assert await mgr.worktree_exists("user-auth") is True

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_worktree_exists_false(self, fake_git_repo: Path):
        mgr = WorktreeManager(fake_git_repo)

        with patch("src.builder.worktree._run_git", _mock_run_git_success("")):
            assert await mgr.worktree_exists("nope") is False
