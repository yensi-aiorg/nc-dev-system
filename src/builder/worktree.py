"""Git worktree management for parallel feature development.

Manages creation, cleanup, merging, and listing of git worktrees used by
Codex builders to implement features in isolation.
"""

import asyncio
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

console = Console()


@dataclass
class WorktreeInfo:
    """Information about a git worktree."""

    name: str
    path: Path
    branch: str
    feature: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class WorktreeError(Exception):
    """Raised when a worktree operation fails."""

    def __init__(self, message: str, command: str = "", stderr: str = ""):
        self.command = command
        self.stderr = stderr
        super().__init__(message)


def _sanitize_feature_name(feature_name: str) -> str:
    """Sanitize a feature name for use as a branch/directory name.

    Converts spaces and special characters to hyphens, lowercases everything,
    strips leading/trailing hyphens, and collapses consecutive hyphens.
    """
    sanitized = re.sub(r"[^a-zA-Z0-9_-]", "-", feature_name.strip().lower())
    sanitized = re.sub(r"-+", "-", sanitized)
    sanitized = sanitized.strip("-")
    if not sanitized:
        raise WorktreeError(
            f"Feature name '{feature_name}' produces an empty sanitized name."
        )
    return sanitized


async def _run_git(
    *args: str,
    cwd: str | Path | None = None,
    timeout: float = 60.0,
) -> tuple[str, str]:
    """Run a git command asynchronously and return (stdout, stderr).

    Raises WorktreeError if the command exits with a non-zero code.
    """
    cmd = ["git"] + list(args)
    cmd_str = " ".join(cmd)

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd) if cwd else None,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        process.kill()
        raise WorktreeError(
            f"Git command timed out after {timeout}s: {cmd_str}",
            command=cmd_str,
        )

    stdout = stdout_bytes.decode("utf-8", errors="replace").strip()
    stderr = stderr_bytes.decode("utf-8", errors="replace").strip()

    if process.returncode != 0:
        raise WorktreeError(
            f"Git command failed (exit {process.returncode}): {cmd_str}\n{stderr}",
            command=cmd_str,
            stderr=stderr,
        )

    return stdout, stderr


class WorktreeManager:
    """Manages git worktrees for parallel feature development.

    Each feature gets its own worktree under .worktrees/ in the repository root,
    with a dedicated branch named nc-dev/{feature_name}. This allows multiple
    Codex builders to work on different features simultaneously without conflicts.
    """

    def __init__(self, repo_path: str | Path):
        self.repo_path = Path(repo_path).resolve()
        self.worktrees_dir = self.repo_path / ".worktrees"

        if not (self.repo_path / ".git").exists():
            raise WorktreeError(
                f"Not a git repository: {self.repo_path}. "
                "WorktreeManager requires an initialized git repo."
            )

    async def create(
        self, feature_name: str, base_branch: str = "main"
    ) -> WorktreeInfo:
        """Create a git worktree for a feature branch.

        Creates a new worktree at .worktrees/{sanitized_name} with a branch
        named nc-dev/{sanitized_name} based on the given base branch.

        Args:
            feature_name: Human-readable feature name (will be sanitized).
            base_branch: Branch to base the new feature branch on.

        Returns:
            WorktreeInfo with the created worktree's details.

        Raises:
            WorktreeError: If the worktree or branch already exists, or git fails.
        """
        sanitized = _sanitize_feature_name(feature_name)
        branch_name = f"nc-dev/{sanitized}"
        worktree_path = self.worktrees_dir / sanitized

        if worktree_path.exists():
            raise WorktreeError(
                f"Worktree directory already exists: {worktree_path}. "
                f"Clean it up with cleanup('{feature_name}') first."
            )

        self.worktrees_dir.mkdir(parents=True, exist_ok=True)

        console.print(
            f"[cyan]Creating worktree[/cyan] [bold]{sanitized}[/bold] "
            f"from [green]{base_branch}[/green]..."
        )

        await _run_git(
            "worktree",
            "add",
            str(worktree_path),
            "-b",
            branch_name,
            base_branch,
            cwd=self.repo_path,
        )

        info = WorktreeInfo(
            name=sanitized,
            path=worktree_path,
            branch=branch_name,
            feature=feature_name,
        )

        console.print(
            Panel(
                f"[green]Worktree created[/green]\n"
                f"  Path:   {info.path}\n"
                f"  Branch: {info.branch}\n"
                f"  Feature: {info.feature}",
                title="Worktree Ready",
                border_style="green",
            )
        )

        return info

    async def cleanup(self, feature_name: str) -> None:
        """Remove a git worktree and its feature branch.

        Forcefully removes the worktree directory and deletes the associated
        nc-dev/{feature_name} branch.

        Args:
            feature_name: The feature name (will be sanitized).

        Raises:
            WorktreeError: If the git commands fail (missing worktree is tolerated).
        """
        sanitized = _sanitize_feature_name(feature_name)
        branch_name = f"nc-dev/{sanitized}"
        worktree_path = self.worktrees_dir / sanitized

        console.print(
            f"[yellow]Cleaning up worktree[/yellow] [bold]{sanitized}[/bold]..."
        )

        # Remove the worktree (--force handles dirty worktrees)
        if worktree_path.exists():
            try:
                await _run_git(
                    "worktree", "remove", "--force", str(worktree_path),
                    cwd=self.repo_path,
                )
            except WorktreeError:
                # If git worktree remove fails, manually remove the directory
                # and prune the worktree list
                console.print(
                    f"[yellow]Git worktree remove failed, "
                    f"removing directory manually...[/yellow]"
                )
                shutil.rmtree(worktree_path, ignore_errors=True)
                await _run_git("worktree", "prune", cwd=self.repo_path)

        # Delete the feature branch (ignore errors if branch doesn't exist)
        try:
            await _run_git(
                "branch", "-D", branch_name,
                cwd=self.repo_path,
            )
        except WorktreeError as exc:
            if "not found" not in exc.stderr.lower():
                console.print(
                    f"[yellow]Warning: Could not delete branch {branch_name}: "
                    f"{exc.stderr}[/yellow]"
                )

        console.print(f"[green]Cleaned up worktree:[/green] {sanitized}")

    async def merge(
        self,
        feature_name: str,
        target_branch: str = "main",
        commit_message: str | None = None,
    ) -> bool:
        """Merge a feature worktree branch into the target branch.

        Checks out the target branch, performs a --no-ff merge of the feature
        branch, then returns to the original branch state.

        Args:
            feature_name: The feature name (will be sanitized).
            target_branch: Branch to merge into (default: main).
            commit_message: Optional custom merge commit message.

        Returns:
            True if the merge succeeded, False otherwise.
        """
        sanitized = _sanitize_feature_name(feature_name)
        branch_name = f"nc-dev/{sanitized}"

        if commit_message is None:
            commit_message = f"feat({sanitized}): merge feature branch {branch_name}"

        console.print(
            f"[cyan]Merging[/cyan] [bold]{branch_name}[/bold] "
            f"into [green]{target_branch}[/green]..."
        )

        # Record current branch to restore later
        current_branch_out, _ = await _run_git(
            "rev-parse", "--abbrev-ref", "HEAD",
            cwd=self.repo_path,
        )
        original_branch = current_branch_out.strip()

        try:
            # Checkout target branch
            await _run_git("checkout", target_branch, cwd=self.repo_path)

            # Merge with --no-ff to always create a merge commit
            await _run_git(
                "merge", "--no-ff", "-m", commit_message, branch_name,
                cwd=self.repo_path,
            )

            console.print(
                f"[green]Successfully merged[/green] {branch_name} "
                f"into {target_branch}"
            )
            return True

        except WorktreeError as exc:
            console.print(
                f"[red]Merge failed:[/red] {exc}\n"
                f"Aborting merge and restoring {original_branch}..."
            )
            # Abort the merge if it's in progress
            try:
                await _run_git("merge", "--abort", cwd=self.repo_path)
            except WorktreeError:
                pass  # merge --abort fails if no merge was in progress, that's fine

            return False

        finally:
            # Always try to restore the original branch
            if original_branch and original_branch != target_branch:
                try:
                    await _run_git(
                        "checkout", original_branch,
                        cwd=self.repo_path,
                    )
                except WorktreeError:
                    console.print(
                        f"[yellow]Warning: Could not restore branch "
                        f"{original_branch}[/yellow]"
                    )

    async def list_worktrees(self) -> list[WorktreeInfo]:
        """List all active nc-dev worktrees.

        Parses `git worktree list --porcelain` output to find worktrees
        managed by this system (those under .worktrees/).

        Returns:
            List of WorktreeInfo for each active nc-dev worktree.
        """
        try:
            stdout, _ = await _run_git(
                "worktree", "list", "--porcelain",
                cwd=self.repo_path,
            )
        except WorktreeError:
            return []

        worktrees: list[WorktreeInfo] = []
        worktrees_prefix = str(self.worktrees_dir)

        # Parse porcelain output: blocks separated by blank lines
        # Each block has: worktree <path>\nHEAD <sha>\nbranch <ref>\n
        current_path: str | None = None
        current_branch: str | None = None

        for line in stdout.split("\n"):
            line = line.strip()

            if line.startswith("worktree "):
                current_path = line[len("worktree "):]
                current_branch = None
            elif line.startswith("branch "):
                current_branch = line[len("branch "):]
            elif line == "" and current_path and current_branch:
                # End of a block - check if this is one of our worktrees
                if current_path.startswith(worktrees_prefix):
                    wt_path = Path(current_path)
                    name = wt_path.name
                    # Branch ref is like refs/heads/nc-dev/feature-name
                    branch_short = current_branch
                    if branch_short.startswith("refs/heads/"):
                        branch_short = branch_short[len("refs/heads/"):]

                    worktrees.append(
                        WorktreeInfo(
                            name=name,
                            path=wt_path,
                            branch=branch_short,
                            feature=name,
                        )
                    )

                current_path = None
                current_branch = None

        # Handle the last block if file doesn't end with a blank line
        if current_path and current_branch and current_path.startswith(worktrees_prefix):
            wt_path = Path(current_path)
            name = wt_path.name
            branch_short = current_branch
            if branch_short.startswith("refs/heads/"):
                branch_short = branch_short[len("refs/heads/"):]
            worktrees.append(
                WorktreeInfo(
                    name=name,
                    path=wt_path,
                    branch=branch_short,
                    feature=name,
                )
            )

        return worktrees

    async def cleanup_all(self) -> None:
        """Remove all nc-dev worktrees and their branches.

        Lists all active worktrees and cleans each one up, then removes
        the .worktrees/ directory if it's empty.
        """
        console.print("[yellow]Cleaning up all worktrees...[/yellow]")

        active = await self.list_worktrees()

        if not active:
            console.print("[dim]No active worktrees found.[/dim]")
            if self.worktrees_dir.exists():
                shutil.rmtree(self.worktrees_dir, ignore_errors=True)
            return

        for wt in active:
            try:
                await self.cleanup(wt.name)
            except WorktreeError as exc:
                console.print(
                    f"[red]Failed to cleanup {wt.name}:[/red] {exc}"
                )

        # Prune any stale worktree references
        try:
            await _run_git("worktree", "prune", cwd=self.repo_path)
        except WorktreeError:
            pass

        # Remove the .worktrees directory if now empty
        if self.worktrees_dir.exists() and not any(self.worktrees_dir.iterdir()):
            self.worktrees_dir.rmdir()

        console.print("[green]All worktrees cleaned up.[/green]")

    async def get_worktree(self, feature_name: str) -> WorktreeInfo | None:
        """Get info for a specific worktree by feature name.

        Args:
            feature_name: The feature name to look up.

        Returns:
            WorktreeInfo if found, None otherwise.
        """
        sanitized = _sanitize_feature_name(feature_name)
        active = await self.list_worktrees()
        for wt in active:
            if wt.name == sanitized:
                return wt
        return None

    async def worktree_exists(self, feature_name: str) -> bool:
        """Check if a worktree exists for the given feature name."""
        return await self.get_worktree(feature_name) is not None
