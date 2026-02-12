---
name: build-feature
description: Build a single feature using Codex GPT 5.3 in an isolated worktree
user-invocable: false
context: fork
agent: general-purpose
model: sonnet
---

Build the feature specified in $ARGUMENTS using Codex CLI:

1. Read the feature spec from .nc-dev/features.json
2. Create worktree: `git worktree add .worktrees/$FEATURE_NAME -b nc-dev/$FEATURE_NAME`
3. Copy CLAUDE.md and project conventions into the worktree
4. Generate the Codex prompt from feature spec + conventions
5. Spawn Codex builder (Codex CLI handles auth via `codex login`):
   ```bash
   codex exec --full-auto --json \
     --cd .worktrees/$FEATURE_NAME \
     "$(cat .nc-dev/prompts/build-$FEATURE_NAME.md)" \
     -o .nc-dev/codex-results/$FEATURE_NAME.json &
   ```
6. Monitor Codex JSONL output for progress
7. When Codex exits:
   - Read result JSON
   - Run `git diff` in worktree to review changes
   - Run tests: `cd .worktrees/$FEATURE_NAME && npm run test && pytest`
   - If tests pass: ready for merge
   - If tests fail: retry with Codex (include error context) OR fall back to Claude Sonnet
8. Report results to Team Lead

## Fallback Strategy
- Codex failure attempt 1: Retry with error context in prompt
- Codex failure attempt 2: Switch to Claude Code Sonnet subagent for this feature
- Sonnet failure: Escalate to user
