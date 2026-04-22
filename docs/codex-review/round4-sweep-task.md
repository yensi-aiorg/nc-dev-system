# Task: Full repo sweep + fix everything you find

You are Codex. You've reviewed this repo three times already. The
prior review requests and responses are on disk at:

- `docs/codex-review/review-response.md` (R1)
- `docs/codex-review/review-response-round2.md` (R2)
- `docs/codex-review/review-response-round3.md` (R3)

Read those first if helpful.

This pass is different. **You are not reviewing — you are fixing.**
You have `--full-auto --sandbox danger-full-access` in the repo at
`/Users/nrupal/dev/yensi/dev/nc-dev-system`, branch
`claude-orchestrator-migration`. Make changes directly.

## Scope

Do a **full sweep of the repo**. You're not restricted to the
hardening diff — look at anything on the branch. Focus on the V3
pipeline (`src/ncdev/v3/`, `src/ncdev/ai_session.py`,
`src/ncdev/claude_session.py`, `scripts/ncdev-hooks/`) but don't
ignore everything else if something there is broken.

The previous three rounds already fixed the big architectural
issues. You're looking for:

- Remaining bugs (including anything you flagged in R3 that I
  didn't fully address)
- New bugs introduced by my R2/R3 hardening passes
- Edge cases the existing tests don't cover
- Code that's technically correct but fragile (narrow this list —
  don't refactor style)
- Test coverage gaps in load-bearing code
- Any dead code or obviously wrong artifacts left over from the
  migration that should be deleted

## What to do

1. **Investigate.** Use whatever tools you need — rg, grep, file
   reads, running the test suite, running individual scripts.
2. **Fix what you find.** Write the code changes yourself. Do not
   produce a list for me to apply.
3. **Add or update tests** to pin the fixes — don't rely on the
   existing suite to catch regressions you just fixed.
4. **Run the full test suite** (`python3 -m pytest -q`) before you
   stop. All tests must pass. If a test you wrote doesn't pass, fix
   the code until it does.
5. **Do not commit.** Leave changes staged / unstaged — I'll review
   the diff, run my own verification, and commit.
6. **Do not push.** Ever.

## Explicit out-of-scope

- Don't rewrite modules wholesale unless genuinely necessary. If
  something needs a large rewrite, explain why in your final summary
  and leave a TODO rather than doing it in this pass.
- Don't touch `.git/` or reset anything.
- Don't modify `.nc-dev/v2/config.yaml` or any `.env*` file unless
  it's the direct fix for a bug.
- Don't add new dependencies. Work with what's in `pyproject.toml`
  today.
- Don't regenerate `prompts/protocols/codex-via-bash.md` unless you
  actually find a bug in the guidance it gives.
- Don't delete the prior review docs under `docs/codex-review/`.

## Cost discipline

You're billed per token. The full sweep should probably touch 5–20
files, not 200. If you find yourself wandering into unrelated areas,
stop.

## Output

When you're done, write a final response with:

1. **Changes made** — bulleted list of files touched and *why*
2. **Tests added** — what you pinned
3. **Tests result** — full-suite pass count (`X passed`)
4. **Anything deferred** — issues you saw but didn't fix, with
   reasoning
5. **Ready to inherit?** — yes/no with the one remaining blocker if any

## Context on the codebase

NC Dev is a Claude-orchestrator for autonomous development. The
migration on this branch replaced a prescriptive prompt + Python
build-ladder with a thin orchestrator that spawns one Claude session
per feature, delegates implementation to Codex via Bash, enforces a
verification contract, and commits on pass. Mode switch
(`.nc-dev/v2/config.yaml` `mode:`) flips who does what without code
changes: `claude_plan_codex_build` (default), `codex_only`,
`claude_only`, `openrouter` (API stub), `custom` (hand-tuned routing).

CLAUDE.md and AGENTS.md describe the shape in detail if needed.

Go. Fix what's broken. Leave the repo better than you found it.
