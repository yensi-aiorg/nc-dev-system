# AGENTS.md — NC Dev System

How to use NC Dev System from Codex CLI, Claude Code, or any other AI agent harness.

---

## 1. What this is

NC Dev System is a **thin orchestrator** for large-scale autonomous development. Claude is the engineer; Codex is Claude's implementation peer; NC Dev is the harness that starts them, streams their events, and commits verified work.

You probably want NC Dev when:

- The task is a full PRD or 4+ interdependent features
- You need cross-feature coherence (feature N+1 sees what N built)
- You need verified-commit checkpoints for recoverability
- You need Citex RAG grounding, asset manifests, or the Stitch design flow

You probably **don't** want NC Dev when:

- The task is a one-off tweak ("fix button alignment")
- You want to iterate freeform in a single Claude or Codex session
- You don't have a PRD yet — brainstorm directly with Claude first

For the small case, go straight to `claude` or `codex exec` in a terminal.

## 2. Architecture at a glance

```
Preflight → Charter → Design → Ingestion → Sequential Features → Summary

Each "feature" = one Claude session:
  - Claude drives with skills (TDD, verification-before-completion,
    systematic-debugging)
  - Claude delegates impl + tests to Codex via Bash:
      codex exec --full-auto --sandbox danger-full-access "<task>"
  - Claude commits with Conventional Commits
  - NC Dev streams events, verifies, tags [BROKEN] on failure
```

## 3. CLI Commands

| Command | Purpose |
|---------|---------|
| `ncdev full --source prd.md` | PRD-scale sequential sprint engine |
| `ncdev full --source prd.md --target-repo /path/to/repo` | Brownfield run |
| `ncdev full --source prd.md --max-budget-usd 50.0` | Cap total cost |
| `ncdev dev --project X --task Y` | Freeform single-task engineering |
| `ncdev dev --project X --task Y --mode bugfix` | Tighter scope hint |
| `ncdev serve` | HTTP intake for Sentinel reports |
| `ncdev doctor` | Preflight check (git, claude, codex, Citex) |

## 4. Mode switch (the budget lever)

Edit `.nc-dev/v2/config.yaml`:

```yaml
mode: claude_plan_codex_build   # default — Claude plans/reviews, Codex builds/tests
# mode: codex_only               # lean days — Codex does everything
# mode: claude_only              # Claude does everything (no Codex)
# mode: openrouter               # API-only, needs OPENROUTER_API_KEY
# mode: custom                   # use the routing block below
```

Flipping one line flips who does what. No code change.

## 5. What gets produced per run

Under `.nc-dev/v2/runs/<run_id>/outputs/`:

- `target-project-contract.json` — hard architectural constraints (stack, ports, auth, deployment, design archetype)
- `verification-contract.json` — what "done" means (test commands, required files, prohibited patterns, screenshots)
- `feature-queue.json` — ordered FeatureStep list
- `design-system.json` — design tokens + screens (UI projects only)

Under `.nc-dev/v2/runs/<run_id>/steps/<feature_id>/`:

- `prompt.md` — the prompt Claude was given
- `session.jsonl` — every stream event from the Claude session
- `final-response.md` — Claude's final summary
- `result.json` — StepResult (status, commits, files, verification)
- `signals.json` — skills invoked, Codex shell-outs, tool calls, cost

Under `<target>/.ncdev/assets-needed/`:

- `<feature_id>.json` — per-feature manifest of images/GIFs/SVGs/videos needed
- `_all.json` — aggregate for batch processing (Nano Banana 2, human)

## 6. Hooks (enforced at commit time)

Every Claude session gets the default hook config wired via `--settings`. Hooks block:

- Commits without Conventional Commits format
- Commits where staged diff contains `TODO`, `FIXME`, `console.log(`, or "Not yet implemented"
- Force-push to `main` / `master` / `production` (unless `NCDEV_ALLOW_FORCE_PUSH=1`)

Project-level overrides: `NCDEV_HOOKS_CONFIG=/path/to/custom.json` with `{"prohibited_patterns": [...]}`.

## 7. When agents talk to NC Dev

### If you are Codex

You usually get invoked **by Claude** through `codex exec --full-auto --sandbox danger-full-access "<prompt>"`. The prompt you receive will follow this 5-section shape:

```
# Task
<one-line description>

# Context
<2-3 lines on the surrounding code>

# Requirements
- <bullets>

# Files
- Read: ...
- Create: ...
- Modify: ...

# Verification
<exact command that must pass>
```

Do the work, run the verification command yourself, return a short summary. Don't speculate beyond the prompt.

### If you are Claude (orchestrator)

When NC Dev spawns you, your system prompt contains the Codex protocol (`prompts/protocols/codex-via-bash.md`). You have:

- **Tools**: Read, Write, Edit, Glob, Grep, **Bash** (shell to codex), **Skill**, **Task**
- **Skills to use**: `writing-plans`, `test-driven-development`, `verification-before-completion`, `systematic-debugging`, `frontend-design`
- **Hooks in place**: your commits will be blocked if they break the rules — fix the violation, don't route around it

Drive the feature end-to-end. Don't ask NC Dev for help — it's just the harness. If you genuinely cannot complete, leave the working tree dirty and exit; NC Dev will tag a `[BROKEN]` commit for recoverability.

## 8. Integration with Sentinel

Sentinel POSTs production failure reports to `ncdev serve` (port 16650). Each report triggers a Claude session in `sentinel_fix` mode — scoped to reproducing the failure and shipping a fix PR. Same architecture: Claude reasons, Codex implements, hooks enforce.

## 9. The three things NC Dev is strict about

1. **Greenfield UI without a design system → hard fail.** Either Stitch MCP is configured, or `docs/design-system/` is pre-populated. No exceptions. (Brownfield without designs lets Claude decide.)
2. **Asset manifest is mandatory** for features that ship UI. Code that references assets without a manifest entry fails verification.
3. **Conventional Commits are enforced by hook.** Your commit won't land without it. This is on purpose — it drives the `[BROKEN]` recovery path and feeds changelog generation.

Everything else is at Claude's discretion.
