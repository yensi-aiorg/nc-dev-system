"""NC Dev System builder module.

Manages the full feature-building pipeline: git worktree creation, Codex prompt
generation, builder process execution, code review, and fallback strategies.

Key classes:
    WorktreeManager   - Git worktree lifecycle management
    PromptGenerator   - Codex builder prompt generation
    CodexRunner       - Codex CLI process spawning and monitoring
    BuildReviewer     - Code review, test execution, and pattern scanning
    FallbackStrategy  - Codex -> retry -> Sonnet -> escalate chain
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
