"""NC Dev System builder module.

Manages the full feature-building pipeline: git worktree creation, CLI builder
prompt generation, builder process execution, code review, and fallback strategies.

Supports configurable CLI backends (Claude Code or OpenAI Codex) via the
CodexRunner's ``cli_mode`` parameter.

Key classes:
    WorktreeManager   - Git worktree lifecycle management
    PromptGenerator   - CLI builder prompt generation
    CodexRunner       - CLI builder process spawning and monitoring (Claude or Codex)
    BuildReviewer     - Code review, test execution, and pattern scanning
    FallbackStrategy  - Builder -> retry -> Sonnet -> escalate chain
"""

from .codex_runner import CodexResult, CodexRunner, CodexRunnerError
from .fallback import BuildMethod, BuildResult, FallbackStrategy, SonnetRunner
from .prompt_gen import PromptGenerator
from .reviewer import BuildReviewer, ReviewResult
from .worktree import WorktreeError, WorktreeInfo, WorktreeManager

__all__ = [
    # Worktree management
    "WorktreeManager",
    "WorktreeInfo",
    "WorktreeError",
    # Prompt generation
    "PromptGenerator",
    # Codex runner
    "CodexRunner",
    "CodexResult",
    "CodexRunnerError",
    # Build reviewer
    "BuildReviewer",
    "ReviewResult",
    # Fallback strategy
    "FallbackStrategy",
    "BuildResult",
    "BuildMethod",
    "SonnetRunner",
]
