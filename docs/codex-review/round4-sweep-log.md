OpenAI Codex v0.121.0 (research preview)
--------
workdir: /Users/nrupal/dev/yensi/dev/nc-dev-system
model: gpt-5.4
provider: openai
approval: never
sandbox: workspace-write [workdir, /tmp, $TMPDIR, /Users/nrupal/.codex/memories]
reasoning effort: medium
reasoning summaries: none
session id: 019db669-fd42-70f0-a5c7-4d98d24492de
--------
user
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

codex
I’m doing a repo sweep with emphasis on the V3 pipeline, prior review follow-ups, and verification paths. I’ll start by reading the existing review notes and the current branch/test state, then I’ll reproduce issues, patch them, add coverage, and finish by running the full suite.
  → Read prior review notes and inspect current branch/test state
  • Identify remaining defects in load-bearing V3/session/hook code
  • Implement targeted fixes and add regression tests
  • Run full pytest suite and verify clean pass
exec
/bin/zsh -lc "sed -n '1,260p' docs/codex-review/review-response-round2.md" in /Users/nrupal/dev/yensi/dev/nc-dev-system
exec
/bin/zsh -lc "sed -n '1,220p' docs/codex-review/review-response.md" in /Users/nrupal/dev/yensi/dev/nc-dev-system
exec
/bin/zsh -lc "sed -n '1,260p' docs/codex-review/review-response-round3.md" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
OpenAI Codex v0.121.0 (research preview)
--------
workdir: /Users/nrupal/dev/yensi/dev/nc-dev-system
model: gpt-5.4
provider: openai
approval: never
sandbox: workspace-write [workdir, /tmp, $TMPDIR, /Users/nrupal/.codex/memories]
reasoning effort: medium
reasoning summaries: none
session id: 019db60a-61cb-7fb0-873f-80bd2ab68493
--------
user
# Peer review request — Round 2, post-hardening

You are Codex. I am Claude. You reviewed this branch
(`claude-orchestrator-migration` at
`/Users/nrupal/dev/yensi/dev/nc-dev-system`) two commits ago. Your first
review is on disk at `docs/codex-review/review-response.md` — read it
first so you know what you said.

I've since committed a hardening pass (`f19934b`, "fix(hardening):
address all critical issues from Codex review") that claims to resolve
every critical item from your first review. Your job this time is:

1. **Verify the fixes.** Did I actually fix what you flagged, or did I
   paper over it with a test that locks in the bug?
2. **Find new issues introduced by the fix pass.** Refactors create
   new bugs. What did I break?
3. **Recheck the concerning-but-not-critical list** from your first
   review — what's still there?
4. **Hold the bar.** If something is still weak, say so plainly. If
   something I claimed to fix is actually a nice UI around the same
   underlying bug, say that too.

## What I changed (commit `f19934b`)

### Fix 1 — mode switch actually drives V3
- New file `src/ncdev/ai_session.py`: `run_ai_session()` dispatches on
  `NCDevV2Config.mode` via `MODE_ORCHESTRATOR` (which provider runs the
  orchestrator session) and `MODE_IMPLEMENTER` (who writes code).
  - `claude_plan_codex_build` → Claude session with Codex protocol injected.
  - `claude_only` → Claude session, Codex protocol suppressed.
  - `codex_only` → `run_codex_session()`, new runner, shells `codex exec`
    directly; no skills, no hooks, no Codex protocol.
  - `openrouter` → `raise NotImplementedError(...)` with a concrete
    actionable message.
  - `custom` → defaults to Claude orchestrator + Codex implementer.
- `charter.py`, `design_phase.py`, `claude_executor.py`, `dev.py` now
  call `run_ai_session` and forward a `config: NCDevV2Config` kwarg.
- `engine.py:run_v3_full()` loads the v2 config via
  `ensure_default_v2_config(workspace)` and threads it through every
  phase call.

### Fix 2 — charter + design phase boundaries
- `charter.py`: removed the greenfield hard-fail from the prompt (that
  was Phase B doing Phase C's job).
- `design_phase.py`:
  - `_stitch_prompt` path corrected (`outputs/feature-queue.json`,
    was `outputs/../feature-queue.json`).
  - `existing_design_system_present()` now requires a known
    token-file name (see `_TOKEN_FILE_NAMES`), not any non-empty file.
  - `DESIGN_TOOLS` split into `STITCH_DESIGN_TOOLS` (full kit) and
    `SUMMARISE_DESIGN_TOOLS` (`Read,Glob,Grep,Write` only). Brownfield
    summariser branch uses the restricted set.
  - New `_finalise_design_phase(session, output_dir)`: every non-skip
    branch funnels through this; requires `session.success == True`
    AND a parseable `design-system.json`, otherwise `hard_failed=True`
    with a specific reason.

### Fix 3 — verification contract is enforced
- `claude_executor._post_session_verification`:
  - Runs `bundle.verification.backend_test_command` and
    `frontend_test_command` via shell, captures output into
    `TestResult`.
  - `minimum_test_count` enforced by `_count_test_files()` across
    conventional patterns.
  - `required_screenshots` matched by existence under
    `.ncdev/evidence/`, `evidence/screenshots/`, `docs/screenshots/`.
  - `backend_health_url` best-effort HTTP probe via `httpx`; recorded
    in `app_boots` but NOT a hard failure (feature may have been
    built correctly without leaving the app running).
  - `_grep_for_prohibited` now uses `re.search()` with literal
    substring fallback on `re.error` — fixes silent no-match of regex
    entries like `r"except:\s*pass"`.
- New flags `run_test_commands` and `probe_health` on the executor
  allow tests to opt out of real shell-outs.

### Fix 4 — dependency gating
- `engine._unmet_dependencies(feature, completed)`: returns the list
  of `depends_on_features` ids that aren't in a PASSED or SKIPPED
  completed state.
- In the feature loop: unmet deps → feature marked `SKIPPED` with the
  reason, session not spawned. `--strict-deps` CLI flag halts the whole
  run at the first broken dep (default: skip-and-continue).

### Fix 5 — subprocess pipe handling
- `claude_session.py`: thread-per-pipe readers. Stderr is drained in
  a background thread so pipe backpressure can't deadlock the child.
- Watchdog thread: kills the whole process group via `os.killpg()`
  (POSIX) / `terminate`→`kill` chain (Windows) on wall-clock timeout.
  `timeout_fired` event communicates expiry back to the main loop.
- `retain_events=False` by default. Ring buffer of 20 events kept
  for the `final_text` fallback; full list only when opt-in.
- Two integration tests spawn real child processes:
  `test_watchdog_actually_kills_hung_subprocess` (infinite-sleep child,
  timeout=2s, asserts kill within 15s) and
  `test_stderr_backpressure_does_not_deadlock` (~2MB stderr flood while
  stdout is tiny, asserts completion within 10s).

### Fix 6 — feature-local asset scan
- `verify_manifest_covers_references(project_root, feature_id,
  touched_files=...)` scans only the given files when provided;
  otherwise falls back to the global scan.
- `claude_executor` passes `files_created + files_modified` from the
  `_diff_since(pre_commit)` call, so each feature is only judged on
  what it actually touched.

### Fix 7 — small fixes
- `claude_executor._commit_broken()` now returns `bool`, logs git
  stderr on failure, no more silent recoverability loss.
- `pre_bash_guard._extract_commit_message()` returns
  `(message, parse_mode)`; handles escaped quotes in `-m` properly,
  detects `-F <file>` and HEREDOC forms and allows them through
  cleanly rather than silently skipping enforcement.
- `max_repair_attempts` moved to end of `run_v3_full` signature with
  an explicit "retained for CLI compat, no-op" comment.

## Numbers

- **411 tests passing** (was 372). 39 new tests cover the regressions
  you flagged.
- Diff `a91fd24..f19934b`: 7 source files modified, 1 new
  (`ai_session.py`), 5 test files extended, 2 new test files.

## Files to look at this round

Don't re-review the whole system. Focus on the fixes:

- `src/ncdev/ai_session.py` — new dispatcher. Is it right? Does every
  branch actually land on the right runner? Edge cases in
  `run_codex_session`?
- `src/ncdev/claude_session.py` lines ~230–380 — subprocess handling.
  Thread safety on the shared lists (`stderr_chunks`, `events`,
  `skills`, `tool_calls`, etc.)? Can the watchdog fire mid-read and
  produce torn state? Is the ring-buffer logic sound?
- `src/ncdev/v3/claude_executor.py` — verification enforcement +
  feature-local asset scan + `_commit_broken` return-code handling.
  Is the TestResult population correct (we set `passed=1 / failed=0`
  based on shell exit, which is cruder than parsing pytest output —
  is that OK given the goal is "did the suite run and succeed")?
- `src/ncdev/v3/design_phase.py` — `_finalise_design_phase` funnel.
  Is it correctly called from all four branches? Does it handle the
  non-UI skip path without breaking?
- `src/ncdev/v3/engine.py` — dep gating loop. Does the skip path
  update state correctly? Does the `--strict-deps` break exit the
  loop cleanly? Does the config load through to every phase?
- `scripts/ncdev-hooks/pre_bash_guard.py` — new message extraction.
  Are there commit-message shapes I still miss?

## Specific questions

1. **Thread safety in `run_claude_session`.** The main thread iterates
   stdout and appends to `events`, `tool_calls`, `skills`, `codex_calls`,
   `subagents`, `files_touched`. The stderr thread appends to
   `stderr_chunks`. The watchdog thread only reads `proc.poll()` and
   calls `_kill_process_tree`. Is there a race I'm missing?
2. **Ring buffer correctness.** `retain_events=False` path keeps last
   20 events for `final_text` fallback. What if the `result` event is
   the 25th event and gets trimmed before the loop ends? (Hint: I
   think it's fine because we extract `final_text` inline on the
   `result` event, but you tell me.)
3. **`run_codex_session` robustness.** It uses `subprocess.run()` with
   `capture_output=True` — what happens if Codex emits a lot of output?
   Do we risk the same stderr backpressure we just fixed in the Claude
   runner?
4. **`_unmet_dependencies` when a dep is literally not in the feature
   queue.** A feature_id in `depends_on_features` that doesn't
   correspond to any queued feature will always be "unmet". Is that
   the right policy, or should we error earlier at charter-load time?
5. **`_commit_broken` interaction with hooks.** The PreToolUse hook
   wraps Claude's Bash tool — but `_commit_broken` is a Python-side
   `subprocess.run`, not a Claude tool call. So a repo-level git
   pre-commit hook (`.git/hooks/pre-commit`) could reject it and we'd
   correctly log the failure. But the NC Dev PreToolUse hook has zero
   reach here. Does the comment/logging make this clear enough to the
   reader, or do we need a named "out of scope" in code?
6. **Custom mode semantics.** I defaulted `custom` to
   `orchestrator=claude, implementer=codex`. What if a user declared
   `custom` specifically to route everything through Codex by
   hand-editing `routing:`? My dispatcher ignores their hand-tuned
   routing. Is that the right call, or should `custom` actually
   consult `provider_dispatch.get_provider_for()` per task_key?

## Output shape

Same format as round 1. Keep it focused on what changed; ignore things
that didn't.

```
## Architecture verdict
<one paragraph>

## Fixes verified (the good)
<which fixes actually landed correctly>

## Fixes that didn't land
<claims in the commit message that don't match the code>

## New issues introduced
<bugs in the hardening pass>

## Previously concerning, still concerning
<things from round 1 that aren't in the critical list but still smell>

## Now truly over-engineered
<complexity I added that isn't pulling its weight>

## Honest one-liner
<would you inherit it now?>
```

Don't soften. Go.

codex
Reviewing the previous review first, then I’ll inspect the hardening commit and the targeted files to verify whether the fixes actually changed behavior or just changed tests.
exec
/bin/zsh -lc 'pwd && git rev-parse --abbrev-ref HEAD && git rev-parse HEAD && rg -n "''^## " docs/codex-review/review-response.md && sed -n '"'1,240p' docs/codex-review/review-response.md" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
/Users/nrupal/dev/yensi/dev/nc-dev-system
claude-orchestrator-migration
f19934bcd31d3c47c14e2ac75e5b27e48f4bb860
22:## Context — what this repo is
40:## What I just migrated it to
90:## Mode switch (the user's budget lever)
103:## Hooks
119:## The four migration commits
139:## Files to read (in roughly this order)
189:## Specific questions I want answered
250:## Format of your response
255:## Architecture verdict
258:## Strengths
261:## Critical issues
264:## Concerning but not critical
267:## Over-engineered / could be deleted
270:## Missing
273:## Test coverage gaps
276:## Honest one-liner
6763:## Architecture verdict
6766:## Strengths
6773:## Critical issues
6783:## Concerning but not critical
6790:## Over-engineered / could be deleted
6796:## Missing
6802:## Test coverage gaps
6809:## Honest one-liner
6813:## Architecture verdict
6816:## Strengths
6823:## Critical issues
6833:## Concerning but not critical
6840:## Over-engineered / could be deleted

 succeeded in 0ms:
OpenAI Codex v0.121.0 (research preview)
--------
workdir: /Users/nrupal/dev/yensi/dev/nc-dev-system
model: gpt-5.4
provider: openai
approval: never
sandbox: workspace-write [workdir, /tmp, $TMPDIR, /Users/nrupal/.codex/memories]
reasoning effort: medium
reasoning summaries: none
session id: 019db5e0-0add-7dd1-9004-d94dffcbcddb
--------
user
# Peer review request — NC Dev System, Claude-orchestrator migration

You are Codex, and I am Claude. We normally work as peers when building
code: I plan and review, you implement and write tests. Right now I'm
asking you to step out of that dynamic and do a full **critical
engineering review** of a system I just architected and built. I want
you to look at it with fresh eyes — you had no part in the design — and
tell me where it's weak, wrong, or over-engineered.

## Context — what this repo is

**nc-dev-system** (`/Users/nrupal/dev/yensi/dev/nc-dev-system`,
branch `claude-orchestrator-migration`).

The user wanted an autonomous development system that takes a PRD and
builds a full application. The old version had a 9-artifact discovery
pipeline, a per-task provider router with 11 task types, prescriptive
multi-kilobyte build prompts (`FRONTEND_METHODOLOGY`, `GUARDRAILS`,
`QUALITY_STANDARDS`, `INFRASTRUCTURE_STANDARDS`), a Python build/verify/
repair ladder, and it invoked Claude and Codex as raw text-in/text-out
CLIs — not using any of Claude Code's skill/subagent/hook machinery.

The user's observation: that design was written for a less-capable
model era. Today's Claude Code is not a text generator; it's an agent
runtime with skills, subagents, hooks, MCP servers. NC Dev was
reimplementing in Python things the runtime already does better.

## What I just migrated it to

Architecture:

```
ncdev full --source prd.md
  │
  ├─ Preflight (git, claude, codex, Citex, optionally Stitch MCP)
  ├─ Phase 2: Charter (one Claude planning session)
  │     → target-project-contract.json (hard architectural constraints)
  │     → verification-contract.json   (what "done" means)
  │     → feature-queue.json           (ordered features)
  ├─ Phase 3: Design system
  │     ├─ Greenfield UI + Stitch MCP    → Stitch generates tokens + screens
  │     ├─ Brownfield + existing designs → Claude summarises
  │     ├─ Brownfield + no designs       → Claude's frontend-design skill
  │     └─ Greenfield + neither          → HARD FAIL
  ├─ Phase 4: Brownfield context ingestion into Citex (RAG)
  ├─ Phase 5: Sequential feature execution
  │     for each feature:
  │       one Claude session with tools [Read,Write,Edit,Glob,Grep,Bash,Skill,Task]
  │       system prompt includes Codex-via-Bash protocol
  │       hooks wired via --settings (block non-conventional commits, prohibited patterns, force-push)
  │       Claude uses skills: writing-plans, test-driven-development,
  │                           verification-before-completion, systematic-debugging
  │       Claude shells to Codex for implementation + test writing:
  │           codex exec --full-auto --sandbox danger-full-access "<scoped task>"
  │       Claude emits .ncdev/assets-needed/<fid>.json during build
  │       Claude commits with Conventional Commits on verification pass
  │     NC Dev streams events, checks git state, tags [BROKEN] on failure
  └─ Phase 6: Summary + metrics
```

Three explicit guarantees the user asked for:

1. **Codex invocation is direct Bash** — Claude runs `codex exec
   --full-auto --sandbox danger-full-access "<prompt>"` from its Bash
   tool. No Claude-subagent-wraps-Codex indirection (would be paying
   Claude tokens to babysit a Codex call). Codex gets the
   implementation work raw.
2. **Greenfield UI without design system = hard fail.** If there's no
   Stitch MCP configured and no `docs/design-system/` on disk and the
   project is greenfield, the run aborts with an actionable error. No
   "Claude generates tokens itself" fallback for greenfield.
   Brownfield lets Claude decide.
3. **Asset manifest during build, not after.** Every feature session
   must emit `.ncdev/assets-needed/<feature_id>.json` while building.
   Verification scans committed code for asset references and fails
   the feature if references aren't covered by the manifest.

## Mode switch (the user's budget lever)

`.nc-dev/v2/config.yaml` has `mode:`. Flip one line, no code change:

- `claude_plan_codex_build` (default): Claude plans/reviews, delegates impl to Codex via Bash
- `codex_only`: Codex does everything (token-lean days)
- `claude_only`: Claude does everything (no Codex)
- `openrouter`: API-only, needs `OPENROUTER_API_KEY`
- `custom`: hand-tuned routing

Implemented via `MODE_PRESETS` in `src/ncdev/v2/config.py` and a
`model_validator` that stamps `RoutingConfig` from the preset.

## Hooks

`scripts/ncdev-hooks/settings.json` wires a `PreToolUse` hook on Bash
that runs `scripts/ncdev-hooks/pre_bash_guard.py`. The hook:

1. Blocks `git commit` commands whose `-m` message is not Conventional
   Commits (feat/fix/test/chore/refactor/docs/perf/style/build/ci/revert).
2. Inspects the staged diff for prohibited patterns (`TODO`, `FIXME`,
   `console.log(`, "Not yet implemented") and blocks commits that add them.
3. Blocks `git push --force` to main/master/production unless
   `NCDEV_ALLOW_FORCE_PUSH=1`.

The hook is wired automatically by `run_claude_session()` via
`--settings` whenever `enable_ncdev_hooks=True` (default). Caller's
own `settings_path` takes precedence.

## The four migration commits

```
dbeb687 Phase A — Claude session runner + Codex-via-Bash protocol
48f8991 Phase B-C-D — charter + design phase + asset manifest
fdb8807 Phase E-F-G-H — Claude-driven executor, thin dev.py, engine rewrite, hooks
a91fd24 Phase I — delete dead modules, update CLI, rewrite docs
```

Diff vs `main`: 34 files, +4830 / -4331 lines. 372 tests passing.

---

# What I want from you

**Read the code. Form your own opinion. Be blunt.** I explicitly don't
want a polite "this looks great." I want to know what's wrong, what's
fragile, what's over-built, what's missing, what I got subtly
incorrect.

## Files to read (in roughly this order)

Start with the primitive and work up:

1. `src/ncdev/claude_session.py` — **the foundation**. One function
   everything depends on. Does it parse stream-json robustly? Is the
   event signal extraction correct? Is the cost-ceiling, timeout,
   hook-wiring plumbing sound? Will it deadlock on a misbehaving
   Claude process? Does it leak file handles on error paths?
2. `prompts/protocols/codex-via-bash.md` — the protocol Claude reads
   at session start. Is the guidance Codex-prompt-shape-correct?
   Anything that would produce sprawling, unfocused Codex work?
   Cost discipline rules reasonable?
3. `src/ncdev/v3/charter.py` — Phase B. Does the prompt actually elicit
   the three artifacts correctly? Is the schema hinting
   (`_schema_excerpt`) precise enough or hand-wavy? Would a real Claude
   session produce valid JSON from this, or will validation fail most
   of the time?
4. `src/ncdev/v3/models.py` — the pydantic schemas. Are
   `TargetProjectContract`, `VerificationContract`, `CharterBundle`,
   `DesignSystemDoc`, `AssetManifestEntry`, `AssetManifest` right
   for the job? Missing fields that will bite us? Over-rigid types?
5. `src/ncdev/v3/design_phase.py` — Phase C. The four-branch decision
   (Stitch / existing / claude_generated / hard-fail) — correct? Is
   the `stitch_available()` probe useful or just theatre? What
   happens when Stitch works partially?
6. `src/ncdev/v3/asset_manifest.py` — Phase D. `scan_code_for_asset_references`
   regexes — will they over-match or under-match? What assets will
   they miss? What about fingerprinted URLs? Is `verify_manifest_covers_references`
   the right enforcement point?
7. `src/ncdev/v3/claude_executor.py` — Phase E. **The main work unit.**
   Is the prompt telling Claude enough? Too little? Is the post-hoc
   verification the right shape (or should we trust
   `verification-before-completion` entirely)? Is `_commit_broken`
   recoverability enough, or will it create a mess across features?
   What about mid-feature session death (timeout, budget cap, crash)?
8. `src/ncdev/dev.py` — Phase F. The `ncdev dev` thin path. Too thin?
   What's missing compared to what a reasonable freeform dev session
   needs?
9. `src/ncdev/v3/engine.py` — Phase G. The top-level orchestrator.
   Does it handle partial success correctly? What about resuming
   after a crashed run?
10. `scripts/ncdev-hooks/pre_bash_guard.py` — Phase H. The hook. Is
    the commit-message extraction regex good enough? Will the
    staged-diff scan work on binary files (crash? skip?). Anything
    an adversarial Claude could bypass?
11. `src/ncdev/v2/config.py` — `MODE_PRESETS` + `mode` validator.
    Is the preset-always-overrides-routing behaviour confusing?
    What if someone hand-edits `routing:` with `mode: claude_plan_codex_build`?

## Specific questions I want answered

**Robustness**

- `claude_session.py` subprocess handling: what happens if Claude
  writes 100k lines of stream events? Is stdout buffering / Popen
  line-mode going to cause issues? Memory growth on long runs?
- `_extract_event_signals`: the stream-json schema is not stable
  across Claude Code versions. How brittle is my parser?
- `claude_executor._commit_broken`: if git commit itself is blocked
  by the hook (Conventional Commits), the BROKEN-tag commit will
  fail — does the current code notice?
- `pre_bash_guard._extract_commit_message`: what happens with
  `git commit -m "feat: add \"escaped\" quotes"`? Multi-line heredoc?

**Architectural soundness**

- Is "one Claude session per feature" really the right unit? Claude's
  context limit is finite. For a feature that touches 50 files with
  a complex data flow, will one session run out of room? Should we
  have session-per-sub-feature with a shared Citex query layer?
- Claude shells to Codex via Bash — does this actually leverage Codex
  effectively, or will Claude just do the work itself most of the
  time because Bash is slower than Edit for small changes?
- The hard-fail on greenfield UI without design system: right bar,
  or too strict? Should we have a `--skip-design` escape hatch for
  prototyping?
- The asset manifest enforcement: we fail features that reference
  unlisted assets. What about legitimately-missing-assets during
  iteration — is this going to cause frustrating re-runs?

**What's missing**

 succeeded in 0ms:
OpenAI Codex v0.121.0 (research preview)
--------
workdir: /Users/nrupal/dev/yensi/dev/nc-dev-system
model: gpt-5.4
provider: openai
approval: never
sandbox: workspace-write [workdir, /tmp, $TMPDIR, /Users/nrupal/.codex/memories]
reasoning effort: medium
reasoning summaries: none
session id: 019db65d-8d84-7423-ad6a-17fb975c9446
--------
user
# Peer review request — Round 3, post-R2-hardening

You are Codex. This is the third pass. Your first two reviews are on
disk at `docs/codex-review/review-response.md` and
`review-response-round2.md` — read them first so you know what you said.

Since round 2, I committed `4a5a0f7` ("fix(hardening-r2): address
regressions from Codex round-2 review") on
`claude-orchestrator-migration`. It claims to close every critical /
didn't-land / new-bug item from your round-2 review. Your job now:

1. **Verify the R2 fixes landed correctly.** In particular, check the
   fixes I claimed for issues you called "didn't land" and "new issues
   introduced" last time.
2. **Find bugs I introduced in the R2 pass.** Same pattern as R2
   itself — refactors create new bugs.
3. **Reassess the "previously concerning" list** — any of those now
   graduated to critical? Any still open?
4. **Tell me if it's ready to inherit yet.** If not, what's the one
   or two remaining blockers?

Don't repeat ground already covered unless the code regressed. Focus on
what changed in `4a5a0f7` vs `f19934b`.

## What I changed in R2 (commit `4a5a0f7`)

### Fix A — `_commit_broken` NameError
Added `import logging` + `logger = logging.getLogger(__name__)` to
`src/ncdev/v3/claude_executor.py`. Replaced all three
`console.print(...)` calls with `logger.warning(...)`. The function no
longer references a non-existent `console`.

### Fix B — `_commit_broken` return value wired
The caller in `execute_feature_claude_driven()` now does:

```python
if dirty:
    if _commit_broken(target_path, feature):
        post_commit = _git_head(target_path)
    else:
        recoverability_note = (
            " | recoverability: [BROKEN] commit failed — dirty "
            "working tree remains; see log for git error"
        )
    status = StepStatus.FAILED
```

and `recoverability_note` is appended to `StepResult.error_message`.

### Fix C — dep gate SKIPPED conflation
Added `StepStatus.BLOCKED` to `v3/models.py`. In the engine's feature
loop, dep-gated features are now `status=StepStatus.BLOCKED` (not
`SKIPPED`). `_unmet_dependencies` counts only `PASSED` + `SKIPPED`
(brownfield) as satisfied; `FAILED` + `BLOCKED` are unmet. The R1 test
that codified the bug (`SKIPPED counts as satisfied`) is replaced with
`test_blocked_dep_does_NOT_count_as_satisfied`.

### Fix D — `--strict-deps` status reporting
`state.status` computation now bucket-sorts into `unsuccessful = [r
for r in completed if r.status in (FAILED, BLOCKED)]` and uses that
instead of just checking `FAILED`. A dep-halted run reports `failed`
or `partial`, never `passed`.

### Fix E — `custom` mode honours hand-tuned routing
Removed `custom` from `MODE_ORCHESTRATOR` / `MODE_IMPLEMENTER`
hardcoded maps. Added `_resolve_custom_providers(cfg)` in
`ai_session.py`:

```python
def _resolve_custom_providers(cfg: NCDevV2Config) -> tuple[str, str]:
    from ncdev.provider_dispatch import resolve_provider_name
    review_chain = cfg.routing.review or ["anthropic_claude_code"]
    impl_chain = cfg.routing.implementation or ["openai_codex"]
    orch = resolve_provider_name(review_chain[0])
    impl = resolve_provider_name(impl_chain[0])
    return orch, impl
```

Dispatch branches into this helper when `cfg.mode == "custom"`. Three
new tests pin the shapes: `custom` with all-claude, all-codex, and
plan-build-style routing.

### Fix F — hook regex parity with the verifier
`pre_bash_guard._check_staged_for_prohibited` now uses `re.search`
with a literal-substring fallback on `re.error`. Same semantics as
`claude_executor._grep_for_prohibited`. A regex-like pattern in the
contract's `prohibited_patterns` will fire at commit time now, not
only post-hoc.

### Fix G — `run_codex_session` hardened
Replaced `subprocess.run(capture_output=True, ...)` with a Popen +
thread-per-pipe reader + watchdog + `_TailBuffer` pattern that mirrors
`run_claude_session`. `_TailBuffer` accumulates text but keeps only
the tail `max_bytes_per_stream` (default 4 MB per stream). Extracted
`_kill_process_tree()` helper for reuse. Two integration tests: hung
child killed by watchdog within 15 s; 200 KB stream cap enforced.

### Fix H — health probe is hard when URL is set
In `_post_session_verification`:

```python
if probe_health and bundle.verification.backend_health_url:
    reachable = _probe_health(
        bundle.verification.backend_health_url,
        timeout=bundle.verification.boot_timeout_seconds,
    )
    ver.app_boots = reachable
    if not reachable:
        reasons.append(
            f"backend health URL unreachable: "
            f"{bundle.verification.backend_health_url} — the feature "
            "must leave the app in a runnable state"
        )
```

Two tests: URL set + unreachable → feature fails;  URL empty → probe
skipped, feature still passes.

### Numbers
- **418/418 tests passing** (was 411). +7 regression tests.
- Diff `f19934b..4a5a0f7`: 9 source + test files modified, 2 docs added.

## Files to look at this round

- `src/ncdev/v3/claude_executor.py` — particularly the new `logger`
  setup, the `recoverability_note` flow, and the hardened health-probe
  branch.
- `src/ncdev/v3/engine.py` — BLOCKED handling in the feature loop,
  and the new status computation. Does the change make
  `state.completed_features` still correct (it only counts PASSED)?
- `src/ncdev/v3/models.py` — new `BLOCKED` enum value. Any place
  that switches on `StepStatus` and now needs to handle BLOCKED?
- `src/ncdev/ai_session.py` — `_resolve_custom_providers()` and the
  new `run_codex_session` Popen implementation. Thread-safety of
  the `_TailBuffer`?
- `scripts/ncdev-hooks/pre_bash_guard.py` — regex compile +
  literal-fallback parity with the verifier.
- The three dep-gating tests in
  `tests/test_ncdev_v3/test_dependency_gating.py` — do they correctly
  differentiate brownfield SKIPPED (good) from BLOCKED (bad)?

## Specific questions

1. **StepStatus.BLOCKED unhandled somewhere.** Are there any other
   code paths that switch on `StepStatus` (metrics, state scanner,
   Citex reporting, summary tables) that need a BLOCKED case added?
2. **`_resolve_custom_providers()` for unknown provider names.** If a
   user sets `review: ["something_weird"]`, `resolve_provider_name`
   raises `ValueError`. Does `run_ai_session` bubble that sensibly, or
   would it crash mid-run?
3. **`_TailBuffer` bytes vs characters.** I encode each chunk to
   compute its length, then re-encode the head to drop. For multi-byte
   characters this is correct but the slicing on `text()` returns the
   concatenated strings, not trimmed-to-exactly-max-bytes. Is that
   acceptable, or should the tail be exactly bytes-bounded?
4. **`recoverability_note` placement.** I append it to
   `StepResult.error_message` only in the failure branch. If the
   broken commit succeeds, the note is empty string — good. But what
   if the caller reads `error_message` expecting it to be JSON or
   empty on pass? Does this break anyone?
5. **Health-probe hardness + flaky apps.** Now that the probe is a
   hard failure when URL is set, a feature that builds everything
   correctly but takes 90 seconds to boot (slower than
   `boot_timeout_seconds=60`) fails. Is that better or worse than the
   old soft signal? Should there be a retry policy?
6. **Status computation edge case.** If the entire feature list is
   SKIPPED (brownfield rerun, nothing to do), `unsuccessful` is
   empty and `passed` is empty. Current code:
   `"passed" if not unsuccessful else ("partial" if passed else "failed")`
   — so it reports `"passed"`. Is that right, or should an empty
   build report a different status like `"noop"`?

## Output shape

Same format as R2, but if everything really did land, say so plainly:

```
## Architecture verdict
<one paragraph>

## R2 fixes verified
<which ones actually closed the issue>

## R2 fixes that still didn't land
<any claims in the R2 commit that don't match the code>

## New issues introduced in R2
<regressions this pass created>

## Still open from earlier rounds
<unresolved concerns>

## Ready to inherit?
<yes/no + the one thing still blocking, if any>

## Honest one-liner
```

Don't soften. If the blocker list is now empty, say that plainly too.
Go.

codex
I’m reading the prior two review responses and the delta from `f19934b..4a5a0f7` first, then I’ll verify the claimed fixes against the code and tests before I call any remaining blockers.
exec
/bin/zsh -lc "sed -n '1,240p' docs/codex-review/review-response.md" in /Users/nrupal/dev/yensi/dev/nc-dev-system
exec
/bin/zsh -lc "sed -n '1,260p' docs/codex-review/review-response-round2.md" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
OpenAI Codex v0.121.0 (research preview)
--------
workdir: /Users/nrupal/dev/yensi/dev/nc-dev-system
model: gpt-5.4
provider: openai
approval: never
sandbox: workspace-write [workdir, /tmp, $TMPDIR, /Users/nrupal/.codex/memories]
reasoning effort: medium
reasoning summaries: none
session id: 019db60a-61cb-7fb0-873f-80bd2ab68493
--------
user
# Peer review request — Round 2, post-hardening

You are Codex. I am Claude. You reviewed this branch
(`claude-orchestrator-migration` at
`/Users/nrupal/dev/yensi/dev/nc-dev-system`) two commits ago. Your first
review is on disk at `docs/codex-review/review-response.md` — read it
first so you know what you said.

I've since committed a hardening pass (`f19934b`, "fix(hardening):
address all critical issues from Codex review") that claims to resolve
every critical item from your first review. Your job this time is:

1. **Verify the fixes.** Did I actually fix what you flagged, or did I
   paper over it with a test that locks in the bug?
2. **Find new issues introduced by the fix pass.** Refactors create
   new bugs. What did I break?
3. **Recheck the concerning-but-not-critical list** from your first
   review — what's still there?
4. **Hold the bar.** If something is still weak, say so plainly. If
   something I claimed to fix is actually a nice UI around the same
   underlying bug, say that too.

## What I changed (commit `f19934b`)

### Fix 1 — mode switch actually drives V3
- New file `src/ncdev/ai_session.py`: `run_ai_session()` dispatches on
  `NCDevV2Config.mode` via `MODE_ORCHESTRATOR` (which provider runs the
  orchestrator session) and `MODE_IMPLEMENTER` (who writes code).

exec
/bin/zsh -lc 'git status --short' in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
?? docs/codex-review/review-request-round4.md
?? docs/codex-review/review-response-round4.md
?? docs/codex-review/round4-sweep-log.md
?? docs/codex-review/round4-sweep-task.md

exec
/bin/zsh -lc "rg --files src/ncdev tests scripts/ncdev-hooks | sed -n '1,260p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
scripts/ncdev-hooks/settings.json
scripts/ncdev-hooks/pre_bash_guard.py
tests/test_preflight.py
tests/test_cli.py
src/ncdev/provider_dispatch.py
src/ncdev/preflight.py
src/ncdev/__main__.py
src/ncdev/claude_session.py
src/ncdev/intake_api.py
src/ncdev/dev.py
tests/integration/test_quality_gate_e2e.py
tests/conftest.py
tests/fixtures/sample_requirements.md
src/ncdev/v3/asset_manifest.py
src/ncdev/v3/state_scanner.py
src/ncdev/v3/design_phase.py
src/ncdev/v3/engine.py
src/ncdev/v3/__init__.py
src/ncdev/v3/context_ingestion.py
src/ncdev/v3/models.py
src/ncdev/v3/metrics.py
src/ncdev/v3/citex_client.py
src/ncdev/v3/charter.py
src/ncdev/v3/claude_executor.py
src/ncdev/utils.py
src/ncdev/cli.py
tests/fixtures/sentinel_reports/frontend_error.json
tests/fixtures/sentinel_reports/backend_error.json
tests/fixtures/sample-requirements.md
src/ncdev/adapters/base.py
src/ncdev/adapters/anthropic_claude_code.py
src/ncdev/adapters/__init__.py
src/ncdev/adapters/registry.py
src/ncdev/adapters/openai_codex.py
tests/unit/test_quality_gate_events.py
tests/unit/test_claude_executor.py
tests/unit/test_ai_session.py
tests/unit/test_quality_gate_models.py
tests/unit/test_hooks.py
tests/unit/test_dev.py
tests/unit/test_orchestrator.py
tests/unit/test_ai_provider.py
tests/unit/test_asset_manifest.py
tests/unit/test_claude_session.py
tests/unit/test_charter.py
tests/unit/test_manifest_generator.py
tests/unit/test_design_phase.py
tests/__init__.py
tests/test_ncdev_v3/test_state_scanner.py
tests/test_ncdev_v3/test_citex_client.py
tests/test_ncdev_v3/test_context_ingestion.py
tests/test_ncdev_v3/test_dependency_gating.py
tests/test_ncdev_v3/__init__.py
tests/test_ncdev_v3/test_metrics.py
src/ncdev/ai_session.py
src/ncdev/__init__.py
src/ncdev/ai_provider.py
src/ncdev/v2/sentinel_safety.py
src/ncdev/v2/routing.py
src/ncdev/v2/engine.py
src/ncdev/v2/__init__.py
src/ncdev/v2/sentinel_prompts.py
src/ncdev/v2/sentinel_callback.py
src/ncdev/v2/models.py
src/ncdev/v2/config.py
tests/test_ncdev_v2/test_v2_routing.py
tests/test_ncdev_v2/test_modes.py
tests/test_ncdev_v2/test_v2_config.py
tests/test_ncdev_v2/test_sentinel_callback.py
tests/test_ncdev_v2/test_sentinel_prompts.py
tests/test_ncdev_v2/test_sentinel_models.py
tests/test_ncdev_v2/test_sentinel_config.py
tests/test_ncdev_v2/test_sentinel_cli.py
tests/test_ncdev_v2/test_v2_adapters.py
tests/test_ncdev_v2/test_sentinel_safety.py
tests/test_ncdev_v2/__init__.py
tests/test_ncdev_v2/test_intake_api.py
tests/test_ncdev_v2/test_sentinel_engine.py
src/ncdev/artifacts/state.py
src/ncdev/artifacts/__init__.py
src/ncdev/quality_gate/manifest.py
src/ncdev/quality_gate/models.py
src/ncdev/quality_gate/config.py
src/ncdev/quality_gate/events.py
src/ncdev/quality_gate/__init__.py
src/ncdev/quality_gate/orchestrator.py

codex
I’ve got the prior review context and the working tree state. Next I’m reading the load-bearing modules and targeted tests directly to find anything still wrong in the current implementation before I start patching.
exec
/bin/zsh -lc "sed -n '1,260p' src/ncdev/ai_session.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
"""Unified AI session runner — dispatches on mode.

``run_ai_session()`` is the single entry point every phase of NC Dev
calls when it needs an AI-driven session. It reads ``NCDevV2Config.mode``
and dispatches to the right concrete runner:

    * ``claude_plan_codex_build`` → Claude session, Codex protocol
      injected so Claude shells to ``codex exec`` for implementation.
    * ``claude_only`` → Claude session, Codex protocol NOT injected;
      Claude does implementation itself.
    * ``codex_only`` → Codex CLI session, no skills / subagents / hooks;
      Codex handles the whole task directly.
    * ``openrouter`` → raises ``NotImplementedError`` (API-only, no CLI
      tooling). Caller should fall back or surface to the user.
    * ``custom`` → falls back to Claude orchestrator as a safe default.

The returned :class:`ClaudeSessionResult` is the common result shape
across runners — ``skills_invoked`` and ``codex_invocations`` are
populated only when they applied.
"""

from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Iterable

_IS_POSIX = sys.platform != "win32"

# Upper bound per stream for run_codex_session capture. A chatty codex
# run can produce a lot — we keep the tail (recent output is more
# useful than the head) and note truncation.
_CODEX_CAPTURE_MAX_BYTES = 4 * 1024 * 1024   # 4 MB per stream

from ncdev.claude_session import (
    DEFAULT_BUILD_TOOLS,
    ClaudeSessionResult,
    NCDEV_HOOKS_DIR,
    NCDEV_HOOKS_SETTINGS,
    run_claude_session,
)
from ncdev.v2.config import NCDevV2Config, load_v2_config

logger = logging.getLogger(__name__)


# Mode → which provider runs the main orchestrator session.
# "custom" is intentionally absent — it's handled by consulting the
# user's hand-tuned routing via provider_dispatch instead.
MODE_ORCHESTRATOR: dict[str, str] = {
    "claude_plan_codex_build": "claude",
    "claude_only": "claude",
    "codex_only": "codex",
    "openrouter": "openrouter",
}

# Mode → who actually writes code. Used by the Claude runner to decide
# whether to inject the Codex-via-Bash protocol (i.e. "delegate impl
# to Codex") vs do the work itself.
MODE_IMPLEMENTER: dict[str, str] = {
    "claude_plan_codex_build": "codex",
    "claude_only": "claude",
    "codex_only": "codex",
    "openrouter": "openrouter",
}


def _resolve_custom_providers(cfg: NCDevV2Config) -> tuple[str, str]:
    """For ``mode=custom``, read orchestrator + implementer from routing.

    Honours the contract stated in v2/config.py: ``custom`` preserves
    the user's hand-tuned ``routing:`` block. We use routing.review to
    pick the orchestrator (review is the "who reasons about code" task)
    and routing.implementation to pick the implementer.

    Both are mapped through :func:`provider_dispatch.resolve_provider_name`
    so long names like ``anthropic_claude_code`` become short
    registry keys (``claude``, ``codex``, ``openrouter``).
    """
    from ncdev.provider_dispatch import resolve_provider_name

    review_chain = cfg.routing.review or ["anthropic_claude_code"]
    impl_chain = cfg.routing.implementation or ["openai_codex"]
    orch = resolve_provider_name(review_chain[0])
    impl = resolve_provider_name(impl_chain[0])
    return orch, impl


def _resolve_config(
    config: NCDevV2Config | None,
    workspace: Path | None,
) -> NCDevV2Config:
    if config is not None:
        return config
    if workspace is not None:
        try:
            return load_v2_config(workspace)
        except Exception:  # noqa: BLE001
            pass
    return NCDevV2Config()


def run_ai_session(
    prompt: str,
    *,
    cwd: Path,
    config: NCDevV2Config | None = None,
    workspace: Path | None = None,
    tools: Iterable[str] = DEFAULT_BUILD_TOOLS,
    model: str | None = None,
    timeout: int = 1800,
    permission_mode: str = "acceptEdits",
    append_system_prompt: str | None = None,
    include_codex_protocol: bool | None = None,
    max_budget_usd: float | None = None,
    log_path: Path | None = None,
    on_event: Callable[[dict], None] | None = None,
    extra_args: list[str] | None = None,
    settings_path: Path | None = None,
    enable_ncdev_hooks: bool = True,
) -> ClaudeSessionResult:
    """Run an AI session, dispatching on the active mode.

    ``include_codex_protocol`` defaults to ``True`` when the mode's
    implementer is Codex (i.e. Claude should delegate), ``False`` when
    implementer is Claude. Explicit values win.
    """
    cfg = _resolve_config(config, workspace)

    if cfg.mode == "custom":
        # Honour the hand-tuned routing block — this is exactly what
        # "custom" means per the config contract.
        try:
            orch, impl = _resolve_custom_providers(cfg)
        except ValueError as exc:
            # Unknown provider name in routing — surface as a structured
            # session failure, not an uncaught exception mid-run.
            return ClaudeSessionResult(
                success=False, final_text="", exit_code=-1,
                error=(
                    f"custom mode config error: {exc}. "
                    "Check `routing.review` and `routing.implementation` "
                    "in .nc-dev/v2/config.yaml — allowed values are "
                    "'anthropic_claude_code', 'openai_codex', 'openrouter', "
                    "or the short aliases 'claude' / 'codex'."
                ),
            )
    else:
        orch = MODE_ORCHESTRATOR.get(cfg.mode, "claude")
        impl = MODE_IMPLEMENTER.get(cfg.mode, "codex")

    logger.info("run_ai_session mode=%s orch=%s impl=%s cwd=%s", cfg.mode, orch, impl, cwd)

    if orch == "openrouter":
        raise NotImplementedError(
            "openrouter mode is API-only and cannot spawn a file-editing "
            "session. Install and configure the Claude or Codex CLI and "
            "pick a CLI mode (claude_plan_codex_build, claude_only, or "
            "codex_only)."
        )

    if orch == "codex":
        return run_codex_session(
            prompt,
            cwd=cwd,
            timeout=timeout,
            model=model,
            log_path=log_path,
            extra_args=extra_args,
        )

    # orch == "claude"
    if include_codex_protocol is None:
        include_codex_protocol = (impl == "codex")

    effective_model = model or "claude-opus-4-6"
    return run_claude_session(
        prompt,
        cwd=cwd,
        tools=tools,
        model=effective_model,
        timeout=timeout,
        permission_mode=permission_mode,
        append_system_prompt=append_system_prompt,
        include_codex_protocol=include_codex_protocol,
        max_budget_usd=max_budget_usd,
        log_path=log_path,
        on_event=on_event,
        extra_args=extra_args,
        settings_path=settings_path,
        enable_ncdev_hooks=enable_ncdev_hooks,
    )


# ---------------------------------------------------------------------------
# Codex runner — used by codex_only mode
# ---------------------------------------------------------------------------


def run_codex_session(
    prompt: str,
    *,
    cwd: Path,
    timeout: int = 1800,
    model: str | None = None,
    log_path: Path | None = None,
    extra_args: list[str] | None = None,
    max_bytes_per_stream: int = _CODEX_CAPTURE_MAX_BYTES,
) -> ClaudeSessionResult:
    """Run a Codex session. No skills, no subagents, no NC Dev hooks.

    Uses the same safety primitives as :func:`run_claude_session`:
    thread-per-pipe readers so backpressure can't deadlock the child,
    watchdog that kills the process group on wall-clock timeout, and
    a tail-bounded byte buffer per stream so a chatty Codex run
    doesn't blow RAM. Returns the same :class:`ClaudeSessionResult`
    shape (common result type across runners).
    """
    if shutil.which("codex") is None:
        return ClaudeSessionResult(
            success=False, final_text="", exit_code=-1,
            error="codex CLI not found on PATH",
        )

    # Codex prompt must be scoped — no Claude skill references.
    codex_prompt = (
        prompt
        + "\n\n---\n\n"
        + "You are running in codex_only mode (no Claude orchestrator). "
        "Produce a plan, implement, write tests, and commit with "
        "Conventional Commits. Leave the working tree clean when done."
    )

    cmd: list[str] = [
        "codex", "exec",
        "--full-auto",
        "--sandbox", "danger-full-access",
    ]
    if model:
        cmd += ["--model", model]
    if extra_args:
        cmd += list(extra_args)
    cmd.append(codex_prompt)

    popen_kwargs: dict = dict(
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    if _IS_POSIX:
        popen_kwargs["start_new_session"] = True

exec
/bin/zsh -lc "sed -n '1,340p' src/ncdev/claude_session.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
"""Claude Code session runner — the single way NC Dev spawns Claude.

This is the primitive every higher-level orchestrator (discovery, feature
executor, dev loop) builds on. It spawns Claude Code in non-interactive
``--print --output-format stream-json`` mode, streams events as they
arrive, writes a full event log, and returns a structured result.

Skills, subagents, and MCP servers are controlled per call via the
``tools`` and ``append_system_prompt`` arguments. Claude's cost ceiling
is enforced by ``--max-budget-usd`` when ``max_budget_usd`` is provided —
this is the primitive the token-budget-driven mode switch hooks into.
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

IS_POSIX = sys.platform != "win32"


PROTOCOLS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts" / "protocols"
CODEX_PROTOCOL_PATH = PROTOCOLS_DIR / "codex-via-bash.md"

# Default NC Dev hooks — block commits with prohibited patterns / non-
# conventional messages, block force-push to protected branches.
NCDEV_HOOKS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "ncdev-hooks"
NCDEV_HOOKS_SETTINGS = NCDEV_HOOKS_DIR / "settings.json"


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class ToolCallRecord:
    """One tool invocation observed in the stream."""
    tool: str
    input_summary: str  # truncated string form of the input
    raw: dict


@dataclass
class ClaudeSessionResult:
    """Structured outcome of a Claude session."""
    success: bool
    final_text: str
    exit_code: int
    events: list[dict] = field(default_factory=list)
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    skills_invoked: list[str] = field(default_factory=list)
    codex_invocations: list[str] = field(default_factory=list)
    subagents_dispatched: list[str] = field(default_factory=list)
    files_touched: list[str] = field(default_factory=list)
    total_cost_usd: float | None = None
    duration_seconds: float = 0.0
    stderr: str = ""
    error: str | None = None

    def summary(self) -> str:
        parts = [
            f"success={self.success}",
            f"exit={self.exit_code}",
            f"dur={self.duration_seconds:.1f}s",
        ]
        if self.total_cost_usd is not None:
            parts.append(f"cost=${self.total_cost_usd:.3f}")
        if self.tool_calls:
            parts.append(f"tools={len(self.tool_calls)}")
        if self.skills_invoked:
            parts.append(f"skills={','.join(self.skills_invoked)}")
        if self.codex_invocations:
            parts.append(f"codex={len(self.codex_invocations)}")
        return " ".join(parts)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


# Default tool allowlist for Claude sessions that orchestrate builds.
# Caller can override completely. Tools that enable the Codex-as-peer
# architecture: Bash (to shell out to codex exec), Skill (to invoke skills
# like test-driven-development), Task (to dispatch subagents).
DEFAULT_BUILD_TOOLS: tuple[str, ...] = (
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
    "Bash",
    "Skill",
    "Task",
)

# Minimal tool set for planning-only sessions that must not edit code.
DEFAULT_PLAN_TOOLS: tuple[str, ...] = (
    "Read",
    "Glob",
    "Grep",
    "Write",       # may write charter / feature-queue artifacts
    "Skill",
)


def run_claude_session(
    prompt: str,
    *,
    cwd: Path,
    tools: Iterable[str] = DEFAULT_BUILD_TOOLS,
    model: str = "claude-opus-4-6",
    timeout: int = 1800,
    permission_mode: str = "acceptEdits",
    append_system_prompt: str | None = None,
    include_codex_protocol: bool = True,
    max_budget_usd: float | None = None,
    log_path: Path | None = None,
    on_event: Callable[[dict], None] | None = None,
    extra_args: list[str] | None = None,
    settings_path: Path | None = None,
    enable_ncdev_hooks: bool = True,
    retain_events: bool = False,
) -> ClaudeSessionResult:
    """Spawn a Claude session and stream its events.

    Parameters
    ----------
    prompt:
        The user-facing prompt. Pass a task statement, not a huge context
        blob — put big context in files and ask Claude to read them.
    cwd:
        Working directory for the session (the target repo, typically).
    tools:
        Tool allowlist. Use :data:`DEFAULT_BUILD_TOOLS` for feature builds
        (includes Bash for Codex shell-out, Skill for skill invocation,
        Task for subagents). Use :data:`DEFAULT_PLAN_TOOLS` for read-only
        planning sessions.
    model:
        Model label for Claude. Default: ``claude-opus-4-6``.
    timeout:
        Kill-switch in seconds. Separate from ``max_budget_usd`` — both
        can terminate the session.
    permission_mode:
        Passed to ``--permission-mode``. Default ``acceptEdits`` lets the
        model edit files without interactive prompts. Use
        ``bypassPermissions`` for fully trusted runs.
    append_system_prompt:
        Text appended to Claude's default system prompt. Use this to
        inject the Codex protocol, project charter reference, etc.
    include_codex_protocol:
        When True (default), the Codex-via-Bash protocol is prepended to
        ``append_system_prompt`` so every session knows how to delegate
        to Codex. Set False for sessions that must not invoke Codex.
    max_budget_usd:
        Hard cost ceiling for this session. Claude aborts if exceeded.
        This is the hook for budget-driven mode switching.
    log_path:
        If provided, every stream event is appended as a JSONL line.
    on_event:
        Optional callback fired per event in real time. Use for live
        progress UI. Exceptions in the callback are caught and logged.
    extra_args:
        Additional raw flags passed to ``claude``. Escape hatch.
    settings_path:
        Optional path to a Claude Code settings JSON with hooks/MCP
        config. When set, passed via ``--settings``.
    enable_ncdev_hooks:
        When True (default), NC Dev's built-in hook guards (commit
        hygiene + force-push protection) are wired in automatically
        unless ``settings_path`` is also set (caller wins).
    retain_events:
        When True, every stream event is appended to
        :attr:`ClaudeSessionResult.events`. Default ``False`` because
        long sessions can produce tens of thousands of events and we
        log them to JSONL already (``log_path``). Turn on for tests /
        debugging only.
    """
    if shutil.which("claude") is None:
        return ClaudeSessionResult(
            success=False, final_text="", exit_code=-1,
            error="claude CLI not found on PATH",
        )

    # Compose the system prompt append block
    system_prompt_parts: list[str] = []
    if include_codex_protocol and CODEX_PROTOCOL_PATH.exists():
        system_prompt_parts.append(CODEX_PROTOCOL_PATH.read_text(encoding="utf-8"))
    if append_system_prompt:
        system_prompt_parts.append(append_system_prompt)
    system_prompt = "\n\n---\n\n".join(system_prompt_parts) if system_prompt_parts else None

    tools_list = list(tools)

    cmd: list[str] = [
        "claude",
        "-p", prompt,
        "--output-format", "stream-json",
        "--include-partial-messages",
        "--include-hook-events",
        "--model", model,
        "--permission-mode", permission_mode,
        "--allowedTools", ",".join(tools_list),
    ]
    if system_prompt:
        cmd += ["--append-system-prompt", system_prompt]
    if max_budget_usd is not None:
        cmd += ["--max-budget-usd", f"{max_budget_usd:.4f}"]

    # Wire hooks: caller-supplied settings_path wins; otherwise, if
    # enable_ncdev_hooks and the default settings file exists, use it.
    chosen_settings = settings_path
    if chosen_settings is None and enable_ncdev_hooks and NCDEV_HOOKS_SETTINGS.exists():
        chosen_settings = NCDEV_HOOKS_SETTINGS
    env_overrides: dict[str, str] = {}
    if chosen_settings is not None:
        cmd += ["--settings", str(chosen_settings)]
        # Make the hooks dir discoverable to the command substitution in settings.json
        env_overrides["NCDEV_HOOKS_DIR"] = str(NCDEV_HOOKS_DIR)
    if extra_args:
        cmd += list(extra_args)

    start = time.time()
    events: list[dict] = []
    log_fh = None
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_fh = log_path.open("w", encoding="utf-8")

    subproc_env = os.environ.copy()
    subproc_env.update(env_overrides)
    popen_kwargs: dict = dict(
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=subproc_env,
    )
    if IS_POSIX:
        # Own process group so we can SIGKILL the whole tree on timeout.
        popen_kwargs["start_new_session"] = True

    try:
        proc = subprocess.Popen(cmd, **popen_kwargs)
    except (FileNotFoundError, OSError) as exc:
        if log_fh:
            log_fh.close()
        return ClaudeSessionResult(
            success=False, final_text="", exit_code=-1,
            error=f"failed to spawn claude: {exc}",
        )

    final_text = ""
    skills: list[str] = []
    tool_calls: list[ToolCallRecord] = []
    codex_calls: list[str] = []
    subagents: list[str] = []
    files_touched: set[str] = set()
    total_cost: float | None = None
    stderr_chunks: list[str] = []

    # Thread-based pipe readers prevent the two classes of hang Codex
    # called out:
    #   1. stderr pipe fills and backpressures the child — drain it.
    #   2. stdout iteration blocks forever if Claude hangs without
    #      closing stdout — watchdog sends SIGTERM/SIGKILL on timeout.
    assert proc.stdout is not None and proc.stderr is not None

    stderr_done = threading.Event()

    def _drain_stderr() -> None:
        try:
            for line in proc.stderr:  # type: ignore[union-attr]
                stderr_chunks.append(line)
        except Exception:  # noqa: BLE001
            pass
        finally:
            stderr_done.set()

    stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
    stderr_thread.start()

    # Watchdog — hard kill on wall-clock expiry.
    timeout_fired = threading.Event()

    def _watchdog() -> None:
        if timeout <= 0:
            return
        if proc.poll() is None:
            time.sleep(timeout)
        if proc.poll() is None:
            timeout_fired.set()
            _kill_process_tree(proc)

    watchdog_thread = threading.Thread(target=_watchdog, daemon=True)
    watchdog_thread.start()

    try:
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                if log_fh:
                    log_fh.write(json.dumps({"_raw": line}) + "\n")
                continue

            if retain_events:
                events.append(event)
            else:
                # Keep a small ring buffer for the final_text fallback path.
                events.append(event)
                if len(events) > 20:
                    events.pop(0)
            if log_fh:
                log_fh.write(json.dumps(event) + "\n")
                log_fh.flush()

            _extract_event_signals(
                event,
                skills=skills,
                tool_calls=tool_calls,
                codex_calls=codex_calls,
                subagents=subagents,
                files_touched=files_touched,
            )

exec
/bin/zsh -lc "sed -n '1,360p' src/ncdev/v3/claude_executor.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
"""Phase E — Claude-driven feature executor.

Replaces the old ``step_executor.py`` manual build/verify/repair loop.
For each feature we spawn exactly one Claude session. Claude drives
the full build using its own skill machinery:

    * ``writing-plans``                 — if the feature is complex
    * ``test-driven-development``       — write failing test, then code
    * ``verification-before-completion`` — no "done" without evidence
    * ``systematic-debugging``          — when verification fails

Claude shells out to Codex via Bash for implementation and test writing
(the Codex-via-bash protocol is injected automatically by
:func:`run_claude_session`).  NC Dev orchestrates the outer loop only:

    1. Compose the feature prompt (charter refs, prior results, asset
       manifest requirement, verification contract).
    2. Run the session. Stream events.
    3. Inspect git state afterwards:
         * clean working tree + new commit(s) → PASSED
         * changes present but no commit     → commit with [BROKEN] tag
         * no changes at all                 → FAILED, builder didn't do anything
    4. Run post-hoc verification: manifest covers refs, required files exist.
    5. Return StepResult. Orchestrator moves to the next feature.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

from ncdev.ai_session import run_ai_session
from ncdev.claude_session import (
    DEFAULT_BUILD_TOOLS,
    ClaudeSessionResult,
)
from ncdev.v2.config import NCDevV2Config
from ncdev.v3.asset_manifest import (
    manifest_prompt_section,
    verify_manifest_covers_references,
)
from ncdev.v3.models import (
    CharterBundle,
    FeatureStep,
    StepResult,
    StepStatus,
    StepVerification,
    TestResult,
)


# ---------------------------------------------------------------------------
# Prompt composition
# ---------------------------------------------------------------------------


def build_feature_prompt(
    feature: FeatureStep,
    target_path: Path,
    charter_dir: Path,
    prior_feature_ids: list[str],
    project_id: str,
    citex_url: str = "http://localhost:20161",
) -> str:
    """Compose the single prompt handed to Claude for this feature.

    Deliberately terse. Heavy reference material (contract, verification,
    design system) stays on disk — Claude reads it with the Read tool.
    This is a departure from the old prescriptive mega-prompts.
    """
    prior_block = (
        "No prior features — this is the first build in the queue."
        if not prior_feature_ids
        else f"Prior features already built and verified: {', '.join(prior_feature_ids)}"
    )

    return f"""# Feature: {feature.feature_id} — {feature.title}

You are the engineer for this feature. You have the Claude skill
machinery available; use it. Codex is your implementation peer
(see the Codex protocol in your system prompt) — delegate raw
implementation and test writing to Codex via Bash, keep judgment
and review yourself.

## Context

- Project charter:        {charter_dir}/target-project-contract.json
- Verification contract:  {charter_dir}/verification-contract.json
- Design system:          {charter_dir}/design-system.json  (if present)
- Feature queue:          {charter_dir}/feature-queue.json
- Target repository:      {target_path}
- Citex project ID:       {project_id}
- Citex URL:              {citex_url}

{prior_block}

## Your feature spec

- ID:          {feature.feature_id}
- Title:       {feature.title}
- Description: {feature.description}
- Complexity:  {feature.estimated_complexity}
- Priority:    {feature.priority}

### Acceptance criteria
{chr(10).join(f"- {c}" for c in feature.acceptance_criteria) or "- (none specified — infer from description)"}

### Test requirements
{chr(10).join(f"- {t}" for t in feature.test_requirements) or "- (use your judgment — tests MUST exist and verify behaviour, not just syntax)"}

### Depends on
{", ".join(feature.depends_on_features) if feature.depends_on_features else "(none)"}

## Required workflow

1. **Read** the charter artifacts listed above. They are the hard
   constraints for stack, ports, auth, deployment. Do not override them.
2. **Query Citex** (the RAG system at `{citex_url}`) for anything you
   need to know about prior features, data models, or existing code.
   Use Bash if Citex exposes a CLI, or read the local `.ncdev/` cache.
3. **Use the `writing-plans` skill** if this is a high-complexity
   feature. For low complexity, go straight to step 4.
4. **Use the `test-driven-development` skill**. Write failing tests
   first (you may delegate the test file content to Codex via Bash).
5. **Delegate implementation to Codex via Bash**. One well-scoped
   Codex call per sub-task is better than five vague ones. Review
   Codex's output yourself before moving on.
6. **Emit the asset manifest** as you build — see the schema below.
7. **Use the `verification-before-completion` skill** before you
   claim done. Run the verification contract's test commands yourself.
   Run the app and probe its health endpoint. Capture the required
   screenshots listed in the verification contract.
8. **If verification fails**, use the `systematic-debugging` skill.
   Do not loop blindly — identify root cause, fix narrowly, re-verify.
9. **Commit the work** once verification passes. Use Conventional
   Commits (feat/fix/test) referencing the feature_id. Leave the
   working tree clean.

{manifest_prompt_section(feature.feature_id)}

## What success looks like

- Working tree is clean (all changes committed).
- The feature's tests exist, run, and pass.
- Verification contract is satisfied (boot, tests, screenshots, files).
- Asset manifest file exists at
  `.ncdev/assets-needed/{feature.feature_id}.json`.
- Your final response summarises what was built in <= 5 sentences.

## What failure looks like (avoid)

- "Implemented, but tests are still failing — here's what I tried."
  → Not done. Use systematic-debugging.
- Working tree dirty when you're "done." → Commit or revert.
- Asset manifest missing. → Write it before committing.
- Any of the `prohibited_patterns` in the verification contract
  landed in a commit. → Those are pre-commit-hook blockers; fix.

Begin.
"""


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------


def execute_feature_claude_driven(
    feature: FeatureStep,
    target_path: Path,
    run_dir: Path,
    charter_bundle: CharterBundle,
    prior_results: list[StepResult],
    project_id: str,
    *,
    model: str | None = None,
    timeout: int = 3600,
    max_budget_usd: float | None = None,
    citex_url: str = "http://localhost:20161",
    config: NCDevV2Config | None = None,
    run_test_commands: bool = True,
    probe_health: bool = True,
) -> StepResult:
    """Run one feature via a Claude session and return the StepResult.

    See module docstring for the outer flow.
    """
    step_dir = run_dir / "steps" / feature.feature_id
    step_dir.mkdir(parents=True, exist_ok=True)

    charter_dir = run_dir / "outputs"
    prior_ids = [r.feature_id for r in prior_results if r.status == StepStatus.PASSED]

    prompt = build_feature_prompt(
        feature=feature,
        target_path=target_path,
        charter_dir=charter_dir,
        prior_feature_ids=prior_ids,
        project_id=project_id,
        citex_url=citex_url,
    )
    (step_dir / "prompt.md").write_text(prompt, encoding="utf-8")

    # Snapshot git state so we can detect what changed
    pre_commit = _git_head(target_path)

    start = time.time()
    session = run_ai_session(
        prompt,
        cwd=target_path,
        config=config,
        workspace=run_dir.parent.parent.parent if run_dir.parent.parent.parent.exists() else None,
        tools=DEFAULT_BUILD_TOOLS,
        model=model,
        timeout=timeout,
        permission_mode="acceptEdits",
        max_budget_usd=max_budget_usd,
        log_path=step_dir / "session.jsonl",
    )
    build_duration = time.time() - start

    # Save session summary for debugging
    (step_dir / "session-summary.txt").write_text(session.summary(), encoding="utf-8")
    if session.final_text:
        (step_dir / "final-response.md").write_text(session.final_text, encoding="utf-8")

    post_commit = _git_head(target_path)
    made_commit = bool(post_commit and post_commit != pre_commit)
    dirty = _git_working_tree_dirty(target_path)

    # Files the feature actually touched — used for feature-local asset
    # manifest verification so one legacy unmanaged asset elsewhere in
    # the repo doesn't fail every future feature.
    feature_files_created, feature_files_modified = _diff_since(target_path, pre_commit)
    touched = feature_files_created + feature_files_modified

    # Post-hoc verification (Claude's own verification-before-completion
    # skill should have caught most things; this is our belt-and-braces)
    verification = _post_session_verification(
        target_path, feature, charter_bundle,
        run_test_commands=run_test_commands,
        probe_health=probe_health,
        touched_files=touched,
    )

    # Decide status
    recoverability_note = ""
    if session.success and made_commit and not dirty and verification.overall_passed:
        status = StepStatus.PASSED
    elif made_commit and verification.overall_passed:
        # Claude might have exited with non-zero for trivial reasons; if
        # the commit and verification are good, we accept.
        status = StepStatus.PASSED
    else:
        # Something is wrong. Commit whatever is there with [BROKEN] tag
        # so the next feature has context to build on. If that commit
        # itself fails (repo hook blocks it, git identity missing, etc.)
        # we surface it explicitly — recoverability is a guarantee we
        # promise in the docs, silent failure is not acceptable.
        if dirty:
            if _commit_broken(target_path, feature):
                post_commit = _git_head(target_path)
            else:
                recoverability_note = (
                    " | recoverability: [BROKEN] commit failed — dirty "
                    "working tree remains; see log for git error"
                )
        status = StepStatus.FAILED

    # Reuse the diff — or recompute if a [BROKEN] commit was made above
    files_created = feature_files_created
    files_modified = feature_files_modified
    if status == StepStatus.FAILED and dirty:
        files_created, files_modified = _diff_since(target_path, pre_commit)

    result = StepResult(
        feature_id=feature.feature_id,
        status=status,
        build_duration_seconds=build_duration,
        verify_duration_seconds=0.0,  # Claude's in-session verification is bundled into build time
        repair_attempts=0,   # Claude handles repair internally via skills
        verification=verification,
        files_created=files_created,
        files_modified=files_modified,
        commit_sha=post_commit or "",
        error_message=(session.error or "") + recoverability_note,
        builder_output=(session.final_text or "")[:2000],
    )
    # Persist the session cost + skills in metadata for metrics
    (step_dir / "result.json").write_text(
        result.model_dump_json(indent=2), encoding="utf-8",
    )
    (step_dir / "signals.json").write_text(json.dumps({
        "success": session.success,
        "made_commit": made_commit,
        "dirty_after": dirty,
        "skills_invoked": session.skills_invoked,
        "subagents_dispatched": session.subagents_dispatched,
        "codex_invocations": len(session.codex_invocations),
        "tool_calls": len(session.tool_calls),
        "total_cost_usd": session.total_cost_usd,
        "duration_seconds": session.duration_seconds,
    }, indent=2), encoding="utf-8")

    return result


# ---------------------------------------------------------------------------
# Post-session verification (light — Claude does the heavy lifting)
# ---------------------------------------------------------------------------


def _post_session_verification(
    target_path: Path,
    feature: FeatureStep,
    bundle: CharterBundle,
    *,
    run_test_commands: bool = True,
    probe_health: bool = True,
    touched_files: list[str] | None = None,
) -> StepVerification:
    """Enforce every clause of the verification contract.

    Belt-and-braces to Claude's in-session ``verification-before-completion``
    skill — we don't trust "claimed done" to mean "actually done".
    """
    ver = StepVerification()
    reasons: list[str] = []

    # 1. Required files from the verification contract must all exist
    for req in bundle.verification.required_files:
        if not (target_path / req).exists():
            reasons.append(f"required file missing: {req}")

    # 2. Asset manifest must exist and cover code references
    if bundle.verification.assets_manifest_required:
        ok, missing = verify_manifest_covers_references(
            target_path, feature.feature_id,
            touched_files=touched_files,
        )
        if not ok:
            if missing == ["<no-manifest>"]:
                reasons.append(f"asset manifest not written for {feature.feature_id}")
            else:
                reasons.append(f"asset references without manifest: {missing[:5]}")

    # 3. Prohibited patterns (regex — treats entries in the contract as
    #    patterns, falls back to literal match if the regex fails to compile)
    patterns = bundle.verification.prohibited_patterns
    if patterns:
        bad = _grep_for_prohibited(target_path, patterns)
        if bad:
            reasons.append(f"prohibited patterns found: {bad[:5]}")


exec
/bin/zsh -lc "sed -n '1,320p' src/ncdev/v3/engine.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
"""V3 Engine — sequential verified sprint pipeline (Claude-orchestrated).

This is the PRD-scale entry point. Replaces the old 9-artifact discovery
+ per-task-routing + parallel-builder pipeline with a thin outer loop:

    Phase 1 — Preflight                        (this module)
    Phase 2 — Charter generation                (v3.charter)
    Phase 3 — Design system                     (v3.design_phase)
    Phase 4 — Context ingestion into Citex      (v3.context_ingestion — brownfield)
    Phase 5 — Sequential feature execution      (v3.claude_executor)
    Phase 6 — Summary + metrics                 (this module)

Each phase is a Claude session (or a no-op for greenfield/skipped cases).
NC Dev itself just:

    * checks preconditions (git, claude, codex, Citex)
    * hands artifacts between phases
    * enforces hard-fail on Phase C for greenfield UI without designs
    * commits on pass, tags [BROKEN] on exhaustion
    * rolls up metrics at the end

The old run_v3_full() interface is preserved so the ``ncdev full`` CLI
command doesn't need to change.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ncdev.utils import make_run_id, write_json
from ncdev.v2.config import NCDevV2Config, ensure_default_v2_config, load_v2_config
from ncdev.v3.charter import generate_charter, load_charter, write_charter
from ncdev.v3.claude_executor import execute_feature_claude_driven
from ncdev.v3.design_phase import run_design_phase
from ncdev.v3.models import (
    CharterBundle,
    StepResult,
    StepStatus,
    V3RunState,
)

console = Console()


def run_v3_full(
    workspace: Path,
    source_path: Path,
    base_url: str = "http://localhost:23000",
    dry_run: bool = False,
    target_repo_path: Path | None = None,
    run_id: str | None = None,
    builder_model: str | None = None,
    builder_timeout: int = 3600,
    max_budget_usd: float | None = None,
    config: NCDevV2Config | None = None,
    strict_deps: bool = False,
    # Retained for CLI signature compat; Claude's systematic-debugging
    # skill handles repair now, so this is a no-op.
    max_repair_attempts: int | None = None,
) -> V3RunState:
    """Run the full V3 pipeline on a PRD.

    Entry point for ``ncdev full --source <prd>``.
    """
    # ── Phase 1: Preflight + workspace setup ─────────────────────────────
    run_id = run_id or make_run_id("v3")
    run_dir = workspace / ".nc-dev" / "v2" / "runs" / run_id
    outputs_dir = run_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    # Mode-aware config: single source of truth for which CLI runs each
    # session. Load once, pass through every phase.
    if config is None:
        try:
            config = ensure_default_v2_config(workspace)
        except Exception:  # noqa: BLE001
            config = NCDevV2Config()

    state = V3RunState(
        run_id=run_id,
        workspace=str(workspace),
        run_dir=str(run_dir),
        target_path=str(target_repo_path) if target_repo_path else "",
        phase="init",
    )

    console.print(Panel(
        f"[bold cyan]NC Dev V3 — {config.mode} mode[/bold cyan]\n"
        f"Run ID: {run_id}\n"
        f"Source: {source_path}\n"
        f"Target: {target_repo_path or '(greenfield)'}",
        border_style="cyan",
    ))

    # ── Phase 2: Charter ─────────────────────────────────────────────────
    state.phase = "charter"
    console.print("\n[bold]Phase 2: Charter (Claude planning session)[/bold]")

    if dry_run:
        console.print("  [dim]Dry run — skipping charter generation[/dim]")
        bundle = None
    else:
        bundle, charter_session = generate_charter(
            prd_path=source_path,
            output_dir=outputs_dir,
            target_repo=target_repo_path,
            model=builder_model,
            max_budget_usd=max_budget_usd,
            log_path=run_dir / "logs" / "charter.jsonl",
            config=config,
        )
        if bundle is None:
            console.print(Panel(
                f"[bold red]Charter generation failed[/bold red]\n"
                f"Session: {charter_session.summary()}\n"
                f"See: {outputs_dir}/charter-error.json (if present) "
                f"or run log at {run_dir}/logs/charter.jsonl",
                border_style="red",
            ))
            state.phase = "failed"
            state.status = "failed"
            _persist_state(state, run_dir)
            return state
        console.print(f"  [green]✓[/green] Charter: {len(bundle.feature_queue.features)} features queued")

    # Resolve target path now that we have the charter
    target_path = (
        Path(bundle.contract.existing_repo_path).expanduser().resolve()
        if bundle and bundle.contract.existing_repo_path
        else (target_repo_path or (workspace / (bundle.contract.project_name if bundle else "project"))).resolve()
    )
    target_path.mkdir(parents=True, exist_ok=True)
    state.target_path = str(target_path)

    # ── Phase 3: Design system ───────────────────────────────────────────
    state.phase = "design"
    console.print("\n[bold]Phase 3: Design system[/bold]")
    if dry_run or bundle is None:
        console.print("  [dim]Skipped[/dim]")
    else:
        design = run_design_phase(
            contract=bundle.contract,
            target_path=target_path,
            output_dir=outputs_dir,
            model=builder_model,
            max_budget_usd=max_budget_usd,
            log_path=run_dir / "logs" / "design.jsonl",
            config=config,
        )
        if design.skipped:
            console.print("  [dim]Non-UI project — design phase skipped[/dim]")
        elif design.hard_failed:
            console.print(Panel(
                f"[bold red]Design phase HARD FAILED[/bold red]\n"
                f"{design.error}\n"
                f"See: {outputs_dir}/design-phase-error.json",
                border_style="red",
            ))
            state.phase = "failed"
            state.status = "failed"
            _persist_state(state, run_dir)
            return state
        else:
            src = design.design_doc.source if design.design_doc else "?"
            console.print(f"  [green]✓[/green] Design system ready (source={src})")

    # ── Phase 4: Brownfield context ingestion ────────────────────────────
    state.phase = "ingestion"
    if bundle and bundle.contract.is_brownfield and bundle.contract.uses_citex and not dry_run:
        console.print("\n[bold]Phase 4: Ingest existing code into Citex[/bold]")
        try:
            from ncdev.v3.citex_client import CitexClient
            from ncdev.v3.context_ingestion import ingest_project_context
            project_id = bundle.contract.project_name
            citex = CitexClient(project_id=project_id)
            if citex.health_check():
                report = ingest_project_context(
                    run_dir=run_dir,
                    target_path=target_path,
                    feature_queue=bundle.feature_queue,
                    project_id=project_id,
                )
                console.print(f"  [green]✓[/green] Ingested {report.successful}/{report.total_documents} docs")
            else:
                console.print("  [yellow]Citex unreachable — feature builds will run without RAG grounding[/yellow]")
        except Exception as exc:  # noqa: BLE001
            console.print(f"  [yellow]Citex ingestion failed: {exc} — continuing without RAG[/yellow]")
    else:
        console.print("\n[dim]Phase 4: Context ingestion skipped (greenfield or dry run)[/dim]")

    # ── Phase 5: Sequential feature execution ────────────────────────────
    state.phase = "building"
    completed: list[StepResult] = []

    if dry_run or bundle is None:
        console.print("\n[dim]Phase 5: Feature execution skipped (dry run)[/dim]")
    else:
        features = bundle.feature_queue.features
        state.feature_queue = bundle.feature_queue
        state.total_features = len(features)

        # Brownfield: skip features already implemented
        remaining = _filter_completed_features(target_path, features, completed)
        console.print(f"\n[bold]Phase 5: Building {len(remaining)} features sequentially[/bold]")

        for feature in remaining:
            state.current_step = feature.feature_id
            _persist_state(state, run_dir)

            # Dependency gate: a feature whose depends_on_features contains
            # any non-PASSED id is skipped rather than built. In strict mode,
            # halt the whole run at the first broken dep.
            unmet = _unmet_dependencies(feature, completed)
            if unmet:
                reason = (
                    f"dependency not satisfied: {', '.join(unmet)} "
                    "(required feature(s) are not in PASSED state)"
                )
                console.print(Panel(
                    f"[red]BLOCKED[/red] {feature.feature_id} — {reason}",
                    border_style="red",
                ))
                completed.append(StepResult(
                    feature_id=feature.feature_id,
                    status=StepStatus.BLOCKED,
                    error_message=reason,
                ))
                state.completed_steps = completed
                _persist_state(state, run_dir)
                if strict_deps:
                    console.print("[red]--strict-deps set: halting run[/red]")
                    break
                continue

            console.print(Panel(
                f"[cyan]{feature.feature_id}[/cyan] — {feature.title}",
                border_style="blue",
            ))

            result = execute_feature_claude_driven(
                feature=feature,
                target_path=target_path,
                run_dir=run_dir,
                charter_bundle=bundle,
                prior_results=completed,
                project_id=bundle.contract.project_name,
                model=builder_model,
                timeout=builder_timeout,
                max_budget_usd=max_budget_usd,
                config=config,
            )
            completed.append(result)
            state.completed_steps = completed
            # Count PASSED + SKIPPED — both are "done from NC Dev's
            # perspective". SKIPPED = brownfield state scanner already
            # found them in the target repo; PASSED = built this run.
            state.completed_features = len([
                r for r in completed
                if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
            ])
            _persist_state(state, run_dir)

            status_style = "green" if result.status == StepStatus.PASSED else "red"
            console.print(f"  [{status_style}]{result.status.value}[/{status_style}] — commit {result.commit_sha[:8] or '(none)'}")

    # ── Phase 6: Summary ─────────────────────────────────────────────────
    state.phase = "complete"
    passed = [r for r in completed if r.status == StepStatus.PASSED]
    # Both FAILED (tried and broke) and BLOCKED (couldn't try because a dep
    # broke) count as run-level failures. Without this, a --strict-deps halt
    # would report "passed" despite halting because of broken deps.
    unsuccessful = [
        r for r in completed
        if r.status in (StepStatus.FAILED, StepStatus.BLOCKED)
    ]
    state.status = "passed" if not unsuccessful else ("partial" if passed else "failed")

    _print_summary_table(completed)

    _persist_state(state, run_dir)
    return state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unmet_dependencies(feature, completed: list[StepResult]) -> list[str]:
    """Return the ids in ``feature.depends_on_features`` that are not met.

    A dep is "met" when it appears in ``completed`` with status:
      * PASSED  — built successfully this run
      * SKIPPED — brownfield state-scanner determined it was already
                  implemented in the target repo before this run started
    A dep is "unmet" when it:
      * is missing from the completed list (never attempted), OR
      * has status FAILED (we tried and it broke), OR
      * has status BLOCKED (its own dep was unmet — cascading failure).

    The BLOCKED distinction stops feature-N-blocked from being treated
    as "already done" and letting feature N+1 sail through.
    """
    acceptable = {
        r.feature_id for r in completed
        if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
    }
    return [dep for dep in feature.depends_on_features if dep not in acceptable]


def _filter_completed_features(target_path: Path, features, completed: list[StepResult]):
    """Brownfield skip: drop features already implemented in the target repo."""
    try:
        from ncdev.v3.state_scanner import build_skip_results, scan_completed_features

exec
/bin/zsh -lc "sed -n '1,280p' src/ncdev/v3/models.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
"""V3 models — sequential verified sprint engine."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class FeatureStep(BaseModel):
    """A single feature to implement in sequence."""

    feature_id: str
    title: str
    description: str
    acceptance_criteria: list[str]
    test_requirements: list[str] = Field(default_factory=list)
    depends_on_features: list[str] = Field(default_factory=list)
    priority: int = 0
    estimated_complexity: str = "medium"  # low, medium, high


class FeatureQueueDoc(BaseModel):
    """Ordered list of features to implement sequentially."""

    version: str = "v3"
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    generator: str = "ncdev.v3.feature_queue"
    project_name: str = ""
    features: list[FeatureStep] = Field(default_factory=list)
    sprint_zero_criteria: list[str] = Field(default_factory=lambda: [
        "App installs without errors",
        "App boots and health endpoint returns OK",
        "Empty test suite runs",
        "First screenshot captured",
    ])


class StepStatus(str, Enum):
    PENDING = "pending"
    BUILDING = "building"
    VERIFYING = "verifying"
    REPAIRING = "repairing"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"   # brownfield state-scanner: feature already implemented
    BLOCKED = "blocked"   # dependency failed / blocked — we did NOT try


class TestResult(BaseModel):
    """Result of running a test suite."""

    suite: str  # "unit", "integration", "e2e"
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    output: str = ""
    success: bool = False
    duration_seconds: float = 0.0


class ScreenshotEvidence(BaseModel):
    """A screenshot captured during verification."""

    path: str
    description: str
    viewport: str = "desktop"  # desktop, mobile
    captured_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class StepVerification(BaseModel):
    """Verification results for a single feature step."""

    lint_passed: bool = False
    lint_output: str = ""
    unit_tests: TestResult | None = None
    integration_tests: TestResult | None = None
    e2e_tests: TestResult | None = None
    screenshots: list[ScreenshotEvidence] = Field(default_factory=list)
    prohibited_patterns: list[str] = Field(default_factory=list)
    app_boots: bool = False
    overall_passed: bool = False
    failure_reasons: list[str] = Field(default_factory=list)


class StepResult(BaseModel):
    """Result of executing one feature step."""

    feature_id: str
    status: StepStatus
    build_duration_seconds: float = 0.0
    verify_duration_seconds: float = 0.0
    repair_attempts: int = 0
    verification: StepVerification | None = None
    files_created: list[str] = Field(default_factory=list)
    files_modified: list[str] = Field(default_factory=list)
    commit_sha: str = ""
    error_message: str = ""
    builder_output: str = ""


class V3RunState(BaseModel):
    """Overall state of a V3 pipeline run."""

    run_id: str
    command: str = "full"
    workspace: str = ""
    run_dir: str = ""
    target_path: str = ""
    phase: str = "init"
    status: str = "running"
    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    feature_queue: FeatureQueueDoc | None = None
    completed_steps: list[StepResult] = Field(default_factory=list)
    current_step: str = ""
    total_features: int = 0
    completed_features: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestionRecord(BaseModel):
    """One document ingested into Citex."""
    category: str
    char_count: int
    success: bool


class IngestionReport(BaseModel):
    """Summary of context ingestion into Citex."""
    project_id: str
    total_documents: int = 0
    successful: int = 0
    failed: int = 0
    records: list[IngestionRecord] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Charter artifacts — the 3 files that replace the old 9-artifact pipeline.
# ---------------------------------------------------------------------------


class TargetProjectContract(BaseModel):
    """Hard architectural constraints. The 'don't override' bag.

    Fields the user controls: stack, language, DB, auth, deployment target,
    ports, design archetype. Claude may infer defaults from the PRD but
    must NOT change these after the first session — they're the invariants.
    """

    version: str = "v3"
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    project_name: str
    project_type: str = "web"  # web | cli | library | api
    is_brownfield: bool = False
    existing_repo_path: str = ""

    # Stack — each field optional; "none" means explicitly not used.
    backend_framework: str = ""     # fastapi | django | express | none
    frontend_framework: str = ""    # react | vue | svelte | none
    database: str = ""              # mongodb | postgres | sqlite | none
    auth_system: str = ""           # keycloak | jwt | none
    language_backend: str = ""
    language_frontend: str = ""

    # Deployment
    deployment_target: str = "docker"   # docker | k8s | serverless
    ports: dict[str, int] = Field(default_factory=dict)

    # Design
    design_archetype: str = ""  # See user's global CLAUDE.md for values
    design_system_source: str = "stitch"   # stitch | existing | claude
    design_system_path: str = "docs/design-system"

    # Other invariants the orchestrator or verification must know
    uses_citex: bool = True
    uses_mock_apis: bool = True
    production_readiness_required: bool = True


class VerificationContract(BaseModel):
    """What 'done' means for this project.

    The Claude feature-executor session must satisfy every clause before
    committing. Hooks enforce where possible; post-hoc checks cover the rest.
    """

    version: str = "v3"
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # App must boot
    backend_health_url: str = ""       # e.g. http://localhost:23001/api/health
    frontend_url: str = ""
    boot_timeout_seconds: int = 60

    # Tests must exist and pass
    backend_test_command: str = ""     # e.g. "cd backend && python -m pytest -q"
    frontend_test_command: str = ""    # e.g. "cd frontend && npm test -- --run"
    e2e_test_command: str = ""         # e.g. "cd frontend && npx playwright test"
    minimum_test_count: int = 1

    # Screenshots
    required_screenshots: list[str] = Field(default_factory=list)
    screenshot_viewports: list[str] = Field(default_factory=lambda: ["desktop", "mobile"])

    # Files that must exist
    required_files: list[str] = Field(default_factory=list)

    # Assets
    assets_manifest_required: bool = True
    assets_manifest_path: str = ".ncdev/assets-needed"

    # Prohibited patterns (grep-able — hooks enforce these on commit)
    prohibited_patterns: list[str] = Field(default_factory=lambda: [
        "TODO",
        "FIXME",
        "console.log(",
        r"except:\s*pass",
        "Not yet implemented",
    ])

    # Commit hygiene
    require_conventional_commits: bool = True
    require_tests_in_commit: bool = True


class CharterBundle(BaseModel):
    """The three artifacts produced by the discovery phase, together."""

    contract: TargetProjectContract
    verification: VerificationContract
    feature_queue: FeatureQueueDoc


# ---------------------------------------------------------------------------
# Design system artifact (Phase C output)
# ---------------------------------------------------------------------------


class DesignScreen(BaseModel):
    """One design screen / page produced by Stitch or equivalent."""
    name: str
    html_path: str = ""         # path to exported HTML within the repo
    screenshot_path: str = ""   # path to PNG export
    description: str = ""


class AssetManifestEntry(BaseModel):
    """One asset the feature needs but couldn't generate itself.

    Listed so a downstream system (Nano Banana 2, stock image service,
    human) can produce it. Claude writes one of these per asset while
    building the feature — during the build, not after.
    """
    id: str                         # unique slug, e.g. "hero-bg"
    name: str                       # human-readable
    type: str                       # image | gif | svg | video | icon | audio
    description: str                # what it shows / represents
    generation_prompt: str          # prompt for an image-gen AI to produce it
    suggested_dimensions: str = ""  # "1920x1080", "64x64", etc
    referenced_in: list[str] = Field(default_factory=list)   # "src/pages/Home.tsx:42"
    target_path: str = ""           # where in the repo the file should land
    status: str = "pending"         # pending | generated | manual | skipped


class AssetManifest(BaseModel):
    """All assets needed by one feature."""
    version: str = "v3"
    feature_id: str
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    assets: list[AssetManifestEntry] = Field(default_factory=list)


class DesignSystemDoc(BaseModel):
    """Summary of the project's design system.


exec
/bin/zsh -lc "sed -n '1,280p' scripts/ncdev-hooks/pre_bash_guard.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
#!/usr/bin/env python3
"""Claude Code PreToolUse hook — guards ``Bash`` commands.

Wired in via ``scripts/ncdev-hooks/settings.json`` when NC Dev spawns a
Claude session.  Runs on every Bash tool call and enforces:

    * ``git commit`` commands cannot land files containing prohibited
      patterns (TODO, FIXME, console.log, bare ``except: pass``,
      "Not yet implemented") in the staged tree.
    * ``git commit`` messages must follow Conventional Commits
      (feat/fix/test/chore/refactor/docs/perf/style/build/ci/revert).
    * ``git push --force`` to protected branches (main/master) is blocked
      unless the user-level allowlist env var is set.

The hook reads a JSON event from stdin with the tool name and input,
writes a decision JSON to stdout, and exits 0 always — the decision
(allow/block + reason) is conveyed in the JSON body so Claude sees
the structured feedback.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable

# Default prohibited patterns — may be overridden per-project by placing
# a JSON file at $NCDEV_HOOKS_CONFIG.
DEFAULT_PROHIBITED: tuple[str, ...] = (
    "TODO",
    "FIXME",
    "console.log(",
    "Not yet implemented",
    "Coming soon",
)

CONVENTIONAL_RE = re.compile(
    r"^(feat|fix|test|chore|refactor|docs|perf|style|build|ci|revert)"
    r"(\([^)]+\))?:\s+.+",
    re.MULTILINE,
)


def _emit(decision: str, reason: str = "") -> None:
    """Write hook decision JSON and exit cleanly."""
    payload = {"decision": decision}
    if reason:
        payload["reason"] = reason
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.exit(0)


def _load_prohibited() -> tuple[str, ...]:
    config_path = os.environ.get("NCDEV_HOOKS_CONFIG")
    if config_path and Path(config_path).exists():
        try:
            cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
            pats = cfg.get("prohibited_patterns")
            if isinstance(pats, list) and all(isinstance(p, str) for p in pats):
                return tuple(pats)
        except Exception:  # noqa: BLE001
            pass
    return DEFAULT_PROHIBITED


def _staged_file_list(cwd: str | None) -> list[str]:
    r = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=cwd, capture_output=True, text=True, timeout=5,
    )
    if r.returncode != 0:
        return []
    return [line for line in r.stdout.splitlines() if line]


def _check_staged_for_prohibited(
    cwd: str | None, patterns: Iterable[str],
) -> list[str]:
    """Return a list of '<file>:<pattern>' violations found in staged diff.

    Each pattern is tried as a compiled regex first (via ``re.search``);
    if that fails to compile, we fall back to literal substring match.
    This matches the semantics of claude_executor._grep_for_prohibited
    — identical rules on both sides of the commit boundary.
    """
    compiled: list[tuple[str, re.Pattern[str] | None]] = []
    for pat in patterns:
        try:
            compiled.append((pat, re.compile(pat)))
        except re.error:
            compiled.append((pat, None))

    hits: list[str] = []
    for path in _staged_file_list(cwd):
        r = subprocess.run(
            ["git", "diff", "--cached", "--", path],
            cwd=cwd, capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            continue
        # Only inspect added lines (prefixed with "+" but not "+++").
        added = [
            line[1:] for line in r.stdout.splitlines()
            if line.startswith("+") and not line.startswith("+++")
        ]
        blob = "\n".join(added)
        for pat, regex in compiled:
            hit = regex.search(blob) if regex is not None else (pat in blob)
            if hit:
                hits.append(f"{path}:{pat}")
                if len(hits) > 20:
                    return hits
    return hits


_HEREDOC_SENTINEL = re.compile(r"<<-?\s*['\"]?(\w+)")


def _extract_commit_message(cmd: str) -> tuple[str | None, str]:
    """Pull the ``-m`` argument out of a git-commit command.

    Returns ``(message, parse_mode)`` where ``parse_mode`` is:
        * "literal"   — we parsed a plain quoted string cleanly
        * "heredoc"   — message is being supplied via a HEREDOC
        * "file"      — ``-F <file>`` used; message is in a file
        * "unknown"   — we don't know what the message is

    Callers can treat "unknown" as "can't enforce, allow through" to
    avoid breaking legitimate non-inline commit flows.
    """
    # -F <file> — message read from a file
    if re.search(r"(?:^|\s)(?:-F|--file)\s+\S+", cmd):
        return None, "file"

    # HEREDOC substitution — e.g. git commit -m "$(cat <<'EOF' ... EOF )"
    if _HEREDOC_SENTINEL.search(cmd):
        return None, "heredoc"

    # Plain quoted message. Handles escaped quotes inside the value by
    # looking for the matching close quote that isn't preceded by a
    # backslash. Double-quote and single-quote variants.
    for quote in ("'", '"'):
        pattern = rf"""-m\s+{quote}((?:\\.|(?!{quote}).)*){quote}"""
        m = re.search(pattern, cmd, flags=re.DOTALL)
        if m:
            raw = m.group(1)
            # Un-escape the quotes so downstream callers see the real message
            raw = raw.replace(f"\\{quote}", quote)
            return raw, "literal"

    return None, "unknown"


def _is_force_push_to_protected(cmd: str) -> bool:
    if "git push" not in cmd:
        return False
    if "--force" not in cmd and "-f " not in cmd and not cmd.rstrip().endswith("-f"):
        return False
    # protected refs
    for ref in ("main", "master", "production", "prod"):
        if re.search(rf"\b{ref}\b", cmd):
            return True
    return False


def evaluate(tool_name: str, tool_input: dict, cwd: str | None = None) -> tuple[str, str]:
    """Pure evaluator — given a tool call, return (decision, reason).

    decision is "allow" or "block". Split out for unit testing; the
    main entry point wraps this in stdin/stdout plumbing.
    """
    if tool_name != "Bash":
        return "allow", ""

    cmd = str(tool_input.get("command", ""))
    if not cmd:
        return "allow", ""

    # Force-push protection
    if _is_force_push_to_protected(cmd):
        if os.environ.get("NCDEV_ALLOW_FORCE_PUSH") != "1":
            return "block", (
                "Force-push to a protected branch. Set "
                "NCDEV_ALLOW_FORCE_PUSH=1 in the environment to override, "
                "or push to a feature branch instead."
            )

    # Only inspect git-commit commands for the remaining rules
    if "git commit" not in cmd:
        return "allow", ""

    # 1. Conventional Commits message shape
    msg, parse_mode = _extract_commit_message(cmd)
    if msg is not None:
        if not CONVENTIONAL_RE.search(msg):
            return "block", (
                "Commit message does not follow Conventional Commits "
                "(feat|fix|test|chore|refactor|docs|perf|style|build|ci|revert). "
                f"Got: {msg.splitlines()[0][:120]!r}"
            )
    elif parse_mode in ("heredoc", "file"):
        # We can't introspect the message body without running git, so
        # allow it. Worst case: a badly-formatted heredoc lands — but
        # relying on heredoc for commits is deliberate, users typically
        # know what they're doing. "unknown" falls through to allow as
        # well, since blocking would break edge-case pipelines.
        pass

    # 2. Prohibited patterns in staged content
    patterns = _load_prohibited()
    hits = _check_staged_for_prohibited(cwd, patterns)
    if hits:
        preview = ", ".join(hits[:5])
        return "block", (
            f"Staged changes contain prohibited patterns: {preview}"
            + (" (and more)" if len(hits) > 5 else "")
            + ". Remove them before committing."
        )

    return "allow", ""


def main() -> None:
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        _emit("allow")

    tool = event.get("tool_name") or event.get("tool") or ""
    inp = event.get("tool_input") or event.get("input") or {}
    cwd = event.get("cwd")

    decision, reason = evaluate(tool, inp, cwd)
    _emit(decision, reason)


if __name__ == "__main__":
    main()

exec
/bin/zsh -lc "sed -n '260,520p' src/ncdev/ai_session.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
        popen_kwargs["start_new_session"] = True

    start = time.time()
    try:
        proc = subprocess.Popen(cmd, **popen_kwargs)
    except (FileNotFoundError, OSError) as exc:
        return ClaudeSessionResult(
            success=False, final_text="", exit_code=-1,
            error=f"failed to spawn codex: {exc}",
        )

    stdout_buf = _TailBuffer(max_bytes_per_stream)
    stderr_buf = _TailBuffer(max_bytes_per_stream)

    def _drain(stream, buf: "_TailBuffer") -> None:
        try:
            for line in stream:
                buf.append(line)
        except Exception:  # noqa: BLE001
            pass

    stdout_thread = threading.Thread(
        target=_drain, args=(proc.stdout, stdout_buf), daemon=True,
    )
    stderr_thread = threading.Thread(
        target=_drain, args=(proc.stderr, stderr_buf), daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()

    timeout_fired = threading.Event()

    def _watchdog() -> None:
        if timeout <= 0:
            return
        if proc.poll() is None:
            time.sleep(timeout)
        if proc.poll() is None:
            timeout_fired.set()
            _kill_process_tree(proc)

    threading.Thread(target=_watchdog, daemon=True).start()

    try:
        proc.wait(timeout=timeout + 30)
    except subprocess.TimeoutExpired:
        _kill_process_tree(proc)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass

    # Drain final bytes
    stdout_thread.join(timeout=2.0)
    stderr_thread.join(timeout=2.0)

    duration = time.time() - start
    final_text = stdout_buf.text()
    stderr_text = stderr_buf.text()
    exit_code = proc.returncode if proc.returncode is not None else -1

    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        truncation_note = ""
        if stdout_buf.truncated or stderr_buf.truncated:
            truncation_note = (
                f"\n(NOTE: output tail-truncated to {max_bytes_per_stream} "
                "bytes per stream)\n"
            )
        log_path.write_text(
            f"RUNNER: codex\nEXIT: {exit_code}\nDURATION: {duration:.1f}s"
            f"{truncation_note}\n\n"
            f"STDOUT:\n{final_text}\n\nSTDERR:\n{stderr_text}\n",
            encoding="utf-8",
        )

    if timeout_fired.is_set():
        return ClaudeSessionResult(
            success=False,
            final_text=final_text,
            exit_code=exit_code,
            duration_seconds=duration,
            stderr=stderr_text,
            error=f"codex session timed out after {timeout}s",
        )

    return ClaudeSessionResult(
        success=exit_code == 0,
        final_text=final_text,
        exit_code=exit_code,
        duration_seconds=duration,
        stderr=stderr_text,
        error=None if exit_code == 0 else f"codex exited with code {exit_code}",
    )


# ---------------------------------------------------------------------------
# Helpers (shared)
# ---------------------------------------------------------------------------


class _TailBuffer:
    """Accumulate text but keep only the tail of ``max_bytes``.

    Recent output is more useful than the head when debugging a builder
    that went off the rails. ``truncated`` flips True once we start
    dropping bytes so callers can surface that to users / logs.

    If a single incoming chunk is larger than ``max_bytes``, we slice
    the tail bytes out of *that* chunk instead of evicting it wholesale
    (Codex R3 flagged: the previous behavior produced an empty buffer
    when a single append overflowed the cap).
    """

    __slots__ = ("_chunks", "_size", "_max", "truncated")

    def __init__(self, max_bytes: int) -> None:
        self._chunks: list[str] = []
        self._size = 0
        self._max = max(max_bytes, 1)
        self.truncated = False

    def append(self, chunk: str) -> None:
        if not chunk:
            return

        # Oversized single chunk: keep the tail bytes of this chunk only.
        chunk_bytes = chunk.encode("utf-8", errors="ignore")
        if len(chunk_bytes) > self._max:
            tail_bytes = chunk_bytes[-self._max:]
            tail = tail_bytes.decode("utf-8", errors="ignore")
            self._chunks = [tail]
            self._size = len(tail.encode("utf-8", errors="ignore"))
            self.truncated = True
            return

        self._chunks.append(chunk)
        self._size += len(chunk_bytes)

        # Normal eviction path: drop whole chunks from the head until
        # we're under the cap again. Safe now because no single chunk
        # is larger than ``_max``.
        while self._size > self._max and len(self._chunks) > 1:
            head = self._chunks.pop(0)
            self._size -= len(head.encode("utf-8", errors="ignore"))
            self.truncated = True

    def text(self) -> str:
        return "".join(self._chunks)


def _kill_process_tree(proc: subprocess.Popen) -> None:
    """Kill a process and its children. Mirror of claude_session's helper."""
    if proc.poll() is not None:
        return
    try:
        if _IS_POSIX:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    proc.kill()
        else:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
    except Exception:  # noqa: BLE001
        pass

exec
/bin/zsh -lc "sed -n '340,620p' src/ncdev/claude_session.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
            )

            if event.get("type") == "result":
                final_text = event.get("result") or event.get("text") or final_text
                total_cost = event.get("total_cost_usd", total_cost)

            if on_event is not None:
                try:
                    on_event(event)
                except Exception:  # noqa: BLE001
                    pass
    finally:
        # Always wait for the process and join the stderr reader so we
        # capture its output and don't leave zombies. The watchdog will
        # have killed on timeout already.
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            _kill_process_tree(proc)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        stderr_done.wait(timeout=2.0)
        stderr_thread.join(timeout=1.0)
        if log_fh:
            log_fh.close()

    stderr_text = "".join(stderr_chunks)
    exit_code = proc.returncode if proc.returncode is not None else -1
    duration = time.time() - start

    result_events = list(events) if retain_events else []

    if timeout_fired.is_set():
        return ClaudeSessionResult(
            success=False, final_text=final_text, exit_code=exit_code,
            events=result_events, tool_calls=tool_calls,
            skills_invoked=skills, codex_invocations=codex_calls,
            subagents_dispatched=subagents,
            files_touched=sorted(files_touched),
            total_cost_usd=total_cost,
            duration_seconds=duration,
            stderr=stderr_text,
            error=f"claude session timed out after {timeout}s",
        )

    # Fall back to final event text if result event didn't land
    if not final_text:
        for ev in reversed(events):
            if ev.get("type") in ("assistant", "result"):
                text = _extract_text(ev)
                if text:
                    final_text = text
                    break

    return ClaudeSessionResult(
        success=exit_code == 0,
        final_text=final_text,
        exit_code=exit_code,
        events=result_events,
        tool_calls=tool_calls,
        skills_invoked=skills,
        codex_invocations=codex_calls,
        subagents_dispatched=subagents,
        files_touched=sorted(files_touched),
        total_cost_usd=total_cost,
        duration_seconds=duration,
        stderr=stderr_text,
        error=None if exit_code == 0 else f"claude exited with code {exit_code}",
    )


# ---------------------------------------------------------------------------
# Subprocess helpers
# ---------------------------------------------------------------------------


def _kill_process_tree(proc: subprocess.Popen) -> None:
    """Kill the Claude process and everything it spawned. Best-effort."""
    if proc.poll() is not None:
        return
    try:
        if IS_POSIX:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    proc.kill()
        else:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
    except Exception:  # noqa: BLE001
        # Never raise from the kill path — worst case we leak a pid,
        # but we don't want to mask the primary failure reason.
        pass


# ---------------------------------------------------------------------------
# Event parsing helpers
# ---------------------------------------------------------------------------


def _extract_event_signals(
    event: dict,
    *,
    skills: list[str],
    tool_calls: list[ToolCallRecord],
    codex_calls: list[str],
    subagents: list[str],
    files_touched: set[str],
) -> None:
    """Pull structured signals out of a stream event.

    Stream-json schema has evolved across Claude Code versions — we keep
    this tolerant: inspect common shapes, ignore unknowns.
    """
    ev_type = event.get("type")

    # Tool use appears inside assistant messages as content items with
    # type=tool_use. Extract recursively.
    if ev_type == "assistant":
        message = event.get("message") or {}
        content = message.get("content") or []
        for item in content:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "tool_use":
                tool_name = item.get("name", "?")
                input_data = item.get("input") or {}
                summary = _summarize_input(tool_name, input_data)
                tool_calls.append(ToolCallRecord(
                    tool=tool_name,
                    input_summary=summary,
                    raw=item,
                ))
                if tool_name == "Skill":
                    skill_name = input_data.get("skill") or input_data.get("name")
                    if skill_name and skill_name not in skills:
                        skills.append(skill_name)
                elif tool_name == "Task":
                    agent = input_data.get("subagent_type") or input_data.get("agent")
                    if agent:
                        subagents.append(agent)
                elif tool_name == "Bash":
                    cmd = input_data.get("command", "")
                    if "codex exec" in cmd or cmd.strip().startswith("codex "):
                        codex_calls.append(cmd[:500])
                elif tool_name in ("Write", "Edit"):
                    path = input_data.get("file_path")
                    if path:
                        files_touched.add(path)


def _summarize_input(tool: str, data: dict) -> str:
    if tool == "Bash":
        cmd = str(data.get("command", ""))
        return cmd[:200]
    if tool in ("Write", "Edit"):
        return str(data.get("file_path", ""))[:200]
    if tool == "Read":
        return str(data.get("file_path", ""))[:200]
    if tool == "Skill":
        return str(data.get("skill") or data.get("name") or "")[:200]
    if tool == "Task":
        desc = data.get("description", "")
        sub = data.get("subagent_type", "")
        return f"{sub}: {desc}"[:200]
    return str(data)[:200]


def _extract_text(event: dict) -> str:
    """Best-effort pull of readable text from an event."""
    if not isinstance(event, dict):
        return ""
    if "result" in event:
        return str(event["result"])
    if "text" in event:
        return str(event["text"])
    message = event.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    texts.append(str(item.get("text", "")))
            if texts:
                return "\n".join(texts)
    return ""

exec
/bin/zsh -lc "sed -n '360,760p' src/ncdev/v3/claude_executor.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:

    # 4. Required screenshots must exist on disk
    for shot in bundle.verification.required_screenshots:
        if not _screenshot_exists(target_path, shot):
            reasons.append(f"required screenshot not captured: {shot}")

    # 5. Minimum test count — prevents "0 tests, all green" gaming
    if bundle.verification.minimum_test_count > 0:
        count = _count_test_files(target_path)
        ver.unit_tests = TestResult(suite="unit", passed=count, success=count > 0)
        if count < bundle.verification.minimum_test_count:
            reasons.append(
                f"test file count {count} below minimum "
                f"{bundle.verification.minimum_test_count}"
            )

    # 6. Run the declared test commands
    if run_test_commands:
        if bundle.verification.backend_test_command:
            ok, out = _run_shell(
                bundle.verification.backend_test_command,
                cwd=target_path, timeout=600,
            )
            ver.integration_tests = TestResult(
                suite="backend", passed=1 if ok else 0,
                failed=0 if ok else 1, success=ok, output=out[:2000],
            )
            if not ok:
                reasons.append(f"backend tests failed: {_last_line(out)}")
        if bundle.verification.frontend_test_command:
            ok, out = _run_shell(
                bundle.verification.frontend_test_command,
                cwd=target_path, timeout=600,
            )
            ver.e2e_tests = TestResult(
                suite="frontend", passed=1 if ok else 0,
                failed=0 if ok else 1, success=ok, output=out[:2000],
            )
            if not ok:
                reasons.append(f"frontend tests failed: {_last_line(out)}")

    # 7. Health probe — if the contract declares a backend_health_url,
    #    the feature is only "done" when that URL responds. Leaving
    #    backend_health_url empty in the contract disables the probe
    #    (common for CLI/library projects). Codex R2 flagged: if the
    #    user put the URL there, they meant it.
    if probe_health and bundle.verification.backend_health_url:
        reachable = _probe_health(
            bundle.verification.backend_health_url,
            timeout=bundle.verification.boot_timeout_seconds,
        )
        ver.app_boots = reachable
        if not reachable:
            reasons.append(
                f"backend health URL unreachable: "
                f"{bundle.verification.backend_health_url} — the feature "
                "must leave the app in a runnable state"
            )

    ver.failure_reasons = reasons
    ver.overall_passed = not reasons
    ver.prohibited_patterns = [r for r in reasons if "prohibited" in r.lower()]
    return ver


def _grep_for_prohibited(target_path: Path, patterns: list[str]) -> list[str]:
    """Scan git-tracked files for prohibited patterns.

    Each entry is treated as a regular expression via ``re.search``. If
    a pattern fails to compile, falls back to a substring check so
    human-written entries like ``TODO`` still work.
    """
    compiled: list[tuple[str, re.Pattern[str] | None]] = []
    for pat in patterns:
        try:
            compiled.append((pat, re.compile(pat)))
        except re.error:
            compiled.append((pat, None))

    hits: list[str] = []
    try:
        ls = subprocess.run(
            ["git", "ls-files"],
            cwd=str(target_path), capture_output=True, text=True, timeout=10,
        )
        if ls.returncode != 0:
            return []
        files = [f for f in ls.stdout.splitlines() if f]
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    for f in files:
        fp = target_path / f
        try:
            if fp.stat().st_size > 1_000_000:
                continue
            text = fp.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pat, regex in compiled:
            hit = regex.search(text) if regex is not None else (pat in text)
            if hit:
                hits.append(f"{f} contains '{pat}'")
                if len(hits) > 20:
                    return hits
                break   # one hit per file is enough
    return hits


# ---------------------------------------------------------------------------
# Verification helpers
# ---------------------------------------------------------------------------


def _screenshot_exists(target_path: Path, name: str) -> bool:
    """True if a file matching the screenshot name exists under the repo.

    Matches common conventions: <name>.png, <name>-desktop.png, name-*.png,
    under evidence/screenshots/, .ncdev/evidence/, or docs/screenshots/.
    """
    slug = name.replace(" ", "-").replace("/", "-").lower()
    candidate_dirs = [
        target_path / ".ncdev" / "evidence",
        target_path / "evidence" / "screenshots",
        target_path / "docs" / "screenshots",
    ]
    for d in candidate_dirs:
        if not d.exists():
            continue
        for f in d.rglob("*.png"):
            if slug in f.name.lower():
                return True
    return False


def _count_test_files(target_path: Path) -> int:
    patterns = (
        "tests/**/test_*.py",
        "tests/**/*_test.py",
        "**/*.test.ts",
        "**/*.test.tsx",
        "**/*.spec.ts",
        "**/*.spec.tsx",
        "backend/tests/**/*.py",
        "frontend/tests/**/*.ts",
        "frontend/tests/**/*.tsx",
    )
    seen: set[Path] = set()
    for pat in patterns:
        for p in target_path.glob(pat):
            if p.is_file() and "node_modules" not in p.parts:
                seen.add(p.resolve())
    return len(seen)


def _run_shell(cmd: str, *, cwd: Path, timeout: int) -> tuple[bool, str]:
    """Run ``cmd`` in a shell. Returns (success, combined_output)."""
    try:
        r = subprocess.run(
            cmd, shell=True, cwd=str(cwd),
            capture_output=True, text=True, timeout=timeout,
        )
        return r.returncode == 0, (r.stdout + "\n" + r.stderr)
    except subprocess.TimeoutExpired as exc:
        return False, f"timed out after {timeout}s: {exc}"
    except Exception as exc:  # noqa: BLE001
        return False, f"exec error: {exc}"


def _last_line(text: str) -> str:
    lines = [l for l in text.strip().splitlines() if l.strip()]
    return lines[-1][:200] if lines else "(no output)"


def _probe_health(
    url: str,
    *,
    timeout: int,
    per_request_timeout: int = 5,
    poll_interval: float = 1.0,
) -> bool:
    """Poll an HTTP endpoint until it returns 2xx or ``timeout`` expires.

    Codex R3 flagged: the earlier single-shot GET failed good builds
    whose apps needed a few seconds to boot. This implementation
    honours ``timeout`` as a real startup grace period — per-request
    timeout stays short (default 5s) so we can retry, but the whole
    probe budget can run up to the configured ``boot_timeout_seconds``.

    Returns True on first 2xx, False when the budget runs out.
    """
    try:
        import httpx
    except ImportError:   # pragma: no cover - runtime dependency
        return False

    deadline = time.time() + max(timeout, 1)
    attempts = 0
    while time.time() < deadline:
        attempts += 1
        remaining = max(deadline - time.time(), 0.1)
        req_timeout = min(per_request_timeout, remaining)
        try:
            r = httpx.get(url, timeout=req_timeout)
            if 200 <= r.status_code < 300:
                return True
        except Exception:  # noqa: BLE001
            # Connection refused / DNS error / timeout — the app is not
            # ready yet. Wait briefly and retry unless budget exhausted.
            pass
        # Sleep until either the next poll or budget expiry, whichever
        # comes first.
        time.sleep(min(poll_interval, max(deadline - time.time(), 0)))
    return False


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _git_head(target_path: Path) -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(target_path), capture_output=True, text=True, timeout=5,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def _git_working_tree_dirty(target_path: Path) -> bool:
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(target_path), capture_output=True, text=True, timeout=5,
        )
        return r.returncode == 0 and bool(r.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _diff_since(target_path: Path, ref: str) -> tuple[list[str], list[str]]:
    if not ref:
        return [], []
    try:
        r = subprocess.run(
            ["git", "diff", "--name-status", f"{ref}..HEAD"],
            cwd=str(target_path), capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            return [], []
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return [], []

    created: list[str] = []
    modified: list[str] = []
    for line in r.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        flag, path = parts[0], parts[-1]
        if flag == "A":
            created.append(path)
        elif flag in ("M", "R", "C"):
            modified.append(path)
    return created, modified


def _commit_broken(target_path: Path, feature: FeatureStep) -> bool:
    """Commit leftover dirty tree with [BROKEN] tag. Returns True on success.

    Explicitly checks git return codes and surfaces failure so the
    caller knows whether recoverability actually worked. If pre-commit
    hooks reject the commit (e.g. the repo has its own guards), we bail
    cleanly and let the orchestrator handle it.
    """
    try:
        add = subprocess.run(
            ["git", "add", "-A"],
            cwd=str(target_path), capture_output=True, text=True, timeout=10,
        )
        if add.returncode != 0:
            logger.warning("BROKEN-commit: git add failed: %s", add.stderr[:200])
            return False
        commit = subprocess.run(
            ["git", "commit", "-m",
             f"[BROKEN] {feature.feature_id}: {feature.title}\n\n"
             "Claude session did not reach a clean-tree final state. "
             "Committed for recoverability."],
            cwd=str(target_path), capture_output=True, text=True, timeout=10,
        )
        if commit.returncode != 0:
            logger.warning(
                "BROKEN-commit: git commit failed (rc=%d): %s",
                commit.returncode,
                (commit.stderr or commit.stdout)[:300],
            )
            return False
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        logger.warning("BROKEN-commit: %s", exc)
        return False

exec
/bin/zsh -lc "sed -n '320,520p' src/ncdev/v3/engine.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
        from ncdev.v3.state_scanner import build_skip_results, scan_completed_features
    except ImportError:
        return features
    try:
        done_ids = set(scan_completed_features(target_path, features))
    except Exception:  # noqa: BLE001
        return features
    if not done_ids:
        return features
    skipped = build_skip_results(features, done_ids)
    completed.extend(skipped)
    remaining = [f for f in features if f.feature_id not in done_ids]
    console.print(f"  [dim]Skipping {len(done_ids)} features already implemented[/dim]")
    return remaining


def _print_summary_table(completed: list[StepResult]) -> None:
    if not completed:
        return
    table = Table(title="V3 Build Summary")
    table.add_column("Feature", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Duration", justify="right")
    table.add_column("Files", justify="right")
    table.add_column("Commit", justify="right")
    for r in completed:
        colour = {
            StepStatus.PASSED: "green",
            StepStatus.FAILED: "red",
            StepStatus.BLOCKED: "red",
            StepStatus.SKIPPED: "yellow",
        }.get(r.status, "white")
        table.add_row(
            r.feature_id,
            f"[{colour}]{r.status.value}[/{colour}]",
            f"{r.build_duration_seconds:.0f}s",
            str(len(r.files_created) + len(r.files_modified)),
            r.commit_sha[:8] if r.commit_sha else "",
        )
    console.print(table)


def _persist_state(state: V3RunState, run_dir: Path) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "state.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")

exec
/bin/zsh -lc "sed -n '280,520p' src/ncdev/v3/models.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:

    Populated by Phase C. Downstream feature builds reference this to
    know what colours / fonts / spacing / component patterns to use.
    """
    version: str = "v3"
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    project_name: str
    design_archetype: str
    source: str = "stitch"           # stitch | existing | claude_generated

    # Where the real design tokens live on disk (project-relative)
    tokens_dir: str = "docs/design-system"
    tokens_files: list[str] = Field(default_factory=list)   # e.g. ["tokens.css", "tailwind.config.js"]

    # Optional: design system description
    colors: dict[str, str] = Field(default_factory=dict)
    typography: dict[str, str] = Field(default_factory=dict)
    spacing: dict[str, str] = Field(default_factory=dict)

    # Screens exported for reference
    screens: list[DesignScreen] = Field(default_factory=list)

    # Provenance
    stitch_project_id: str = ""
    notes: list[str] = Field(default_factory=list)

codex
I have the core implementation loaded. I’m checking the current tests against the failure modes in this code now, because the likely remaining bugs are in the seams: status accounting, prompt/runner behavior, and commit/verification edge cases that unit coverage may still miss.
exec
/bin/zsh -lc "sed -n '1,360p' tests/unit/test_ai_session.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
"""Tests for the mode-aware AI session dispatcher."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from ncdev import ai_session
from ncdev.ai_session import (
    MODE_IMPLEMENTER,
    MODE_ORCHESTRATOR,
    run_ai_session,
    run_codex_session,
)
from ncdev.claude_session import ClaudeSessionResult
from ncdev.v2.config import NCDevV2Config


# ---------------------------------------------------------------------------
# Mode tables
# ---------------------------------------------------------------------------


def test_mode_tables_cover_every_preset_except_custom():
    """Every non-custom preset must have an orchestrator/implementer
    entry. 'custom' is deliberately absent — it's resolved from the
    user's hand-tuned routing via _resolve_custom_providers."""
    from ncdev.v2.config import MODE_PRESETS
    expected = set(MODE_PRESETS.keys()) - {"custom"}
    assert set(MODE_ORCHESTRATOR.keys()) == expected
    assert set(MODE_IMPLEMENTER.keys()) == expected


def test_claude_plan_codex_build_orchestrator_is_claude_implementer_is_codex():
    assert MODE_ORCHESTRATOR["claude_plan_codex_build"] == "claude"
    assert MODE_IMPLEMENTER["claude_plan_codex_build"] == "codex"


def test_codex_only_has_codex_for_both():
    assert MODE_ORCHESTRATOR["codex_only"] == "codex"
    assert MODE_IMPLEMENTER["codex_only"] == "codex"


def test_claude_only_has_claude_for_both():
    assert MODE_ORCHESTRATOR["claude_only"] == "claude"
    assert MODE_IMPLEMENTER["claude_only"] == "claude"


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def _claude_result() -> ClaudeSessionResult:
    return ClaudeSessionResult(success=True, final_text="claude did it", exit_code=0)


def _codex_result() -> ClaudeSessionResult:
    return ClaudeSessionResult(success=True, final_text="codex did it", exit_code=0)


def test_claude_plan_codex_build_routes_to_claude_with_protocol(tmp_path: Path):
    cfg = NCDevV2Config(mode="claude_plan_codex_build")
    captured: dict = {}

    def fake_claude(prompt, **kwargs):
        captured.update(kwargs)
        return _claude_result()

    with patch("ncdev.ai_session.run_claude_session", side_effect=fake_claude):
        result = run_ai_session("do it", cwd=tmp_path, config=cfg)

    assert result.final_text == "claude did it"
    # Codex protocol MUST be injected — this is the whole point of
    # claude_plan_codex_build
    assert captured["include_codex_protocol"] is True


def test_claude_only_routes_to_claude_without_protocol(tmp_path: Path):
    cfg = NCDevV2Config(mode="claude_only")
    captured: dict = {}

    def fake_claude(prompt, **kwargs):
        captured.update(kwargs)
        return _claude_result()

    with patch("ncdev.ai_session.run_claude_session", side_effect=fake_claude):
        run_ai_session("do it", cwd=tmp_path, config=cfg)

    # No Codex delegation in claude_only mode
    assert captured["include_codex_protocol"] is False


def test_codex_only_routes_to_codex(tmp_path: Path):
    cfg = NCDevV2Config(mode="codex_only")
    captured: dict = {}

    def fake_codex(prompt, **kwargs):
        captured["prompt"] = prompt
        captured.update(kwargs)
        return _codex_result()

    with patch("ncdev.ai_session.run_codex_session", side_effect=fake_codex):
        result = run_ai_session("do it", cwd=tmp_path, config=cfg)

    assert result.final_text == "codex did it"
    assert "prompt" in captured


def test_codex_only_does_not_call_claude(tmp_path: Path):
    """codex_only must not spawn a Claude session under any circumstances."""
    cfg = NCDevV2Config(mode="codex_only")

    def fake_claude(*a, **k):  # noqa: ARG001
        raise AssertionError("Claude must not be invoked in codex_only mode")

    with patch("ncdev.ai_session.run_claude_session", side_effect=fake_claude):
        with patch("ncdev.ai_session.run_codex_session", return_value=_codex_result()):
            run_ai_session("x", cwd=tmp_path, config=cfg)


def test_claude_only_does_not_call_codex(tmp_path: Path):
    cfg = NCDevV2Config(mode="claude_only")

    def fake_codex(*a, **k):  # noqa: ARG001
        raise AssertionError("Codex session must not be invoked in claude_only mode")

    with patch("ncdev.ai_session.run_codex_session", side_effect=fake_codex):
        with patch("ncdev.ai_session.run_claude_session", return_value=_claude_result()):
            run_ai_session("x", cwd=tmp_path, config=cfg)


def test_openrouter_raises_not_implemented(tmp_path: Path):
    cfg = NCDevV2Config(mode="openrouter")
    with pytest.raises(NotImplementedError, match="API-only"):
        run_ai_session("x", cwd=tmp_path, config=cfg)


def test_custom_mode_honours_hand_tuned_routing_claude_everywhere(tmp_path: Path):
    """Codex R2 flagged: custom was hardcoded to claude+codex, ignoring
    the user's routing: block. Verify: user routes everything to
    anthropic_claude_code → Claude orchestrator, Claude implementer,
    protocol OFF (Claude isn't delegating)."""
    cfg = NCDevV2Config(
        mode="custom",
        routing={
            "review": ["anthropic_claude_code"],
            "implementation": ["anthropic_claude_code"],
        },
    )
    captured: dict = {}

    def fake_claude(prompt, **kwargs):
        captured.update(kwargs)
        return _claude_result()

    with patch("ncdev.ai_session.run_claude_session", side_effect=fake_claude):
        run_ai_session("x", cwd=tmp_path, config=cfg)

    # orchestrator=claude, implementer=claude → NO codex protocol
    assert captured["include_codex_protocol"] is False


def test_custom_mode_routes_to_codex_when_user_requests_it(tmp_path: Path):
    """User flips everything to codex via custom — must actually route
    to codex runner, not fall back to Claude."""
    cfg = NCDevV2Config(
        mode="custom",
        routing={
            "review": ["openai_codex"],
            "implementation": ["openai_codex"],
        },
    )
    called = {"claude": False, "codex": False}

    def fake_claude(*a, **k):  # noqa: ARG001
        called["claude"] = True
        return _claude_result()

    def fake_codex(*a, **k):  # noqa: ARG001
        called["codex"] = True
        return _codex_result()

    with patch("ncdev.ai_session.run_claude_session", side_effect=fake_claude):
        with patch("ncdev.ai_session.run_codex_session", side_effect=fake_codex):
            run_ai_session("x", cwd=tmp_path, config=cfg)

    assert called["codex"] is True, "custom mode must route to codex when user routes review+impl to codex"
    assert called["claude"] is False


def test_custom_mode_unknown_provider_returns_structured_failure(tmp_path: Path):
    """Codex R3: an unknown provider name in routing used to raise
    ValueError uncaught mid-run. Now must surface as a structured
    ClaudeSessionResult with success=False + actionable error."""
    cfg = NCDevV2Config(
        mode="custom",
        routing={
            "review": ["something_weird"],
            "implementation": ["openai_codex"],
        },
    )
    result = run_ai_session("x", cwd=tmp_path, config=cfg)
    assert result.success is False
    assert result.exit_code == -1
    assert "custom mode" in (result.error or "")
    assert "something_weird" in (result.error or "")
    # Must not have spawned any runner
    assert result.final_text == ""


def test_custom_mode_plan_codex_build_like_routing(tmp_path: Path):
    """User configures custom to mimic claude_plan_codex_build: review=
    claude, implementation=codex → Claude orch WITH codex protocol."""
    cfg = NCDevV2Config(
        mode="custom",
        routing={
            "review": ["anthropic_claude_code"],
            "implementation": ["openai_codex"],
        },
    )
    captured: dict = {}

    def fake_claude(prompt, **kwargs):
        captured.update(kwargs)
        return _claude_result()

    with patch("ncdev.ai_session.run_claude_session", side_effect=fake_claude):
        run_ai_session("x", cwd=tmp_path, config=cfg)

    # Claude orchestrates, Codex implements → protocol ON
    assert captured["include_codex_protocol"] is True


def test_explicit_include_codex_protocol_wins_over_mode_default(tmp_path: Path):
    """Caller can override the mode-inferred default."""
    cfg = NCDevV2Config(mode="claude_plan_codex_build")  # would default True
    captured: dict = {}

    def fake_claude(prompt, **kwargs):
        captured.update(kwargs)
        return _claude_result()

    with patch("ncdev.ai_session.run_claude_session", side_effect=fake_claude):
        run_ai_session(
            "x", cwd=tmp_path, config=cfg, include_codex_protocol=False,
        )
    assert captured["include_codex_protocol"] is False


# ---------------------------------------------------------------------------
# run_codex_session
# ---------------------------------------------------------------------------


def test_run_codex_session_errors_when_cli_missing(tmp_path: Path):
    with patch("ncdev.ai_session.shutil.which", return_value=None):
        result = run_codex_session("task", cwd=tmp_path)
    assert result.success is False
    assert "codex CLI not found" in (result.error or "")


class _FakeCodexProc:
    """Minimal Popen stand-in: stdout + stderr iterable, immediate exit."""

    _next_pid = 9000

    def __init__(self, stdout: str = "codex output\n", stderr: str = "", returncode: int = 0):
        _FakeCodexProc._next_pid += 1
        self.pid = _FakeCodexProc._next_pid
        self.stdout = iter([stdout] if stdout else [])
        self.stderr = iter([stderr] if stderr else [])
        self.returncode = returncode

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):  # noqa: ARG002
        return self.returncode

    def kill(self):
        pass

    def terminate(self):
        pass


def test_run_codex_session_builds_correct_argv(tmp_path: Path):
    captured: dict = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return _FakeCodexProc(stdout="codex output\n")

    with patch("ncdev.ai_session.shutil.which", return_value="/usr/bin/codex"):
        with patch("ncdev.ai_session.subprocess.Popen", side_effect=fake_popen):
            result = run_codex_session("build feature X", cwd=tmp_path)

    cmd = captured["cmd"]
    assert cmd[0] == "codex"
    assert cmd[1] == "exec"
    assert "--full-auto" in cmd
    assert "--sandbox" in cmd
    assert "danger-full-access" in cmd
    # Prompt is last arg
    assert "build feature X" in cmd[-1]
    assert "codex_only mode" in cmd[-1]
    assert result.success is True
    assert "codex output" in result.final_text


def test_run_codex_session_writes_log(tmp_path: Path):
    def fake_popen(cmd, **kwargs):  # noqa: ARG001
        return _FakeCodexProc(stdout="the work\n", stderr="")

    log_path = tmp_path / "logs" / "codex.log"

    with patch("ncdev.ai_session.shutil.which", return_value="/usr/bin/codex"):
        with patch("ncdev.ai_session.subprocess.Popen", side_effect=fake_popen):
            run_codex_session("x", cwd=tmp_path, log_path=log_path)

    assert log_path.exists()
    body = log_path.read_text(encoding="utf-8")
    assert "RUNNER: codex" in body
    assert "the work" in body


def test_run_codex_session_truncates_huge_stream(tmp_path: Path):
    """Codex R2 flagged: unbounded capture_output can blow RAM.
    Verify the tail-buffer caps memory for chatty runs."""
    huge = "x" * 1024   # 1KB per line
    lines = [huge + "\n"] * 200  # 200 KB total

    class HugeProc(_FakeCodexProc):
        def __init__(self):
            super().__init__(stdout="", returncode=0)
            self.stdout = iter(lines)

    with patch("ncdev.ai_session.shutil.which", return_value="/usr/bin/codex"):
        with patch("ncdev.ai_session.subprocess.Popen", side_effect=lambda *a, **k: HugeProc()):
            # Cap at 50 KB — result must be capped, no crash
            result = run_codex_session(
                "x", cwd=tmp_path, max_bytes_per_stream=50_000,
            )

    assert result.success is True
    assert len(result.final_text.encode("utf-8")) <= 60_000  # some tolerance


def test_tail_buffer_preserves_tail_of_oversized_chunk():
    """Codex R3 flagged: _TailBuffer(10).append('x' * 25) previously
    returned ''. Now must preserve the last 10 bytes."""
    from ncdev.ai_session import _TailBuffer

    buf = _TailBuffer(10)
    buf.append("x" * 25)

exec
/bin/zsh -lc "sed -n '1,420p' tests/unit/test_claude_session.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
"""Tests for the Claude session runner primitive.

The runner shells out to the real ``claude`` CLI, so these tests fake the
subprocess layer. They verify:
- The command is composed correctly (tools, model, system prompt, budget)
- Stream-json events are parsed into structured signals (tool calls,
  skills invoked, codex shell-outs, files touched)
- Timeouts, missing CLI, and non-zero exits produce well-formed results
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from ncdev import claude_session
from ncdev.claude_session import (
    ClaudeSessionResult,
    DEFAULT_BUILD_TOOLS,
    DEFAULT_PLAN_TOOLS,
    run_claude_session,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeProc:
    """Minimal stand-in for subprocess.Popen.

    Supports the production interface: iteration over stdout, iteration
    over stderr (for the drain thread), poll(), wait(), kill(), pid,
    terminate(). Good enough for verifying event parsing + argv
    composition without spawning a real child.
    """

    _next_pid = 10000

    def __init__(self, stdout_lines: list[str], returncode: int = 0, stderr: str = ""):
        _FakeProc._next_pid += 1
        self.pid = _FakeProc._next_pid
        self._stdout_lines = stdout_lines
        self.returncode = returncode
        self.stdout = iter(stdout_lines)
        self.stderr = _FakeStderr(stderr)
        self._done = True   # synchronous fake — process is "complete" immediately

    def poll(self):
        return self.returncode if self._done else None

    def wait(self, timeout=None):  # noqa: ARG002
        return self.returncode

    def kill(self):
        pass

    def terminate(self):
        pass


class _FakeStderr:
    def __init__(self, text: str):
        self._text = text

    def __iter__(self):
        if self._text:
            yield self._text
        return

    def read(self) -> str:
        return self._text


def _popen_factory(stdout_events: list[dict], returncode: int = 0, stderr: str = ""):
    """Return a Popen stand-in that streams the given JSON events."""
    lines = [json.dumps(ev) + "\n" for ev in stdout_events]
    captured: dict = {}

    def _popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return _FakeProc(lines, returncode=returncode, stderr=stderr)

    return _popen, captured


# ---------------------------------------------------------------------------
# Command composition
# ---------------------------------------------------------------------------


def test_command_includes_stream_json_and_tools(tmp_path: Path):
    popen, captured = _popen_factory([{"type": "result", "result": "ok"}])

    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
            run_claude_session(
                "plan this",
                cwd=tmp_path,
                tools=DEFAULT_PLAN_TOOLS,
                include_codex_protocol=False,
            )

    cmd = captured["cmd"]
    assert cmd[0] == "claude"
    assert "--print" not in cmd  # we use -p
    assert "-p" in cmd
    assert "--output-format" in cmd
    assert cmd[cmd.index("--output-format") + 1] == "stream-json"
    tools_idx = cmd.index("--allowedTools") + 1
    assert cmd[tools_idx] == ",".join(DEFAULT_PLAN_TOOLS)


def test_default_build_tools_include_bash_skill_task():
    # These are the three tools that unlock the new architecture.
    assert "Bash" in DEFAULT_BUILD_TOOLS
    assert "Skill" in DEFAULT_BUILD_TOOLS
    assert "Task" in DEFAULT_BUILD_TOOLS


def test_plan_tools_exclude_write_beyond_artifacts():
    assert "Bash" not in DEFAULT_PLAN_TOOLS
    assert "Edit" not in DEFAULT_PLAN_TOOLS
    # Write stays — planning sessions write charter/queue JSON.
    assert "Write" in DEFAULT_PLAN_TOOLS


def test_max_budget_flag_passed_when_specified(tmp_path: Path):
    popen, captured = _popen_factory([{"type": "result", "result": "done"}])

    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
            run_claude_session(
                "build",
                cwd=tmp_path,
                max_budget_usd=2.50,
                include_codex_protocol=False,
            )

    cmd = captured["cmd"]
    assert "--max-budget-usd" in cmd
    idx = cmd.index("--max-budget-usd")
    assert cmd[idx + 1] == "2.5000"


def test_codex_protocol_prepended_to_system_prompt(tmp_path: Path):
    popen, captured = _popen_factory([{"type": "result", "result": "done"}])

    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
            run_claude_session(
                "build",
                cwd=tmp_path,
                append_system_prompt="project charter here",
                include_codex_protocol=True,
            )

    cmd = captured["cmd"]
    assert "--append-system-prompt" in cmd
    idx = cmd.index("--append-system-prompt")
    system_text = cmd[idx + 1]
    # Protocol file content is included verbatim
    assert "Codex Protocol" in system_text
    assert "codex exec --full-auto" in system_text
    # Caller's own prompt appended after
    assert "project charter here" in system_text


def test_include_codex_protocol_false_omits_protocol(tmp_path: Path):
    popen, captured = _popen_factory([{"type": "result", "result": "done"}])

    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
            run_claude_session(
                "plan only",
                cwd=tmp_path,
                append_system_prompt="just this",
                include_codex_protocol=False,
            )

    cmd = captured["cmd"]
    idx = cmd.index("--append-system-prompt")
    assert cmd[idx + 1] == "just this"


# ---------------------------------------------------------------------------
# Event parsing
# ---------------------------------------------------------------------------


def test_tool_calls_extracted_from_stream(tmp_path: Path):
    events = [
        {
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "tool_use", "name": "Read",
                     "input": {"file_path": "src/app.py"}},
                    {"type": "tool_use", "name": "Bash",
                     "input": {"command": "codex exec --full-auto 'Task: impl'"}},
                    {"type": "tool_use", "name": "Skill",
                     "input": {"skill": "test-driven-development"}},
                    {"type": "tool_use", "name": "Task",
                     "input": {"subagent_type": "code-reviewer",
                               "description": "review feature"}},
                    {"type": "tool_use", "name": "Write",
                     "input": {"file_path": "src/new_file.py", "content": "..."}},
                ],
            },
        },
        {"type": "result", "result": "done", "total_cost_usd": 0.42},
    ]
    popen, _ = _popen_factory(events)

    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
            result = run_claude_session(
                "build", cwd=tmp_path, include_codex_protocol=False,
            )

    assert result.success is True
    assert result.total_cost_usd == 0.42
    # All five tool calls captured
    assert len(result.tool_calls) == 5
    tool_names = [t.tool for t in result.tool_calls]
    assert tool_names == ["Read", "Bash", "Skill", "Task", "Write"]
    # Skill name parsed out
    assert "test-driven-development" in result.skills_invoked
    # Codex shell-out recognized
    assert len(result.codex_invocations) == 1
    assert "codex exec --full-auto" in result.codex_invocations[0]
    # Subagent dispatched
    assert "code-reviewer" in result.subagents_dispatched
    # File touched
    assert "src/new_file.py" in result.files_touched


def test_final_text_from_result_event(tmp_path: Path):
    events = [
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "thinking"}]}},
        {"type": "result", "result": "build complete", "total_cost_usd": 0.10},
    ]
    popen, _ = _popen_factory(events)
    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
            result = run_claude_session("x", cwd=tmp_path, include_codex_protocol=False)
    assert result.final_text == "build complete"


def test_final_text_falls_back_to_last_assistant_message(tmp_path: Path):
    # No result event — runner falls back to extracting from last assistant event
    events = [
        {"type": "assistant",
         "message": {"content": [{"type": "text", "text": "final answer"}]}},
    ]
    popen, _ = _popen_factory(events)
    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
            result = run_claude_session("x", cwd=tmp_path, include_codex_protocol=False)
    assert result.final_text == "final answer"


def test_on_event_callback_invoked_per_event(tmp_path: Path):
    events = [
        {"type": "assistant", "message": {"content": []}},
        {"type": "result", "result": "ok"},
    ]
    popen, _ = _popen_factory(events)

    seen: list[dict] = []

    def cb(ev):
        seen.append(ev)

    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
            run_claude_session(
                "x", cwd=tmp_path, on_event=cb, include_codex_protocol=False,
            )

    assert len(seen) == 2


def test_on_event_exception_does_not_crash_session(tmp_path: Path):
    events = [{"type": "result", "result": "ok"}]
    popen, _ = _popen_factory(events)

    def bad_cb(_ev):
        raise RuntimeError("boom")

    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
            result = run_claude_session(
                "x", cwd=tmp_path, on_event=bad_cb, include_codex_protocol=False,
            )
    assert result.success is True


def test_event_log_written_as_jsonl(tmp_path: Path):
    events = [
        {"type": "assistant", "message": {"content": []}},
        {"type": "result", "result": "ok"},
    ]
    popen, _ = _popen_factory(events)
    log_path = tmp_path / "logs" / "session.jsonl"

    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
            run_claude_session(
                "x", cwd=tmp_path, log_path=log_path, include_codex_protocol=False,
            )

    assert log_path.exists()
    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["type"] == "assistant"
    assert json.loads(lines[1])["type"] == "result"


def test_malformed_json_line_is_tolerated(tmp_path: Path):
    # Claude CLI occasionally emits debug noise — runner must not crash.
    lines = [
        "not a json line\n",
        json.dumps({"type": "result", "result": "ok"}) + "\n",
    ]

    def popen(cmd, **kwargs):  # noqa: ARG001
        return _FakeProc(lines, returncode=0)

    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
            result = run_claude_session(
                "x", cwd=tmp_path, include_codex_protocol=False,
            )
    assert result.success is True
    assert result.final_text == "ok"


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_claude_cli_missing_returns_structured_error(tmp_path: Path):
    with patch("ncdev.claude_session.shutil.which", return_value=None):
        result = run_claude_session("x", cwd=tmp_path)
    assert result.success is False
    assert result.exit_code == -1
    assert "claude CLI not found" in (result.error or "")


def test_non_zero_exit_marked_unsuccessful(tmp_path: Path):
    events = [{"type": "result", "result": "partial"}]
    popen, _ = _popen_factory(events, returncode=2, stderr="something broke")

    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
            result = run_claude_session(
                "x", cwd=tmp_path, include_codex_protocol=False,
            )

    assert result.success is False
    assert result.exit_code == 2
    assert result.stderr == "something broke"
    assert "exited with code 2" in (result.error or "")


def test_ncdev_hooks_wired_in_by_default(tmp_path: Path):
    """When enable_ncdev_hooks=True (default) and the bundled settings
    file exists, --settings is passed to claude."""
    popen, captured = _popen_factory([{"type": "result", "result": "ok"}])

    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
            run_claude_session(
                "do thing", cwd=tmp_path, include_codex_protocol=False,
            )
    cmd = captured["cmd"]
    assert "--settings" in cmd
    idx = cmd.index("--settings")
    settings_path = cmd[idx + 1]
    assert settings_path.endswith("settings.json")


def test_enable_ncdev_hooks_false_omits_settings(tmp_path: Path):
    popen, captured = _popen_factory([{"type": "result", "result": "ok"}])
    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
            run_claude_session(
                "x", cwd=tmp_path, include_codex_protocol=False,
                enable_ncdev_hooks=False,
            )
    cmd = captured["cmd"]
    assert "--settings" not in cmd


def test_caller_supplied_settings_path_wins(tmp_path: Path):
    user_settings = tmp_path / "custom-settings.json"
    user_settings.write_text("{}")
    popen, captured = _popen_factory([{"type": "result", "result": "ok"}])
    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
            run_claude_session(
                "x", cwd=tmp_path, include_codex_protocol=False,
                settings_path=user_settings,
            )
    cmd = captured["cmd"]
    idx = cmd.index("--settings")
    assert cmd[idx + 1] == str(user_settings)


def test_events_not_retained_by_default(tmp_path: Path):
    """Codex flag: in-memory event list is wasteful on long runs.
    Default is now OFF — result.events should be empty unless asked."""

exec
/bin/zsh -lc "sed -n '1,420p' tests/unit/test_claude_executor.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
"""Tests for Phase E Claude-driven feature executor."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from ncdev.claude_session import ClaudeSessionResult
from ncdev.v3.asset_manifest import save_feature_manifest
from ncdev.v3.claude_executor import (
    build_feature_prompt,
    execute_feature_claude_driven,
)
from ncdev.v3.models import (
    AssetManifest,
    AssetManifestEntry,
    CharterBundle,
    FeatureQueueDoc,
    FeatureStep,
    StepResult,
    StepStatus,
    TargetProjectContract,
    VerificationContract,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_feature(fid: str = "f01-scaffold") -> FeatureStep:
    return FeatureStep(
        feature_id=fid,
        title="Scaffold",
        description="Boot skeleton + health endpoint",
        acceptance_criteria=["Health endpoint returns 200"],
        test_requirements=["Integration test hits /api/health"],
    )


def _make_bundle(required_files: list[str] | None = None) -> CharterBundle:
    # Test-only bundle: empty test commands + no health URL so
    # _post_session_verification doesn't try to run real pytest / probe
    # a non-existent server in unit tests.
    return CharterBundle(
        contract=TargetProjectContract(project_name="myapp", project_type="web"),
        verification=VerificationContract(
            backend_health_url="",
            backend_test_command="",
            frontend_test_command="",
            minimum_test_count=0,
            required_files=required_files or [],
            prohibited_patterns=["TODO"],
            assets_manifest_required=True,
        ),
        feature_queue=FeatureQueueDoc(project_name="myapp", features=[_make_feature()]),
    )


def _init_git(path: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=str(path), check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=str(path), check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=str(path), check=True)
    (path / "README.md").write_text("initial")
    subprocess.run(["git", "add", "-A"], cwd=str(path), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(path), check=True)


def _seed_manifest(target: Path, feature_id: str) -> None:
    save_feature_manifest(target, AssetManifest(feature_id=feature_id, assets=[]))


# ---------------------------------------------------------------------------
# Prompt shape
# ---------------------------------------------------------------------------


def test_prompt_has_expected_structure(tmp_path: Path):
    feature = _make_feature()
    prompt = build_feature_prompt(
        feature=feature,
        target_path=tmp_path,
        charter_dir=tmp_path / "outputs",
        prior_feature_ids=[],
        project_id="myapp",
    )
    # Feature identity
    assert "f01-scaffold" in prompt
    assert "Scaffold" in prompt
    # Points to the charter artifacts on disk, does NOT inline them
    assert "target-project-contract.json" in prompt
    assert "verification-contract.json" in prompt
    assert "design-system.json" in prompt
    # Instructs skill usage
    assert "test-driven-development" in prompt
    assert "verification-before-completion" in prompt
    assert "systematic-debugging" in prompt
    # Codex protocol referenced (detail is in system prompt)
    assert "Codex" in prompt
    # Asset manifest section spliced in
    assert ".ncdev/assets-needed/f01-scaffold.json" in prompt


def test_prompt_mentions_prior_features(tmp_path: Path):
    prompt = build_feature_prompt(
        feature=_make_feature("f03-auth"),
        target_path=tmp_path,
        charter_dir=tmp_path / "outputs",
        prior_feature_ids=["f01-scaffold", "f02-db"],
        project_id="myapp",
    )
    assert "f01-scaffold, f02-db" in prompt


def test_prompt_handles_empty_acceptance_criteria(tmp_path: Path):
    feature = FeatureStep(
        feature_id="f01",
        title="X",
        description="Y",
        acceptance_criteria=[],
    )
    prompt = build_feature_prompt(
        feature=feature,
        target_path=tmp_path,
        charter_dir=tmp_path,
        prior_feature_ids=[],
        project_id="p",
    )
    assert "infer from description" in prompt


# ---------------------------------------------------------------------------
# Executor happy path
# ---------------------------------------------------------------------------


def test_passed_when_session_succeeds_and_commits(tmp_path: Path):
    target = tmp_path / "app"
    target.mkdir()
    _init_git(target)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        # Simulate Claude making a commit + writing a manifest
        _seed_manifest(target, "f01-scaffold")
        (target / "app.py").write_text("print('hi')")
        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "feat(f01-scaffold): hi"],
                       cwd=str(target), check=True)
        return ClaudeSessionResult(
            success=True, final_text="done", exit_code=0,
            duration_seconds=2.0, total_cost_usd=0.42,
        )

    bundle = _make_bundle()
    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):
        result = execute_feature_claude_driven(
            feature=_make_feature(),
            target_path=target,
            run_dir=tmp_path / "run",
            charter_bundle=bundle,
            prior_results=[],
            project_id="myapp",
        )

    assert result.status == StepStatus.PASSED
    assert result.commit_sha != ""
    assert "app.py" in result.files_created
    # Session metadata captured on disk
    assert (tmp_path / "run" / "steps" / "f01-scaffold" / "result.json").exists()
    assert (tmp_path / "run" / "steps" / "f01-scaffold" / "signals.json").exists()


# ---------------------------------------------------------------------------
# Executor failure paths
# ---------------------------------------------------------------------------


def test_failed_when_no_commit_made(tmp_path: Path):
    target = tmp_path / "app"
    target.mkdir()
    _init_git(target)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        # Claude session ran but did nothing
        return ClaudeSessionResult(
            success=True, final_text="I'm confused", exit_code=0,
        )

    bundle = _make_bundle()
    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):
        result = execute_feature_claude_driven(
            feature=_make_feature(),
            target_path=target,
            run_dir=tmp_path / "run",
            charter_bundle=bundle,
            prior_results=[],
            project_id="myapp",
        )
    assert result.status == StepStatus.FAILED


def test_dirty_working_tree_committed_as_broken(tmp_path: Path):
    target = tmp_path / "app"
    target.mkdir()
    _init_git(target)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        # Claude made changes but didn't commit — orchestrator must
        # commit with [BROKEN] tag so the next feature has context.
        (target / "half_done.py").write_text("# TODO implement")
        return ClaudeSessionResult(success=False, final_text="gave up", exit_code=1)

    bundle = _make_bundle()
    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):
        result = execute_feature_claude_driven(
            feature=_make_feature(),
            target_path=target,
            run_dir=tmp_path / "run",
            charter_bundle=bundle,
            prior_results=[],
            project_id="myapp",
        )

    assert result.status == StepStatus.FAILED
    # A [BROKEN] commit should exist
    log = subprocess.run(
        ["git", "log", "--oneline"],
        cwd=str(target), capture_output=True, text=True, check=True,
    )
    assert "[BROKEN]" in log.stdout


def test_missing_asset_manifest_causes_verification_failure(tmp_path: Path):
    target = tmp_path / "app"
    target.mkdir()
    _init_git(target)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        # Claude commits code that references an asset but writes no manifest.
        src = target / "src" / "App.tsx"
        src.parent.mkdir(parents=True)
        src.write_text('<img src="/images/missing.png" />')
        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): commit"],
                       cwd=str(target), check=True)
        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)

    bundle = _make_bundle()
    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):
        result = execute_feature_claude_driven(
            feature=_make_feature(),
            target_path=target,
            run_dir=tmp_path / "run",
            charter_bundle=bundle,
            prior_results=[],
            project_id="myapp",
        )

    # Session "succeeded" and committed, but verification blocks the pass
    assert result.status == StepStatus.FAILED
    reasons = result.verification.failure_reasons if result.verification else []
    assert any("manifest" in r.lower() for r in reasons)


def test_prohibited_patterns_block_pass(tmp_path: Path):
    target = tmp_path / "app"
    target.mkdir()
    _init_git(target)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        _seed_manifest(target, "f01-scaffold")
        (target / "bad.py").write_text("# TODO something")
        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): bad"],
                       cwd=str(target), check=True)
        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)

    bundle = _make_bundle()  # prohibited_patterns=["TODO"]
    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):
        result = execute_feature_claude_driven(
            feature=_make_feature(),
            target_path=target,
            run_dir=tmp_path / "run",
            charter_bundle=bundle,
            prior_results=[],
            project_id="myapp",
        )
    assert result.status == StepStatus.FAILED
    assert any("prohibited" in r.lower() for r in result.verification.failure_reasons)


def test_verification_runs_backend_test_command_when_configured(tmp_path: Path):
    """New enforcement: backend_test_command actually runs, not just documented."""
    target = tmp_path / "app"
    target.mkdir()
    _init_git(target)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        _seed_manifest(target, "f01-scaffold")
        (target / "a.py").write_text("x=1")
        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): a"],
                       cwd=str(target), check=True)
        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)

    bundle = _make_bundle()
    # Contract declares a test command that deliberately fails
    bundle.verification.backend_test_command = "false"  # exit 1

    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):
        result = execute_feature_claude_driven(
            feature=_make_feature(),
            target_path=target,
            run_dir=tmp_path / "run",
            charter_bundle=bundle,
            prior_results=[],
            project_id="myapp",
        )

    assert result.status == StepStatus.FAILED
    reasons = result.verification.failure_reasons if result.verification else []
    assert any("backend tests failed" in r for r in reasons)


def test_health_probe_polls_until_app_comes_up(monkeypatch):
    """Codex R3 blocker: probe was single-shot; now it must poll and
    accept the app when it comes up within boot_timeout_seconds."""
    from ncdev.v3 import claude_executor as ex

    attempts = {"count": 0}

    class FakeResp:
        def __init__(self, status):
            self.status_code = status

    def fake_get(url, timeout=None):  # noqa: ARG001
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise ConnectionError("app not up yet")
        return FakeResp(200)

    import httpx
    monkeypatch.setattr(httpx, "get", fake_get)

    result = ex._probe_health(
        "http://localhost:99999/health",
        timeout=10,
        per_request_timeout=1,
        poll_interval=0.05,
    )
    assert result is True
    # Multiple attempts were made — polling worked
    assert attempts["count"] >= 3


def test_health_probe_returns_false_when_budget_exhausted(monkeypatch):
    """Apps that never come up within the budget fail cleanly."""
    from ncdev.v3 import claude_executor as ex

    def fake_get(url, timeout=None):  # noqa: ARG001
        raise ConnectionError("never up")

    import httpx
    monkeypatch.setattr(httpx, "get", fake_get)

    start = time.time()
    result = ex._probe_health(
        "http://localhost:99999/health",
        timeout=1,
        per_request_timeout=1,
        poll_interval=0.1,
    )
    elapsed = time.time() - start
    assert result is False
    # Must actually respect the budget — not give up immediately, not
    # run 10x longer.
    assert 0.8 <= elapsed < 3.0, f"probe ran for {elapsed:.2f}s, expected ~1s"


def test_health_probe_early_success_returns_immediately(monkeypatch):
    """If the app is already up, don't waste the budget polling."""
    from ncdev.v3 import claude_executor as ex

    class FakeResp:
        status_code = 200

    def fake_get(url, timeout=None):  # noqa: ARG001
        return FakeResp()

    import httpx
    monkeypatch.setattr(httpx, "get", fake_get)

    start = time.time()
    result = ex._probe_health(
        "http://localhost:99999/health",
        timeout=30,
        per_request_timeout=5,
    )
    elapsed = time.time() - start
    assert result is True
    assert elapsed < 1.0


def test_health_probe_failure_blocks_pass_when_url_set(tmp_path: Path):
    """Codex R2: boot probe was soft-signal only. When the contract
    declares backend_health_url, we must enforce it — the user put
    the URL there intentionally."""
    target = tmp_path / "app"
    target.mkdir()
    _init_git(target)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        _seed_manifest(target, "f01-scaffold")
        (target / "a.py").write_text("x=1")
        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)

exec
/bin/zsh -lc "sed -n '1,320p' tests/test_ncdev_v3/test_dependency_gating.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
"""Tests for Fix 4 — dependency gating in the engine feature loop."""

from __future__ import annotations

from ncdev.v3.engine import _unmet_dependencies
from ncdev.v3.models import FeatureStep, StepResult, StepStatus


def _feat(fid: str, deps: list[str] | None = None) -> FeatureStep:
    return FeatureStep(
        feature_id=fid,
        title=fid,
        description="",
        acceptance_criteria=[],
        depends_on_features=deps or [],
    )


def test_no_deps_is_always_satisfied():
    f = _feat("f05", deps=[])
    assert _unmet_dependencies(f, completed=[]) == []


def test_dependency_not_yet_built_is_unmet():
    f = _feat("f02", deps=["f01"])
    assert _unmet_dependencies(f, completed=[]) == ["f01"]


def test_dependency_passed_is_satisfied():
    f = _feat("f02", deps=["f01"])
    completed = [StepResult(feature_id="f01", status=StepStatus.PASSED)]
    assert _unmet_dependencies(f, completed=completed) == []


def test_dependency_failed_is_unmet():
    """A failed dependency is NOT satisfied — downstream must skip."""
    f = _feat("f02", deps=["f01"])
    completed = [StepResult(feature_id="f01", status=StepStatus.FAILED)]
    assert _unmet_dependencies(f, completed=completed) == ["f01"]


def test_brownfield_skipped_dep_counts_as_satisfied():
    """Brownfield state scanner marks already-implemented features as
    SKIPPED — those count as satisfying a dep (they're really done)."""
    f = _feat("f02", deps=["f01"])
    completed = [StepResult(feature_id="f01", status=StepStatus.SKIPPED)]
    assert _unmet_dependencies(f, completed=completed) == []


def test_blocked_dep_does_NOT_count_as_satisfied():
    """Codex R2 flagged: a dependency that was BLOCKED (its own dep
    failed) must not count as met. Otherwise cascading failures break
    through the gate."""
    f = _feat("f03", deps=["f02"])
    completed = [
        StepResult(feature_id="f01", status=StepStatus.FAILED),
        StepResult(feature_id="f02", status=StepStatus.BLOCKED),
    ]
    assert _unmet_dependencies(f, completed=completed) == ["f02"]


def test_multiple_deps_partial_satisfaction():
    f = _feat("f03", deps=["f01", "f02"])
    completed = [
        StepResult(feature_id="f01", status=StepStatus.PASSED),
        StepResult(feature_id="f02", status=StepStatus.FAILED),
    ]
    assert _unmet_dependencies(f, completed=completed) == ["f02"]


def test_dep_returns_all_unmet_in_order():
    f = _feat("f05", deps=["f01", "f02", "f03", "f04"])
    completed = [
        StepResult(feature_id="f01", status=StepStatus.PASSED),
        StepResult(feature_id="f03", status=StepStatus.PASSED),
    ]
    # f02 and f04 missing entirely — both unmet, order preserved
    assert _unmet_dependencies(f, completed=completed) == ["f02", "f04"]

exec
/bin/zsh -lc "sed -n '1,320p' tests/unit/test_hooks.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
"""Tests for Phase H hooks — pre_bash_guard.evaluate()."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

# Import the hook module. Add scripts dir to path for import.
import sys
HOOKS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts" / "ncdev-hooks"
sys.path.insert(0, str(HOOKS_DIR))
import pre_bash_guard  # noqa: E402


def _init_git_with_staged(path: Path, file_content: dict[str, str]) -> None:
    """Init a git repo at ``path`` with the given files staged (not committed)."""
    subprocess.run(["git", "init", "-q"], cwd=str(path), check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=str(path), check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=str(path), check=True)
    # Seed a clean initial commit so diff --cached shows real changes
    (path / "README.md").write_text("init")
    subprocess.run(["git", "add", "README.md"], cwd=str(path), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(path), check=True)
    # Now stage the test files
    for rel, content in file_content.items():
        full = path / rel
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content)
        subprocess.run(["git", "add", rel], cwd=str(path), check=True)


# ---------------------------------------------------------------------------
# Non-Bash tools always allowed
# ---------------------------------------------------------------------------


def test_non_bash_tool_is_allowed(tmp_path: Path):
    decision, reason = pre_bash_guard.evaluate("Edit", {"file_path": "x"}, cwd=str(tmp_path))
    assert decision == "allow"
    assert reason == ""


def test_empty_bash_command_allowed(tmp_path: Path):
    decision, _ = pre_bash_guard.evaluate("Bash", {"command": ""}, cwd=str(tmp_path))
    assert decision == "allow"


def test_non_git_commands_allowed(tmp_path: Path):
    decision, _ = pre_bash_guard.evaluate("Bash", {"command": "ls -la"}, cwd=str(tmp_path))
    assert decision == "allow"
    decision, _ = pre_bash_guard.evaluate("Bash", {"command": "pytest -q"}, cwd=str(tmp_path))
    assert decision == "allow"


# ---------------------------------------------------------------------------
# Conventional Commits enforcement
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("good", [
    "feat: add login",
    "fix(auth): handle expired tokens",
    "test: cover edge case",
    "chore: bump deps",
    "refactor(api): split router",
    "docs: update readme",
    "perf: cache query",
])
def test_conventional_messages_pass(tmp_path: Path, good: str):
    _init_git_with_staged(tmp_path, {"foo.py": "x = 1\n"})
    cmd = f'git commit -m "{good}"'
    decision, reason = pre_bash_guard.evaluate("Bash", {"command": cmd}, cwd=str(tmp_path))
    assert decision == "allow", reason


@pytest.mark.parametrize("bad", [
    "updated stuff",
    "WIP",
    "quick fix",
    "Added feature",
])
def test_non_conventional_messages_blocked(tmp_path: Path, bad: str):
    _init_git_with_staged(tmp_path, {"foo.py": "x = 1\n"})
    cmd = f'git commit -m "{bad}"'
    decision, reason = pre_bash_guard.evaluate("Bash", {"command": cmd}, cwd=str(tmp_path))
    assert decision == "block"
    assert "Conventional Commits" in reason


def test_commit_with_F_file_flag_is_allowed(tmp_path: Path):
    """-F <file> — message is in a file; we can't introspect, allow."""
    _init_git_with_staged(tmp_path, {"foo.py": "x = 1\n"})
    decision, _ = pre_bash_guard.evaluate(
        "Bash",
        {"command": 'git commit -F message.txt'},
        cwd=str(tmp_path),
    )
    assert decision == "allow"


def test_commit_with_heredoc_is_allowed(tmp_path: Path):
    """HEREDOC substitution — can't parse the message cheaply, allow."""
    _init_git_with_staged(tmp_path, {"foo.py": "x = 1\n"})
    cmd = '''git commit -m "$(cat <<'EOF'
feat: add heredoc support
EOF
)"'''
    decision, _ = pre_bash_guard.evaluate(
        "Bash", {"command": cmd}, cwd=str(tmp_path),
    )
    assert decision == "allow"


def test_commit_message_with_escaped_quotes_parses_correctly(tmp_path: Path):
    """Codex flag: escaped inner quotes broke the extractor. Verify fix."""
    _init_git_with_staged(tmp_path, {"foo.py": "x = 1\n"})
    cmd = 'git commit -m "feat: handle \\"escaped\\" quotes"'
    decision, reason = pre_bash_guard.evaluate(
        "Bash", {"command": cmd}, cwd=str(tmp_path),
    )
    # The message starts with "feat:" so Conventional Commits accepts it
    assert decision == "allow", reason


def test_bad_message_with_escaped_quotes_still_blocked(tmp_path: Path):
    """Extractor must not be tricked into missing a bad message by escapes."""
    _init_git_with_staged(tmp_path, {"foo.py": "x = 1\n"})
    cmd = 'git commit -m "updated \\"thing\\" again"'
    decision, reason = pre_bash_guard.evaluate(
        "Bash", {"command": cmd}, cwd=str(tmp_path),
    )
    assert decision == "block"
    assert "Conventional Commits" in reason


# ---------------------------------------------------------------------------
# Prohibited patterns
# ---------------------------------------------------------------------------


def test_staged_content_with_todo_is_blocked(tmp_path: Path):
    _init_git_with_staged(tmp_path, {
        "src/app.py": "def run():\n    # TODO implement\n    pass\n",
    })
    decision, reason = pre_bash_guard.evaluate(
        "Bash",
        {"command": 'git commit -m "feat: initial"'},
        cwd=str(tmp_path),
    )
    assert decision == "block"
    assert "TODO" in reason
    assert "src/app.py" in reason


def test_regex_prohibited_pattern_matches_at_hook_level(tmp_path: Path, monkeypatch):
    """Codex R2: hook used substring only; regex entries from the
    verification contract never fired at commit time. Parity check."""
    config = tmp_path / "hooks.json"
    config.write_text('{"prohibited_patterns": ["except:\\\\s*pass"]}')
    monkeypatch.setenv("NCDEV_HOOKS_CONFIG", str(config))

    _init_git_with_staged(tmp_path, {
        "bad.py": "try:\n    x = 1\nexcept:    pass\n",
    })
    decision, reason = pre_bash_guard.evaluate(
        "Bash", {"command": 'git commit -m "feat: add thing"'},
        cwd=str(tmp_path),
    )
    assert decision == "block"
    assert "except:" in reason or "pass" in reason


def test_staged_content_with_console_log_is_blocked(tmp_path: Path):
    _init_git_with_staged(tmp_path, {
        "frontend/app.tsx": 'export const x = () => { console.log("hi"); };\n',
    })
    decision, reason = pre_bash_guard.evaluate(
        "Bash",
        {"command": 'git commit -m "feat: add thing"'},
        cwd=str(tmp_path),
    )
    assert decision == "block"
    assert "console.log(" in reason


def test_clean_staged_content_passes(tmp_path: Path):
    _init_git_with_staged(tmp_path, {
        "src/app.py": "def run():\n    return 42\n",
        "tests/test_app.py": "def test_run():\n    assert run() == 42\n",
    })
    decision, reason = pre_bash_guard.evaluate(
        "Bash",
        {"command": 'git commit -m "feat: add run"'},
        cwd=str(tmp_path),
    )
    assert decision == "allow", reason


def test_prohibited_in_existing_unchanged_file_is_ok(tmp_path: Path):
    # Pattern exists in HEAD but is not being added by the current diff — OK.
    subprocess.run(["git", "init", "-q"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=str(tmp_path), check=True)
    (tmp_path / "old.py").write_text("# TODO from history\n")
    subprocess.run(["git", "add", "-A"], cwd=str(tmp_path), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init: legacy"], cwd=str(tmp_path), check=True)

    # New clean change staged
    (tmp_path / "new.py").write_text("x = 1\n")
    subprocess.run(["git", "add", "new.py"], cwd=str(tmp_path), check=True)

    decision, reason = pre_bash_guard.evaluate(
        "Bash",
        {"command": 'git commit -m "feat: add new"'},
        cwd=str(tmp_path),
    )
    assert decision == "allow", reason


# ---------------------------------------------------------------------------
# Force-push protection
# ---------------------------------------------------------------------------


def test_force_push_to_main_blocked(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("NCDEV_ALLOW_FORCE_PUSH", raising=False)
    decision, reason = pre_bash_guard.evaluate(
        "Bash",
        {"command": "git push --force origin main"},
        cwd=str(tmp_path),
    )
    assert decision == "block"
    assert "Force-push" in reason
    assert "NCDEV_ALLOW_FORCE_PUSH" in reason


def test_force_push_to_feature_branch_allowed(tmp_path: Path):
    decision, _ = pre_bash_guard.evaluate(
        "Bash",
        {"command": "git push --force origin feature/my-branch"},
        cwd=str(tmp_path),
    )
    assert decision == "allow"


def test_force_push_override_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("NCDEV_ALLOW_FORCE_PUSH", "1")
    decision, _ = pre_bash_guard.evaluate(
        "Bash",
        {"command": "git push --force origin main"},
        cwd=str(tmp_path),
    )
    assert decision == "allow"


# ---------------------------------------------------------------------------
# Project-level hook config override
# ---------------------------------------------------------------------------


def test_custom_prohibited_patterns_via_env(tmp_path: Path, monkeypatch):
    config = tmp_path / "hooks.json"
    config.write_text('{"prohibited_patterns": ["SECRET"]}')
    monkeypatch.setenv("NCDEV_HOOKS_CONFIG", str(config))

    # Stage content with SECRET, not TODO
    _init_git_with_staged(tmp_path, {
        "x.py": 'API_SECRET = "oops"\n',
    })
    decision, reason = pre_bash_guard.evaluate(
        "Bash",
        {"command": 'git commit -m "feat: add key"'},
        cwd=str(tmp_path),
    )
    assert decision == "block"
    assert "SECRET" in reason

exec
/bin/zsh -lc "sed -n '360,520p' tests/unit/test_ai_session.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
    buf.append("x" * 25)
    text = buf.text()
    assert buf.truncated is True
    assert len(text.encode("utf-8")) <= 10
    # The tail is preserved — last 10 'x' characters
    assert text == "x" * 10


def test_tail_buffer_normal_eviction_across_chunks():
    """Multiple small chunks — head gets evicted as cap is exceeded."""
    from ncdev.ai_session import _TailBuffer

    buf = _TailBuffer(10)
    buf.append("aaaa")
    buf.append("bbbb")
    buf.append("cccc")    # total 12 > 10; head "aaaa" gets evicted
    text = buf.text()
    assert buf.truncated is True
    assert "cccc" in text
    # "aaaa" at the head was evicted; size must be under cap
    assert len(text.encode("utf-8")) <= 10


def test_tail_buffer_keeps_last_chunk_even_when_oversized_alone():
    """When only one chunk exists and it's oversized, slice its tail
    instead of losing everything."""
    from ncdev.ai_session import _TailBuffer

    buf = _TailBuffer(5)
    buf.append("1234567890")
    text = buf.text()
    assert text == "67890"


def test_run_codex_session_watchdog_kills_hung_child(tmp_path: Path):
    """Integration: actual hung child must be killed by the watchdog,
    same guarantee as run_claude_session."""
    import sys as _sys

    fake_cli = tmp_path / "fake-codex"
    fake_cli.write_text(
        "#!/usr/bin/env python3\nimport time\n"
        "while True:\n    time.sleep(1)\n",
        encoding="utf-8",
    )
    fake_cli.chmod(0o755)

    import subprocess as _sp
    orig_popen = _sp.Popen

    def fake_popen(cmd, **kwargs):
        new_cmd = [_sys.executable, str(fake_cli)] + list(cmd[1:])
        return orig_popen(new_cmd, **kwargs)

    start = time.time()
    with patch("ncdev.ai_session.shutil.which", return_value=str(fake_cli)):
        with patch("ncdev.ai_session.subprocess.Popen", side_effect=fake_popen):
            result = run_codex_session("x", cwd=tmp_path, timeout=2)
    elapsed = time.time() - start

    assert elapsed < 15, f"codex watchdog failed: {elapsed:.1f}s"
    assert result.success is False
    assert "timed out" in (result.error or "")

exec
/bin/zsh -lc "sed -n '420,760p' tests/unit/test_claude_session.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
    Default is now OFF — result.events should be empty unless asked."""
    events = [
        {"type": "assistant", "message": {"content": []}},
        {"type": "result", "result": "ok"},
    ]
    popen, _ = _popen_factory(events)
    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
            result = run_claude_session(
                "x", cwd=tmp_path, include_codex_protocol=False,
            )
    assert result.events == []
    # But final_text still resolves via the ring buffer
    assert result.final_text == "ok"


def test_retain_events_flag_opt_in(tmp_path: Path):
    events = [
        {"type": "assistant", "message": {"content": []}},
        {"type": "result", "result": "ok"},
    ]
    popen, _ = _popen_factory(events)
    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
            result = run_claude_session(
                "x", cwd=tmp_path,
                include_codex_protocol=False,
                retain_events=True,
            )
    assert len(result.events) == 2


def test_watchdog_actually_kills_hung_subprocess(tmp_path: Path):
    """Integration — spawn a real process that never exits, verify
    run_claude_session kills it via the watchdog within ~timeout seconds.

    This is Codex's critical issue: stdout-block deadlock. If the
    watchdog isn't wired, this test hangs forever.
    """
    import sys as _sys

    # Stand-in for `claude` — a python inline script that hangs reading stdin.
    # We point shutil.which at this to fool the preflight check.
    fake_cli = tmp_path / "fake-claude"
    fake_cli.write_text(
        "#!/usr/bin/env python3\nimport sys, time\n"
        "# never produces output, never exits\n"
        "while True:\n    time.sleep(1)\n",
        encoding="utf-8",
    )
    fake_cli.chmod(0o755)

    import subprocess as _sp

    orig_popen = _sp.Popen

    def fake_popen(cmd, **kwargs):
        # Replace the claude executable with our hanging script
        new_cmd = [_sys.executable, str(fake_cli)] + list(cmd[1:])
        return orig_popen(new_cmd, **kwargs)

    start = time.time()
    with patch("ncdev.claude_session.shutil.which", return_value=str(fake_cli)):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=fake_popen):
            result = run_claude_session(
                "x", cwd=tmp_path,
                timeout=2,   # wall-clock kill after 2s
                include_codex_protocol=False,
            )
    elapsed = time.time() - start

    # Hard upper bound: watchdog + wait should terminate within ~10s even
    # on a slow CI runner. No test should take 2 minutes, which is what
    # would happen if the watchdog were broken.
    assert elapsed < 15, f"watchdog failed to kill: elapsed={elapsed:.1f}s"
    assert result.success is False
    assert "timed out" in (result.error or "")


def test_stderr_backpressure_does_not_deadlock(tmp_path: Path):
    """Integration — child emits massive stderr while stdout is light.
    Without the stderr-drain thread, the pipe fills and the child hangs.
    """
    import sys as _sys
    fake_cli = tmp_path / "fake-claude"
    fake_cli.write_text(
        "#!/usr/bin/env python3\nimport sys, json\n"
        # Emit one result event on stdout, then flood stderr with ~2MB
        # of output and exit cleanly.
        'print(json.dumps({"type":"result","result":"ok"}))\n'
        "sys.stdout.flush()\n"
        "for _ in range(20000):\n"
        '    sys.stderr.write("x" * 100 + "\\n")\n'
        "sys.stderr.flush()\n",
        encoding="utf-8",
    )
    fake_cli.chmod(0o755)

    import subprocess as _sp
    orig_popen = _sp.Popen

    def fake_popen(cmd, **kwargs):
        new_cmd = [_sys.executable, str(fake_cli)] + list(cmd[1:])
        return orig_popen(new_cmd, **kwargs)

    start = time.time()
    with patch("ncdev.claude_session.shutil.which", return_value=str(fake_cli)):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=fake_popen):
            result = run_claude_session(
                "x", cwd=tmp_path,
                timeout=15,
                include_codex_protocol=False,
            )
    elapsed = time.time() - start
    # Must complete cleanly — not timeout, not hang
    assert elapsed < 10, f"stderr backpressure deadlocked: elapsed={elapsed:.1f}s"
    assert result.success is True
    assert result.final_text == "ok"
    assert len(result.stderr) > 100_000    # captured the flood


def test_summary_includes_key_signals(tmp_path: Path):
    events = [
        {
            "type": "assistant",
            "message": {"content": [
                {"type": "tool_use", "name": "Skill",
                 "input": {"skill": "verification-before-completion"}},
                {"type": "tool_use", "name": "Bash",
                 "input": {"command": "codex exec --full-auto 'x'"}},
            ]},
        },
        {"type": "result", "result": "ok", "total_cost_usd": 1.23},
    ]
    popen, _ = _popen_factory(events)
    with patch("ncdev.claude_session.shutil.which", return_value="/usr/bin/claude"):
        with patch("ncdev.claude_session.subprocess.Popen", side_effect=popen):
            result = run_claude_session(
                "x", cwd=tmp_path, include_codex_protocol=False,
            )
    s = result.summary()
    assert "success=True" in s
    assert "cost=$1.230" in s
    assert "skills=verification-before-completion" in s
    assert "codex=1" in s

exec
/bin/zsh -lc "sed -n '420,840p' tests/unit/test_claude_executor.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): a"],
                       cwd=str(target), check=True)
        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)

    bundle = _make_bundle()
    # Set a URL that definitely doesn't respond
    bundle.verification.backend_health_url = "http://127.0.0.1:1/health"
    bundle.verification.boot_timeout_seconds = 1

    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):
        result = execute_feature_claude_driven(
            feature=_make_feature(),
            target_path=target,
            run_dir=tmp_path / "run",
            charter_bundle=bundle,
            prior_results=[],
            project_id="myapp",
        )

    assert result.status == StepStatus.FAILED
    reasons = result.verification.failure_reasons
    assert any("health URL unreachable" in r for r in reasons)


def test_health_probe_not_run_when_url_empty(tmp_path: Path):
    """Empty URL means contract says 'no web boot check' — skip probe."""
    target = tmp_path / "app"
    target.mkdir()
    _init_git(target)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        _seed_manifest(target, "f01-scaffold")
        (target / "a.py").write_text("x=1")
        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): a"],
                       cwd=str(target), check=True)
        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)

    bundle = _make_bundle()  # backend_health_url="" by default in _make_bundle
    assert bundle.verification.backend_health_url == ""

    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):
        result = execute_feature_claude_driven(
            feature=_make_feature(),
            target_path=target,
            run_dir=tmp_path / "run",
            charter_bundle=bundle,
            prior_results=[],
            project_id="myapp",
        )
    # No health-URL failure — probe was skipped
    assert result.status == StepStatus.PASSED


def test_verification_enforces_minimum_test_count(tmp_path: Path):
    target = tmp_path / "app"
    target.mkdir()
    _init_git(target)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        _seed_manifest(target, "f01-scaffold")
        (target / "foo.py").write_text("pass")
        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): notests"],
                       cwd=str(target), check=True)
        return ClaudeSessionResult(success=True, final_text="ok", exit_code=0)

    bundle = _make_bundle()
    bundle.verification.minimum_test_count = 1
    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):
        result = execute_feature_claude_driven(
            feature=_make_feature(),
            target_path=target,
            run_dir=tmp_path / "run",
            charter_bundle=bundle,
            prior_results=[],
            project_id="myapp",
        )
    assert result.status == StepStatus.FAILED
    assert any("test file count" in r for r in result.verification.failure_reasons)


def test_verification_regex_prohibited_pattern_matches(tmp_path: Path):
    """Codex flagged: `r'except:\\s*pass'` was substring-checked and never
    fired. With regex enforcement it must match."""
    target = tmp_path / "app"
    target.mkdir()
    _init_git(target)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        _seed_manifest(target, "f01-scaffold")
        (target / "bad.py").write_text("try:\n    x = 1\nexcept:   pass\n")
        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): bad"],
                       cwd=str(target), check=True)
        return ClaudeSessionResult(success=True, final_text="ok", exit_code=0)

    bundle = _make_bundle()
    bundle.verification.prohibited_patterns = [r"except:\s*pass"]
    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):
        result = execute_feature_claude_driven(
            feature=_make_feature(),
            target_path=target,
            run_dir=tmp_path / "run",
            charter_bundle=bundle,
            prior_results=[],
            project_id="myapp",
        )
    assert result.status == StepStatus.FAILED
    assert any("prohibited" in r.lower() for r in result.verification.failure_reasons)


def test_required_files_missing_blocks_pass(tmp_path: Path):
    target = tmp_path / "app"
    target.mkdir()
    _init_git(target)

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        _seed_manifest(target, "f01-scaffold")
        (target / "thing.py").write_text("x=1")
        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): x"],
                       cwd=str(target), check=True)
        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)

    bundle = _make_bundle(required_files=["docker-compose.yml", "README.md"])
    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):
        result = execute_feature_claude_driven(
            feature=_make_feature(),
            target_path=target,
            run_dir=tmp_path / "run",
            charter_bundle=bundle,
            prior_results=[],
            project_id="myapp",
        )
    # docker-compose.yml missing — verification fails, but README.md already exists from _init_git.
    assert result.status == StepStatus.FAILED
    reasons = result.verification.failure_reasons
    assert any("docker-compose.yml" in r for r in reasons)

codex
I’ve narrowed this to a few likely seam bugs rather than broad architectural problems. I’m checking whether the current round-4 notes already line up with what the code is still doing wrong, then I’ll patch the concrete defects and add regression coverage around them.
exec
/bin/zsh -lc "sed -n '1,260p' docs/codex-review/review-response-round4.md" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
OpenAI Codex v0.121.0 (research preview)
--------
workdir: /Users/nrupal/dev/yensi/dev/nc-dev-system
model: gpt-5.4
provider: openai
approval: never
sandbox: workspace-write [workdir, /tmp, $TMPDIR, /Users/nrupal/.codex/memories]
reasoning effort: medium
reasoning summaries: none
session id: 019db668-2114-7c30-8e32-fff70131e58f
--------
user
# Peer review request — Round 4

You are Codex. This is the fourth pass. Your three previous reviews
are on disk at `docs/codex-review/review-response.md`,
`review-response-round2.md`, and `review-response-round3.md`.

Since R3 I committed `f80247f` on `claude-orchestrator-migration`.
It claims to close every item from your R3 review:

- **R3-A (the default-path blocker you called out)**: `_probe_health`
  now polls with short per-request timeout, retries on failure, honours
  the full `boot_timeout_seconds` as the startup grace budget.
- **R3-B**: `state_scanner.build_skip_results` now returns
  `StepStatus.SKIPPED`, not `PASSED`. Engine's `state.completed_features`
  counter adjusted to count PASSED + SKIPPED so the human-facing
  "done" number stays meaningful.
- **R3-C**: `metrics.py` now tracks `blocked_features` + `skipped_features`
  as detail, and `failed_features = FAILED + BLOCKED` so the
  run-level failure count matches the engine's overall-status
  computation.
- **R3-D**: `_TailBuffer` oversized single-chunk behaviour fixed —
  when one chunk > max_bytes, we slice the UTF-8 tail bytes of that
  chunk instead of evicting it wholesale.
- **R3-E**: `run_ai_session` catches `ValueError` from
  `_resolve_custom_providers` and returns a structured
  `ClaudeSessionResult(success=False, error=...)` with an actionable
  message naming the bad provider value.

426/426 tests passing. +8 regression tests.

Your job now:

1. **Verify R3 fixes landed correctly** — same drill as before, but
   focus specifically on the probe polling (your stated blocker),
   `_TailBuffer` edge cases, and the state_scanner semantic fix.
2. **Find bugs I introduced in the R3 pass.**
3. **Decide: ready to inherit?** You said R3 needed the probe fix +
   ideally the TailBuffer fix. Both are done. If anything else is
   still blocking, name it plainly. If not, say so plainly.

## Files to look at

- `src/ncdev/v3/claude_executor.py` around `_probe_health` — new
  polling loop. Is the time-budget math right? Does it respect
  `per_request_timeout`? What if `per_request_timeout > timeout`?
- `src/ncdev/ai_session.py` `_TailBuffer.append()` — new oversized-
  chunk branch. UTF-8 boundary safety on the slice? The decode uses
  `errors="ignore"` — is that acceptable?
- `src/ncdev/v3/state_scanner.py` `build_skip_results` — SKIPPED change.
- `src/ncdev/v3/engine.py` `state.completed_features` — PASSED+SKIPPED.
- `src/ncdev/v3/metrics.py` `compute_run_metrics` — BLOCKED accounting.
- `src/ncdev/ai_session.py` `run_ai_session` — new ValueError catch.

## Specific questions

1. **Probe polling math.** The loop is:
   ```python
   deadline = time.time() + max(timeout, 1)
   while time.time() < deadline:
       ...
       time.sleep(min(poll_interval, max(deadline - time.time(), 0)))
   ```
   Is there a case where a single request's `req_timeout` is tiny
   (because the remaining budget is <5s) and we burn through attempts
   too fast? Is `min(per_request_timeout, remaining)` right when
   `remaining` is 0.1s?
2. **`_TailBuffer` UTF-8 boundary.** Slicing bytes at `-self._max:`
   can land mid-codepoint. `decode(errors="ignore")` drops the broken
   bytes. That's what I wanted, but it means callers see slightly less
   than `max_bytes` in the common case. Acceptable?
3. **`state.completed_features` semantics.** Human reads the run
   panel and sees "3/5 features completed". After R3-B, that 3 now
   includes features the state scanner skipped as brownfield-already-
   done. Is that the right human reading, or should the panel separate
   "built" from "already there"? (Low priority, UX question.)
4. **Metrics throughput math.** `feature_throughput_per_hour` divides
   `len(passed)` by duration. With R3-B, brownfield-skipped features
   are SKIPPED (not PASSED), so they're excluded from throughput —
   correct, because we didn't actually build them. Agree?

## Output shape

Keep it tight. If the blocker list is empty, say so.

```
## R3 fixes verified

## R3 fixes that still didn't land

## New issues introduced in R3

## Ready to inherit?

## Honest one-liner
```

Last round unless you find something real.

codex
Reviewing the delta around the R3 fixes first, with emphasis on the probe loop, `_TailBuffer`, and the skip-state semantics. Then I’ll check the new regression tests against the code paths they claim to cover and look for any fresh regressions introduced by `f80247f`.
exec
/bin/zsh -lc 'git rev-parse --abbrev-ref HEAD && git rev-parse HEAD && git show --stat --oneline --no-patch f80247f && rg -n "def _probe_health|deadline = time.time|per_request_timeout|req_timeout|_TailBuffer|build_skip_results|completed_features|compute_run_metrics|ValueError|_resolve_custom_providers|feature_throughput_per_hour" src tests' in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
claude-orchestrator-migration
f80247f58acf3412c7fe3b82f90aa33335cdfcc3
f80247f fix(hardening-r3): address R3 regressions from Codex round-3 review
src/ncdev/provider_dispatch.py:64:        raise ValueError(
src/ncdev/provider_dispatch.py:81:        raise ValueError(
tests/test_ncdev_v3/test_state_scanner.py:7:    build_skip_results,
tests/test_ncdev_v3/test_state_scanner.py:8:    scan_completed_features,
tests/test_ncdev_v3/test_state_scanner.py:61:def test_build_skip_results():
tests/test_ncdev_v3/test_state_scanner.py:66:    results = build_skip_results(features, {"f1", "f3"})
tests/test_ncdev_v3/test_state_scanner.py:74:def test_scan_completed_features_no_git(tmp_path):
tests/test_ncdev_v3/test_state_scanner.py:77:    result = scan_completed_features(tmp_path, features)
tests/test_ncdev_v3/test_state_scanner.py:81:def test_scan_completed_features_with_git(tmp_path):
tests/test_ncdev_v3/test_state_scanner.py:101:    result = scan_completed_features(tmp_path, features)
src/ncdev/cli.py:376:        console.print(f"features: {state.completed_features}/{state.total_features} passed")
tests/unit/test_ai_provider.py:42:        with pytest.raises(ValueError, match="Unknown AI provider 'gpt4'"):
tests/unit/test_ai_provider.py:143:        with pytest.raises(ValueError):
tests/unit/test_ai_provider.py:148:            with pytest.raises(ValueError):
tests/test_ncdev_v3/test_metrics.py:1:from ncdev.v3.metrics import compute_run_metrics
tests/test_ncdev_v3/test_metrics.py:18:    m = compute_run_metrics(state)
tests/test_ncdev_v3/test_metrics.py:37:    m = compute_run_metrics(state)
tests/test_ncdev_v3/test_metrics.py:55:    m = compute_run_metrics(state)
tests/test_ncdev_v3/test_metrics.py:64:    m = compute_run_metrics(state)
tests/test_ncdev_v3/test_metrics.py:74:    m = compute_run_metrics(state)
tests/test_ncdev_v3/test_metrics.py:94:    m = compute_run_metrics(state)
tests/test_ncdev_v3/test_metrics.py:108:    m = compute_run_metrics(state, ingestion_doc_count=12)
tests/unit/test_claude_executor.py:353:        per_request_timeout=1,
tests/unit/test_claude_executor.py:375:        per_request_timeout=1,
tests/unit/test_claude_executor.py:402:        per_request_timeout=5,
tests/test_ncdev_v2/test_modes.py:63:    with pytest.raises(ValueError, match="Unknown mode"):
tests/unit/test_ai_session.py:30:    user's hand-tuned routing via _resolve_custom_providers."""
tests/unit/test_ai_session.py:197:    ValueError uncaught mid-run. Now must surface as a structured
tests/unit/test_ai_session.py:355:    """Codex R3 flagged: _TailBuffer(10).append('x' * 25) previously
tests/unit/test_ai_session.py:357:    from ncdev.ai_session import _TailBuffer
tests/unit/test_ai_session.py:359:    buf = _TailBuffer(10)
tests/unit/test_ai_session.py:370:    from ncdev.ai_session import _TailBuffer
tests/unit/test_ai_session.py:372:    buf = _TailBuffer(10)
tests/unit/test_ai_session.py:386:    from ncdev.ai_session import _TailBuffer
tests/unit/test_ai_session.py:388:    buf = _TailBuffer(5)
src/ncdev/v3/models.py:122:    completed_features: int = 0
src/ncdev/v3/claude_executor.py:534:def _probe_health(
src/ncdev/v3/claude_executor.py:538:    per_request_timeout: int = 5,
src/ncdev/v3/claude_executor.py:556:    deadline = time.time() + max(timeout, 1)
src/ncdev/v3/claude_executor.py:561:        req_timeout = min(per_request_timeout, remaining)
src/ncdev/v3/claude_executor.py:563:            r = httpx.get(url, timeout=req_timeout)
tests/conftest.py:1212:                    "error": "AssertionError: Expected status 'invalid' to raise ValueError",
src/ncdev/v3/charter.py:212:    except (FileNotFoundError, json.JSONDecodeError, ValueError):
src/ncdev/v3/metrics.py:41:    feature_throughput_per_hour: float = 0.0
src/ncdev/v3/metrics.py:49:def compute_run_metrics(
src/ncdev/v3/metrics.py:113:        feature_throughput_per_hour=(
src/ncdev/v3/state_scanner.py:21:def scan_completed_features(
src/ncdev/v3/state_scanner.py:54:def build_skip_results(
src/ncdev/v3/engine.py:209:        remaining = _filter_completed_features(target_path, features, completed)
src/ncdev/v3/engine.py:263:            state.completed_features = len([
src/ncdev/v3/engine.py:317:def _filter_completed_features(target_path: Path, features, completed: list[StepResult]):
src/ncdev/v3/engine.py:320:        from ncdev.v3.state_scanner import build_skip_results, scan_completed_features
src/ncdev/v3/engine.py:324:        done_ids = set(scan_completed_features(target_path, features))
src/ncdev/v3/engine.py:329:    skipped = build_skip_results(features, done_ids)
tests/test_ncdev_v2/test_sentinel_safety.py:197:        key = DeduplicationTracker.make_key("svc", "file.py", "func", "ValueError")
tests/test_ncdev_v2/test_sentinel_safety.py:202:        key = DeduplicationTracker.make_key("svc", "file.py", "func", "ValueError")
tests/test_ncdev_v2/test_sentinel_safety.py:208:        key = DeduplicationTracker.make_key("svc", "file.py", "func", "ValueError")
src/ncdev/ai_provider.py:420:    Raises :class:`ValueError` for unknown provider names.
src/ncdev/ai_provider.py:423:        raise ValueError(
src/ncdev/ai_provider.py:438:    Raises :class:`ValueError` if neither name is valid.
src/ncdev/ai_session.py:75:def _resolve_custom_providers(cfg: NCDevV2Config) -> tuple[str, str]:
src/ncdev/ai_session.py:141:            orch, impl = _resolve_custom_providers(cfg)
src/ncdev/ai_session.py:142:        except ValueError as exc:
src/ncdev/ai_session.py:271:    stdout_buf = _TailBuffer(max_bytes_per_stream)
src/ncdev/ai_session.py:272:    stderr_buf = _TailBuffer(max_bytes_per_stream)
src/ncdev/ai_session.py:274:    def _drain(stream, buf: "_TailBuffer") -> None:
src/ncdev/ai_session.py:361:class _TailBuffer:
src/ncdev/v2/config.py:188:            raise ValueError(

exec
/bin/zsh -lc "sed -n '1,260p' src/ncdev/v3/claude_executor.py && printf '\\n---FILE---\\n' && sed -n '1,260p' src/ncdev/ai_session.py && printf '\\n---FILE---\\n' && sed -n '1,240p' src/ncdev/v3/state_scanner.py && printf '\\n---FILE---\\n' && sed -n '1,260p' src/ncdev/v3/engine.py && printf '\\n---FILE---\\n' && sed -n '1,260p' src/ncdev/v3/metrics.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
"""Phase E — Claude-driven feature executor.

Replaces the old ``step_executor.py`` manual build/verify/repair loop.
For each feature we spawn exactly one Claude session. Claude drives
the full build using its own skill machinery:

    * ``writing-plans``                 — if the feature is complex
    * ``test-driven-development``       — write failing test, then code
    * ``verification-before-completion`` — no "done" without evidence
    * ``systematic-debugging``          — when verification fails

Claude shells out to Codex via Bash for implementation and test writing
(the Codex-via-bash protocol is injected automatically by
:func:`run_claude_session`).  NC Dev orchestrates the outer loop only:

    1. Compose the feature prompt (charter refs, prior results, asset
       manifest requirement, verification contract).
    2. Run the session. Stream events.
    3. Inspect git state afterwards:
         * clean working tree + new commit(s) → PASSED
         * changes present but no commit     → commit with [BROKEN] tag
         * no changes at all                 → FAILED, builder didn't do anything
    4. Run post-hoc verification: manifest covers refs, required files exist.
    5. Return StepResult. Orchestrator moves to the next feature.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

from ncdev.ai_session import run_ai_session
from ncdev.claude_session import (
    DEFAULT_BUILD_TOOLS,
    ClaudeSessionResult,
)
from ncdev.v2.config import NCDevV2Config
from ncdev.v3.asset_manifest import (
    manifest_prompt_section,
    verify_manifest_covers_references,
)
from ncdev.v3.models import (
    CharterBundle,
    FeatureStep,
    StepResult,
    StepStatus,
    StepVerification,
    TestResult,
)


# ---------------------------------------------------------------------------
# Prompt composition
# ---------------------------------------------------------------------------


def build_feature_prompt(
    feature: FeatureStep,
    target_path: Path,
    charter_dir: Path,
    prior_feature_ids: list[str],
    project_id: str,
    citex_url: str = "http://localhost:20161",
) -> str:

exec
/bin/zsh -lc "sed -n '1,260p' docs/codex-review/round4-sweep-log.md" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
OpenAI Codex v0.121.0 (research preview)
--------
workdir: /Users/nrupal/dev/yensi/dev/nc-dev-system
model: gpt-5.4
provider: openai
approval: never
sandbox: workspace-write [workdir, /tmp, $TMPDIR, /Users/nrupal/.codex/memories]
reasoning effort: medium
reasoning summaries: none
session id: 019db669-fd42-70f0-a5c7-4d98d24492de
--------
user
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

codex
I’m doing a repo sweep with emphasis on the V3 pipeline, prior review follow-ups, and verification paths. I’ll start by reading the existing review notes and the current branch/test state, then I’ll reproduce issues, patch them, add coverage, and finish by running the full suite.
  → Read prior review notes and inspect current branch/test state
  • Identify remaining defects in load-bearing V3/session/hook code
  • Implement targeted fixes and add regression tests
  • Run full pytest suite and verify clean pass
exec
/bin/zsh -lc "sed -n '1,260p' docs/codex-review/review-response-round2.md" in /Users/nrupal/dev/yensi/dev/nc-dev-system
exec
/bin/zsh -lc "sed -n '1,220p' docs/codex-review/review-response.md" in /Users/nrupal/dev/yensi/dev/nc-dev-system
exec
/bin/zsh -lc "sed -n '1,260p' docs/codex-review/review-response-round3.md" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
OpenAI Codex v0.121.0 (research preview)
--------
workdir: /Users/nrupal/dev/yensi/dev/nc-dev-system
model: gpt-5.4
provider: openai
approval: never
sandbox: workspace-write [workdir, /tmp, $TMPDIR, /Users/nrupal/.codex/memories]
reasoning effort: medium
reasoning summaries: none
session id: 019db60a-61cb-7fb0-873f-80bd2ab68493
--------
user
# Peer review request — Round 2, post-hardening

You are Codex. I am Claude. You reviewed this branch
(`claude-orchestrator-migration` at
`/Users/nrupal/dev/yensi/dev/nc-dev-system`) two commits ago. Your first
review is on disk at `docs/codex-review/review-response.md` — read it
first so you know what you said.

I've since committed a hardening pass (`f19934b`, "fix(hardening):
address all critical issues from Codex review") that claims to resolve
every critical item from your first review. Your job this time is:

1. **Verify the fixes.** Did I actually fix what you flagged, or did I
   paper over it with a test that locks in the bug?
2. **Find new issues introduced by the fix pass.** Refactors create
   new bugs. What did I break?
3. **Recheck the concerning-but-not-critical list** from your first
   review — what's still there?
4. **Hold the bar.** If something is still weak, say so plainly. If
   something I claimed to fix is actually a nice UI around the same
   underlying bug, say that too.

## What I changed (commit `f19934b`)

### Fix 1 — mode switch actually drives V3
- New file `src/ncdev/ai_session.py`: `run_ai_session()` dispatches on
  `NCDevV2Config.mode` via `MODE_ORCHESTRATOR` (which provider runs the
  orchestrator session) and `MODE_IMPLEMENTER` (who writes code).
  - `claude_plan_codex_build` → Claude session with Codex protocol injected.
  - `claude_only` → Claude session, Codex protocol suppressed.
  - `codex_only` → `run_codex_session()`, new runner, shells `codex exec`
    directly; no skills, no hooks, no Codex protocol.
  - `openrouter` → `raise NotImplementedError(...)` with a concrete
    actionable message.
  - `custom` → defaults to Claude orchestrator + Codex implementer.
- `charter.py`, `design_phase.py`, `claude_executor.py`, `dev.py` now
  call `run_ai_session` and forward a `config: NCDevV2Config` kwarg.
- `engine.py:run_v3_full()` loads the v2 config via
  `ensure_default_v2_config(workspace)` and threads it through every
  phase call.

### Fix 2 — charter + design phase boundaries
- `charter.py`: removed the greenfield hard-fail from the prompt (that
  was Phase B doing Phase C's job).
- `design_phase.py`:
  - `_stitch_prompt` path corrected (`outputs/feature-queue.json`,
    was `outputs/../feature-queue.json`).
  - `existing_design_system_present()` now requires a known
    token-file name (see `_TOKEN_FILE_NAMES`), not any non-empty file.
  - `DESIGN_TOOLS` split into `STITCH_DESIGN_TOOLS` (full kit) and
    `SUMMARISE_DESIGN_TOOLS` (`Read,Glob,Grep,Write` only). Brownfield
    summariser branch uses the restricted set.
  - New `_finalise_design_phase(session, output_dir)`: every non-skip
    branch funnels through this; requires `session.success == True`
    AND a parseable `design-system.json`, otherwise `hard_failed=True`
    with a specific reason.

### Fix 3 — verification contract is enforced
- `claude_executor._post_session_verification`:
  - Runs `bundle.verification.backend_test_command` and
    `frontend_test_command` via shell, captures output into
    `TestResult`.
  - `minimum_test_count` enforced by `_count_test_files()` across
    conventional patterns.
  - `required_screenshots` matched by existence under
    `.ncdev/evidence/`, `evidence/screenshots/`, `docs/screenshots/`.
  - `backend_health_url` best-effort HTTP probe via `httpx`; recorded
    in `app_boots` but NOT a hard failure (feature may have been
    built correctly without leaving the app running).
  - `_grep_for_prohibited` now uses `re.search()` with literal
    substring fallback on `re.error` — fixes silent no-match of regex
    entries like `r"except:\s*pass"`.
- New flags `run_test_commands` and `probe_health` on the executor
  allow tests to opt out of real shell-outs.

### Fix 4 — dependency gating
- `engine._unmet_dependencies(feature, completed)`: returns the list
  of `depends_on_features` ids that aren't in a PASSED or SKIPPED
  completed state.
- In the feature loop: unmet deps → feature marked `SKIPPED` with the
  reason, session not spawned. `--strict-deps` CLI flag halts the whole
  run at the first broken dep (default: skip-and-continue).

### Fix 5 — subprocess pipe handling
- `claude_session.py`: thread-per-pipe readers. Stderr is drained in
  a background thread so pipe backpressure can't deadlock the child.
- Watchdog thread: kills the whole process group via `os.killpg()`
  (POSIX) / `terminate`→`kill` chain (Windows) on wall-clock timeout.
  `timeout_fired` event communicates expiry back to the main loop.
- `retain_events=False` by default. Ring buffer of 20 events kept
  for the `final_text` fallback; full list only when opt-in.
- Two integration tests spawn real child processes:
  `test_watchdog_actually_kills_hung_subprocess` (infinite-sleep child,
  timeout=2s, asserts kill within 15s) and
  `test_stderr_backpressure_does_not_deadlock` (~2MB stderr flood while
  stdout is tiny, asserts completion within 10s).

### Fix 6 — feature-local asset scan
- `verify_manifest_covers_references(project_root, feature_id,
  touched_files=...)` scans only the given files when provided;
  otherwise falls back to the global scan.
- `claude_executor` passes `files_created + files_modified` from the
  `_diff_since(pre_commit)` call, so each feature is only judged on
  what it actually touched.

### Fix 7 — small fixes
- `claude_executor._commit_broken()` now returns `bool`, logs git
  stderr on failure, no more silent recoverability loss.
- `pre_bash_guard._extract_commit_message()` returns
  `(message, parse_mode)`; handles escaped quotes in `-m` properly,
  detects `-F <file>` and HEREDOC forms and allows them through
  cleanly rather than silently skipping enforcement.
- `max_repair_attempts` moved to end of `run_v3_full` signature with
  an explicit "retained for CLI compat, no-op" comment.

## Numbers

- **411 tests passing** (was 372). 39 new tests cover the regressions
  you flagged.
- Diff `a91fd24..f19934b`: 7 source files modified, 1 new
  (`ai_session.py`), 5 test files extended, 2 new test files.

## Files to look at this round

Don't re-review the whole system. Focus on the fixes:

exec
/bin/zsh -lc "sed -n '1,260p' docs/codex-review/review-request-round4.md" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
# Peer review request — Round 4

You are Codex. This is the fourth pass. Your three previous reviews
are on disk at `docs/codex-review/review-response.md`,
`review-response-round2.md`, and `review-response-round3.md`.

Since R3 I committed `f80247f` on `claude-orchestrator-migration`.
It claims to close every item from your R3 review:

- **R3-A (the default-path blocker you called out)**: `_probe_health`
  now polls with short per-request timeout, retries on failure, honours
  the full `boot_timeout_seconds` as the startup grace budget.
- **R3-B**: `state_scanner.build_skip_results` now returns
  `StepStatus.SKIPPED`, not `PASSED`. Engine's `state.completed_features`
  counter adjusted to count PASSED + SKIPPED so the human-facing
  "done" number stays meaningful.
- **R3-C**: `metrics.py` now tracks `blocked_features` + `skipped_features`
  as detail, and `failed_features = FAILED + BLOCKED` so the
  run-level failure count matches the engine's overall-status
  computation.
- **R3-D**: `_TailBuffer` oversized single-chunk behaviour fixed —
  when one chunk > max_bytes, we slice the UTF-8 tail bytes of that
  chunk instead of evicting it wholesale.
- **R3-E**: `run_ai_session` catches `ValueError` from
  `_resolve_custom_providers` and returns a structured
  `ClaudeSessionResult(success=False, error=...)` with an actionable
  message naming the bad provider value.

426/426 tests passing. +8 regression tests.

Your job now:

1. **Verify R3 fixes landed correctly** — same drill as before, but
   focus specifically on the probe polling (your stated blocker),
   `_TailBuffer` edge cases, and the state_scanner semantic fix.
2. **Find bugs I introduced in the R3 pass.**
3. **Decide: ready to inherit?** You said R3 needed the probe fix +
   ideally the TailBuffer fix. Both are done. If anything else is
   still blocking, name it plainly. If not, say so plainly.

## Files to look at

- `src/ncdev/v3/claude_executor.py` around `_probe_health` — new
  polling loop. Is the time-budget math right? Does it respect
  `per_request_timeout`? What if `per_request_timeout > timeout`?
- `src/ncdev/ai_session.py` `_TailBuffer.append()` — new oversized-
  chunk branch. UTF-8 boundary safety on the slice? The decode uses
  `errors="ignore"` — is that acceptable?
- `src/ncdev/v3/state_scanner.py` `build_skip_results` — SKIPPED change.
- `src/ncdev/v3/engine.py` `state.completed_features` — PASSED+SKIPPED.
- `src/ncdev/v3/metrics.py` `compute_run_metrics` — BLOCKED accounting.
- `src/ncdev/ai_session.py` `run_ai_session` — new ValueError catch.

## Specific questions

1. **Probe polling math.** The loop is:
   ```python
   deadline = time.time() + max(timeout, 1)
   while time.time() < deadline:
       ...
       time.sleep(min(poll_interval, max(deadline - time.time(), 0)))
   ```
   Is there a case where a single request's `req_timeout` is tiny
   (because the remaining budget is <5s) and we burn through attempts
   too fast? Is `min(per_request_timeout, remaining)` right when
   `remaining` is 0.1s?
2. **`_TailBuffer` UTF-8 boundary.** Slicing bytes at `-self._max:`
   can land mid-codepoint. `decode(errors="ignore")` drops the broken
   bytes. That's what I wanted, but it means callers see slightly less
   than `max_bytes` in the common case. Acceptable?
3. **`state.completed_features` semantics.** Human reads the run
   panel and sees "3/5 features completed". After R3-B, that 3 now
   includes features the state scanner skipped as brownfield-already-
   done. Is that the right human reading, or should the panel separate
   "built" from "already there"? (Low priority, UX question.)
4. **Metrics throughput math.** `feature_throughput_per_hour` divides
   `len(passed)` by duration. With R3-B, brownfield-skipped features
   are SKIPPED (not PASSED), so they're excluded from throughput —
   correct, because we didn't actually build them. Agree?

## Output shape

Keep it tight. If the blocker list is empty, say so.

```
## R3 fixes verified

## R3 fixes that still didn't land

## New issues introduced in R3

## Ready to inherit?

## Honest one-liner
```

Last round unless you find something real.

exec
/bin/zsh -lc "sed -n '330,410p' src/ncdev/cli.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
    fix_parser.add_argument("--auto-deploy", action="store_true", default=False, help="Auto-create PR if fix passes")
    fix_parser.add_argument("--max-attempts", type=int, default=3, help="Max fix attempts")
    fix_parser.add_argument("--batch", action="store_true", default=False, help="Process multiple reports")
    fix_parser.add_argument("--run-id", default=None, help="Resume a previous fix run")
    fix_parser.add_argument("--workspace", default=None)

    # --- Sentinel HTTP Intake ---
    serve_parser = sub.add_parser("serve", help="Start HTTP intake API for Sentinel reports")
    serve_parser.add_argument("--port", type=int, default=16650)
    serve_parser.add_argument("--workers", type=int, default=1)
    serve_parser.add_argument("--api-key", default=None, help="API key for authentication")
    serve_parser.add_argument("--workspace", default=None)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "quickstart":
        console.print(_quickstart_text())
        return 0

    if args.command == "doctor":
        workspace = Path.cwd()
        ok, report = _doctor_report(workspace)
        console.print(report)
        return 0 if ok else 1

    if args.command == "full":
        workspace = _workspace(args.workspace)
        target_repo = _resolve_target_repo(args.target_repo, workspace)
        state = run_v3_full(
            workspace=workspace,
            source_path=Path(args.source).resolve(),
            base_url=args.base_url,
            dry_run=bool(args.dry_run),
            target_repo_path=target_repo,
            builder_model=args.model,
            builder_timeout=args.timeout,
            max_repair_attempts=args.max_repairs,
            max_budget_usd=getattr(args, "max_budget_usd", None),
            strict_deps=bool(getattr(args, "strict_deps", False)),
        )
        console.print(f"run_id={state.run_id} status={state.status}")
        console.print(f"features: {state.completed_features}/{state.total_features} passed")
        console.print(f"run_dir={state.run_dir}")
        if state.status != "passed":
            return 1

        if args.quality_gate and not args.dry_run:
            import asyncio
            from ncdev.quality_gate.config import QualityGateConfig
            from ncdev.quality_gate.orchestrator import QualityGateOrchestrator

            qg_config = QualityGateConfig(enabled=True, max_cycles=3)
            orchestrator = QualityGateOrchestrator(qg_config)
            prd_content = Path(args.source).resolve().read_text()
            console.print("[cyan]Starting quality gate loop...[/cyan]")
            qg_state = asyncio.run(
                orchestrator.run(
                    project_name=workspace.name,
                    target_url=args.base_url,
                    target_path=str(target_repo or workspace),
                    prd_content=prd_content,
                    fix_callback=_run_quality_gate_fixes,
                )
            )
            console.print(f"quality_gate phase={qg_state.phase} cycles={qg_state.current_cycle}")
            if qg_state.final_scores:
                s = qg_state.final_scores
                console.print(f"scores: core_flow={s.core_flow} resilience={s.resilience} polish={s.polish}")
            return 0 if qg_state.phase == "passed" else 1

        return 0

    if args.command == "dev":
        from ncdev.dev import run_dev
        project_path = Path(args.project).resolve()
        result = run_dev(

exec
/bin/zsh -lc "sed -n '1,240p' src/ncdev/v3/state_scanner.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
"""Project state scanner — determines which features are already implemented.

Scans the target repo's git history, file tree, and test results to figure out
what's already built, so the engine can skip completed work and resume from
where the previous run left off.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from rich.console import Console

from ncdev.v3.models import FeatureStep, StepResult, StepStatus

console = Console()


def scan_completed_features(
    target_path: Path,
    feature_queue: list[FeatureStep],
) -> list[str]:
    """Scan the target repo and return feature_ids that are already done.

    A feature is considered done if:
    1. It appears in a git commit message (feat(feature_id): ...), OR
    2. Key files described by its title/description exist in the repo, AND
    3. The project's tests pass (basic smoke check)
    """
    if not (target_path / ".git").exists():
        return []

    git_log = _get_git_log(target_path)
    file_tree = _get_file_set(target_path)
    tests_pass = _run_smoke_test(target_path)

    completed: list[str] = []

    for feature in feature_queue:
        # Check 1: Is this feature in the git history?
        in_git = _feature_in_git_history(feature, git_log)

        # Check 2: Do files related to this feature exist?
        has_files = _feature_has_files(feature, file_tree)

        if tests_pass and (in_git or has_files):
            completed.append(feature.feature_id)

    return completed


def build_skip_results(
    feature_queue: list[FeatureStep],
    completed_ids: set[str],
) -> list[StepResult]:
    """Create SKIPPED StepResults for already-completed brownfield features.

    Uses :attr:`StepStatus.SKIPPED` — these features were done before
    this run started. The dependency gate treats SKIPPED as dep-
    satisfying, and metrics / summary correctly exclude them from
    PASSED / BLOCKED / FAILED counters.
    """
    return [
        StepResult(
            feature_id=f.feature_id,
            status=StepStatus.SKIPPED,
            error_message="Already implemented in target repo (state-scanner detection)",
        )
        for f in feature_queue
        if f.feature_id in completed_ids
    ]


def _get_git_log(target_path: Path) -> str:
    """Get full git log with commit messages."""
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "--all", "-200"],
            cwd=str(target_path),
            capture_output=True, text=True, timeout=10,
        )
        return result.stdout.lower() if result.returncode == 0 else ""
    except Exception:
        return ""


def _get_file_set(target_path: Path) -> set[str]:
    """Get set of all file paths in the repo (relative, lowercase)."""
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=str(target_path),
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return {line.strip().lower() for line in result.stdout.splitlines() if line.strip()}
    except Exception:
        pass
    return set()


def _run_smoke_test(target_path: Path) -> bool:
    """Quick check: do backend tests pass? (or at least not crash)"""
    backend = target_path / "backend"
    if not backend.exists():
        # Maybe tests are at root level
        backend = target_path

    has_tests = any(backend.rglob("test_*.py")) or any(backend.rglob("*_test.py"))
    if not has_tests:
        return True

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-x", "--no-header"],
            cwd=str(backend),
            capture_output=True, text=True, timeout=60,
        )
        # Accept green runs and partially green runs that still discovered passing tests.
        if result.returncode == 0 or "passed" in result.stdout:
            return True

        combined_output = f"{result.stdout}\n{result.stderr}".lower()

        # Brownfield repos often do not have pytest wired yet. That should not block
        # feature detection entirely.
        non_blocking_markers = [
            "no tests ran",
            "collected 0 items",
            "unrecognized arguments: --timeout=30",
            "module named pytest",
        ]
        return any(marker in combined_output for marker in non_blocking_markers)
    except Exception:
        return False


def _feature_in_git_history(feature: FeatureStep, git_log: str) -> bool:
    """Check if a feature appears in git commit messages."""
    feature_id_lower = feature.feature_id.lower()
    title_lower = feature.title.lower()

    # Direct feature ID match: feat(sprint-0):, feat(feature-01):, [feature-01]
    if feature_id_lower in git_log:
        return True

    # Title keywords match (at least 3 significant words from title in same commit line)
    title_words = [w for w in re.split(r'\W+', title_lower) if len(w) > 3]
    if len(title_words) >= 2:
        for line in git_log.splitlines():
            matches = sum(1 for w in title_words if w in line)
            if matches >= min(3, len(title_words)):
                return True

    return False


def _feature_has_files(feature: FeatureStep, file_tree: set[str]) -> bool:
    """Check if files related to the feature exist in the repo.

    For sprint-0 (scaffold): check for fundamental files.
    For other features: check for feature-specific files using title keywords.
    """
    fid = feature.feature_id.lower()

    # Sprint-0: scaffold is done if basic project structure exists
    if "sprint-0" in fid or "scaffold" in feature.title.lower():
        scaffold_markers = [
            "backend/app/main.py",
            "backend/requirements.txt",
            "docker-compose.yml",
        ]
        found = sum(1 for m in scaffold_markers if m in file_tree)
        return found >= 2

    # For other features: extract keywords from title and check file tree
    title_words = [w.lower() for w in re.split(r'\W+', feature.title) if len(w) > 3]
    if not title_words:
        return False

    # Check if any file path contains feature keywords (prefix match for stems)
    keyword_hits = 0
    for word in title_words:
        # Use first 4+ chars as stem to match "auth" in path against "authentication" in title
        stem = word[:4] if len(word) > 4 else word
        for fpath in file_tree:
            if stem in fpath:
                keyword_hits += 1
                break

    # Need at least 1 keyword match to consider the feature has files
    return keyword_hits >= 1

exec
/bin/zsh -lc "sed -n '1,220p' src/ncdev/v3/metrics.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
"""Run-level build metrics for the V3 pipeline."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from ncdev.v3.models import StepStatus, V3RunState


class FeatureMetric(BaseModel):
    """Per-feature effectiveness metrics."""

    feature_id: str
    status: str
    passed_first_try: bool
    repair_attempts: int = 0
    build_duration_seconds: float = 0.0
    verify_duration_seconds: float = 0.0
    files_created: int = 0
    files_modified: int = 0


class RunMetrics(BaseModel):
    """Aggregate metrics for one V3 run."""

    run_id: str
    project_name: str = ""
    started_at: str = ""
    completed_at: str = ""
    total_duration_seconds: float = 0.0
    total_features: int = 0
    passed_features: int = 0          # built successfully this run
    failed_features: int = 0          # tried and broke OR dep-blocked
    skipped_features: int = 0         # brownfield — already implemented
    blocked_features: int = 0         # broken dep cascaded here
    first_pass_success_rate: float = 0.0
    repair_rate: float = 0.0
    mean_repair_attempts: float = 0.0
    build_efficiency: float = 0.0
    feature_throughput_per_hour: float = 0.0
    features: list[FeatureMetric] = Field(default_factory=list)
    builder_primary: str = "codex"
    builder_model: str = "gpt-5.4"
    citex_documents_ingested: int = 0
    citex_queries_by_codex: int = 0


def compute_run_metrics(
    state: V3RunState,
    ingestion_doc_count: int = 0,
) -> RunMetrics:
    """Compute aggregate run metrics from the current V3 run state."""
    steps = state.completed_steps
    total = len(steps)

    if total == 0:
        return RunMetrics(run_id=state.run_id, started_at=state.started_at)

    passed = [s for s in steps if s.status == StepStatus.PASSED]
    # Both FAILED (tried and broke) and BLOCKED (upstream dep broke)
    # are failures at the run-metric level — they count against
    # failed_features so the number matches the engine's "unsuccessful"
    # run status. blocked_features is tracked separately for detail.
    failed_direct = [s for s in steps if s.status == StepStatus.FAILED]
    blocked = [s for s in steps if s.status == StepStatus.BLOCKED]
    failed = failed_direct + blocked
    skipped = [s for s in steps if s.status == StepStatus.SKIPPED]
    first_pass = [s for s in passed if s.repair_attempts == 0]
    repaired = [s for s in steps if s.repair_attempts > 0]

    build_sum = sum(s.build_duration_seconds for s in steps)
    verify_sum = sum(s.verify_duration_seconds for s in steps)
    total_active_time = build_sum + verify_sum

    started = _parse_iso(state.started_at)
    completed_at = state.updated_at or state.started_at
    completed = _parse_iso(completed_at)
    total_duration_seconds = max((completed - started).total_seconds(), 0.0)

    feature_metrics = [
        FeatureMetric(
            feature_id=s.feature_id,
            status=s.status.value,
            passed_first_try=(s.status == StepStatus.PASSED and s.repair_attempts == 0),
            repair_attempts=s.repair_attempts,
            build_duration_seconds=s.build_duration_seconds,
            verify_duration_seconds=s.verify_duration_seconds,
            files_created=len(s.files_created),
            files_modified=len(s.files_modified),
        )
        for s in steps
    ]

    return RunMetrics(
        run_id=state.run_id,
        project_name=_resolve_project_name(state),
        started_at=state.started_at,
        completed_at=completed_at,
        total_duration_seconds=total_duration_seconds,
        total_features=total,
        passed_features=len(passed),
        failed_features=len(failed),
        skipped_features=len(skipped),
        blocked_features=len(blocked),
        first_pass_success_rate=len(first_pass) / total,
        repair_rate=len(repaired) / total,
        mean_repair_attempts=(
            sum(s.repair_attempts for s in repaired) / len(repaired)
            if repaired else 0.0
        ),
        build_efficiency=build_sum / total_active_time if total_active_time > 0 else 0.0,
        feature_throughput_per_hour=(
            len(passed) / (total_duration_seconds / 3600.0) if total_duration_seconds > 0 else 0.0
        ),
        features=feature_metrics,
        citex_documents_ingested=ingestion_doc_count,
        citex_queries_by_codex=int(state.metadata.get("citex_queries_by_codex", 0)),
    )


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _resolve_project_name(state: V3RunState) -> str:
    if state.feature_queue and state.feature_queue.project_name:
        return state.feature_queue.project_name
    return str(state.metadata.get("project_id", "")) or "unknown"

exec
/bin/zsh -lc "rg -n \"completed_features|passed\\)\" src tests" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
src/ncdev/cli.py:376:        console.print(f"features: {state.completed_features}/{state.total_features} passed")
tests/test_ncdev_v3/test_state_scanner.py:8:    scan_completed_features,
tests/test_ncdev_v3/test_state_scanner.py:74:def test_scan_completed_features_no_git(tmp_path):
tests/test_ncdev_v3/test_state_scanner.py:77:    result = scan_completed_features(tmp_path, features)
tests/test_ncdev_v3/test_state_scanner.py:81:def test_scan_completed_features_with_git(tmp_path):
tests/test_ncdev_v3/test_state_scanner.py:101:    result = scan_completed_features(tmp_path, features)
src/ncdev/v3/state_scanner.py:21:def scan_completed_features(
src/ncdev/quality_gate/orchestrator.py:48:        - All three thresholds are met (pipeline passed).
src/ncdev/v3/metrics.py:102:        passed_features=len(passed),
src/ncdev/v3/metrics.py:114:            len(passed) / (total_duration_seconds / 3600.0) if total_duration_seconds > 0 else 0.0
src/ncdev/v3/engine.py:209:        remaining = _filter_completed_features(target_path, features, completed)
src/ncdev/v3/engine.py:263:            state.completed_features = len([
src/ncdev/v3/engine.py:317:def _filter_completed_features(target_path: Path, features, completed: list[StepResult]):
src/ncdev/v3/engine.py:320:        from ncdev.v3.state_scanner import build_skip_results, scan_completed_features
src/ncdev/v3/engine.py:324:        done_ids = set(scan_completed_features(target_path, features))
src/ncdev/v3/models.py:122:    completed_features: int = 0

exec
/bin/zsh -lc 'rg -n "prohibited patterns|global grep|legacy|brownfield" docs/codex-review src tests' in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
docs/codex-review/review-request-round4.md:73:   includes features the state scanner skipped as brownfield-already-
docs/codex-review/review-request-round4.md:77:   `len(passed)` by duration. With R3-B, brownfield-skipped features
docs/codex-review/review-request.md:50:  │       hooks wired via --settings (block non-conventional commits, prohibited patterns, force-push)
docs/codex-review/review-request.md:98:2. Inspects the staged diff for prohibited patterns (`TODO`, `FIXME`,
src/ncdev/claude_session.py:35:# Default NC Dev hooks — block commits with prohibited patterns / non-
tests/test_ncdev_v3/test_dependency_gating.py:42:def test_brownfield_skipped_dep_counts_as_satisfied():
docs/codex-review/round4-sweep-log.md:447:  │       hooks wired via --settings (block non-conventional commits, prohibited patterns, force-push)
docs/codex-review/round4-sweep-log.md:495:2. Inspects the staged diff for prohibited patterns (`TODO`, `FIXME`,
docs/codex-review/round4-sweep-log.md:673:(brownfield) as satisfied; `FAILED` + `BLOCKED` are unmet. The R1 test
docs/codex-review/round4-sweep-log.md:759:  differentiate brownfield SKIPPED (good) from BLOCKED (bad)?
docs/codex-review/round4-sweep-log.md:786:   SKIPPED (brownfield rerun, nothing to do), `unsuccessful` is
docs/codex-review/round4-sweep-log.md:1270:# Default NC Dev hooks — block commits with prohibited patterns / non-
docs/codex-review/round4-sweep-log.md:1817:    # manifest verification so one legacy unmanaged asset elsewhere in
docs/codex-review/round4-sweep-log.md:1938:            reasons.append(f"prohibited patterns found: {bad[:5]}")
docs/codex-review/round4-sweep-log.md:1952:    Phase 4 — Context ingestion into Citex      (v3.context_ingestion — brownfield)
docs/codex-review/round4-sweep-log.md:2118:    if bundle and bundle.contract.is_brownfield and bundle.contract.uses_citex and not dry_run:
docs/codex-review/round4-sweep-log.md:2204:            # perspective". SKIPPED = brownfield state scanner already
docs/codex-review/round4-sweep-log.md:2243:      * SKIPPED — brownfield state-scanner determined it was already
docs/codex-review/round4-sweep-log.md:2316:    SKIPPED = "skipped"   # brownfield state-scanner: feature already implemented
docs/codex-review/round4-sweep-log.md:2426:    is_brownfield: bool = False
docs/codex-review/round4-sweep-log.md:2582:# Default prohibited patterns — may be overridden per-project by placing
docs/codex-review/round4-sweep-log.md:2770:            f"Staged changes contain prohibited patterns: {preview}"
docs/codex-review/round4-sweep-log.md:3249:    """Scan git-tracked files for prohibited patterns.
docs/codex-review/round4-sweep-log.md:4825:def test_brownfield_skipped_dep_counts_as_satisfied():
docs/codex-review/round4-sweep-log.md:5073:    subprocess.run(["git", "commit", "-q", "-m", "init: legacy"], cwd=str(tmp_path), check=True)
docs/codex-review/round4-sweep-log.md:5594:   includes features the state scanner skipped as brownfield-already-
docs/codex-review/round4-sweep-log.md:5598:   `len(passed)` by duration. With R3-B, brownfield-skipped features
docs/codex-review/round4-sweep-log.md:6110:   includes features the state scanner skipped as brownfield-already-
docs/codex-review/round4-sweep-log.md:6114:   `len(passed)` by duration. With R3-B, brownfield-skipped features
docs/codex-review/round4-sweep-log.md:6281:    """Create SKIPPED StepResults for already-completed brownfield features.
docs/codex-review/round4-sweep-log.md:6456:    skipped_features: int = 0         # brownfield — already implemented
docs/codex-review/review-response-round4.md:85:   includes features the state scanner skipped as brownfield-already-
docs/codex-review/review-response-round4.md:89:   `len(passed)` by duration. With R3-B, brownfield-skipped features
docs/codex-review/review-response-round4.md:428:    # manifest verification so one legacy unmanaged asset elsewhere in
docs/codex-review/review-response-round4.md:772:    """Create SKIPPED StepResults for already-completed brownfield features.
docs/codex-review/review-response-round4.md:919:    Phase 4 — Context ingestion into Citex      (v3.context_ingestion — brownfield)
docs/codex-review/review-response-round4.md:1085:    if bundle and bundle.contract.is_brownfield and bundle.contract.uses_citex and not dry_run:
docs/codex-review/review-response-round4.md:1207:    skipped_features: int = 0         # brownfield — already implemented
docs/codex-review/review-response-round4.md:1449:+            # perspective". SKIPPED = brownfield state scanner already
docs/codex-review/review-response-round4.md:1470:+    skipped_features: int = 0         # brownfield — already implemented
docs/codex-review/review-response-round4.md:1509:+    """Create SKIPPED StepResults for already-completed brownfield features.
docs/codex-review/review-response-round4.md:1968:            # perspective". SKIPPED = brownfield state scanner already
docs/codex-review/review-response-round4.md:2007:      * SKIPPED — brownfield state-scanner determined it was already
docs/codex-review/review-response-round4.md:3182:    SKIPPED = "skipped"   # brownfield state-scanner: feature already implemented
docs/codex-review/review-response-round4.md:3292:    is_brownfield: bool = False
docs/codex-review/review-response-round4.md:3494:(brownfield) as satisfied; `FAILED` + `BLOCKED` are unmet. The R1 test
docs/codex-review/review-response-round4.md:3580:  differentiate brownfield SKIPPED (good) from BLOCKED (bad)?
docs/codex-review/review-response-round4.md:3607:   SKIPPED (brownfield rerun, nothing to do), `unsuccessful` is
docs/codex-review/review-response-round4.md:3724:   261	            # perspective". SKIPPED = brownfield state scanner already
docs/codex-review/review-response-round4.md:3870:    58	    """Create SKIPPED StepResults for already-completed brownfield features.
src/ncdev/v3/models.py:49:    SKIPPED = "skipped"   # brownfield state-scanner: feature already implemented
src/ncdev/v3/models.py:159:    is_brownfield: bool = False
src/ncdev/v3/asset_manifest.py:245:        from git diff). This is the preferred call shape: one legacy
docs/codex-review/review-request-round3.md:54:(brownfield) as satisfied; `FAILED` + `BLOCKED` are unmet. The R1 test
docs/codex-review/review-request-round3.md:140:  differentiate brownfield SKIPPED (good) from BLOCKED (bad)?
docs/codex-review/review-request-round3.md:167:   SKIPPED (brownfield rerun, nothing to do), `unsuccessful` is
src/ncdev/v3/engine.py:9:    Phase 4 — Context ingestion into Citex      (v3.context_ingestion — brownfield)
src/ncdev/v3/engine.py:175:    if bundle and bundle.contract.is_brownfield and bundle.contract.uses_citex and not dry_run:
src/ncdev/v3/engine.py:261:            # perspective". SKIPPED = brownfield state scanner already
src/ncdev/v3/engine.py:300:      * SKIPPED — brownfield state-scanner determined it was already
src/ncdev/v3/metrics.py:35:    skipped_features: int = 0         # brownfield — already implemented
docs/codex-review/review-response-round2.md:325:  │       hooks wired via --settings (block non-conventional commits, prohibited patterns, force-push)
docs/codex-review/review-response-round2.md:373:2. Inspects the staged diff for prohibited patterns (`TODO`, `FIXME`,
docs/codex-review/review-response-round2.md:578:- The verification contract is mostly unenforced. [models.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/models.py:195) defines boot URLs, test commands, screenshot requirements, and minimum test count, but [_post_session_verification](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:287) only checks required files, asset manifests, and prohibited patterns. A feature can “pass” without NC Dev ever verifying tests, app boot, screenshots, or test count.
docs/codex-review/review-response-round2.md:582:- Asset-manifest verification is global, not feature-local. [verify_manifest_covers_references](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/asset_manifest.py:196) scans the whole repo every feature. One legacy missing asset in brownfield code will fail every future feature, even if that feature never touched assets.
docs/codex-review/review-response-round2.md:595:- `DESIGN_TOOLS` in [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:45) is too broad for the brownfield summarizer path; giving it `Edit`, `Bash`, and `Task` undermines the “read and summarise only” contract.
docs/codex-review/review-response-round2.md:628:- The verification contract is mostly unenforced. [models.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/models.py:195) defines boot URLs, test commands, screenshot requirements, and minimum test count, but [_post_session_verification](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:287) only checks required files, asset manifests, and prohibited patterns. A feature can “pass” without NC Dev ever verifying tests, app boot, screenshots, or test count.
docs/codex-review/review-response-round2.md:632:- Asset-manifest verification is global, not feature-local. [verify_manifest_covers_references](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/asset_manifest.py:196) scans the whole repo every feature. One legacy missing asset in brownfield code will fail every future feature, even if that feature never touched assets.
docs/codex-review/review-response-round2.md:645:- `DESIGN_TOOLS` in [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:45) is too broad for the brownfield summarizer path; giving it `Edit`, `Bash`, and `Task` undermines the “read and summarise only” contract.
docs/codex-review/review-response-round2.md:1360:    # manifest verification so one legacy unmanaged asset elsewhere in
docs/codex-review/review-response-round2.md:1472:            reasons.append(f"prohibited patterns found: {bad[:5]}")
docs/codex-review/review-response-round2.md:1540:    """Scan git-tracked files for prohibited patterns.
docs/codex-review/review-response-round2.md:1760:    * ``source="existing"`` — brownfield case: ``docs/design-system/`` is
docs/codex-review/review-response-round2.md:1764:                              unavailable AND the project is brownfield.
docs/codex-review/review-response-round2.md:1804:# Tools for the brownfield summariser — Claude reads the existing
docs/codex-review/review-response-round2.md:1956:def _brownfield_prompt(contract: TargetProjectContract, target_path: Path, output_dir: Path) -> str:
docs/codex-review/review-response-round2.md:1957:    return f"""This is a brownfield project. A design system already exists at:
docs/codex-review/review-response-round2.md:2018:    if not contract.is_brownfield and not has_existing and not has_stitch:
docs/codex-review/review-response-round2.md:2033:        prompt = _brownfield_prompt(contract, target_path, output_dir)
docs/codex-review/review-response-round2.md:2047:    # --- Greenfield (or brownfield without designs) + Stitch available ----
docs/codex-review/review-response-round2.md:2064:    # Per the user's ruling: "brownfield or design-provided → Claude makes
docs/codex-review/review-response-round2.md:2068:        f"This is a brownfield project '{contract.project_name}' without "
docs/codex-review/review-response-round2.md:2103:    Phase 4 — Context ingestion into Citex      (v3.context_ingestion — brownfield)
docs/codex-review/review-response-round2.md:2269:    if bundle and bundle.contract.is_brownfield and bundle.contract.uses_citex and not dry_run:
docs/codex-review/review-response-round2.md:2381:    status PASSED or SKIPPED (state scanner can mark a brownfield
docs/codex-review/review-response-round2.md:2449:# Default prohibited patterns — may be overridden per-project by placing
docs/codex-review/review-response-round2.md:2625:            f"Staged changes contain prohibited patterns: {preview}"
docs/codex-review/review-response-round2.md:2696:- Target repository (may be empty for greenfield, existing for brownfield):
docs/codex-review/review-response-round2.md:2715:- For brownfield, DETECT from the existing repo — do not override what
docs/codex-review/review-response-round2.md:2720:- `design_system_source` is "stitch" for new UIs unless the brownfield
docs/codex-review/review-response-round2.md:3739:        is_brownfield=False,
docs/codex-review/review-response-round2.md:3823:    contract = _web_contract(is_brownfield=False)
docs/codex-review/review-response-round2.md:3847:def test_brownfield_with_design_system_runs_summariser(tmp_path: Path):
docs/codex-review/review-response-round2.md:3848:    contract = _web_contract(is_brownfield=True)
docs/codex-review/review-response-round2.md:3880:    # Prompt must be the brownfield-summariser variant
docs/codex-review/review-response-round2.md:3891:    contract = _web_contract(is_brownfield=False)
docs/codex-review/review-response-round2.md:3925:    contract = _web_contract(is_brownfield=False)
docs/codex-review/review-response-round2.md:3950:def test_brownfield_without_designs_and_no_stitch_lets_claude_decide(tmp_path: Path):
docs/codex-review/review-response-round2.md:3951:    contract = _web_contract(is_brownfield=True)
docs/codex-review/review-response-round2.md:3984:    contract = _web_contract(is_brownfield=True)
docs/codex-review/review-response-round2.md:4007:    contract = _web_contract(is_brownfield=True)
docs/codex-review/review-response-round2.md:4294:    subprocess.run(["git", "commit", "-q", "-m", "init: legacy"], cwd=str(tmp_path), check=True)
docs/codex-review/review-response-round2.md:5035:        from git diff). This is the preferred call shape: one legacy
docs/codex-review/review-response-round2.md:5555:# Default NC Dev hooks — block commits with prohibited patterns / non-
docs/codex-review/review-response-round2.md:5997:   287	    status PASSED or SKIPPED (state scanner can mark a brownfield
docs/codex-review/review-response-round2.md:6060:   235	    # manifest verification so one legacy unmanaged asset elsewhere in
docs/codex-review/review-response-round2.md:6547:   268	    if not contract.is_brownfield and not has_existing and not has_stitch:
docs/codex-review/review-response-round2.md:6562:   283	        prompt = _brownfield_prompt(contract, target_path, output_dir)
docs/codex-review/review-response-round2.md:6576:   297	    # --- Greenfield (or brownfield without designs) + Stitch available ----
docs/codex-review/review-response-round2.md:6593:   314	    # Per the user's ruling: "brownfield or design-provided → Claude makes
docs/codex-review/review-response-round2.md:6597:   318	        f"This is a brownfield project '{contract.project_name}' without "
docs/codex-review/review-response-round2.md:6736:   347	            reasons.append(f"prohibited patterns found: {bad[:5]}")
docs/codex-review/review-response-round2.md:6799:   410	    """Scan git-tracked files for prohibited patterns.
docs/codex-review/review-response-round2.md:7079:- The dependency gate is now semantically wrong. `_unmet_dependencies()` treats every `SKIPPED` dependency as satisfied at [engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:283). That conflates “already implemented in brownfield, safe to skip” with “skipped because an upstream dependency failed.” So `f03` can run even when `f02` never built. The new test at [test_dependency_gating.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/tests/test_ncdev_v3/test_dependency_gating.py:42) codifies the bug.
docs/codex-review/review-response-round2.md:7090:- The filename whitelist in `existing_design_system_present()` at [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:96) fixes the old false-positive bug, but it does it with a brittle policy list instead of validating token content. That is maintenance-heavy and easy to false-negative on legitimate brownfield systems.
docs/codex-review/review-response-round2.md:7117:- The dependency gate is now semantically wrong. `_unmet_dependencies()` treats every `SKIPPED` dependency as satisfied at [engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:283). That conflates “already implemented in brownfield, safe to skip” with “skipped because an upstream dependency failed.” So `f03` can run even when `f02` never built. The new test at [test_dependency_gating.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/tests/test_ncdev_v3/test_dependency_gating.py:42) codifies the bug.
docs/codex-review/review-response-round2.md:7128:- The filename whitelist in `existing_design_system_present()` at [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:96) fixes the old false-positive bug, but it does it with a brittle policy list instead of validating token content. That is maintenance-heavy and easy to false-negative on legitimate brownfield systems.
src/ncdev/v3/state_scanner.py:58:    """Create SKIPPED StepResults for already-completed brownfield features.
docs/codex-review/review-response.md:62:  │       hooks wired via --settings (block non-conventional commits, prohibited patterns, force-push)
docs/codex-review/review-response.md:110:2. Inspects the staged diff for prohibited patterns (`TODO`, `FIXME`,
docs/codex-review/review-response.md:360:    29	# Default NC Dev hooks — block commits with prohibited patterns / non-
docs/codex-review/review-response.md:967:    43	- Target repository (may be empty for greenfield, existing for brownfield):
docs/codex-review/review-response.md:986:    62	- For brownfield, DETECT from the existing repo — do not override what
docs/codex-review/review-response.md:991:    67	- `design_system_source` is "stitch" for new UIs unless the brownfield
docs/codex-review/review-response.md:1350:   158	    is_brownfield: bool = False
docs/codex-review/review-response.md:1510:    10	    * ``source="existing"`` — brownfield case: ``docs/design-system/`` is
docs/codex-review/review-response.md:1514:    14	                              unavailable AND the project is brownfield.
docs/codex-review/review-response.md:1670:   170	def _brownfield_prompt(contract: TargetProjectContract, target_path: Path, output_dir: Path) -> str:
docs/codex-review/review-response.md:1671:   171	    return f"""This is a brownfield project. A design system already exists at:
docs/codex-review/review-response.md:1731:   231	    if not contract.is_brownfield and not has_existing and not has_stitch:
docs/codex-review/review-response.md:1746:   246	        prompt = _brownfield_prompt(contract, target_path, output_dir)
docs/codex-review/review-response.md:1760:   260	    # --- Greenfield (or brownfield without designs) + Stitch available ----
docs/codex-review/review-response.md:1785:   285	    # Per the user's ruling: "brownfield or design-provided → Claude makes
docs/codex-review/review-response.md:1789:   289	        f"This is a brownfield project '{contract.project_name}' without "
docs/codex-review/review-response.md:2395:   315	            reasons.append(f"prohibited patterns found: {bad[:5]}")
docs/codex-review/review-response.md:2404:   324	    """Grep committed files (staged tree) for prohibited patterns."""
docs/codex-review/review-response.md:2852:     9	    Phase 4 — Context ingestion into Citex      (v3.context_ingestion — brownfield)
docs/codex-review/review-response.md:3003:   160	    if bundle and bundle.contract.is_brownfield and bundle.contract.uses_citex and not dry_run:
docs/codex-review/review-response.md:3166:    31	# Default prohibited patterns — may be overridden per-project by placing
docs/codex-review/review-response.md:3307:   172	            f"Staged changes contain prohibited patterns: {preview}"
docs/codex-review/review-response.md:4733:   155	    subprocess.run(["git", "commit", "-q", "-m", "init: legacy"], cwd=str(tmp_path), check=True)
docs/codex-review/review-response.md:5089:    29	        is_brownfield=False,
docs/codex-review/review-response.md:5159:    99	    contract = _web_contract(is_brownfield=False)
docs/codex-review/review-response.md:5183:   123	def test_brownfield_with_design_system_runs_summariser(tmp_path: Path):
docs/codex-review/review-response.md:5184:   124	    contract = _web_contract(is_brownfield=True)
docs/codex-review/review-response.md:5216:   156	    # Prompt must be the brownfield-summariser variant
docs/codex-review/review-response.md:5227:   167	    contract = _web_contract(is_brownfield=False)
docs/codex-review/review-response.md:5261:   201	    contract = _web_contract(is_brownfield=False)
docs/codex-review/review-response.md:5286:   226	def test_brownfield_without_designs_and_no_stitch_lets_claude_decide(tmp_path: Path):
docs/codex-review/review-response.md:5287:   227	    contract = _web_contract(is_brownfield=True)
docs/codex-review/review-response.md:5318:   258	    contract = _web_contract(is_brownfield=True)
docs/codex-review/review-response.md:5946:     2	  "_comment": "NC Dev System — Claude Code hooks wired in at session spawn. Passed via --settings <this file> by claude_executor and dev.py. pre_bash_guard.py blocks git commit commands that violate Conventional Commits or contain prohibited patterns; force-push to protected branches requires NCDEV_ALLOW_FORCE_PUSH=1.",
docs/codex-review/review-response.md:6777:- The verification contract is mostly unenforced. [models.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/models.py:195) defines boot URLs, test commands, screenshot requirements, and minimum test count, but [_post_session_verification](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:287) only checks required files, asset manifests, and prohibited patterns. A feature can “pass” without NC Dev ever verifying tests, app boot, screenshots, or test count.
docs/codex-review/review-response.md:6781:- Asset-manifest verification is global, not feature-local. [verify_manifest_covers_references](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/asset_manifest.py:196) scans the whole repo every feature. One legacy missing asset in brownfield code will fail every future feature, even if that feature never touched assets.
docs/codex-review/review-response.md:6794:- `DESIGN_TOOLS` in [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:45) is too broad for the brownfield summarizer path; giving it `Edit`, `Bash`, and `Task` undermines the “read and summarise only” contract.
docs/codex-review/review-response.md:6827:- The verification contract is mostly unenforced. [models.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/models.py:195) defines boot URLs, test commands, screenshot requirements, and minimum test count, but [_post_session_verification](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:287) only checks required files, asset manifests, and prohibited patterns. A feature can “pass” without NC Dev ever verifying tests, app boot, screenshots, or test count.
docs/codex-review/review-response.md:6831:- Asset-manifest verification is global, not feature-local. [verify_manifest_covers_references](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/asset_manifest.py:196) scans the whole repo every feature. One legacy missing asset in brownfield code will fail every future feature, even if that feature never touched assets.
docs/codex-review/review-response.md:6844:- `DESIGN_TOOLS` in [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:45) is too broad for the brownfield summarizer path; giving it `Edit`, `Bash`, and `Task` undermines the “read and summarise only” contract.
docs/codex-review/review-response-round3.md:66:(brownfield) as satisfied; `FAILED` + `BLOCKED` are unmet. The R1 test
docs/codex-review/review-response-round3.md:152:  differentiate brownfield SKIPPED (good) from BLOCKED (bad)?
docs/codex-review/review-response-round3.md:179:   SKIPPED (brownfield rerun, nothing to do), `unsuccessful` is
docs/codex-review/review-response-round3.md:544:  │       hooks wired via --settings (block non-conventional commits, prohibited patterns, force-push)
docs/codex-review/review-response-round3.md:592:2. Inspects the staged diff for prohibited patterns (`TODO`, `FIXME`,
docs/codex-review/review-response-round3.md:860:   410	    """Scan git-tracked files for prohibited patterns.
docs/codex-review/review-response-round3.md:1437:-    status PASSED or SKIPPED (state scanner can mark a brownfield
docs/codex-review/review-response-round3.md:1444:+      * SKIPPED — brownfield state-scanner determined it was already
docs/codex-review/review-response-round3.md:1473:+    SKIPPED = "skipped"   # brownfield state-scanner: feature already implemented
docs/codex-review/review-response-round3.md:1487:+def test_brownfield_skipped_dep_counts_as_satisfied():
docs/codex-review/review-response-round3.md:2281:     9	    Phase 4 — Context ingestion into Citex      (v3.context_ingestion — brownfield)
docs/codex-review/review-response-round3.md:2447:   175	    if bundle and bundle.contract.is_brownfield and bundle.contract.uses_citex and not dry_run:
docs/codex-review/review-response-round3.md:2566:   294	      * SKIPPED — brownfield state-scanner determined it was already
docs/codex-review/review-response-round3.md:2653:   238	    # manifest verification so one legacy unmanaged asset elsewhere in
docs/codex-review/review-response-round3.md:2774:   359	            reasons.append(f"prohibited patterns found: {bad[:5]}")
docs/codex-review/review-response-round3.md:2841:   426	    """Scan git-tracked files for prohibited patterns.
docs/codex-review/review-response-round3.md:3497:    49	    SKIPPED = "skipped"   # brownfield state-scanner: feature already implemented
docs/codex-review/review-response-round3.md:3607:   159	    is_brownfield: bool = False
docs/codex-review/review-response-round3.md:3869:- The dependency gate is now semantically wrong. `_unmet_dependencies()` treats every `SKIPPED` dependency as satisfied at [engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:283). That conflates “already implemented in brownfield, safe to skip” with “skipped because an upstream dependency failed.” So `f03` can run even when `f02` never built. The new test at [test_dependency_gating.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/tests/test_ncdev_v3/test_dependency_gating.py:42) codifies the bug.
docs/codex-review/review-response-round3.md:3880:- The filename whitelist in `existing_design_system_present()` at [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:96) fixes the old false-positive bug, but it does it with a brittle policy list instead of validating token content. That is maintenance-heavy and easy to false-negative on legitimate brownfield systems.
docs/codex-review/review-response-round3.md:3907:- The dependency gate is now semantically wrong. `_unmet_dependencies()` treats every `SKIPPED` dependency as satisfied at [engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:283). That conflates “already implemented in brownfield, safe to skip” with “skipped because an upstream dependency failed.” So `f03` can run even when `f02` never built. The new test at [test_dependency_gating.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/tests/test_ncdev_v3/test_dependency_gating.py:42) codifies the bug.
docs/codex-review/review-response-round3.md:3918:- The filename whitelist in `existing_design_system_present()` at [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:96) fixes the old false-positive bug, but it does it with a brittle policy list instead of validating token content. That is maintenance-heavy and easy to false-negative on legitimate brownfield systems.
docs/codex-review/review-response-round3.md:3961:    31	# Default prohibited patterns — may be overridden per-project by placing
docs/codex-review/review-response-round3.md:4149:   219	            f"Staged changes contain prohibited patterns: {preview}"
docs/codex-review/review-response-round3.md:4263:      * SKIPPED — brownfield state-scanner determined it was already
docs/codex-review/review-response-round3.md:4441:   268	    if not contract.is_brownfield and not has_existing and not has_stitch:
docs/codex-review/review-response-round3.md:4456:   283	        prompt = _brownfield_prompt(contract, target_path, output_dir)
docs/codex-review/review-response-round3.md:4470:   297	    # --- Greenfield (or brownfield without designs) + Stitch available ----
docs/codex-review/review-response-round3.md:4487:   314	    # Per the user's ruling: "brownfield or design-provided → Claude makes
docs/codex-review/review-response-round3.md:4491:   318	        f"This is a brownfield project '{contract.project_name}' without "
docs/codex-review/review-response-round3.md:4820:`4a5a0f7` closes the round-2 “didn’t land” items I called out: the `console` crash is gone, `_commit_broken()`’s return value is now wired, dependency blocking is no longer conflated with brownfield skips, `--strict-deps` no longer reports a false pass, `custom` mode now honors configured routing, and hook/verifier regex behavior now matches. I reran the targeted regression suite for the touched areas, and it passes. The branch is much closer, but there is still one real default-path blocker and a couple smaller regressions from the hardening itself.
docs/codex-review/review-response-round3.md:4844:- Status semantics are still internally inconsistent: [`models.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/models.py:49>) says brownfield already-done work is `SKIPPED`, but [`state_scanner.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/state_scanner.py:60>) still emits `PASSED`. So `state.completed_features` is “correct” today only because the scanner lies in its favor.
docs/codex-review/review-response-round3.md:4854:`4a5a0f7` closes the round-2 “didn’t land” items I called out: the `console` crash is gone, `_commit_broken()`’s return value is now wired, dependency blocking is no longer conflated with brownfield skips, `--strict-deps` no longer reports a false pass, `custom` mode now honors configured routing, and hook/verifier regex behavior now matches. I reran the targeted regression suite for the touched areas, and it passes. The branch is much closer, but there is still one real default-path blocker and a couple smaller regressions from the hardening itself.
docs/codex-review/review-response-round3.md:4878:- Status semantics are still internally inconsistent: [`models.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/models.py:49>) says brownfield already-done work is `SKIPPED`, but [`state_scanner.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/state_scanner.py:60>) still emits `PASSED`. So `state.completed_features` is “correct” today only because the scanner lies in its favor.
src/ncdev/v3/design_phase.py:10:    * ``source="existing"`` — brownfield case: ``docs/design-system/`` is
src/ncdev/v3/design_phase.py:14:                              unavailable AND the project is brownfield.
src/ncdev/v3/design_phase.py:54:# Tools for the brownfield summariser — Claude reads the existing
src/ncdev/v3/design_phase.py:206:def _brownfield_prompt(contract: TargetProjectContract, target_path: Path, output_dir: Path) -> str:
src/ncdev/v3/design_phase.py:207:    return f"""This is a brownfield project. A design system already exists at:
src/ncdev/v3/design_phase.py:268:    if not contract.is_brownfield and not has_existing and not has_stitch:
src/ncdev/v3/design_phase.py:283:        prompt = _brownfield_prompt(contract, target_path, output_dir)
src/ncdev/v3/design_phase.py:297:    # --- Greenfield (or brownfield without designs) + Stitch available ----
src/ncdev/v3/design_phase.py:314:    # Per the user's ruling: "brownfield or design-provided → Claude makes
src/ncdev/v3/design_phase.py:318:        f"This is a brownfield project '{contract.project_name}' without "
src/ncdev/v3/claude_executor.py:238:    # manifest verification so one legacy unmanaged asset elsewhere in
src/ncdev/v3/claude_executor.py:359:            reasons.append(f"prohibited patterns found: {bad[:5]}")
src/ncdev/v3/claude_executor.py:426:    """Scan git-tracked files for prohibited patterns.
src/ncdev/v3/charter.py:44:- Target repository (may be empty for greenfield, existing for brownfield):
src/ncdev/v3/charter.py:63:- For brownfield, DETECT from the existing repo — do not override what
src/ncdev/v3/charter.py:68:- `design_system_source` is "stitch" for new UIs unless the brownfield
tests/unit/test_hooks.py:208:    subprocess.run(["git", "commit", "-q", "-m", "init: legacy"], cwd=str(tmp_path), check=True)
tests/unit/test_design_phase.py:29:        is_brownfield=False,
tests/unit/test_design_phase.py:113:    contract = _web_contract(is_brownfield=False)
tests/unit/test_design_phase.py:137:def test_brownfield_with_design_system_runs_summariser(tmp_path: Path):
tests/unit/test_design_phase.py:138:    contract = _web_contract(is_brownfield=True)
tests/unit/test_design_phase.py:170:    # Prompt must be the brownfield-summariser variant
tests/unit/test_design_phase.py:181:    contract = _web_contract(is_brownfield=False)
tests/unit/test_design_phase.py:215:    contract = _web_contract(is_brownfield=False)
tests/unit/test_design_phase.py:240:def test_brownfield_without_designs_and_no_stitch_lets_claude_decide(tmp_path: Path):
tests/unit/test_design_phase.py:241:    contract = _web_contract(is_brownfield=True)
tests/unit/test_design_phase.py:274:    contract = _web_contract(is_brownfield=True)
tests/unit/test_design_phase.py:297:    contract = _web_contract(is_brownfield=True)
tests/unit/test_design_phase.py:324:def test_brownfield_summariser_uses_read_only_tools(tmp_path: Path):
tests/unit/test_design_phase.py:327:    contract = _web_contract(is_brownfield=True)
tests/unit/test_design_phase.py:354:    contract = _web_contract(is_brownfield=True)
tests/unit/test_asset_manifest.py:205:    Codex's flag: global scans made one legacy unmanaged asset anywhere
tests/unit/test_asset_manifest.py:209:    legacy = tmp_path / "frontend" / "src" / "Legacy.tsx"
tests/unit/test_asset_manifest.py:210:    legacy.parent.mkdir(parents=True)
tests/unit/test_asset_manifest.py:211:    legacy.write_text('<img src="/images/legacy.png" />')
tests/unit/test_asset_manifest.py:220:        touched_files=["frontend/src/Clean.tsx"],  # legacy NOT in list

exec
/bin/zsh -lc 'rg -n "TODO from history|unchanged file" tests/unit/test_claude_executor.py tests/unit/test_hooks.py' in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
tests/unit/test_hooks.py:206:    (tmp_path / "old.py").write_text("# TODO from history\n")

codex
I found two concrete load-bearing issues worth fixing, not just “smells”: one in brownfield progress accounting and one in post-hoc verification scope. I’m patching those now, and I’ll fold in the CLI wording fix because the current output lies about skipped features being “passed.”
exec
/bin/zsh -lc "sed -n '1,260p' tests/test_cli.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
from pathlib import Path

from ncdev.cli import _doctor_report, _quickstart_text, _resolve_target_repo, build_parser


def test_cli_quickstart_parses() -> None:
    parser = build_parser()
    args = parser.parse_args(["quickstart"])
    assert args.command == "quickstart"


def test_cli_doctor_parses() -> None:
    parser = build_parser()
    args = parser.parse_args(["doctor"])
    assert args.command == "doctor"


def test_cli_full_defaults() -> None:
    parser = build_parser()
    args = parser.parse_args(["full", "--source", "/tmp/requirements.md"])
    assert args.base_url == "http://localhost:23000"
    assert args.dry_run is False
    assert args.target_repo is None
    assert args.model == "claude-opus-4-6"
    assert args.timeout == 600
    assert args.max_repairs == 2


def test_cli_full_custom_options() -> None:
    parser = build_parser()
    args = parser.parse_args([
        "full", "--source", "/tmp/requirements.md",
        "--model", "claude-sonnet-4-6", "--timeout", "900", "--max-repairs", "3",
        "--dry-run", "--target-repo", "/tmp/repo",
    ])
    assert args.model == "claude-sonnet-4-6"
    assert args.timeout == 900
    assert args.max_repairs == 3
    assert args.dry_run is True
    assert args.target_repo == "/tmp/repo"


def test_cli_dev_parses() -> None:
    parser = build_parser()
    args = parser.parse_args(["dev", "--project", "/tmp/proj", "--task", "Build feature"])
    assert args.command == "dev"
    assert args.project == "/tmp/proj"
    assert args.task == "Build feature"
    assert args.mode == "auto"


def test_cli_fix_parses() -> None:
    parser = build_parser()
    args = parser.parse_args(["fix", "--report", "/tmp/rpt.json", "--target", "/tmp/repo"])
    assert args.command == "fix"
    assert args.report == "/tmp/rpt.json"
    assert args.target == "/tmp/repo"
    assert args.dry_run is False


def test_cli_serve_parses() -> None:
    parser = build_parser()
    args = parser.parse_args(["serve", "--port", "8080"])
    assert args.command == "serve"
    assert args.port == 8080


def test_resolve_target_repo_uses_workspace_git_repo(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    assert _resolve_target_repo(None, tmp_path) == tmp_path


def test_resolve_target_repo_prefers_explicit_value(tmp_path: Path) -> None:
    explicit = tmp_path / "explicit"
    explicit.mkdir()
    assert _resolve_target_repo(str(explicit), tmp_path) == explicit


def test_quickstart_text_mentions_full() -> None:
    text = _quickstart_text()
    assert "ncdev full" in text
    assert "ncdev dev" in text
    assert "ncdev fix" in text


def test_doctor_report_detects_git_repo(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    _, report = _doctor_report(tmp_path)
    assert "git repository" in report

exec
/bin/zsh -lc 'rg -n "completed_features|features:" tests src/ncdev/cli.py tests/test_cli.py tests/unit/test_* tests/test_ncdev_v3' in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
src/ncdev/cli.py:376:        console.print(f"features: {state.completed_features}/{state.total_features} passed")
tests/test_ncdev_v3/test_state_scanner.py:8:    scan_completed_features,
tests/test_ncdev_v3/test_state_scanner.py:74:def test_scan_completed_features_no_git(tmp_path):
tests/test_ncdev_v3/test_state_scanner.py:77:    result = scan_completed_features(tmp_path, features)
tests/test_ncdev_v3/test_state_scanner.py:81:def test_scan_completed_features_with_git(tmp_path):
tests/test_ncdev_v3/test_state_scanner.py:101:    result = scan_completed_features(tmp_path, features)
tests/test_ncdev_v3/test_state_scanner.py:8:    scan_completed_features,
tests/test_ncdev_v3/test_state_scanner.py:74:def test_scan_completed_features_no_git(tmp_path):
tests/test_ncdev_v3/test_state_scanner.py:77:    result = scan_completed_features(tmp_path, features)
tests/test_ncdev_v3/test_state_scanner.py:81:def test_scan_completed_features_with_git(tmp_path):
tests/test_ncdev_v3/test_state_scanner.py:101:    result = scan_completed_features(tmp_path, features)
tests/conftest.py:991:    parsed_features: list[dict[str, Any]],

exec
/bin/zsh -lc "sed -n '1,220p' tests/test_ncdev_v3/test_state_scanner.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
import subprocess
from pathlib import Path
from unittest.mock import patch

from ncdev.v3.models import FeatureStep, StepStatus
from ncdev.v3.state_scanner import (
    build_skip_results,
    scan_completed_features,
    _feature_in_git_history,
    _feature_has_files,
)


def _feat(fid: str, title: str) -> FeatureStep:
    return FeatureStep(feature_id=fid, title=title, description=title, acceptance_criteria=["works"])


def test_feature_in_git_history_by_id():
    log = "abc1234 feat(sprint-0): project scaffold\ndef5678 feat(feature-01): user auth"
    assert _feature_in_git_history(_feat("sprint-0", "Scaffold"), log) is True
    assert _feature_in_git_history(_feat("feature-01", "Auth"), log) is True
    assert _feature_in_git_history(_feat("feature-99", "Missing"), log) is False


def test_feature_in_git_history_by_title_keywords():
    log = "abc1234 implement user authentication with jwt tokens"
    feat = _feat("f1", "User Authentication JWT Tokens")
    assert _feature_in_git_history(feat, log) is True


def test_feature_in_git_history_no_match():
    log = "abc1234 fix typo in readme"
    feat = _feat("f1", "User Authentication System")
    assert _feature_in_git_history(feat, log) is False


def test_feature_has_files_scaffold():
    files = {"backend/app/main.py", "backend/requirements.txt", "docker-compose.yml", "readme.md"}
    feat = _feat("sprint-0", "Project Scaffold & Boot")
    assert _feature_has_files(feat, files) is True


def test_feature_has_files_scaffold_incomplete():
    files = {"readme.md"}
    feat = _feat("sprint-0", "Project Scaffold & Boot")
    assert _feature_has_files(feat, files) is False


def test_feature_has_files_by_keyword():
    files = {"backend/app/services/auth_service.py", "backend/app/api/v1/endpoints/auth.py"}
    feat = _feat("f1", "User Authentication")
    assert _feature_has_files(feat, files) is True


def test_feature_has_files_no_match():
    files = {"backend/app/main.py", "readme.md"}
    feat = _feat("f1", "Dashboard Analytics")
    assert _feature_has_files(feat, files) is False


def test_build_skip_results():
    """Brownfield-done features must be SKIPPED (not PASSED) — the
    status needs to differentiate 'built this run' from 'already there'
    so metrics and dep gating stay consistent."""
    features = [_feat("f1", "Auth"), _feat("f2", "Dashboard"), _feat("f3", "Settings")]
    results = build_skip_results(features, {"f1", "f3"})
    assert len(results) == 2
    assert results[0].feature_id == "f1"
    assert results[0].status == StepStatus.SKIPPED
    assert "Already implemented" in results[0].error_message
    assert results[1].feature_id == "f3"


def test_scan_completed_features_no_git(tmp_path):
    """No .git directory → nothing detected."""
    features = [_feat("f1", "Auth")]
    result = scan_completed_features(tmp_path, features)
    assert result == []


def test_scan_completed_features_with_git(tmp_path):
    """Git repo with matching commit → feature detected."""
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@test",
                     "commit", "--allow-empty", "-m", "feat(sprint-0): project scaffold"],
                    cwd=tmp_path, capture_output=True)
    (tmp_path / "backend" / "app").mkdir(parents=True)
    (tmp_path / "backend" / "app" / "main.py").write_text("app = 'ok'")
    (tmp_path / "backend" / "requirements.txt").write_text("fastapi")
    (tmp_path / "docker-compose.yml").write_text("version: '3'")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, capture_output=True)
    subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@test",
                     "commit", "-m", "feat(feature-01): user auth"],
                    cwd=tmp_path, capture_output=True)

    features = [
        _feat("sprint-0", "Project Scaffold & Boot"),
        _feat("feature-01", "User Authentication"),
        _feat("feature-02", "Dashboard"),
    ]
    result = scan_completed_features(tmp_path, features)
    assert "sprint-0" in result
    assert "feature-01" in result
    assert "feature-02" not in result

exec
/bin/zsh -lc "sed -n '1,260p' tests/test_ncdev_v3/test_metrics.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
from ncdev.v3.metrics import compute_run_metrics
from ncdev.v3.models import FeatureQueueDoc, StepResult, StepStatus, V3RunState


def _make_result(fid: str, status: StepStatus, repairs: int = 0, build_s: float = 60, verify_s: float = 10) -> StepResult:
    return StepResult(
        feature_id=fid, status=status, build_duration_seconds=build_s,
        verify_duration_seconds=verify_s, repair_attempts=repairs,
        files_created=["a.py", "b.py"], files_modified=["c.py"],
    )


def test_all_pass_first_try():
    state = V3RunState(
        run_id="t1", started_at="2026-04-11T10:00:00+00:00", updated_at="2026-04-11T11:00:00+00:00",
        completed_steps=[_make_result("f1", StepStatus.PASSED), _make_result("f2", StepStatus.PASSED), _make_result("f3", StepStatus.PASSED)],
    )
    m = compute_run_metrics(state)
    assert m.first_pass_success_rate == 1.0
    assert m.repair_rate == 0.0
    assert m.passed_features == 3
    assert m.failed_features == 0
    assert all(f.passed_first_try for f in m.features)


def test_mixed_results():
    state = V3RunState(
        run_id="t2", started_at="2026-04-11T10:00:00+00:00", updated_at="2026-04-11T11:00:00+00:00",
        feature_queue=FeatureQueueDoc(project_name="test-proj"),
        completed_steps=[
            _make_result("f1", StepStatus.PASSED, 0),
            _make_result("f2", StepStatus.PASSED, 2),
            _make_result("f3", StepStatus.FAILED, 2),
            _make_result("f4", StepStatus.PASSED, 0),
        ],
    )
    m = compute_run_metrics(state)
    assert m.first_pass_success_rate == 0.5
    assert m.repair_rate == 0.5
    assert m.mean_repair_attempts == 2.0
    assert m.passed_features == 3
    assert m.failed_features == 1
    assert m.project_name == "test-proj"
    assert [f.passed_first_try for f in m.features] == [True, False, False, True]


def test_build_efficiency():
    state = V3RunState(
        run_id="t3", started_at="2026-04-11T10:00:00+00:00", updated_at="2026-04-11T11:00:00+00:00",
        completed_steps=[
            _make_result("f1", StepStatus.PASSED, 0, build_s=80, verify_s=20),
            _make_result("f2", StepStatus.PASSED, 0, build_s=120, verify_s=30),
        ],
    )
    m = compute_run_metrics(state)
    assert abs(m.build_efficiency - 0.8) < 0.01


def test_feature_metrics_populated():
    state = V3RunState(
        run_id="t4", started_at="2026-04-11T10:00:00+00:00", updated_at="2026-04-11T11:00:00+00:00",
        completed_steps=[_make_result("f1", StepStatus.PASSED, 0)],
    )
    m = compute_run_metrics(state)
    assert len(m.features) == 1
    assert m.features[0].feature_id == "f1"
    assert m.features[0].passed_first_try is True
    assert m.features[0].files_created == 2
    assert m.features[0].files_modified == 1


def test_empty_run():
    state = V3RunState(run_id="t5", started_at="2026-04-11T10:00:00+00:00")
    m = compute_run_metrics(state)
    assert m.first_pass_success_rate == 0.0
    assert m.total_features == 0
    assert m.features == []


def test_blocked_counted_as_failure_not_skipped():
    """Codex R3: BLOCKED must count against failed_features so metrics
    match the engine's overall-status determination."""
    state = V3RunState(
        run_id="rm1",
        started_at="2026-04-11T10:00:00+00:00",
        updated_at="2026-04-11T10:10:00+00:00",
        completed_steps=[
            _make_result("f1", StepStatus.PASSED),
            _make_result("f2", StepStatus.FAILED),
            _make_result("f3", StepStatus.BLOCKED),
            _make_result("f4", StepStatus.SKIPPED),
        ],
    )
    m = compute_run_metrics(state)
    assert m.total_features == 4
    assert m.passed_features == 1
    assert m.failed_features == 2      # FAILED + BLOCKED together
    assert m.blocked_features == 1     # tracked separately for detail
    assert m.skipped_features == 1


def test_ingestion_count_passed_through():
    state = V3RunState(
        run_id="t6", started_at="2026-04-11T10:00:00+00:00", updated_at="2026-04-11T10:30:00+00:00",
        completed_steps=[_make_result("f1", StepStatus.PASSED)],
        metadata={"citex_queries_by_codex": 7},
    )
    m = compute_run_metrics(state, ingestion_doc_count=12)
    assert m.citex_documents_ingested == 12
    assert m.citex_queries_by_codex == 7

exec
/bin/zsh -lc 'rg -n "run_v3_full|strict-deps|state.status|Skipping" tests' in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
tests/test_ncdev_v2/test_sentinel_engine.py:126:        assert state.status == V2TaskStatus.BLOCKED
tests/test_ncdev_v2/test_sentinel_engine.py:143:        assert state.status == V2TaskStatus.BLOCKED
tests/test_ncdev_v2/test_sentinel_engine.py:158:        assert state.status == V2TaskStatus.BLOCKED

exec
/bin/zsh -lc "sed -n '1,80p' src/ncdev/cli.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
from __future__ import annotations

import argparse
import subprocess
import shutil
import sys
from pathlib import Path

from rich.console import Console

from ncdev.preflight import run_preflight, require_citex
from ncdev.v2.engine import (
    load_v2_run_state,
    run_v2_fix,
    summarize_v2_status,
)
from ncdev.v3.engine import run_v3_full

console = Console()


def _workspace(path: str | None) -> Path:
    return Path(path).resolve() if path else Path.cwd()


def _resolve_target_repo(explicit_target_repo: str | None, workspace: Path) -> Path | None:
    if explicit_target_repo:
        return Path(explicit_target_repo).resolve()
    if (workspace / ".git").exists():
        return workspace
    return None


def _quickstart_text() -> str:
    return """NC Dev System Quickstart

Recommended flow:

1. Dry-run discovery
   ncdev full --source ./docs/README.md --dry-run

2. Full build (sequential verified sprints)
   ncdev full --source ./docs/README.md --base-url http://localhost:23000

3. Full build with explicit target repo
   ncdev full --source /path/to/docs --target-repo /path/to/repo --base-url http://localhost:23000

4. Autonomous dev mode
   ncdev dev --project /path/to/project --task "Build feature X"

5. Generate video report
   ncdev report --project /path/to/project

Other commands:
   ncdev fix --report report.json --target /path/to/repo
   ncdev serve --port 16650
   ncdev doctor
"""


def _check_app_boots(target_path: Path) -> bool:
    """Check whether the backend app still imports cleanly after a fix."""
    backend_path = target_path / "backend"
    if not backend_path.exists():
        return True

    try:
        result = subprocess.run(
            [sys.executable, "-c", "from app.main import app; print('BOOT_OK')"],
            cwd=str(backend_path),
            capture_output=True,
            text=True,
            timeout=30,
        )
        return "BOOT_OK" in result.stdout
    except Exception:
        return False


async def _run_quality_gate_fixes(manifest, config=None) -> int:

codex
I’ve isolated the first two code changes: feature verification should not re-fail brownfield work because of legacy prohibited text elsewhere in the repo, and engine progress state needs to reflect state-scanner skips immediately, not only after a built feature completes. I’m applying those fixes and adding tests that would have failed on the current code.
apply patch
patch: completed
/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py
diff --git a/src/ncdev/v3/claude_executor.py b/src/ncdev/v3/claude_executor.py
index 973459e5f764d4bf2d0bde198747c6949f216bd5..9fc826c2d005686dea54106495ec650aa569ce7b
--- a/src/ncdev/v3/claude_executor.py
+++ b/src/ncdev/v3/claude_executor.py
@@ -351,10 +351,13 @@
                 reasons.append(f"asset references without manifest: {missing[:5]}")
 
     # 3. Prohibited patterns (regex — treats entries in the contract as
-    #    patterns, falls back to literal match if the regex fails to compile)
+    #    patterns, falls back to literal match if the regex fails to compile).
+    #    Feature-local scope matters here for the same reason it matters for
+    #    asset manifests: one legacy TODO elsewhere in a brownfield repo should
+    #    not fail every future feature.
     patterns = bundle.verification.prohibited_patterns
     if patterns:
-        bad = _grep_for_prohibited(target_path, patterns)
+        bad = _grep_for_prohibited(target_path, patterns, touched_files=touched_files)
         if bad:
             reasons.append(f"prohibited patterns found: {bad[:5]}")
 
@@ -422,12 +425,20 @@
     return ver
 
 
-def _grep_for_prohibited(target_path: Path, patterns: list[str]) -> list[str]:
+def _grep_for_prohibited(
+    target_path: Path,
+    patterns: list[str],
+    *,
+    touched_files: list[str] | None = None,
+) -> list[str]:
     """Scan git-tracked files for prohibited patterns.
 
     Each entry is treated as a regular expression via ``re.search``. If
     a pattern fails to compile, falls back to a substring check so
     human-written entries like ``TODO`` still work.
+
+    When ``touched_files`` is provided, only scan that feature-local set.
+    This keeps brownfield legacy debt from failing unrelated future work.
     """
     compiled: list[tuple[str, re.Pattern[str] | None]] = []
     for pat in patterns:
@@ -444,10 +455,15 @@
         )
         if ls.returncode != 0:
             return []
-        files = [f for f in ls.stdout.splitlines() if f]
+        tracked_files = {f for f in ls.stdout.splitlines() if f}
     except (subprocess.TimeoutExpired, FileNotFoundError):
         return []
 
+    if touched_files is not None:
+        files = [f for f in touched_files if f in tracked_files]
+    else:
+        files = sorted(tracked_files)
+
     for f in files:
         fp = target_path / f
         try:

diff --git a/src/ncdev/v3/claude_executor.py b/src/ncdev/v3/claude_executor.py
index 973459e5f764d4bf2d0bde198747c6949f216bd5..9fc826c2d005686dea54106495ec650aa569ce7b
--- a/src/ncdev/v3/claude_executor.py
+++ b/src/ncdev/v3/claude_executor.py
@@ -351,10 +351,13 @@
                 reasons.append(f"asset references without manifest: {missing[:5]}")
 
     # 3. Prohibited patterns (regex — treats entries in the contract as
-    #    patterns, falls back to literal match if the regex fails to compile)
+    #    patterns, falls back to literal match if the regex fails to compile).
+    #    Feature-local scope matters here for the same reason it matters for
+    #    asset manifests: one legacy TODO elsewhere in a brownfield repo should
+    #    not fail every future feature.
     patterns = bundle.verification.prohibited_patterns
     if patterns:
-        bad = _grep_for_prohibited(target_path, patterns)
+        bad = _grep_for_prohibited(target_path, patterns, touched_files=touched_files)
         if bad:
             reasons.append(f"prohibited patterns found: {bad[:5]}")
 
@@ -422,12 +425,20 @@
     return ver
 
 
-def _grep_for_prohibited(target_path: Path, patterns: list[str]) -> list[str]:
+def _grep_for_prohibited(
+    target_path: Path,
+    patterns: list[str],
+    *,
+    touched_files: list[str] | None = None,
+) -> list[str]:
     """Scan git-tracked files for prohibited patterns.
 
     Each entry is treated as a regular expression via ``re.search``. If
     a pattern fails to compile, falls back to a substring check so
     human-written entries like ``TODO`` still work.
+
+    When ``touched_files`` is provided, only scan that feature-local set.
+    This keeps brownfield legacy debt from failing unrelated future work.
     """
     compiled: list[tuple[str, re.Pattern[str] | None]] = []
     for pat in patterns:
@@ -444,10 +455,15 @@
         )
         if ls.returncode != 0:
             return []
-        files = [f for f in ls.stdout.splitlines() if f]
+        tracked_files = {f for f in ls.stdout.splitlines() if f}
     except (subprocess.TimeoutExpired, FileNotFoundError):
         return []
 
+    if touched_files is not None:
+        files = [f for f in touched_files if f in tracked_files]
+    else:
+        files = sorted(tracked_files)
+
     for f in files:
         fp = target_path / f
         try:

apply patch
patch: completed
/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py
diff --git a/src/ncdev/v3/claude_executor.py b/src/ncdev/v3/claude_executor.py
index 973459e5f764d4bf2d0bde198747c6949f216bd5..9fc826c2d005686dea54106495ec650aa569ce7b
--- a/src/ncdev/v3/claude_executor.py
+++ b/src/ncdev/v3/claude_executor.py
@@ -351,10 +351,13 @@
                 reasons.append(f"asset references without manifest: {missing[:5]}")
 
     # 3. Prohibited patterns (regex — treats entries in the contract as
-    #    patterns, falls back to literal match if the regex fails to compile)
+    #    patterns, falls back to literal match if the regex fails to compile).
+    #    Feature-local scope matters here for the same reason it matters for
+    #    asset manifests: one legacy TODO elsewhere in a brownfield repo should
+    #    not fail every future feature.
     patterns = bundle.verification.prohibited_patterns
     if patterns:
-        bad = _grep_for_prohibited(target_path, patterns)
+        bad = _grep_for_prohibited(target_path, patterns, touched_files=touched_files)
         if bad:
             reasons.append(f"prohibited patterns found: {bad[:5]}")
 
@@ -422,12 +425,20 @@
     return ver
 
 
-def _grep_for_prohibited(target_path: Path, patterns: list[str]) -> list[str]:
+def _grep_for_prohibited(
+    target_path: Path,
+    patterns: list[str],
+    *,
+    touched_files: list[str] | None = None,
+) -> list[str]:
     """Scan git-tracked files for prohibited patterns.
 
     Each entry is treated as a regular expression via ``re.search``. If
     a pattern fails to compile, falls back to a substring check so
     human-written entries like ``TODO`` still work.
+
+    When ``touched_files`` is provided, only scan that feature-local set.
+    This keeps brownfield legacy debt from failing unrelated future work.
     """
     compiled: list[tuple[str, re.Pattern[str] | None]] = []
     for pat in patterns:
@@ -444,10 +455,15 @@
         )
         if ls.returncode != 0:
             return []
-        files = [f for f in ls.stdout.splitlines() if f]
+        tracked_files = {f for f in ls.stdout.splitlines() if f}
     except (subprocess.TimeoutExpired, FileNotFoundError):
         return []
 
+    if touched_files is not None:
+        files = [f for f in touched_files if f in tracked_files]
+    else:
+        files = sorted(tracked_files)
+
     for f in files:
         fp = target_path / f
         try:
diff --git a/src/ncdev/v3/engine.py b/src/ncdev/v3/engine.py
index 86cebe171c78ff9d0fded0c142a6793f98ca4944..78a18f3debbfd201af46ad4254db8d29afbb8aa5
--- a/src/ncdev/v3/engine.py
+++ b/src/ncdev/v3/engine.py
@@ -207,6 +207,8 @@
 
         # Brownfield: skip features already implemented
         remaining = _filter_completed_features(target_path, features, completed)
+        _sync_progress_state(state, completed)
+        _persist_state(state, run_dir)
         console.print(f"\n[bold]Phase 5: Building {len(remaining)} features sequentially[/bold]")
 
         for feature in remaining:
@@ -231,7 +233,7 @@
                     status=StepStatus.BLOCKED,
                     error_message=reason,
                 ))
-                state.completed_steps = completed
+                _sync_progress_state(state, completed)
                 _persist_state(state, run_dir)
                 if strict_deps:
                     console.print("[red]--strict-deps set: halting run[/red]")
@@ -256,14 +258,7 @@
                 config=config,
             )
             completed.append(result)
-            state.completed_steps = completed
-            # Count PASSED + SKIPPED — both are "done from NC Dev's
-            # perspective". SKIPPED = brownfield state scanner already
-            # found them in the target repo; PASSED = built this run.
-            state.completed_features = len([
-                r for r in completed
-                if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
-            ])
+            _sync_progress_state(state, completed)
             _persist_state(state, run_dir)
 
             status_style = "green" if result.status == StepStatus.PASSED else "red"
@@ -362,3 +357,14 @@
 def _persist_state(state: V3RunState, run_dir: Path) -> None:
     run_dir.mkdir(parents=True, exist_ok=True)
     (run_dir / "state.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")
+
+
+def _sync_progress_state(state: V3RunState, completed: list[StepResult]) -> None:
+    """Keep persisted progress counters in sync with the completed list."""
+    state.completed_steps = list(completed)
+    # Count PASSED + SKIPPED — both are "done from NC Dev's perspective".
+    # SKIPPED means the brownfield state scanner found them already present;
+    # PASSED means they were built successfully during this run.
+    state.completed_features = sum(
+        1 for r in completed if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
+    )

diff --git a/src/ncdev/v3/claude_executor.py b/src/ncdev/v3/claude_executor.py
index 973459e5f764d4bf2d0bde198747c6949f216bd5..9fc826c2d005686dea54106495ec650aa569ce7b
--- a/src/ncdev/v3/claude_executor.py
+++ b/src/ncdev/v3/claude_executor.py
@@ -351,10 +351,13 @@
                 reasons.append(f"asset references without manifest: {missing[:5]}")
 
     # 3. Prohibited patterns (regex — treats entries in the contract as
-    #    patterns, falls back to literal match if the regex fails to compile)
+    #    patterns, falls back to literal match if the regex fails to compile).
+    #    Feature-local scope matters here for the same reason it matters for
+    #    asset manifests: one legacy TODO elsewhere in a brownfield repo should
+    #    not fail every future feature.
     patterns = bundle.verification.prohibited_patterns
     if patterns:
-        bad = _grep_for_prohibited(target_path, patterns)
+        bad = _grep_for_prohibited(target_path, patterns, touched_files=touched_files)
         if bad:
             reasons.append(f"prohibited patterns found: {bad[:5]}")
 
@@ -422,12 +425,20 @@
     return ver
 
 
-def _grep_for_prohibited(target_path: Path, patterns: list[str]) -> list[str]:
+def _grep_for_prohibited(
+    target_path: Path,
+    patterns: list[str],
+    *,
+    touched_files: list[str] | None = None,
+) -> list[str]:
     """Scan git-tracked files for prohibited patterns.
 
     Each entry is treated as a regular expression via ``re.search``. If
     a pattern fails to compile, falls back to a substring check so
     human-written entries like ``TODO`` still work.
+
+    When ``touched_files`` is provided, only scan that feature-local set.
+    This keeps brownfield legacy debt from failing unrelated future work.
     """
     compiled: list[tuple[str, re.Pattern[str] | None]] = []
     for pat in patterns:
@@ -444,10 +455,15 @@
         )
         if ls.returncode != 0:
             return []
-        files = [f for f in ls.stdout.splitlines() if f]
+        tracked_files = {f for f in ls.stdout.splitlines() if f}
     except (subprocess.TimeoutExpired, FileNotFoundError):
         return []
 
+    if touched_files is not None:
+        files = [f for f in touched_files if f in tracked_files]
+    else:
+        files = sorted(tracked_files)
+
     for f in files:
         fp = target_path / f
         try:
diff --git a/src/ncdev/v3/engine.py b/src/ncdev/v3/engine.py
index 86cebe171c78ff9d0fded0c142a6793f98ca4944..78a18f3debbfd201af46ad4254db8d29afbb8aa5
--- a/src/ncdev/v3/engine.py
+++ b/src/ncdev/v3/engine.py
@@ -207,6 +207,8 @@
 
         # Brownfield: skip features already implemented
         remaining = _filter_completed_features(target_path, features, completed)
+        _sync_progress_state(state, completed)
+        _persist_state(state, run_dir)
         console.print(f"\n[bold]Phase 5: Building {len(remaining)} features sequentially[/bold]")
 
         for feature in remaining:
@@ -231,7 +233,7 @@
                     status=StepStatus.BLOCKED,
                     error_message=reason,
                 ))
-                state.completed_steps = completed
+                _sync_progress_state(state, completed)
                 _persist_state(state, run_dir)
                 if strict_deps:
                     console.print("[red]--strict-deps set: halting run[/red]")
@@ -256,14 +258,7 @@
                 config=config,
             )
             completed.append(result)
-            state.completed_steps = completed
-            # Count PASSED + SKIPPED — both are "done from NC Dev's
-            # perspective". SKIPPED = brownfield state scanner already
-            # found them in the target repo; PASSED = built this run.
-            state.completed_features = len([
-                r for r in completed
-                if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
-            ])
+            _sync_progress_state(state, completed)
             _persist_state(state, run_dir)
 
             status_style = "green" if result.status == StepStatus.PASSED else "red"
@@ -362,3 +357,14 @@
 def _persist_state(state: V3RunState, run_dir: Path) -> None:
     run_dir.mkdir(parents=True, exist_ok=True)
     (run_dir / "state.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")
+
+
+def _sync_progress_state(state: V3RunState, completed: list[StepResult]) -> None:
+    """Keep persisted progress counters in sync with the completed list."""
+    state.completed_steps = list(completed)
+    # Count PASSED + SKIPPED — both are "done from NC Dev's perspective".
+    # SKIPPED means the brownfield state scanner found them already present;
+    # PASSED means they were built successfully during this run.
+    state.completed_features = sum(
+        1 for r in completed if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
+    )

apply patch
patch: completed
/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/cli.py
diff --git a/src/ncdev/cli.py b/src/ncdev/cli.py
index 78347ed18abd9502b64378f77fe7d52c8c01d42e..b9f4d9dd0e16042063902ff869cc2bbc5fd2d255
--- a/src/ncdev/cli.py
+++ b/src/ncdev/cli.py
@@ -373,7 +373,7 @@
             strict_deps=bool(getattr(args, "strict_deps", False)),
         )
         console.print(f"run_id={state.run_id} status={state.status}")
-        console.print(f"features: {state.completed_features}/{state.total_features} passed")
+        console.print(f"features: {state.completed_features}/{state.total_features} completed")
         console.print(f"run_dir={state.run_dir}")
         if state.status != "passed":
             return 1
diff --git a/src/ncdev/v3/claude_executor.py b/src/ncdev/v3/claude_executor.py
index 973459e5f764d4bf2d0bde198747c6949f216bd5..9fc826c2d005686dea54106495ec650aa569ce7b
--- a/src/ncdev/v3/claude_executor.py
+++ b/src/ncdev/v3/claude_executor.py
@@ -351,10 +351,13 @@
                 reasons.append(f"asset references without manifest: {missing[:5]}")
 
     # 3. Prohibited patterns (regex — treats entries in the contract as
-    #    patterns, falls back to literal match if the regex fails to compile)
+    #    patterns, falls back to literal match if the regex fails to compile).
+    #    Feature-local scope matters here for the same reason it matters for
+    #    asset manifests: one legacy TODO elsewhere in a brownfield repo should
+    #    not fail every future feature.
     patterns = bundle.verification.prohibited_patterns
     if patterns:
-        bad = _grep_for_prohibited(target_path, patterns)
+        bad = _grep_for_prohibited(target_path, patterns, touched_files=touched_files)
         if bad:
             reasons.append(f"prohibited patterns found: {bad[:5]}")
 
@@ -422,12 +425,20 @@
     return ver
 
 
-def _grep_for_prohibited(target_path: Path, patterns: list[str]) -> list[str]:
+def _grep_for_prohibited(
+    target_path: Path,
+    patterns: list[str],
+    *,
+    touched_files: list[str] | None = None,
+) -> list[str]:
     """Scan git-tracked files for prohibited patterns.
 
     Each entry is treated as a regular expression via ``re.search``. If
     a pattern fails to compile, falls back to a substring check so
     human-written entries like ``TODO`` still work.
+
+    When ``touched_files`` is provided, only scan that feature-local set.
+    This keeps brownfield legacy debt from failing unrelated future work.
     """
     compiled: list[tuple[str, re.Pattern[str] | None]] = []
     for pat in patterns:
@@ -444,10 +455,15 @@
         )
         if ls.returncode != 0:
             return []
-        files = [f for f in ls.stdout.splitlines() if f]
+        tracked_files = {f for f in ls.stdout.splitlines() if f}
     except (subprocess.TimeoutExpired, FileNotFoundError):
         return []
 
+    if touched_files is not None:
+        files = [f for f in touched_files if f in tracked_files]
+    else:
+        files = sorted(tracked_files)
+
     for f in files:
         fp = target_path / f
         try:
diff --git a/src/ncdev/v3/engine.py b/src/ncdev/v3/engine.py
index 86cebe171c78ff9d0fded0c142a6793f98ca4944..78a18f3debbfd201af46ad4254db8d29afbb8aa5
--- a/src/ncdev/v3/engine.py
+++ b/src/ncdev/v3/engine.py
@@ -207,6 +207,8 @@
 
         # Brownfield: skip features already implemented
         remaining = _filter_completed_features(target_path, features, completed)
+        _sync_progress_state(state, completed)
+        _persist_state(state, run_dir)
         console.print(f"\n[bold]Phase 5: Building {len(remaining)} features sequentially[/bold]")
 
         for feature in remaining:
@@ -231,7 +233,7 @@
                     status=StepStatus.BLOCKED,
                     error_message=reason,
                 ))
-                state.completed_steps = completed
+                _sync_progress_state(state, completed)
                 _persist_state(state, run_dir)
                 if strict_deps:
                     console.print("[red]--strict-deps set: halting run[/red]")
@@ -256,14 +258,7 @@
                 config=config,
             )
             completed.append(result)
-            state.completed_steps = completed
-            # Count PASSED + SKIPPED — both are "done from NC Dev's
-            # perspective". SKIPPED = brownfield state scanner already
-            # found them in the target repo; PASSED = built this run.
-            state.completed_features = len([
-                r for r in completed
-                if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
-            ])
+            _sync_progress_state(state, completed)
             _persist_state(state, run_dir)
 
             status_style = "green" if result.status == StepStatus.PASSED else "red"
@@ -362,3 +357,14 @@
 def _persist_state(state: V3RunState, run_dir: Path) -> None:
     run_dir.mkdir(parents=True, exist_ok=True)
     (run_dir / "state.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")
+
+
+def _sync_progress_state(state: V3RunState, completed: list[StepResult]) -> None:
+    """Keep persisted progress counters in sync with the completed list."""
+    state.completed_steps = list(completed)
+    # Count PASSED + SKIPPED — both are "done from NC Dev's perspective".
+    # SKIPPED means the brownfield state scanner found them already present;
+    # PASSED means they were built successfully during this run.
+    state.completed_features = sum(
+        1 for r in completed if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
+    )

diff --git a/src/ncdev/cli.py b/src/ncdev/cli.py
index 78347ed18abd9502b64378f77fe7d52c8c01d42e..b9f4d9dd0e16042063902ff869cc2bbc5fd2d255
--- a/src/ncdev/cli.py
+++ b/src/ncdev/cli.py
@@ -373,7 +373,7 @@
             strict_deps=bool(getattr(args, "strict_deps", False)),
         )
         console.print(f"run_id={state.run_id} status={state.status}")
-        console.print(f"features: {state.completed_features}/{state.total_features} passed")
+        console.print(f"features: {state.completed_features}/{state.total_features} completed")
         console.print(f"run_dir={state.run_dir}")
         if state.status != "passed":
             return 1
diff --git a/src/ncdev/v3/claude_executor.py b/src/ncdev/v3/claude_executor.py
index 973459e5f764d4bf2d0bde198747c6949f216bd5..9fc826c2d005686dea54106495ec650aa569ce7b
--- a/src/ncdev/v3/claude_executor.py
+++ b/src/ncdev/v3/claude_executor.py
@@ -351,10 +351,13 @@
                 reasons.append(f"asset references without manifest: {missing[:5]}")
 
     # 3. Prohibited patterns (regex — treats entries in the contract as
-    #    patterns, falls back to literal match if the regex fails to compile)
+    #    patterns, falls back to literal match if the regex fails to compile).
+    #    Feature-local scope matters here for the same reason it matters for
+    #    asset manifests: one legacy TODO elsewhere in a brownfield repo should
+    #    not fail every future feature.
     patterns = bundle.verification.prohibited_patterns
     if patterns:
-        bad = _grep_for_prohibited(target_path, patterns)
+        bad = _grep_for_prohibited(target_path, patterns, touched_files=touched_files)
         if bad:
             reasons.append(f"prohibited patterns found: {bad[:5]}")
 
@@ -422,12 +425,20 @@
     return ver
 
 
-def _grep_for_prohibited(target_path: Path, patterns: list[str]) -> list[str]:
+def _grep_for_prohibited(
+    target_path: Path,
+    patterns: list[str],
+    *,
+    touched_files: list[str] | None = None,
+) -> list[str]:
     """Scan git-tracked files for prohibited patterns.
 
     Each entry is treated as a regular expression via ``re.search``. If
     a pattern fails to compile, falls back to a substring check so
     human-written entries like ``TODO`` still work.
+
+    When ``touched_files`` is provided, only scan that feature-local set.
+    This keeps brownfield legacy debt from failing unrelated future work.
     """
     compiled: list[tuple[str, re.Pattern[str] | None]] = []
     for pat in patterns:
@@ -444,10 +455,15 @@
         )
         if ls.returncode != 0:
             return []
-        files = [f for f in ls.stdout.splitlines() if f]
+        tracked_files = {f for f in ls.stdout.splitlines() if f}
     except (subprocess.TimeoutExpired, FileNotFoundError):
         return []
 
+    if touched_files is not None:
+        files = [f for f in touched_files if f in tracked_files]
+    else:
+        files = sorted(tracked_files)
+
     for f in files:
         fp = target_path / f
         try:
diff --git a/src/ncdev/v3/engine.py b/src/ncdev/v3/engine.py
index 86cebe171c78ff9d0fded0c142a6793f98ca4944..78a18f3debbfd201af46ad4254db8d29afbb8aa5
--- a/src/ncdev/v3/engine.py
+++ b/src/ncdev/v3/engine.py
@@ -207,6 +207,8 @@
 
         # Brownfield: skip features already implemented
         remaining = _filter_completed_features(target_path, features, completed)
+        _sync_progress_state(state, completed)
+        _persist_state(state, run_dir)
         console.print(f"\n[bold]Phase 5: Building {len(remaining)} features sequentially[/bold]")
 
         for feature in remaining:
@@ -231,7 +233,7 @@
                     status=StepStatus.BLOCKED,
                     error_message=reason,
                 ))
-                state.completed_steps = completed
+                _sync_progress_state(state, completed)
                 _persist_state(state, run_dir)
                 if strict_deps:
                     console.print("[red]--strict-deps set: halting run[/red]")
@@ -256,14 +258,7 @@
                 config=config,
             )
             completed.append(result)
-            state.completed_steps = completed
-            # Count PASSED + SKIPPED — both are "done from NC Dev's
-            # perspective". SKIPPED = brownfield state scanner already
-            # found them in the target repo; PASSED = built this run.
-            state.completed_features = len([
-                r for r in completed
-                if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
-            ])
+            _sync_progress_state(state, completed)
             _persist_state(state, run_dir)
 
             status_style = "green" if result.status == StepStatus.PASSED else "red"
@@ -362,3 +357,14 @@
 def _persist_state(state: V3RunState, run_dir: Path) -> None:
     run_dir.mkdir(parents=True, exist_ok=True)
     (run_dir / "state.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")
+
+
+def _sync_progress_state(state: V3RunState, completed: list[StepResult]) -> None:
+    """Keep persisted progress counters in sync with the completed list."""
+    state.completed_steps = list(completed)
+    # Count PASSED + SKIPPED — both are "done from NC Dev's perspective".
+    # SKIPPED means the brownfield state scanner found them already present;
+    # PASSED means they were built successfully during this run.
+    state.completed_features = sum(
+        1 for r in completed if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
+    )

apply patch
patch: completed
/Users/nrupal/dev/yensi/dev/nc-dev-system/tests/unit/test_claude_executor.py
diff --git a/src/ncdev/cli.py b/src/ncdev/cli.py
index 78347ed18abd9502b64378f77fe7d52c8c01d42e..b9f4d9dd0e16042063902ff869cc2bbc5fd2d255
--- a/src/ncdev/cli.py
+++ b/src/ncdev/cli.py
@@ -373,7 +373,7 @@
             strict_deps=bool(getattr(args, "strict_deps", False)),
         )
         console.print(f"run_id={state.run_id} status={state.status}")
-        console.print(f"features: {state.completed_features}/{state.total_features} passed")
+        console.print(f"features: {state.completed_features}/{state.total_features} completed")
         console.print(f"run_dir={state.run_dir}")
         if state.status != "passed":
             return 1
diff --git a/src/ncdev/v3/claude_executor.py b/src/ncdev/v3/claude_executor.py
index 973459e5f764d4bf2d0bde198747c6949f216bd5..9fc826c2d005686dea54106495ec650aa569ce7b
--- a/src/ncdev/v3/claude_executor.py
+++ b/src/ncdev/v3/claude_executor.py
@@ -351,10 +351,13 @@
                 reasons.append(f"asset references without manifest: {missing[:5]}")
 
     # 3. Prohibited patterns (regex — treats entries in the contract as
-    #    patterns, falls back to literal match if the regex fails to compile)
+    #    patterns, falls back to literal match if the regex fails to compile).
+    #    Feature-local scope matters here for the same reason it matters for
+    #    asset manifests: one legacy TODO elsewhere in a brownfield repo should
+    #    not fail every future feature.
     patterns = bundle.verification.prohibited_patterns
     if patterns:
-        bad = _grep_for_prohibited(target_path, patterns)
+        bad = _grep_for_prohibited(target_path, patterns, touched_files=touched_files)
         if bad:
             reasons.append(f"prohibited patterns found: {bad[:5]}")
 
@@ -422,12 +425,20 @@
     return ver
 
 
-def _grep_for_prohibited(target_path: Path, patterns: list[str]) -> list[str]:
+def _grep_for_prohibited(
+    target_path: Path,
+    patterns: list[str],
+    *,
+    touched_files: list[str] | None = None,
+) -> list[str]:
     """Scan git-tracked files for prohibited patterns.
 
     Each entry is treated as a regular expression via ``re.search``. If
     a pattern fails to compile, falls back to a substring check so
     human-written entries like ``TODO`` still work.
+
+    When ``touched_files`` is provided, only scan that feature-local set.
+    This keeps brownfield legacy debt from failing unrelated future work.
     """
     compiled: list[tuple[str, re.Pattern[str] | None]] = []
     for pat in patterns:
@@ -444,10 +455,15 @@
         )
         if ls.returncode != 0:
             return []
-        files = [f for f in ls.stdout.splitlines() if f]
+        tracked_files = {f for f in ls.stdout.splitlines() if f}
     except (subprocess.TimeoutExpired, FileNotFoundError):
         return []
 
+    if touched_files is not None:
+        files = [f for f in touched_files if f in tracked_files]
+    else:
+        files = sorted(tracked_files)
+
     for f in files:
         fp = target_path / f
         try:
diff --git a/src/ncdev/v3/engine.py b/src/ncdev/v3/engine.py
index 86cebe171c78ff9d0fded0c142a6793f98ca4944..78a18f3debbfd201af46ad4254db8d29afbb8aa5
--- a/src/ncdev/v3/engine.py
+++ b/src/ncdev/v3/engine.py
@@ -207,6 +207,8 @@
 
         # Brownfield: skip features already implemented
         remaining = _filter_completed_features(target_path, features, completed)
+        _sync_progress_state(state, completed)
+        _persist_state(state, run_dir)
         console.print(f"\n[bold]Phase 5: Building {len(remaining)} features sequentially[/bold]")
 
         for feature in remaining:
@@ -231,7 +233,7 @@
                     status=StepStatus.BLOCKED,
                     error_message=reason,
                 ))
-                state.completed_steps = completed
+                _sync_progress_state(state, completed)
                 _persist_state(state, run_dir)
                 if strict_deps:
                     console.print("[red]--strict-deps set: halting run[/red]")
@@ -256,14 +258,7 @@
                 config=config,
             )
             completed.append(result)
-            state.completed_steps = completed
-            # Count PASSED + SKIPPED — both are "done from NC Dev's
-            # perspective". SKIPPED = brownfield state scanner already
-            # found them in the target repo; PASSED = built this run.
-            state.completed_features = len([
-                r for r in completed
-                if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
-            ])
+            _sync_progress_state(state, completed)
             _persist_state(state, run_dir)
 
             status_style = "green" if result.status == StepStatus.PASSED else "red"
@@ -362,3 +357,14 @@
 def _persist_state(state: V3RunState, run_dir: Path) -> None:
     run_dir.mkdir(parents=True, exist_ok=True)
     (run_dir / "state.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")
+
+
+def _sync_progress_state(state: V3RunState, completed: list[StepResult]) -> None:
+    """Keep persisted progress counters in sync with the completed list."""
+    state.completed_steps = list(completed)
+    # Count PASSED + SKIPPED — both are "done from NC Dev's perspective".
+    # SKIPPED means the brownfield state scanner found them already present;
+    # PASSED means they were built successfully during this run.
+    state.completed_features = sum(
+        1 for r in completed if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
+    )
diff --git a/tests/unit/test_claude_executor.py b/tests/unit/test_claude_executor.py
index a08e209565101214bc64e0f710ac287b458bb03a..3261c2cbcac84262b510769fca4e661d2b9f008e
--- a/tests/unit/test_claude_executor.py
+++ b/tests/unit/test_claude_executor.py
@@ -294,6 +294,46 @@
     assert any("prohibited" in r.lower() for r in result.verification.failure_reasons)
 
 
+def test_legacy_prohibited_pattern_outside_touched_files_does_not_block_pass(tmp_path: Path):
+    """Post-hoc verification must stay feature-local.
+
+    A brownfield repo can contain an old TODO in some untouched file; that
+    should not fail a new clean feature, because the pre-commit hook only
+    guards staged content and the executor already scopes asset checks
+    feature-locally for the same reason.
+    """
+    target = tmp_path / "app"
+    target.mkdir()
+    _init_git(target)
+
+    # Legacy debt that predates this feature.
+    (target / "legacy.py").write_text("# TODO historical debt\n")
+    subprocess.run(["git", "add", "legacy.py"], cwd=str(target), check=True)
+    subprocess.run(["git", "commit", "-q", "-m", "feat(legacy): existing debt"],
+                   cwd=str(target), check=True)
+
+    def fake_session(prompt, **kwargs):  # noqa: ARG001
+        _seed_manifest(target, "f01-scaffold")
+        (target / "clean.py").write_text("x = 1\n")
+        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
+        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): clean"],
+                       cwd=str(target), check=True)
+        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)
+
+    bundle = _make_bundle()  # prohibited_patterns=["TODO"]
+    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):
+        result = execute_feature_claude_driven(
+            feature=_make_feature(),
+            target_path=target,
+            run_dir=tmp_path / "run",
+            charter_bundle=bundle,
+            prior_results=[],
+            project_id="myapp",
+        )
+
+    assert result.status == StepStatus.PASSED
+
+
 def test_verification_runs_backend_test_command_when_configured(tmp_path: Path):
     """New enforcement: backend_test_command actually runs, not just documented."""
     target = tmp_path / "app"

diff --git a/src/ncdev/cli.py b/src/ncdev/cli.py
index 78347ed18abd9502b64378f77fe7d52c8c01d42e..b9f4d9dd0e16042063902ff869cc2bbc5fd2d255
--- a/src/ncdev/cli.py
+++ b/src/ncdev/cli.py
@@ -373,7 +373,7 @@
             strict_deps=bool(getattr(args, "strict_deps", False)),
         )
         console.print(f"run_id={state.run_id} status={state.status}")
-        console.print(f"features: {state.completed_features}/{state.total_features} passed")
+        console.print(f"features: {state.completed_features}/{state.total_features} completed")
         console.print(f"run_dir={state.run_dir}")
         if state.status != "passed":
             return 1
diff --git a/src/ncdev/v3/claude_executor.py b/src/ncdev/v3/claude_executor.py
index 973459e5f764d4bf2d0bde198747c6949f216bd5..9fc826c2d005686dea54106495ec650aa569ce7b
--- a/src/ncdev/v3/claude_executor.py
+++ b/src/ncdev/v3/claude_executor.py
@@ -351,10 +351,13 @@
                 reasons.append(f"asset references without manifest: {missing[:5]}")
 
     # 3. Prohibited patterns (regex — treats entries in the contract as
-    #    patterns, falls back to literal match if the regex fails to compile)
+    #    patterns, falls back to literal match if the regex fails to compile).
+    #    Feature-local scope matters here for the same reason it matters for
+    #    asset manifests: one legacy TODO elsewhere in a brownfield repo should
+    #    not fail every future feature.
     patterns = bundle.verification.prohibited_patterns
     if patterns:
-        bad = _grep_for_prohibited(target_path, patterns)
+        bad = _grep_for_prohibited(target_path, patterns, touched_files=touched_files)
         if bad:
             reasons.append(f"prohibited patterns found: {bad[:5]}")
 
@@ -422,12 +425,20 @@
     return ver
 
 
-def _grep_for_prohibited(target_path: Path, patterns: list[str]) -> list[str]:
+def _grep_for_prohibited(
+    target_path: Path,
+    patterns: list[str],
+    *,
+    touched_files: list[str] | None = None,
+) -> list[str]:
     """Scan git-tracked files for prohibited patterns.
 
     Each entry is treated as a regular expression via ``re.search``. If
     a pattern fails to compile, falls back to a substring check so
     human-written entries like ``TODO`` still work.
+
+    When ``touched_files`` is provided, only scan that feature-local set.
+    This keeps brownfield legacy debt from failing unrelated future work.
     """
     compiled: list[tuple[str, re.Pattern[str] | None]] = []
     for pat in patterns:
@@ -444,10 +455,15 @@
         )
         if ls.returncode != 0:
             return []
-        files = [f for f in ls.stdout.splitlines() if f]
+        tracked_files = {f for f in ls.stdout.splitlines() if f}
     except (subprocess.TimeoutExpired, FileNotFoundError):
         return []
 
+    if touched_files is not None:
+        files = [f for f in touched_files if f in tracked_files]
+    else:
+        files = sorted(tracked_files)
+
     for f in files:
         fp = target_path / f
         try:
diff --git a/src/ncdev/v3/engine.py b/src/ncdev/v3/engine.py
index 86cebe171c78ff9d0fded0c142a6793f98ca4944..78a18f3debbfd201af46ad4254db8d29afbb8aa5
--- a/src/ncdev/v3/engine.py
+++ b/src/ncdev/v3/engine.py
@@ -207,6 +207,8 @@
 
         # Brownfield: skip features already implemented
         remaining = _filter_completed_features(target_path, features, completed)
+        _sync_progress_state(state, completed)
+        _persist_state(state, run_dir)
         console.print(f"\n[bold]Phase 5: Building {len(remaining)} features sequentially[/bold]")
 
         for feature in remaining:
@@ -231,7 +233,7 @@
                     status=StepStatus.BLOCKED,
                     error_message=reason,
                 ))
-                state.completed_steps = completed
+                _sync_progress_state(state, completed)
                 _persist_state(state, run_dir)
                 if strict_deps:
                     console.print("[red]--strict-deps set: halting run[/red]")
@@ -256,14 +258,7 @@
                 config=config,
             )
             completed.append(result)
-            state.completed_steps = completed
-            # Count PASSED + SKIPPED — both are "done from NC Dev's
-            # perspective". SKIPPED = brownfield state scanner already
-            # found them in the target repo; PASSED = built this run.
-            state.completed_features = len([
-                r for r in completed
-                if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
-            ])
+            _sync_progress_state(state, completed)
             _persist_state(state, run_dir)
 
             status_style = "green" if result.status == StepStatus.PASSED else "red"
@@ -362,3 +357,14 @@
 def _persist_state(state: V3RunState, run_dir: Path) -> None:
     run_dir.mkdir(parents=True, exist_ok=True)
     (run_dir / "state.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")
+
+
+def _sync_progress_state(state: V3RunState, completed: list[StepResult]) -> None:
+    """Keep persisted progress counters in sync with the completed list."""
+    state.completed_steps = list(completed)
+    # Count PASSED + SKIPPED — both are "done from NC Dev's perspective".
+    # SKIPPED means the brownfield state scanner found them already present;
+    # PASSED means they were built successfully during this run.
+    state.completed_features = sum(
+        1 for r in completed if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
+    )
diff --git a/tests/unit/test_claude_executor.py b/tests/unit/test_claude_executor.py
index a08e209565101214bc64e0f710ac287b458bb03a..3261c2cbcac84262b510769fca4e661d2b9f008e
--- a/tests/unit/test_claude_executor.py
+++ b/tests/unit/test_claude_executor.py
@@ -294,6 +294,46 @@
     assert any("prohibited" in r.lower() for r in result.verification.failure_reasons)
 
 
+def test_legacy_prohibited_pattern_outside_touched_files_does_not_block_pass(tmp_path: Path):
+    """Post-hoc verification must stay feature-local.
+
+    A brownfield repo can contain an old TODO in some untouched file; that
+    should not fail a new clean feature, because the pre-commit hook only
+    guards staged content and the executor already scopes asset checks
+    feature-locally for the same reason.
+    """
+    target = tmp_path / "app"
+    target.mkdir()
+    _init_git(target)
+
+    # Legacy debt that predates this feature.
+    (target / "legacy.py").write_text("# TODO historical debt\n")
+    subprocess.run(["git", "add", "legacy.py"], cwd=str(target), check=True)
+    subprocess.run(["git", "commit", "-q", "-m", "feat(legacy): existing debt"],
+                   cwd=str(target), check=True)
+
+    def fake_session(prompt, **kwargs):  # noqa: ARG001
+        _seed_manifest(target, "f01-scaffold")
+        (target / "clean.py").write_text("x = 1\n")
+        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
+        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): clean"],
+                       cwd=str(target), check=True)
+        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)
+
+    bundle = _make_bundle()  # prohibited_patterns=["TODO"]
+    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):
+        result = execute_feature_claude_driven(
+            feature=_make_feature(),
+            target_path=target,
+            run_dir=tmp_path / "run",
+            charter_bundle=bundle,
+            prior_results=[],
+            project_id="myapp",
+        )
+
+    assert result.status == StepStatus.PASSED
+
+
 def test_verification_runs_backend_test_command_when_configured(tmp_path: Path):
     """New enforcement: backend_test_command actually runs, not just documented."""
     target = tmp_path / "app"

apply patch
patch: completed
/Users/nrupal/dev/yensi/dev/nc-dev-system/tests/test_ncdev_v3/test_engine.py
diff --git a/src/ncdev/cli.py b/src/ncdev/cli.py
index 78347ed18abd9502b64378f77fe7d52c8c01d42e..b9f4d9dd0e16042063902ff869cc2bbc5fd2d255
--- a/src/ncdev/cli.py
+++ b/src/ncdev/cli.py
@@ -373,7 +373,7 @@
             strict_deps=bool(getattr(args, "strict_deps", False)),
         )
         console.print(f"run_id={state.run_id} status={state.status}")
-        console.print(f"features: {state.completed_features}/{state.total_features} passed")
+        console.print(f"features: {state.completed_features}/{state.total_features} completed")
         console.print(f"run_dir={state.run_dir}")
         if state.status != "passed":
             return 1
diff --git a/src/ncdev/v3/claude_executor.py b/src/ncdev/v3/claude_executor.py
index 973459e5f764d4bf2d0bde198747c6949f216bd5..9fc826c2d005686dea54106495ec650aa569ce7b
--- a/src/ncdev/v3/claude_executor.py
+++ b/src/ncdev/v3/claude_executor.py
@@ -351,10 +351,13 @@
                 reasons.append(f"asset references without manifest: {missing[:5]}")
 
     # 3. Prohibited patterns (regex — treats entries in the contract as
-    #    patterns, falls back to literal match if the regex fails to compile)
+    #    patterns, falls back to literal match if the regex fails to compile).
+    #    Feature-local scope matters here for the same reason it matters for
+    #    asset manifests: one legacy TODO elsewhere in a brownfield repo should
+    #    not fail every future feature.
     patterns = bundle.verification.prohibited_patterns
     if patterns:
-        bad = _grep_for_prohibited(target_path, patterns)
+        bad = _grep_for_prohibited(target_path, patterns, touched_files=touched_files)
         if bad:
             reasons.append(f"prohibited patterns found: {bad[:5]}")
 
@@ -422,12 +425,20 @@
     return ver
 
 
-def _grep_for_prohibited(target_path: Path, patterns: list[str]) -> list[str]:
+def _grep_for_prohibited(
+    target_path: Path,
+    patterns: list[str],
+    *,
+    touched_files: list[str] | None = None,
+) -> list[str]:
     """Scan git-tracked files for prohibited patterns.
 
     Each entry is treated as a regular expression via ``re.search``. If
     a pattern fails to compile, falls back to a substring check so
     human-written entries like ``TODO`` still work.
+
+    When ``touched_files`` is provided, only scan that feature-local set.
+    This keeps brownfield legacy debt from failing unrelated future work.
     """
     compiled: list[tuple[str, re.Pattern[str] | None]] = []
     for pat in patterns:
@@ -444,10 +455,15 @@
         )
         if ls.returncode != 0:
             return []
-        files = [f for f in ls.stdout.splitlines() if f]
+        tracked_files = {f for f in ls.stdout.splitlines() if f}
     except (subprocess.TimeoutExpired, FileNotFoundError):
         return []
 
+    if touched_files is not None:
+        files = [f for f in touched_files if f in tracked_files]
+    else:
+        files = sorted(tracked_files)
+
     for f in files:
         fp = target_path / f
         try:
diff --git a/src/ncdev/v3/engine.py b/src/ncdev/v3/engine.py
index 86cebe171c78ff9d0fded0c142a6793f98ca4944..78a18f3debbfd201af46ad4254db8d29afbb8aa5
--- a/src/ncdev/v3/engine.py
+++ b/src/ncdev/v3/engine.py
@@ -207,6 +207,8 @@
 
         # Brownfield: skip features already implemented
         remaining = _filter_completed_features(target_path, features, completed)
+        _sync_progress_state(state, completed)
+        _persist_state(state, run_dir)
         console.print(f"\n[bold]Phase 5: Building {len(remaining)} features sequentially[/bold]")
 
         for feature in remaining:
@@ -231,7 +233,7 @@
                     status=StepStatus.BLOCKED,
                     error_message=reason,
                 ))
-                state.completed_steps = completed
+                _sync_progress_state(state, completed)
                 _persist_state(state, run_dir)
                 if strict_deps:
                     console.print("[red]--strict-deps set: halting run[/red]")
@@ -256,14 +258,7 @@
                 config=config,
             )
             completed.append(result)
-            state.completed_steps = completed
-            # Count PASSED + SKIPPED — both are "done from NC Dev's
-            # perspective". SKIPPED = brownfield state scanner already
-            # found them in the target repo; PASSED = built this run.
-            state.completed_features = len([
-                r for r in completed
-                if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
-            ])
+            _sync_progress_state(state, completed)
             _persist_state(state, run_dir)
 
             status_style = "green" if result.status == StepStatus.PASSED else "red"
@@ -362,3 +357,14 @@
 def _persist_state(state: V3RunState, run_dir: Path) -> None:
     run_dir.mkdir(parents=True, exist_ok=True)
     (run_dir / "state.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")
+
+
+def _sync_progress_state(state: V3RunState, completed: list[StepResult]) -> None:
+    """Keep persisted progress counters in sync with the completed list."""
+    state.completed_steps = list(completed)
+    # Count PASSED + SKIPPED — both are "done from NC Dev's perspective".
+    # SKIPPED means the brownfield state scanner found them already present;
+    # PASSED means they were built successfully during this run.
+    state.completed_features = sum(
+        1 for r in completed if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
+    )
diff --git a/tests/test_ncdev_v3/test_engine.py b/tests/test_ncdev_v3/test_engine.py
new file mode 100644
index 0000000000000000000000000000000000000000..d4c48cda3f6e41c3ca90e7483dc2d8578b7a7940
--- /dev/null
+++ b/tests/test_ncdev_v3/test_engine.py
@@ -0,0 +1,67 @@
+from __future__ import annotations
+
+from pathlib import Path
+from types import SimpleNamespace
+
+from ncdev.v3.engine import run_v3_full
+from ncdev.v3.models import (
+    CharterBundle,
+    FeatureQueueDoc,
+    FeatureStep,
+    StepResult,
+    StepStatus,
+    TargetProjectContract,
+    VerificationContract,
+)
+
+
+def _bundle(*features: FeatureStep) -> CharterBundle:
+    return CharterBundle(
+        contract=TargetProjectContract(project_name="proj", project_type="web"),
+        verification=VerificationContract(),
+        feature_queue=FeatureQueueDoc(project_name="proj", features=list(features)),
+    )
+
+
+def test_run_v3_full_persists_brownfield_skips_in_progress_state(tmp_path: Path, monkeypatch):
+    """State-scanner skips must show up immediately in persisted progress.
+
+    Before this fix, completed_steps/completed_features stayed at zero when
+    the scanner skipped features before the build loop ran, so a fully
+    brownfield/no-op run reported no completed work in state.json.
+    """
+    workspace = tmp_path / "ws"
+    workspace.mkdir()
+    source = workspace / "prd.md"
+    source.write_text("# PRD\n")
+    target = workspace / "target"
+    target.mkdir()
+
+    feature = FeatureStep(
+        feature_id="f1",
+        title="Already done",
+        description="",
+        acceptance_criteria=[],
+    )
+    bundle = _bundle(feature)
+
+    monkeypatch.setattr("ncdev.v3.engine.generate_charter", lambda **kwargs: (bundle, SimpleNamespace(summary=lambda: "ok")))
+    monkeypatch.setattr("ncdev.v3.engine.run_design_phase", lambda **kwargs: SimpleNamespace(skipped=True, hard_failed=False, design_doc=None))
+    monkeypatch.setattr("ncdev.v3.state_scanner.scan_completed_features", lambda target_path, features: ["f1"])
+    monkeypatch.setattr(
+        "ncdev.v3.state_scanner.build_skip_results",
+        lambda features, done_ids: [StepResult(feature_id="f1", status=StepStatus.SKIPPED)],
+    )
+
+    state = run_v3_full(
+        workspace=workspace,
+        source_path=source,
+        target_repo_path=target,
+        builder_model="claude-opus-4-6",
+    )
+
+    assert state.status == "passed"
+    assert state.completed_features == 1
+    assert len(state.completed_steps) == 1
+    assert state.completed_steps[0].status == StepStatus.SKIPPED
+
diff --git a/tests/unit/test_claude_executor.py b/tests/unit/test_claude_executor.py
index a08e209565101214bc64e0f710ac287b458bb03a..3261c2cbcac84262b510769fca4e661d2b9f008e
--- a/tests/unit/test_claude_executor.py
+++ b/tests/unit/test_claude_executor.py
@@ -294,6 +294,46 @@
     assert any("prohibited" in r.lower() for r in result.verification.failure_reasons)
 
 
+def test_legacy_prohibited_pattern_outside_touched_files_does_not_block_pass(tmp_path: Path):
+    """Post-hoc verification must stay feature-local.
+
+    A brownfield repo can contain an old TODO in some untouched file; that
+    should not fail a new clean feature, because the pre-commit hook only
+    guards staged content and the executor already scopes asset checks
+    feature-locally for the same reason.
+    """
+    target = tmp_path / "app"
+    target.mkdir()
+    _init_git(target)
+
+    # Legacy debt that predates this feature.
+    (target / "legacy.py").write_text("# TODO historical debt\n")
+    subprocess.run(["git", "add", "legacy.py"], cwd=str(target), check=True)
+    subprocess.run(["git", "commit", "-q", "-m", "feat(legacy): existing debt"],
+                   cwd=str(target), check=True)
+
+    def fake_session(prompt, **kwargs):  # noqa: ARG001
+        _seed_manifest(target, "f01-scaffold")
+        (target / "clean.py").write_text("x = 1\n")
+        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
+        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): clean"],
+                       cwd=str(target), check=True)
+        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)
+
+    bundle = _make_bundle()  # prohibited_patterns=["TODO"]
+    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):
+        result = execute_feature_claude_driven(
+            feature=_make_feature(),
+            target_path=target,
+            run_dir=tmp_path / "run",
+            charter_bundle=bundle,
+            prior_results=[],
+            project_id="myapp",
+        )
+
+    assert result.status == StepStatus.PASSED
+
+
 def test_verification_runs_backend_test_command_when_configured(tmp_path: Path):
     """New enforcement: backend_test_command actually runs, not just documented."""
     target = tmp_path / "app"

diff --git a/src/ncdev/cli.py b/src/ncdev/cli.py
index 78347ed18abd9502b64378f77fe7d52c8c01d42e..b9f4d9dd0e16042063902ff869cc2bbc5fd2d255
--- a/src/ncdev/cli.py
+++ b/src/ncdev/cli.py
@@ -373,7 +373,7 @@
             strict_deps=bool(getattr(args, "strict_deps", False)),
         )
         console.print(f"run_id={state.run_id} status={state.status}")
-        console.print(f"features: {state.completed_features}/{state.total_features} passed")
+        console.print(f"features: {state.completed_features}/{state.total_features} completed")
         console.print(f"run_dir={state.run_dir}")
         if state.status != "passed":
             return 1
diff --git a/src/ncdev/v3/claude_executor.py b/src/ncdev/v3/claude_executor.py
index 973459e5f764d4bf2d0bde198747c6949f216bd5..9fc826c2d005686dea54106495ec650aa569ce7b
--- a/src/ncdev/v3/claude_executor.py
+++ b/src/ncdev/v3/claude_executor.py
@@ -351,10 +351,13 @@
                 reasons.append(f"asset references without manifest: {missing[:5]}")
 
     # 3. Prohibited patterns (regex — treats entries in the contract as
-    #    patterns, falls back to literal match if the regex fails to compile)
+    #    patterns, falls back to literal match if the regex fails to compile).
+    #    Feature-local scope matters here for the same reason it matters for
+    #    asset manifests: one legacy TODO elsewhere in a brownfield repo should
+    #    not fail every future feature.
     patterns = bundle.verification.prohibited_patterns
     if patterns:
-        bad = _grep_for_prohibited(target_path, patterns)
+        bad = _grep_for_prohibited(target_path, patterns, touched_files=touched_files)
         if bad:
             reasons.append(f"prohibited patterns found: {bad[:5]}")
 
@@ -422,12 +425,20 @@
     return ver
 
 
-def _grep_for_prohibited(target_path: Path, patterns: list[str]) -> list[str]:
+def _grep_for_prohibited(
+    target_path: Path,
+    patterns: list[str],
+    *,
+    touched_files: list[str] | None = None,
+) -> list[str]:
     """Scan git-tracked files for prohibited patterns.
 
     Each entry is treated as a regular expression via ``re.search``. If
     a pattern fails to compile, falls back to a substring check so
     human-written entries like ``TODO`` still work.
+
+    When ``touched_files`` is provided, only scan that feature-local set.
+    This keeps brownfield legacy debt from failing unrelated future work.
     """
     compiled: list[tuple[str, re.Pattern[str] | None]] = []
     for pat in patterns:
@@ -444,10 +455,15 @@
         )
         if ls.returncode != 0:
             return []
-        files = [f for f in ls.stdout.splitlines() if f]
+        tracked_files = {f for f in ls.stdout.splitlines() if f}
     except (subprocess.TimeoutExpired, FileNotFoundError):
         return []
 
+    if touched_files is not None:
+        files = [f for f in touched_files if f in tracked_files]
+    else:
+        files = sorted(tracked_files)
+
     for f in files:
         fp = target_path / f
         try:
diff --git a/src/ncdev/v3/engine.py b/src/ncdev/v3/engine.py
index 86cebe171c78ff9d0fded0c142a6793f98ca4944..78a18f3debbfd201af46ad4254db8d29afbb8aa5
--- a/src/ncdev/v3/engine.py
+++ b/src/ncdev/v3/engine.py
@@ -207,6 +207,8 @@
 
         # Brownfield: skip features already implemented
         remaining = _filter_completed_features(target_path, features, completed)
+        _sync_progress_state(state, completed)
+        _persist_state(state, run_dir)
         console.print(f"\n[bold]Phase 5: Building {len(remaining)} features sequentially[/bold]")
 
         for feature in remaining:
@@ -231,7 +233,7 @@
                     status=StepStatus.BLOCKED,
                     error_message=reason,
                 ))
-                state.completed_steps = completed
+                _sync_progress_state(state, completed)
                 _persist_state(state, run_dir)
                 if strict_deps:
                     console.print("[red]--strict-deps set: halting run[/red]")
@@ -256,14 +258,7 @@
                 config=config,
             )
             completed.append(result)
-            state.completed_steps = completed
-            # Count PASSED + SKIPPED — both are "done from NC Dev's
-            # perspective". SKIPPED = brownfield state scanner already
-            # found them in the target repo; PASSED = built this run.
-            state.completed_features = len([
-                r for r in completed
-                if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
-            ])
+            _sync_progress_state(state, completed)
             _persist_state(state, run_dir)
 
             status_style = "green" if result.status == StepStatus.PASSED else "red"
@@ -362,3 +357,14 @@
 def _persist_state(state: V3RunState, run_dir: Path) -> None:
     run_dir.mkdir(parents=True, exist_ok=True)
     (run_dir / "state.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")
+
+
+def _sync_progress_state(state: V3RunState, completed: list[StepResult]) -> None:
+    """Keep persisted progress counters in sync with the completed list."""
+    state.completed_steps = list(completed)
+    # Count PASSED + SKIPPED — both are "done from NC Dev's perspective".
+    # SKIPPED means the brownfield state scanner found them already present;
+    # PASSED means they were built successfully during this run.
+    state.completed_features = sum(
+        1 for r in completed if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
+    )
diff --git a/tests/test_ncdev_v3/test_engine.py b/tests/test_ncdev_v3/test_engine.py
new file mode 100644
index 0000000000000000000000000000000000000000..d4c48cda3f6e41c3ca90e7483dc2d8578b7a7940
--- /dev/null
+++ b/tests/test_ncdev_v3/test_engine.py
@@ -0,0 +1,67 @@
+from __future__ import annotations
+
+from pathlib import Path
+from types import SimpleNamespace
+
+from ncdev.v3.engine import run_v3_full
+from ncdev.v3.models import (
+    CharterBundle,
+    FeatureQueueDoc,
+    FeatureStep,
+    StepResult,
+    StepStatus,
+    TargetProjectContract,
+    VerificationContract,
+)
+
+
+def _bundle(*features: FeatureStep) -> CharterBundle:
+    return CharterBundle(
+        contract=TargetProjectContract(project_name="proj", project_type="web"),
+        verification=VerificationContract(),
+        feature_queue=FeatureQueueDoc(project_name="proj", features=list(features)),
+    )
+
+
+def test_run_v3_full_persists_brownfield_skips_in_progress_state(tmp_path: Path, monkeypatch):
+    """State-scanner skips must show up immediately in persisted progress.
+
+    Before this fix, completed_steps/completed_features stayed at zero when
+    the scanner skipped features before the build loop ran, so a fully
+    brownfield/no-op run reported no completed work in state.json.
+    """
+    workspace = tmp_path / "ws"
+    workspace.mkdir()
+    source = workspace / "prd.md"
+    source.write_text("# PRD\n")
+    target = workspace / "target"
+    target.mkdir()
+
+    feature = FeatureStep(
+        feature_id="f1",
+        title="Already done",
+        description="",
+        acceptance_criteria=[],
+    )
+    bundle = _bundle(feature)
+
+    monkeypatch.setattr("ncdev.v3.engine.generate_charter", lambda **kwargs: (bundle, SimpleNamespace(summary=lambda: "ok")))
+    monkeypatch.setattr("ncdev.v3.engine.run_design_phase", lambda **kwargs: SimpleNamespace(skipped=True, hard_failed=False, design_doc=None))
+    monkeypatch.setattr("ncdev.v3.state_scanner.scan_completed_features", lambda target_path, features: ["f1"])
+    monkeypatch.setattr(
+        "ncdev.v3.state_scanner.build_skip_results",
+        lambda features, done_ids: [StepResult(feature_id="f1", status=StepStatus.SKIPPED)],
+    )
+
+    state = run_v3_full(
+        workspace=workspace,
+        source_path=source,
+        target_repo_path=target,
+        builder_model="claude-opus-4-6",
+    )
+
+    assert state.status == "passed"
+    assert state.completed_features == 1
+    assert len(state.completed_steps) == 1
+    assert state.completed_steps[0].status == StepStatus.SKIPPED
+
diff --git a/tests/unit/test_claude_executor.py b/tests/unit/test_claude_executor.py
index a08e209565101214bc64e0f710ac287b458bb03a..3261c2cbcac84262b510769fca4e661d2b9f008e
--- a/tests/unit/test_claude_executor.py
+++ b/tests/unit/test_claude_executor.py
@@ -294,6 +294,46 @@
     assert any("prohibited" in r.lower() for r in result.verification.failure_reasons)
 
 
+def test_legacy_prohibited_pattern_outside_touched_files_does_not_block_pass(tmp_path: Path):
+    """Post-hoc verification must stay feature-local.
+
+    A brownfield repo can contain an old TODO in some untouched file; that
+    should not fail a new clean feature, because the pre-commit hook only
+    guards staged content and the executor already scopes asset checks
+    feature-locally for the same reason.
+    """
+    target = tmp_path / "app"
+    target.mkdir()
+    _init_git(target)
+
+    # Legacy debt that predates this feature.
+    (target / "legacy.py").write_text("# TODO historical debt\n")
+    subprocess.run(["git", "add", "legacy.py"], cwd=str(target), check=True)
+    subprocess.run(["git", "commit", "-q", "-m", "feat(legacy): existing debt"],
+                   cwd=str(target), check=True)
+
+    def fake_session(prompt, **kwargs):  # noqa: ARG001
+        _seed_manifest(target, "f01-scaffold")
+        (target / "clean.py").write_text("x = 1\n")
+        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
+        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): clean"],
+                       cwd=str(target), check=True)
+        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)
+
+    bundle = _make_bundle()  # prohibited_patterns=["TODO"]
+    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):
+        result = execute_feature_claude_driven(
+            feature=_make_feature(),
+            target_path=target,
+            run_dir=tmp_path / "run",
+            charter_bundle=bundle,
+            prior_results=[],
+            project_id="myapp",
+        )
+
+    assert result.status == StepStatus.PASSED
+
+
 def test_verification_runs_backend_test_command_when_configured(tmp_path: Path):
     """New enforcement: backend_test_command actually runs, not just documented."""
     target = tmp_path / "app"

apply patch
patch: completed
/Users/nrupal/dev/yensi/dev/nc-dev-system/tests/test_cli.py
diff --git a/src/ncdev/cli.py b/src/ncdev/cli.py
index 78347ed18abd9502b64378f77fe7d52c8c01d42e..b9f4d9dd0e16042063902ff869cc2bbc5fd2d255
--- a/src/ncdev/cli.py
+++ b/src/ncdev/cli.py
@@ -373,7 +373,7 @@
             strict_deps=bool(getattr(args, "strict_deps", False)),
         )
         console.print(f"run_id={state.run_id} status={state.status}")
-        console.print(f"features: {state.completed_features}/{state.total_features} passed")
+        console.print(f"features: {state.completed_features}/{state.total_features} completed")
         console.print(f"run_dir={state.run_dir}")
         if state.status != "passed":
             return 1
diff --git a/src/ncdev/v3/claude_executor.py b/src/ncdev/v3/claude_executor.py
index 973459e5f764d4bf2d0bde198747c6949f216bd5..9fc826c2d005686dea54106495ec650aa569ce7b
--- a/src/ncdev/v3/claude_executor.py
+++ b/src/ncdev/v3/claude_executor.py
@@ -351,10 +351,13 @@
                 reasons.append(f"asset references without manifest: {missing[:5]}")
 
     # 3. Prohibited patterns (regex — treats entries in the contract as
-    #    patterns, falls back to literal match if the regex fails to compile)
+    #    patterns, falls back to literal match if the regex fails to compile).
+    #    Feature-local scope matters here for the same reason it matters for
+    #    asset manifests: one legacy TODO elsewhere in a brownfield repo should
+    #    not fail every future feature.
     patterns = bundle.verification.prohibited_patterns
     if patterns:
-        bad = _grep_for_prohibited(target_path, patterns)
+        bad = _grep_for_prohibited(target_path, patterns, touched_files=touched_files)
         if bad:
             reasons.append(f"prohibited patterns found: {bad[:5]}")
 
@@ -422,12 +425,20 @@
     return ver
 
 
-def _grep_for_prohibited(target_path: Path, patterns: list[str]) -> list[str]:
+def _grep_for_prohibited(
+    target_path: Path,
+    patterns: list[str],
+    *,
+    touched_files: list[str] | None = None,
+) -> list[str]:
     """Scan git-tracked files for prohibited patterns.
 
     Each entry is treated as a regular expression via ``re.search``. If
     a pattern fails to compile, falls back to a substring check so
     human-written entries like ``TODO`` still work.
+
+    When ``touched_files`` is provided, only scan that feature-local set.
+    This keeps brownfield legacy debt from failing unrelated future work.
     """
     compiled: list[tuple[str, re.Pattern[str] | None]] = []
     for pat in patterns:
@@ -444,10 +455,15 @@
         )
         if ls.returncode != 0:
             return []
-        files = [f for f in ls.stdout.splitlines() if f]
+        tracked_files = {f for f in ls.stdout.splitlines() if f}
     except (subprocess.TimeoutExpired, FileNotFoundError):
         return []
 
+    if touched_files is not None:
+        files = [f for f in touched_files if f in tracked_files]
+    else:
+        files = sorted(tracked_files)
+
     for f in files:
         fp = target_path / f
         try:
diff --git a/src/ncdev/v3/engine.py b/src/ncdev/v3/engine.py
index 86cebe171c78ff9d0fded0c142a6793f98ca4944..78a18f3debbfd201af46ad4254db8d29afbb8aa5
--- a/src/ncdev/v3/engine.py
+++ b/src/ncdev/v3/engine.py
@@ -207,6 +207,8 @@
 
         # Brownfield: skip features already implemented
         remaining = _filter_completed_features(target_path, features, completed)
+        _sync_progress_state(state, completed)
+        _persist_state(state, run_dir)
         console.print(f"\n[bold]Phase 5: Building {len(remaining)} features sequentially[/bold]")
 
         for feature in remaining:
@@ -231,7 +233,7 @@
                     status=StepStatus.BLOCKED,
                     error_message=reason,
                 ))
-                state.completed_steps = completed
+                _sync_progress_state(state, completed)
                 _persist_state(state, run_dir)
                 if strict_deps:
                     console.print("[red]--strict-deps set: halting run[/red]")
@@ -256,14 +258,7 @@
                 config=config,
             )
             completed.append(result)
-            state.completed_steps = completed
-            # Count PASSED + SKIPPED — both are "done from NC Dev's
-            # perspective". SKIPPED = brownfield state scanner already
-            # found them in the target repo; PASSED = built this run.
-            state.completed_features = len([
-                r for r in completed
-                if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
-            ])
+            _sync_progress_state(state, completed)
             _persist_state(state, run_dir)
 
             status_style = "green" if result.status == StepStatus.PASSED else "red"
@@ -362,3 +357,14 @@
 def _persist_state(state: V3RunState, run_dir: Path) -> None:
     run_dir.mkdir(parents=True, exist_ok=True)
     (run_dir / "state.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")
+
+
+def _sync_progress_state(state: V3RunState, completed: list[StepResult]) -> None:
+    """Keep persisted progress counters in sync with the completed list."""
+    state.completed_steps = list(completed)
+    # Count PASSED + SKIPPED — both are "done from NC Dev's perspective".
+    # SKIPPED means the brownfield state scanner found them already present;
+    # PASSED means they were built successfully during this run.
+    state.completed_features = sum(
+        1 for r in completed if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
+    )
diff --git a/tests/test_cli.py b/tests/test_cli.py
index 6e1d69ab2f720b5fd71b603de93f8d2967eb7c95..395d8c6e8ff314a3735129c59434f9c31c171365
--- a/tests/test_cli.py
+++ b/tests/test_cli.py
@@ -1,6 +1,8 @@
 from pathlib import Path
+from types import SimpleNamespace
+from unittest.mock import patch
 
-from ncdev.cli import _doctor_report, _quickstart_text, _resolve_target_repo, build_parser
+from ncdev.cli import _doctor_report, _quickstart_text, _resolve_target_repo, build_parser, main
 
 
 def test_cli_quickstart_parses() -> None:
@@ -87,3 +89,23 @@
     (tmp_path / ".git").mkdir()
     _, report = _doctor_report(tmp_path)
     assert "git repository" in report
+
+
+def test_cli_full_reports_completed_not_passed(tmp_path: Path) -> None:
+    source = tmp_path / "requirements.md"
+    source.write_text("x")
+    printed: list[str] = []
+    state = SimpleNamespace(
+        run_id="r1",
+        status="passed",
+        completed_features=2,
+        total_features=3,
+        run_dir="/tmp/run",
+    )
+
+    with patch("ncdev.cli.run_v3_full", return_value=state):
+        with patch("ncdev.cli.console.print", side_effect=lambda *args, **kwargs: printed.append(str(args[0]))):
+            with patch("sys.argv", ["ncdev", "full", "--source", str(source), "--dry-run"]):
+                assert main() == 0
+
+    assert any("features: 2/3 completed" in line for line in printed)
diff --git a/tests/test_ncdev_v3/test_engine.py b/tests/test_ncdev_v3/test_engine.py
new file mode 100644
index 0000000000000000000000000000000000000000..d4c48cda3f6e41c3ca90e7483dc2d8578b7a7940
--- /dev/null
+++ b/tests/test_ncdev_v3/test_engine.py
@@ -0,0 +1,67 @@
+from __future__ import annotations
+
+from pathlib import Path
+from types import SimpleNamespace
+
+from ncdev.v3.engine import run_v3_full
+from ncdev.v3.models import (
+    CharterBundle,
+    FeatureQueueDoc,
+    FeatureStep,
+    StepResult,
+    StepStatus,
+    TargetProjectContract,
+    VerificationContract,
+)
+
+
+def _bundle(*features: FeatureStep) -> CharterBundle:
+    return CharterBundle(
+        contract=TargetProjectContract(project_name="proj", project_type="web"),
+        verification=VerificationContract(),
+        feature_queue=FeatureQueueDoc(project_name="proj", features=list(features)),
+    )
+
+
+def test_run_v3_full_persists_brownfield_skips_in_progress_state(tmp_path: Path, monkeypatch):
+    """State-scanner skips must show up immediately in persisted progress.
+
+    Before this fix, completed_steps/completed_features stayed at zero when
+    the scanner skipped features before the build loop ran, so a fully
+    brownfield/no-op run reported no completed work in state.json.
+    """
+    workspace = tmp_path / "ws"
+    workspace.mkdir()
+    source = workspace / "prd.md"
+    source.write_text("# PRD\n")
+    target = workspace / "target"
+    target.mkdir()
+
+    feature = FeatureStep(
+        feature_id="f1",
+        title="Already done",
+        description="",
+        acceptance_criteria=[],
+    )
+    bundle = _bundle(feature)
+
+    monkeypatch.setattr("ncdev.v3.engine.generate_charter", lambda **kwargs: (bundle, SimpleNamespace(summary=lambda: "ok")))
+    monkeypatch.setattr("ncdev.v3.engine.run_design_phase", lambda **kwargs: SimpleNamespace(skipped=True, hard_failed=False, design_doc=None))
+    monkeypatch.setattr("ncdev.v3.state_scanner.scan_completed_features", lambda target_path, features: ["f1"])
+    monkeypatch.setattr(
+        "ncdev.v3.state_scanner.build_skip_results",
+        lambda features, done_ids: [StepResult(feature_id="f1", status=StepStatus.SKIPPED)],
+    )
+
+    state = run_v3_full(
+        workspace=workspace,
+        source_path=source,
+        target_repo_path=target,
+        builder_model="claude-opus-4-6",
+    )
+
+    assert state.status == "passed"
+    assert state.completed_features == 1
+    assert len(state.completed_steps) == 1
+    assert state.completed_steps[0].status == StepStatus.SKIPPED
+
diff --git a/tests/unit/test_claude_executor.py b/tests/unit/test_claude_executor.py
index a08e209565101214bc64e0f710ac287b458bb03a..3261c2cbcac84262b510769fca4e661d2b9f008e
--- a/tests/unit/test_claude_executor.py
+++ b/tests/unit/test_claude_executor.py
@@ -294,6 +294,46 @@
     assert any("prohibited" in r.lower() for r in result.verification.failure_reasons)
 
 
+def test_legacy_prohibited_pattern_outside_touched_files_does_not_block_pass(tmp_path: Path):
+    """Post-hoc verification must stay feature-local.
+
+    A brownfield repo can contain an old TODO in some untouched file; that
+    should not fail a new clean feature, because the pre-commit hook only
+    guards staged content and the executor already scopes asset checks
+    feature-locally for the same reason.
+    """
+    target = tmp_path / "app"
+    target.mkdir()
+    _init_git(target)
+
+    # Legacy debt that predates this feature.
+    (target / "legacy.py").write_text("# TODO historical debt\n")
+    subprocess.run(["git", "add", "legacy.py"], cwd=str(target), check=True)
+    subprocess.run(["git", "commit", "-q", "-m", "feat(legacy): existing debt"],
+                   cwd=str(target), check=True)
+
+    def fake_session(prompt, **kwargs):  # noqa: ARG001
+        _seed_manifest(target, "f01-scaffold")
+        (target / "clean.py").write_text("x = 1\n")
+        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
+        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): clean"],
+                       cwd=str(target), check=True)
+        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)
+
+    bundle = _make_bundle()  # prohibited_patterns=["TODO"]
+    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):
+        result = execute_feature_claude_driven(
+            feature=_make_feature(),
+            target_path=target,
+            run_dir=tmp_path / "run",
+            charter_bundle=bundle,
+            prior_results=[],
+            project_id="myapp",
+        )
+
+    assert result.status == StepStatus.PASSED
+
+
 def test_verification_runs_backend_test_command_when_configured(tmp_path: Path):
     """New enforcement: backend_test_command actually runs, not just documented."""
     target = tmp_path / "app"

diff --git a/src/ncdev/cli.py b/src/ncdev/cli.py
index 78347ed18abd9502b64378f77fe7d52c8c01d42e..b9f4d9dd0e16042063902ff869cc2bbc5fd2d255
--- a/src/ncdev/cli.py
+++ b/src/ncdev/cli.py
@@ -373,7 +373,7 @@
             strict_deps=bool(getattr(args, "strict_deps", False)),
         )
         console.print(f"run_id={state.run_id} status={state.status}")
-        console.print(f"features: {state.completed_features}/{state.total_features} passed")
+        console.print(f"features: {state.completed_features}/{state.total_features} completed")
         console.print(f"run_dir={state.run_dir}")
         if state.status != "passed":
             return 1
diff --git a/src/ncdev/v3/claude_executor.py b/src/ncdev/v3/claude_executor.py
index 973459e5f764d4bf2d0bde198747c6949f216bd5..9fc826c2d005686dea54106495ec650aa569ce7b
--- a/src/ncdev/v3/claude_executor.py
+++ b/src/ncdev/v3/claude_executor.py
@@ -351,10 +351,13 @@
                 reasons.append(f"asset references without manifest: {missing[:5]}")
 
     # 3. Prohibited patterns (regex — treats entries in the contract as
-    #    patterns, falls back to literal match if the regex fails to compile)
+    #    patterns, falls back to literal match if the regex fails to compile).
+    #    Feature-local scope matters here for the same reason it matters for
+    #    asset manifests: one legacy TODO elsewhere in a brownfield repo should
+    #    not fail every future feature.
     patterns = bundle.verification.prohibited_patterns
     if patterns:
-        bad = _grep_for_prohibited(target_path, patterns)
+        bad = _grep_for_prohibited(target_path, patterns, touched_files=touched_files)
         if bad:
             reasons.append(f"prohibited patterns found: {bad[:5]}")
 
@@ -422,12 +425,20 @@
     return ver
 
 
-def _grep_for_prohibited(target_path: Path, patterns: list[str]) -> list[str]:
+def _grep_for_prohibited(
+    target_path: Path,
+    patterns: list[str],
+    *,
+    touched_files: list[str] | None = None,
+) -> list[str]:
     """Scan git-tracked files for prohibited patterns.
 
     Each entry is treated as a regular expression via ``re.search``. If
     a pattern fails to compile, falls back to a substring check so
     human-written entries like ``TODO`` still work.
+
+    When ``touched_files`` is provided, only scan that feature-local set.
+    This keeps brownfield legacy debt from failing unrelated future work.
     """
     compiled: list[tuple[str, re.Pattern[str] | None]] = []
     for pat in patterns:
@@ -444,10 +455,15 @@
         )
         if ls.returncode != 0:
             return []
-        files = [f for f in ls.stdout.splitlines() if f]
+        tracked_files = {f for f in ls.stdout.splitlines() if f}
     except (subprocess.TimeoutExpired, FileNotFoundError):
         return []
 
+    if touched_files is not None:
+        files = [f for f in touched_files if f in tracked_files]
+    else:
+        files = sorted(tracked_files)
+
     for f in files:
         fp = target_path / f
         try:
diff --git a/src/ncdev/v3/engine.py b/src/ncdev/v3/engine.py
index 86cebe171c78ff9d0fded0c142a6793f98ca4944..78a18f3debbfd201af46ad4254db8d29afbb8aa5
--- a/src/ncdev/v3/engine.py
+++ b/src/ncdev/v3/engine.py
@@ -207,6 +207,8 @@
 
         # Brownfield: skip features already implemented
         remaining = _filter_completed_features(target_path, features, completed)
+        _sync_progress_state(state, completed)
+        _persist_state(state, run_dir)
         console.print(f"\n[bold]Phase 5: Building {len(remaining)} features sequentially[/bold]")
 
         for feature in remaining:
@@ -231,7 +233,7 @@
                     status=StepStatus.BLOCKED,
                     error_message=reason,
                 ))
-                state.completed_steps = completed
+                _sync_progress_state(state, completed)
                 _persist_state(state, run_dir)
                 if strict_deps:
                     console.print("[red]--strict-deps set: halting run[/red]")
@@ -256,14 +258,7 @@
                 config=config,
             )
             completed.append(result)
-            state.completed_steps = completed
-            # Count PASSED + SKIPPED — both are "done from NC Dev's
-            # perspective". SKIPPED = brownfield state scanner already
-            # found them in the target repo; PASSED = built this run.
-            state.completed_features = len([
-                r for r in completed
-                if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
-            ])
+            _sync_progress_state(state, completed)
             _persist_state(state, run_dir)
 
             status_style = "green" if result.status == StepStatus.PASSED else "red"
@@ -362,3 +357,14 @@
 def _persist_state(state: V3RunState, run_dir: Path) -> None:
     run_dir.mkdir(parents=True, exist_ok=True)
     (run_dir / "state.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")
+
+
+def _sync_progress_state(state: V3RunState, completed: list[StepResult]) -> None:
+    """Keep persisted progress counters in sync with the completed list."""
+    state.completed_steps = list(completed)
+    # Count PASSED + SKIPPED — both are "done from NC Dev's perspective".
+    # SKIPPED means the brownfield state scanner found them already present;
+    # PASSED means they were built successfully during this run.
+    state.completed_features = sum(
+        1 for r in completed if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
+    )
diff --git a/tests/test_cli.py b/tests/test_cli.py
index 6e1d69ab2f720b5fd71b603de93f8d2967eb7c95..395d8c6e8ff314a3735129c59434f9c31c171365
--- a/tests/test_cli.py
+++ b/tests/test_cli.py
@@ -1,6 +1,8 @@
 from pathlib import Path
+from types import SimpleNamespace
+from unittest.mock import patch
 
-from ncdev.cli import _doctor_report, _quickstart_text, _resolve_target_repo, build_parser
+from ncdev.cli import _doctor_report, _quickstart_text, _resolve_target_repo, build_parser, main
 
 
 def test_cli_quickstart_parses() -> None:
@@ -87,3 +89,23 @@
     (tmp_path / ".git").mkdir()
     _, report = _doctor_report(tmp_path)
     assert "git repository" in report
+
+
+def test_cli_full_reports_completed_not_passed(tmp_path: Path) -> None:
+    source = tmp_path / "requirements.md"
+    source.write_text("x")
+    printed: list[str] = []
+    state = SimpleNamespace(
+        run_id="r1",
+        status="passed",
+        completed_features=2,
+        total_features=3,
+        run_dir="/tmp/run",
+    )
+
+    with patch("ncdev.cli.run_v3_full", return_value=state):
+        with patch("ncdev.cli.console.print", side_effect=lambda *args, **kwargs: printed.append(str(args[0]))):
+            with patch("sys.argv", ["ncdev", "full", "--source", str(source), "--dry-run"]):
+                assert main() == 0
+
+    assert any("features: 2/3 completed" in line for line in printed)
diff --git a/tests/test_ncdev_v3/test_engine.py b/tests/test_ncdev_v3/test_engine.py
new file mode 100644
index 0000000000000000000000000000000000000000..d4c48cda3f6e41c3ca90e7483dc2d8578b7a7940
--- /dev/null
+++ b/tests/test_ncdev_v3/test_engine.py
@@ -0,0 +1,67 @@
+from __future__ import annotations
+
+from pathlib import Path
+from types import SimpleNamespace
+
+from ncdev.v3.engine import run_v3_full
+from ncdev.v3.models import (
+    CharterBundle,
+    FeatureQueueDoc,
+    FeatureStep,
+    StepResult,
+    StepStatus,
+    TargetProjectContract,
+    VerificationContract,
+)
+
+
+def _bundle(*features: FeatureStep) -> CharterBundle:
+    return CharterBundle(
+        contract=TargetProjectContract(project_name="proj", project_type="web"),
+        verification=VerificationContract(),
+        feature_queue=FeatureQueueDoc(project_name="proj", features=list(features)),
+    )
+
+
+def test_run_v3_full_persists_brownfield_skips_in_progress_state(tmp_path: Path, monkeypatch):
+    """State-scanner skips must show up immediately in persisted progress.
+
+    Before this fix, completed_steps/completed_features stayed at zero when
+    the scanner skipped features before the build loop ran, so a fully
+    brownfield/no-op run reported no completed work in state.json.
+    """
+    workspace = tmp_path / "ws"
+    workspace.mkdir()
+    source = workspace / "prd.md"
+    source.write_text("# PRD\n")
+    target = workspace / "target"
+    target.mkdir()
+
+    feature = FeatureStep(
+        feature_id="f1",
+        title="Already done",
+        description="",
+        acceptance_criteria=[],
+    )
+    bundle = _bundle(feature)
+
+    monkeypatch.setattr("ncdev.v3.engine.generate_charter", lambda **kwargs: (bundle, SimpleNamespace(summary=lambda: "ok")))
+    monkeypatch.setattr("ncdev.v3.engine.run_design_phase", lambda **kwargs: SimpleNamespace(skipped=True, hard_failed=False, design_doc=None))
+    monkeypatch.setattr("ncdev.v3.state_scanner.scan_completed_features", lambda target_path, features: ["f1"])
+    monkeypatch.setattr(
+        "ncdev.v3.state_scanner.build_skip_results",
+        lambda features, done_ids: [StepResult(feature_id="f1", status=StepStatus.SKIPPED)],
+    )
+
+    state = run_v3_full(
+        workspace=workspace,
+        source_path=source,
+        target_repo_path=target,
+        builder_model="claude-opus-4-6",
+    )
+
+    assert state.status == "passed"
+    assert state.completed_features == 1
+    assert len(state.completed_steps) == 1
+    assert state.completed_steps[0].status == StepStatus.SKIPPED
+
diff --git a/tests/unit/test_claude_executor.py b/tests/unit/test_claude_executor.py
index a08e209565101214bc64e0f710ac287b458bb03a..3261c2cbcac84262b510769fca4e661d2b9f008e
--- a/tests/unit/test_claude_executor.py
+++ b/tests/unit/test_claude_executor.py
@@ -294,6 +294,46 @@
     assert any("prohibited" in r.lower() for r in result.verification.failure_reasons)
 
 
+def test_legacy_prohibited_pattern_outside_touched_files_does_not_block_pass(tmp_path: Path):
+    """Post-hoc verification must stay feature-local.
+
+    A brownfield repo can contain an old TODO in some untouched file; that
+    should not fail a new clean feature, because the pre-commit hook only
+    guards staged content and the executor already scopes asset checks
+    feature-locally for the same reason.
+    """
+    target = tmp_path / "app"
+    target.mkdir()
+    _init_git(target)
+
+    # Legacy debt that predates this feature.
+    (target / "legacy.py").write_text("# TODO historical debt\n")
+    subprocess.run(["git", "add", "legacy.py"], cwd=str(target), check=True)
+    subprocess.run(["git", "commit", "-q", "-m", "feat(legacy): existing debt"],
+                   cwd=str(target), check=True)
+
+    def fake_session(prompt, **kwargs):  # noqa: ARG001
+        _seed_manifest(target, "f01-scaffold")
+        (target / "clean.py").write_text("x = 1\n")
+        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
+        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): clean"],
+                       cwd=str(target), check=True)
+        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)
+
+    bundle = _make_bundle()  # prohibited_patterns=["TODO"]
+    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):
+        result = execute_feature_claude_driven(
+            feature=_make_feature(),
+            target_path=target,
+            run_dir=tmp_path / "run",
+            charter_bundle=bundle,
+            prior_results=[],
+            project_id="myapp",
+        )
+
+    assert result.status == StepStatus.PASSED
+
+
 def test_verification_runs_backend_test_command_when_configured(tmp_path: Path):
     """New enforcement: backend_test_command actually runs, not just documented."""
     target = tmp_path / "app"

codex
The first patch set is in. I’m running the new and adjacent tests now before I touch anything else; if they shake out another seam bug, I’ll fix it before moving to the full suite.
exec
/bin/zsh -lc 'git diff -- src/ncdev/v3/claude_executor.py src/ncdev/v3/engine.py src/ncdev/cli.py tests/unit/test_claude_executor.py tests/test_ncdev_v3/test_engine.py tests/test_cli.py' in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
diff --git a/src/ncdev/cli.py b/src/ncdev/cli.py
index 78347ed..b9f4d9d 100644
--- a/src/ncdev/cli.py
+++ b/src/ncdev/cli.py
@@ -373,7 +373,7 @@ def main() -> int:
             strict_deps=bool(getattr(args, "strict_deps", False)),
         )
         console.print(f"run_id={state.run_id} status={state.status}")
-        console.print(f"features: {state.completed_features}/{state.total_features} passed")
+        console.print(f"features: {state.completed_features}/{state.total_features} completed")
         console.print(f"run_dir={state.run_dir}")
         if state.status != "passed":
             return 1
diff --git a/src/ncdev/v3/claude_executor.py b/src/ncdev/v3/claude_executor.py
index 973459e..9fc826c 100644
--- a/src/ncdev/v3/claude_executor.py
+++ b/src/ncdev/v3/claude_executor.py
@@ -351,10 +351,13 @@ def _post_session_verification(
                 reasons.append(f"asset references without manifest: {missing[:5]}")
 
     # 3. Prohibited patterns (regex — treats entries in the contract as
-    #    patterns, falls back to literal match if the regex fails to compile)
+    #    patterns, falls back to literal match if the regex fails to compile).
+    #    Feature-local scope matters here for the same reason it matters for
+    #    asset manifests: one legacy TODO elsewhere in a brownfield repo should
+    #    not fail every future feature.
     patterns = bundle.verification.prohibited_patterns
     if patterns:
-        bad = _grep_for_prohibited(target_path, patterns)
+        bad = _grep_for_prohibited(target_path, patterns, touched_files=touched_files)
         if bad:
             reasons.append(f"prohibited patterns found: {bad[:5]}")
 
@@ -422,12 +425,20 @@ def _post_session_verification(
     return ver
 
 
-def _grep_for_prohibited(target_path: Path, patterns: list[str]) -> list[str]:
+def _grep_for_prohibited(
+    target_path: Path,
+    patterns: list[str],
+    *,
+    touched_files: list[str] | None = None,
+) -> list[str]:
     """Scan git-tracked files for prohibited patterns.
 
     Each entry is treated as a regular expression via ``re.search``. If
     a pattern fails to compile, falls back to a substring check so
     human-written entries like ``TODO`` still work.
+
+    When ``touched_files`` is provided, only scan that feature-local set.
+    This keeps brownfield legacy debt from failing unrelated future work.
     """
     compiled: list[tuple[str, re.Pattern[str] | None]] = []
     for pat in patterns:
@@ -444,10 +455,15 @@ def _grep_for_prohibited(target_path: Path, patterns: list[str]) -> list[str]:
         )
         if ls.returncode != 0:
             return []
-        files = [f for f in ls.stdout.splitlines() if f]
+        tracked_files = {f for f in ls.stdout.splitlines() if f}
     except (subprocess.TimeoutExpired, FileNotFoundError):
         return []
 
+    if touched_files is not None:
+        files = [f for f in touched_files if f in tracked_files]
+    else:
+        files = sorted(tracked_files)
+
     for f in files:
         fp = target_path / f
         try:
diff --git a/src/ncdev/v3/engine.py b/src/ncdev/v3/engine.py
index 86cebe1..78a18f3 100644
--- a/src/ncdev/v3/engine.py
+++ b/src/ncdev/v3/engine.py
@@ -207,6 +207,8 @@ def run_v3_full(
 
         # Brownfield: skip features already implemented
         remaining = _filter_completed_features(target_path, features, completed)
+        _sync_progress_state(state, completed)
+        _persist_state(state, run_dir)
         console.print(f"\n[bold]Phase 5: Building {len(remaining)} features sequentially[/bold]")
 
         for feature in remaining:
@@ -231,7 +233,7 @@ def run_v3_full(
                     status=StepStatus.BLOCKED,
                     error_message=reason,
                 ))
-                state.completed_steps = completed
+                _sync_progress_state(state, completed)
                 _persist_state(state, run_dir)
                 if strict_deps:
                     console.print("[red]--strict-deps set: halting run[/red]")
@@ -256,14 +258,7 @@ def run_v3_full(
                 config=config,
             )
             completed.append(result)
-            state.completed_steps = completed
-            # Count PASSED + SKIPPED — both are "done from NC Dev's
-            # perspective". SKIPPED = brownfield state scanner already
-            # found them in the target repo; PASSED = built this run.
-            state.completed_features = len([
-                r for r in completed
-                if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
-            ])
+            _sync_progress_state(state, completed)
             _persist_state(state, run_dir)
 
             status_style = "green" if result.status == StepStatus.PASSED else "red"
@@ -362,3 +357,14 @@ def _print_summary_table(completed: list[StepResult]) -> None:
 def _persist_state(state: V3RunState, run_dir: Path) -> None:
     run_dir.mkdir(parents=True, exist_ok=True)
     (run_dir / "state.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")
+
+
+def _sync_progress_state(state: V3RunState, completed: list[StepResult]) -> None:
+    """Keep persisted progress counters in sync with the completed list."""
+    state.completed_steps = list(completed)
+    # Count PASSED + SKIPPED — both are "done from NC Dev's perspective".
+    # SKIPPED means the brownfield state scanner found them already present;
+    # PASSED means they were built successfully during this run.
+    state.completed_features = sum(
+        1 for r in completed if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
+    )
diff --git a/tests/test_cli.py b/tests/test_cli.py
index 6e1d69a..395d8c6 100644
--- a/tests/test_cli.py
+++ b/tests/test_cli.py
@@ -1,6 +1,8 @@
 from pathlib import Path
+from types import SimpleNamespace
+from unittest.mock import patch
 
-from ncdev.cli import _doctor_report, _quickstart_text, _resolve_target_repo, build_parser
+from ncdev.cli import _doctor_report, _quickstart_text, _resolve_target_repo, build_parser, main
 
 
 def test_cli_quickstart_parses() -> None:
@@ -87,3 +89,23 @@ def test_doctor_report_detects_git_repo(tmp_path: Path) -> None:
     (tmp_path / ".git").mkdir()
     _, report = _doctor_report(tmp_path)
     assert "git repository" in report
+
+
+def test_cli_full_reports_completed_not_passed(tmp_path: Path) -> None:
+    source = tmp_path / "requirements.md"
+    source.write_text("x")
+    printed: list[str] = []
+    state = SimpleNamespace(
+        run_id="r1",
+        status="passed",
+        completed_features=2,
+        total_features=3,
+        run_dir="/tmp/run",
+    )
+
+    with patch("ncdev.cli.run_v3_full", return_value=state):
+        with patch("ncdev.cli.console.print", side_effect=lambda *args, **kwargs: printed.append(str(args[0]))):
+            with patch("sys.argv", ["ncdev", "full", "--source", str(source), "--dry-run"]):
+                assert main() == 0
+
+    assert any("features: 2/3 completed" in line for line in printed)
diff --git a/tests/unit/test_claude_executor.py b/tests/unit/test_claude_executor.py
index a08e209..3261c2c 100644
--- a/tests/unit/test_claude_executor.py
+++ b/tests/unit/test_claude_executor.py
@@ -294,6 +294,46 @@ def test_prohibited_patterns_block_pass(tmp_path: Path):
     assert any("prohibited" in r.lower() for r in result.verification.failure_reasons)
 
 
+def test_legacy_prohibited_pattern_outside_touched_files_does_not_block_pass(tmp_path: Path):
+    """Post-hoc verification must stay feature-local.
+
+    A brownfield repo can contain an old TODO in some untouched file; that
+    should not fail a new clean feature, because the pre-commit hook only
+    guards staged content and the executor already scopes asset checks
+    feature-locally for the same reason.
+    """
+    target = tmp_path / "app"
+    target.mkdir()
+    _init_git(target)
+
+    # Legacy debt that predates this feature.
+    (target / "legacy.py").write_text("# TODO historical debt\n")
+    subprocess.run(["git", "add", "legacy.py"], cwd=str(target), check=True)
+    subprocess.run(["git", "commit", "-q", "-m", "feat(legacy): existing debt"],
+                   cwd=str(target), check=True)
+
+    def fake_session(prompt, **kwargs):  # noqa: ARG001
+        _seed_manifest(target, "f01-scaffold")
+        (target / "clean.py").write_text("x = 1\n")
+        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
+        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): clean"],
+                       cwd=str(target), check=True)
+        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)
+
+    bundle = _make_bundle()  # prohibited_patterns=["TODO"]
+    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):
+        result = execute_feature_claude_driven(
+            feature=_make_feature(),
+            target_path=target,
+            run_dir=tmp_path / "run",
+            charter_bundle=bundle,
+            prior_results=[],
+            project_id="myapp",
+        )
+
+    assert result.status == StepStatus.PASSED
+
+
 def test_verification_runs_backend_test_command_when_configured(tmp_path: Path):
     """New enforcement: backend_test_command actually runs, not just documented."""
     target = tmp_path / "app"

exec
/bin/zsh -lc 'python3 -m pytest -q tests/unit/test_claude_executor.py tests/test_ncdev_v3/test_engine.py tests/test_cli.py' in /Users/nrupal/dev/yensi/dev/nc-dev-system
diff --git a/src/ncdev/cli.py b/src/ncdev/cli.py
index 78347ed18abd9502b64378f77fe7d52c8c01d42e..b9f4d9dd0e16042063902ff869cc2bbc5fd2d255
--- a/src/ncdev/cli.py
+++ b/src/ncdev/cli.py
@@ -373,7 +373,7 @@
             strict_deps=bool(getattr(args, "strict_deps", False)),
         )
         console.print(f"run_id={state.run_id} status={state.status}")
-        console.print(f"features: {state.completed_features}/{state.total_features} passed")
+        console.print(f"features: {state.completed_features}/{state.total_features} completed")
         console.print(f"run_dir={state.run_dir}")
         if state.status != "passed":
             return 1
diff --git a/src/ncdev/v3/claude_executor.py b/src/ncdev/v3/claude_executor.py
index 973459e5f764d4bf2d0bde198747c6949f216bd5..9fc826c2d005686dea54106495ec650aa569ce7b
--- a/src/ncdev/v3/claude_executor.py
+++ b/src/ncdev/v3/claude_executor.py
@@ -351,10 +351,13 @@
                 reasons.append(f"asset references without manifest: {missing[:5]}")
 
     # 3. Prohibited patterns (regex — treats entries in the contract as
-    #    patterns, falls back to literal match if the regex fails to compile)
+    #    patterns, falls back to literal match if the regex fails to compile).
+    #    Feature-local scope matters here for the same reason it matters for
+    #    asset manifests: one legacy TODO elsewhere in a brownfield repo should
+    #    not fail every future feature.
     patterns = bundle.verification.prohibited_patterns
     if patterns:
-        bad = _grep_for_prohibited(target_path, patterns)
+        bad = _grep_for_prohibited(target_path, patterns, touched_files=touched_files)
         if bad:
             reasons.append(f"prohibited patterns found: {bad[:5]}")
 
@@ -422,12 +425,20 @@
     return ver
 
 
-def _grep_for_prohibited(target_path: Path, patterns: list[str]) -> list[str]:
+def _grep_for_prohibited(
+    target_path: Path,
+    patterns: list[str],
+    *,
+    touched_files: list[str] | None = None,
+) -> list[str]:
     """Scan git-tracked files for prohibited patterns.
 
     Each entry is treated as a regular expression via ``re.search``. If
     a pattern fails to compile, falls back to a substring check so
     human-written entries like ``TODO`` still work.
+
+    When ``touched_files`` is provided, only scan that feature-local set.
+    This keeps brownfield legacy debt from failing unrelated future work.
     """
     compiled: list[tuple[str, re.Pattern[str] | None]] = []
     for pat in patterns:
@@ -444,10 +455,15 @@
         )
         if ls.returncode != 0:
             return []
-        files = [f for f in ls.stdout.splitlines() if f]
+        tracked_files = {f for f in ls.stdout.splitlines() if f}
     except (subprocess.TimeoutExpired, FileNotFoundError):
         return []
 
+    if touched_files is not None:
+        files = [f for f in touched_files if f in tracked_files]
+    else:
+        files = sorted(tracked_files)
+
     for f in files:
         fp = target_path / f
         try:
diff --git a/src/ncdev/v3/engine.py b/src/ncdev/v3/engine.py
index 86cebe171c78ff9d0fded0c142a6793f98ca4944..78a18f3debbfd201af46ad4254db8d29afbb8aa5
--- a/src/ncdev/v3/engine.py
+++ b/src/ncdev/v3/engine.py
@@ -207,6 +207,8 @@
 
         # Brownfield: skip features already implemented
         remaining = _filter_completed_features(target_path, features, completed)
+        _sync_progress_state(state, completed)
+        _persist_state(state, run_dir)
         console.print(f"\n[bold]Phase 5: Building {len(remaining)} features sequentially[/bold]")
 
         for feature in remaining:
@@ -231,7 +233,7 @@
                     status=StepStatus.BLOCKED,
                     error_message=reason,
                 ))
-                state.completed_steps = completed
+                _sync_progress_state(state, completed)
                 _persist_state(state, run_dir)
                 if strict_deps:
                     console.print("[red]--strict-deps set: halting run[/red]")
@@ -256,14 +258,7 @@
                 config=config,
             )
             completed.append(result)
-            state.completed_steps = completed
-            # Count PASSED + SKIPPED — both are "done from NC Dev's
-            # perspective". SKIPPED = brownfield state scanner already
-            # found them in the target repo; PASSED = built this run.
-            state.completed_features = len([
-                r for r in completed
-                if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
-            ])
+            _sync_progress_state(state, completed)
             _persist_state(state, run_dir)
 
             status_style = "green" if result.status == StepStatus.PASSED else "red"
@@ -362,3 +357,14 @@
 def _persist_state(state: V3RunState, run_dir: Path) -> None:
     run_dir.mkdir(parents=True, exist_ok=True)
     (run_dir / "state.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")
+
+
+def _sync_progress_state(state: V3RunState, completed: list[StepResult]) -> None:
+    """Keep persisted progress counters in sync with the completed list."""
+    state.completed_steps = list(completed)
+    # Count PASSED + SKIPPED — both are "done from NC Dev's perspective".
+    # SKIPPED means the brownfield state scanner found them already present;
+    # PASSED means they were built successfully during this run.
+    state.completed_features = sum(
+        1 for r in completed if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
+    )
diff --git a/tests/test_cli.py b/tests/test_cli.py
index 6e1d69ab2f720b5fd71b603de93f8d2967eb7c95..395d8c6e8ff314a3735129c59434f9c31c171365
--- a/tests/test_cli.py
+++ b/tests/test_cli.py
@@ -1,6 +1,8 @@
 from pathlib import Path
+from types import SimpleNamespace
+from unittest.mock import patch
 
-from ncdev.cli import _doctor_report, _quickstart_text, _resolve_target_repo, build_parser
+from ncdev.cli import _doctor_report, _quickstart_text, _resolve_target_repo, build_parser, main
 
 
 def test_cli_quickstart_parses() -> None:
@@ -87,3 +89,23 @@
     (tmp_path / ".git").mkdir()
     _, report = _doctor_report(tmp_path)
     assert "git repository" in report
+
+
+def test_cli_full_reports_completed_not_passed(tmp_path: Path) -> None:
+    source = tmp_path / "requirements.md"
+    source.write_text("x")
+    printed: list[str] = []
+    state = SimpleNamespace(
+        run_id="r1",
+        status="passed",
+        completed_features=2,
+        total_features=3,
+        run_dir="/tmp/run",
+    )
+
+    with patch("ncdev.cli.run_v3_full", return_value=state):
+        with patch("ncdev.cli.console.print", side_effect=lambda *args, **kwargs: printed.append(str(args[0]))):
+            with patch("sys.argv", ["ncdev", "full", "--source", str(source), "--dry-run"]):
+                assert main() == 0
+
+    assert any("features: 2/3 completed" in line for line in printed)
diff --git a/tests/test_ncdev_v3/test_engine.py b/tests/test_ncdev_v3/test_engine.py
new file mode 100644
index 0000000000000000000000000000000000000000..d4c48cda3f6e41c3ca90e7483dc2d8578b7a7940
--- /dev/null
+++ b/tests/test_ncdev_v3/test_engine.py
@@ -0,0 +1,67 @@
+from __future__ import annotations
+
+from pathlib import Path
+from types import SimpleNamespace
+
+from ncdev.v3.engine import run_v3_full
+from ncdev.v3.models import (
+    CharterBundle,
+    FeatureQueueDoc,
+    FeatureStep,
+    StepResult,
+    StepStatus,
+    TargetProjectContract,
+    VerificationContract,
+)
+
+
+def _bundle(*features: FeatureStep) -> CharterBundle:
+    return CharterBundle(
+        contract=TargetProjectContract(project_name="proj", project_type="web"),
+        verification=VerificationContract(),
+        feature_queue=FeatureQueueDoc(project_name="proj", features=list(features)),
+    )
+
+
+def test_run_v3_full_persists_brownfield_skips_in_progress_state(tmp_path: Path, monkeypatch):
+    """State-scanner skips must show up immediately in persisted progress.
+
+    Before this fix, completed_steps/completed_features stayed at zero when
+    the scanner skipped features before the build loop ran, so a fully
+    brownfield/no-op run reported no completed work in state.json.
+    """
+    workspace = tmp_path / "ws"
+    workspace.mkdir()
+    source = workspace / "prd.md"
+    source.write_text("# PRD\n")
+    target = workspace / "target"
+    target.mkdir()
+
+    feature = FeatureStep(
+        feature_id="f1",
+        title="Already done",
+        description="",
+        acceptance_criteria=[],
+    )
+    bundle = _bundle(feature)
+
+    monkeypatch.setattr("ncdev.v3.engine.generate_charter", lambda **kwargs: (bundle, SimpleNamespace(summary=lambda: "ok")))
+    monkeypatch.setattr("ncdev.v3.engine.run_design_phase", lambda **kwargs: SimpleNamespace(skipped=True, hard_failed=False, design_doc=None))
+    monkeypatch.setattr("ncdev.v3.state_scanner.scan_completed_features", lambda target_path, features: ["f1"])
+    monkeypatch.setattr(
+        "ncdev.v3.state_scanner.build_skip_results",
+        lambda features, done_ids: [StepResult(feature_id="f1", status=StepStatus.SKIPPED)],
+    )
+
+    state = run_v3_full(
+        workspace=workspace,
+        source_path=source,
+        target_repo_path=target,
+        builder_model="claude-opus-4-6",
+    )
+
+    assert state.status == "passed"
+    assert state.completed_features == 1
+    assert len(state.completed_steps) == 1
+    assert state.completed_steps[0].status == StepStatus.SKIPPED
+
diff --git a/tests/unit/test_claude_executor.py b/tests/unit/test_claude_executor.py
index a08e209565101214bc64e0f710ac287b458bb03a..3261c2cbcac84262b510769fca4e661d2b9f008e
--- a/tests/unit/test_claude_executor.py
+++ b/tests/unit/test_claude_executor.py
@@ -294,6 +294,46 @@
     assert any("prohibited" in r.lower() for r in result.verification.failure_reasons)
 
 
+def test_legacy_prohibited_pattern_outside_touched_files_does_not_block_pass(tmp_path: Path):
+    """Post-hoc verification must stay feature-local.
+
+    A brownfield repo can contain an old TODO in some untouched file; that
+    should not fail a new clean feature, because the pre-commit hook only
+    guards staged content and the executor already scopes asset checks
+    feature-locally for the same reason.
+    """
+    target = tmp_path / "app"
+    target.mkdir()
+    _init_git(target)
+
+    # Legacy debt that predates this feature.
+    (target / "legacy.py").write_text("# TODO historical debt\n")
+    subprocess.run(["git", "add", "legacy.py"], cwd=str(target), check=True)
+    subprocess.run(["git", "commit", "-q", "-m", "feat(legacy): existing debt"],
+                   cwd=str(target), check=True)
+
+    def fake_session(prompt, **kwargs):  # noqa: ARG001
+        _seed_manifest(target, "f01-scaffold")
+        (target / "clean.py").write_text("x = 1\n")
+        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
+        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): clean"],
+                       cwd=str(target), check=True)
+        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)
+
+    bundle = _make_bundle()  # prohibited_patterns=["TODO"]
+    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):
+        result = execute_feature_claude_driven(
+            feature=_make_feature(),
+            target_path=target,
+            run_dir=tmp_path / "run",
+            charter_bundle=bundle,
+            prior_results=[],
+            project_id="myapp",
+        )
+
+    assert result.status == StepStatus.PASSED
+
+
 def test_verification_runs_backend_test_command_when_configured(tmp_path: Path):
     """New enforcement: backend_test_command actually runs, not just documented."""
     target = tmp_path / "app"

diff --git a/src/ncdev/cli.py b/src/ncdev/cli.py
index 78347ed18abd9502b64378f77fe7d52c8c01d42e..b9f4d9dd0e16042063902ff869cc2bbc5fd2d255
--- a/src/ncdev/cli.py
+++ b/src/ncdev/cli.py
@@ -373,7 +373,7 @@
             strict_deps=bool(getattr(args, "strict_deps", False)),
         )
         console.print(f"run_id={state.run_id} status={state.status}")
-        console.print(f"features: {state.completed_features}/{state.total_features} passed")
+        console.print(f"features: {state.completed_features}/{state.total_features} completed")
         console.print(f"run_dir={state.run_dir}")
         if state.status != "passed":
             return 1
diff --git a/src/ncdev/v3/claude_executor.py b/src/ncdev/v3/claude_executor.py
index 973459e5f764d4bf2d0bde198747c6949f216bd5..9fc826c2d005686dea54106495ec650aa569ce7b
--- a/src/ncdev/v3/claude_executor.py
+++ b/src/ncdev/v3/claude_executor.py
@@ -351,10 +351,13 @@
                 reasons.append(f"asset references without manifest: {missing[:5]}")
 
     # 3. Prohibited patterns (regex — treats entries in the contract as
-    #    patterns, falls back to literal match if the regex fails to compile)
+    #    patterns, falls back to literal match if the regex fails to compile).
+    #    Feature-local scope matters here for the same reason it matters for
+    #    asset manifests: one legacy TODO elsewhere in a brownfield repo should
+    #    not fail every future feature.
     patterns = bundle.verification.prohibited_patterns
     if patterns:
-        bad = _grep_for_prohibited(target_path, patterns)
+        bad = _grep_for_prohibited(target_path, patterns, touched_files=touched_files)
         if bad:
             reasons.append(f"prohibited patterns found: {bad[:5]}")
 
@@ -422,12 +425,20 @@
     return ver
 
 
-def _grep_for_prohibited(target_path: Path, patterns: list[str]) -> list[str]:
+def _grep_for_prohibited(
+    target_path: Path,
+    patterns: list[str],
+    *,
+    touched_files: list[str] | None = None,
+) -> list[str]:
     """Scan git-tracked files for prohibited patterns.
 
     Each entry is treated as a regular expression via ``re.search``. If
     a pattern fails to compile, falls back to a substring check so
     human-written entries like ``TODO`` still work.
+
+    When ``touched_files`` is provided, only scan that feature-local set.
+    This keeps brownfield legacy debt from failing unrelated future work.
     """
     compiled: list[tuple[str, re.Pattern[str] | None]] = []
     for pat in patterns:
@@ -444,10 +455,15 @@
         )
         if ls.returncode != 0:
             return []
-        files = [f for f in ls.stdout.splitlines() if f]
+        tracked_files = {f for f in ls.stdout.splitlines() if f}
     except (subprocess.TimeoutExpired, FileNotFoundError):
         return []
 
+    if touched_files is not None:
+        files = [f for f in touched_files if f in tracked_files]
+    else:
+        files = sorted(tracked_files)
+
     for f in files:
         fp = target_path / f
         try:
diff --git a/src/ncdev/v3/engine.py b/src/ncdev/v3/engine.py
index 86cebe171c78ff9d0fded0c142a6793f98ca4944..78a18f3debbfd201af46ad4254db8d29afbb8aa5
--- a/src/ncdev/v3/engine.py
+++ b/src/ncdev/v3/engine.py
@@ -207,6 +207,8 @@
 
         # Brownfield: skip features already implemented
         remaining = _filter_completed_features(target_path, features, completed)
+        _sync_progress_state(state, completed)
+        _persist_state(state, run_dir)
         console.print(f"\n[bold]Phase 5: Building {len(remaining)} features sequentially[/bold]")
 
         for feature in remaining:
@@ -231,7 +233,7 @@
                     status=StepStatus.BLOCKED,
                     error_message=reason,
                 ))
-                state.completed_steps = completed
+                _sync_progress_state(state, completed)
                 _persist_state(state, run_dir)
                 if strict_deps:
                     console.print("[red]--strict-deps set: halting run[/red]")
@@ -256,14 +258,7 @@
                 config=config,
             )
             completed.append(result)
-            state.completed_steps = completed
-            # Count PASSED + SKIPPED — both are "done from NC Dev's
-            # perspective". SKIPPED = brownfield state scanner already
-            # found them in the target repo; PASSED = built this run.
-            state.completed_features = len([
-                r for r in completed
-                if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
-            ])
+            _sync_progress_state(state, completed)
             _persist_state(state, run_dir)
 
             status_style = "green" if result.status == StepStatus.PASSED else "red"
@@ -362,3 +357,14 @@
 def _persist_state(state: V3RunState, run_dir: Path) -> None:
     run_dir.mkdir(parents=True, exist_ok=True)
     (run_dir / "state.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")
+
+
+def _sync_progress_state(state: V3RunState, completed: list[StepResult]) -> None:
+    """Keep persisted progress counters in sync with the completed list."""
+    state.completed_steps = list(completed)
+    # Count PASSED + SKIPPED — both are "done from NC Dev's perspective".
+    # SKIPPED means the brownfield state scanner found them already present;
+    # PASSED means they were built successfully during this run.
+    state.completed_features = sum(
+        1 for r in completed if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
+    )
diff --git a/tests/test_cli.py b/tests/test_cli.py
index 6e1d69ab2f720b5fd71b603de93f8d2967eb7c95..395d8c6e8ff314a3735129c59434f9c31c171365
--- a/tests/test_cli.py
+++ b/tests/test_cli.py
@@ -1,6 +1,8 @@
 from pathlib import Path
+from types import SimpleNamespace
+from unittest.mock import patch
 
-from ncdev.cli import _doctor_report, _quickstart_text, _resolve_target_repo, build_parser
+from ncdev.cli import _doctor_report, _quickstart_text, _resolve_target_repo, build_parser, main
 
 
 def test_cli_quickstart_parses() -> None:
@@ -87,3 +89,23 @@
     (tmp_path / ".git").mkdir()
     _, report = _doctor_report(tmp_path)
     assert "git repository" in report
+
+
+def test_cli_full_reports_completed_not_passed(tmp_path: Path) -> None:
+    source = tmp_path / "requirements.md"
+    source.write_text("x")
+    printed: list[str] = []
+    state = SimpleNamespace(
+        run_id="r1",
+        status="passed",
+        completed_features=2,
+        total_features=3,
+        run_dir="/tmp/run",
+    )
+
+    with patch("ncdev.cli.run_v3_full", return_value=state):
+        with patch("ncdev.cli.console.print", side_effect=lambda *args, **kwargs: printed.append(str(args[0]))):
+            with patch("sys.argv", ["ncdev", "full", "--source", str(source), "--dry-run"]):
+                assert main() == 0
+
+    assert any("features: 2/3 completed" in line for line in printed)
diff --git a/tests/test_ncdev_v3/test_engine.py b/tests/test_ncdev_v3/test_engine.py
new file mode 100644
index 0000000000000000000000000000000000000000..d4c48cda3f6e41c3ca90e7483dc2d8578b7a7940
--- /dev/null
+++ b/tests/test_ncdev_v3/test_engine.py
@@ -0,0 +1,67 @@
+from __future__ import annotations
+
+from pathlib import Path
+from types import SimpleNamespace
+
+from ncdev.v3.engine import run_v3_full
+from ncdev.v3.models import (
+    CharterBundle,
+    FeatureQueueDoc,
+    FeatureStep,
+    StepResult,
+    StepStatus,
+    TargetProjectContract,
+    VerificationContract,
+)
+
+
+def _bundle(*features: FeatureStep) -> CharterBundle:
+    return CharterBundle(
+        contract=TargetProjectContract(project_name="proj", project_type="web"),
+        verification=VerificationContract(),
+        feature_queue=FeatureQueueDoc(project_name="proj", features=list(features)),
+    )
+
+
+def test_run_v3_full_persists_brownfield_skips_in_progress_state(tmp_path: Path, monkeypatch):
+    """State-scanner skips must show up immediately in persisted progress.
+
+    Before this fix, completed_steps/completed_features stayed at zero when
+    the scanner skipped features before the build loop ran, so a fully
+    brownfield/no-op run reported no completed work in state.json.
+    """
+    workspace = tmp_path / "ws"
+    workspace.mkdir()
+    source = workspace / "prd.md"
+    source.write_text("# PRD\n")
+    target = workspace / "target"
+    target.mkdir()
+
+    feature = FeatureStep(
+        feature_id="f1",
+        title="Already done",
+        description="",
+        acceptance_criteria=[],
+    )
+    bundle = _bundle(feature)
+
+    monkeypatch.setattr("ncdev.v3.engine.generate_charter", lambda **kwargs: (bundle, SimpleNamespace(summary=lambda: "ok")))
+    monkeypatch.setattr("ncdev.v3.engine.run_design_phase", lambda **kwargs: SimpleNamespace(skipped=True, hard_failed=False, design_doc=None))
+    monkeypatch.setattr("ncdev.v3.state_scanner.scan_completed_features", lambda target_path, features: ["f1"])
+    monkeypatch.setattr(
+        "ncdev.v3.state_scanner.build_skip_results",
+        lambda features, done_ids: [StepResult(feature_id="f1", status=StepStatus.SKIPPED)],
+    )
+
+    state = run_v3_full(
+        workspace=workspace,
+        source_path=source,
+        target_repo_path=target,
+        builder_model="claude-opus-4-6",
+    )
+
+    assert state.status == "passed"
+    assert state.completed_features == 1
+    assert len(state.completed_steps) == 1
+    assert state.completed_steps[0].status == StepStatus.SKIPPED
+
diff --git a/tests/unit/test_claude_executor.py b/tests/unit/test_claude_executor.py
index a08e209565101214bc64e0f710ac287b458bb03a..3261c2cbcac84262b510769fca4e661d2b9f008e
--- a/tests/unit/test_claude_executor.py
+++ b/tests/unit/test_claude_executor.py
@@ -294,6 +294,46 @@
     assert any("prohibited" in r.lower() for r in result.verification.failure_reasons)
 
 
+def test_legacy_prohibited_pattern_outside_touched_files_does_not_block_pass(tmp_path: Path):
+    """Post-hoc verification must stay feature-local.
+
+    A brownfield repo can contain an old TODO in some untouched file; that
+    should not fail a new clean feature, because the pre-commit hook only
+    guards staged content and the executor already scopes asset checks
+    feature-locally for the same reason.
+    """
+    target = tmp_path / "app"
+    target.mkdir()
+    _init_git(target)
+
+    # Legacy debt that predates this feature.
+    (target / "legacy.py").write_text("# TODO historical debt\n")
+    subprocess.run(["git", "add", "legacy.py"], cwd=str(target), check=True)
+    subprocess.run(["git", "commit", "-q", "-m", "feat(legacy): existing debt"],
+                   cwd=str(target), check=True)
+
+    def fake_session(prompt, **kwargs):  # noqa: ARG001
+        _seed_manifest(target, "f01-scaffold")
+        (target / "clean.py").write_text("x = 1\n")
+        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
+        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): clean"],
+                       cwd=str(target), check=True)
+        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)
+
+    bundle = _make_bundle()  # prohibited_patterns=["TODO"]
+    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):
+        result = execute_feature_claude_driven(
+            feature=_make_feature(),
+            target_path=target,
+            run_dir=tmp_path / "run",
+            charter_bundle=bundle,
+            prior_results=[],
+            project_id="myapp",
+        )
+
+    assert result.status == StepStatus.PASSED
+
+
 def test_verification_runs_backend_test_command_when_configured(tmp_path: Path):
     """New enforcement: backend_test_command actually runs, not just documented."""
     target = tmp_path / "app"

 succeeded in 6416ms:
...............................                                          [100%]

codex
The targeted regressions pass. I’m running the full suite now; if it exposes another real seam issue, I’ll fix that before I stop.
exec
/bin/zsh -lc 'python3 -m pytest -q' in /Users/nrupal/dev/yensi/dev/nc-dev-system
diff --git a/src/ncdev/cli.py b/src/ncdev/cli.py
index 78347ed18abd9502b64378f77fe7d52c8c01d42e..b9f4d9dd0e16042063902ff869cc2bbc5fd2d255
--- a/src/ncdev/cli.py
+++ b/src/ncdev/cli.py
@@ -373,7 +373,7 @@
             strict_deps=bool(getattr(args, "strict_deps", False)),
         )
         console.print(f"run_id={state.run_id} status={state.status}")
-        console.print(f"features: {state.completed_features}/{state.total_features} passed")
+        console.print(f"features: {state.completed_features}/{state.total_features} completed")
         console.print(f"run_dir={state.run_dir}")
         if state.status != "passed":
             return 1
diff --git a/src/ncdev/v3/claude_executor.py b/src/ncdev/v3/claude_executor.py
index 973459e5f764d4bf2d0bde198747c6949f216bd5..9fc826c2d005686dea54106495ec650aa569ce7b
--- a/src/ncdev/v3/claude_executor.py
+++ b/src/ncdev/v3/claude_executor.py
@@ -351,10 +351,13 @@
                 reasons.append(f"asset references without manifest: {missing[:5]}")
 
     # 3. Prohibited patterns (regex — treats entries in the contract as
-    #    patterns, falls back to literal match if the regex fails to compile)
+    #    patterns, falls back to literal match if the regex fails to compile).
+    #    Feature-local scope matters here for the same reason it matters for
+    #    asset manifests: one legacy TODO elsewhere in a brownfield repo should
+    #    not fail every future feature.
     patterns = bundle.verification.prohibited_patterns
     if patterns:
-        bad = _grep_for_prohibited(target_path, patterns)
+        bad = _grep_for_prohibited(target_path, patterns, touched_files=touched_files)
         if bad:
             reasons.append(f"prohibited patterns found: {bad[:5]}")
 
@@ -422,12 +425,20 @@
     return ver
 
 
-def _grep_for_prohibited(target_path: Path, patterns: list[str]) -> list[str]:
+def _grep_for_prohibited(
+    target_path: Path,
+    patterns: list[str],
+    *,
+    touched_files: list[str] | None = None,
+) -> list[str]:
     """Scan git-tracked files for prohibited patterns.
 
     Each entry is treated as a regular expression via ``re.search``. If
     a pattern fails to compile, falls back to a substring check so
     human-written entries like ``TODO`` still work.
+
+    When ``touched_files`` is provided, only scan that feature-local set.
+    This keeps brownfield legacy debt from failing unrelated future work.
     """
     compiled: list[tuple[str, re.Pattern[str] | None]] = []
     for pat in patterns:
@@ -444,10 +455,15 @@
         )
         if ls.returncode != 0:
             return []
-        files = [f for f in ls.stdout.splitlines() if f]
+        tracked_files = {f for f in ls.stdout.splitlines() if f}
     except (subprocess.TimeoutExpired, FileNotFoundError):
         return []
 
+    if touched_files is not None:
+        files = [f for f in touched_files if f in tracked_files]
+    else:
+        files = sorted(tracked_files)
+
     for f in files:
         fp = target_path / f
         try:
diff --git a/src/ncdev/v3/engine.py b/src/ncdev/v3/engine.py
index 86cebe171c78ff9d0fded0c142a6793f98ca4944..78a18f3debbfd201af46ad4254db8d29afbb8aa5
--- a/src/ncdev/v3/engine.py
+++ b/src/ncdev/v3/engine.py
@@ -207,6 +207,8 @@
 
         # Brownfield: skip features already implemented
         remaining = _filter_completed_features(target_path, features, completed)
+        _sync_progress_state(state, completed)
+        _persist_state(state, run_dir)
         console.print(f"\n[bold]Phase 5: Building {len(remaining)} features sequentially[/bold]")
 
         for feature in remaining:
@@ -231,7 +233,7 @@
                     status=StepStatus.BLOCKED,
                     error_message=reason,
                 ))
-                state.completed_steps = completed
+                _sync_progress_state(state, completed)
                 _persist_state(state, run_dir)
                 if strict_deps:
                     console.print("[red]--strict-deps set: halting run[/red]")
@@ -256,14 +258,7 @@
                 config=config,
             )
             completed.append(result)
-            state.completed_steps = completed
-            # Count PASSED + SKIPPED — both are "done from NC Dev's
-            # perspective". SKIPPED = brownfield state scanner already
-            # found them in the target repo; PASSED = built this run.
-            state.completed_features = len([
-                r for r in completed
-                if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
-            ])
+            _sync_progress_state(state, completed)
             _persist_state(state, run_dir)
 
             status_style = "green" if result.status == StepStatus.PASSED else "red"
@@ -362,3 +357,14 @@
 def _persist_state(state: V3RunState, run_dir: Path) -> None:
     run_dir.mkdir(parents=True, exist_ok=True)
     (run_dir / "state.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")
+
+
+def _sync_progress_state(state: V3RunState, completed: list[StepResult]) -> None:
+    """Keep persisted progress counters in sync with the completed list."""
+    state.completed_steps = list(completed)
+    # Count PASSED + SKIPPED — both are "done from NC Dev's perspective".
+    # SKIPPED means the brownfield state scanner found them already present;
+    # PASSED means they were built successfully during this run.
+    state.completed_features = sum(
+        1 for r in completed if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
+    )
diff --git a/tests/test_cli.py b/tests/test_cli.py
index 6e1d69ab2f720b5fd71b603de93f8d2967eb7c95..395d8c6e8ff314a3735129c59434f9c31c171365
--- a/tests/test_cli.py
+++ b/tests/test_cli.py
@@ -1,6 +1,8 @@
 from pathlib import Path
+from types import SimpleNamespace
+from unittest.mock import patch
 
-from ncdev.cli import _doctor_report, _quickstart_text, _resolve_target_repo, build_parser
+from ncdev.cli import _doctor_report, _quickstart_text, _resolve_target_repo, build_parser, main
 
 
 def test_cli_quickstart_parses() -> None:
@@ -87,3 +89,23 @@
     (tmp_path / ".git").mkdir()
     _, report = _doctor_report(tmp_path)
     assert "git repository" in report
+
+
+def test_cli_full_reports_completed_not_passed(tmp_path: Path) -> None:
+    source = tmp_path / "requirements.md"
+    source.write_text("x")
+    printed: list[str] = []
+    state = SimpleNamespace(
+        run_id="r1",
+        status="passed",
+        completed_features=2,
+        total_features=3,
+        run_dir="/tmp/run",
+    )
+
+    with patch("ncdev.cli.run_v3_full", return_value=state):
+        with patch("ncdev.cli.console.print", side_effect=lambda *args, **kwargs: printed.append(str(args[0]))):
+            with patch("sys.argv", ["ncdev", "full", "--source", str(source), "--dry-run"]):
+                assert main() == 0
+
+    assert any("features: 2/3 completed" in line for line in printed)
diff --git a/tests/test_ncdev_v3/test_engine.py b/tests/test_ncdev_v3/test_engine.py
new file mode 100644
index 0000000000000000000000000000000000000000..d4c48cda3f6e41c3ca90e7483dc2d8578b7a7940
--- /dev/null
+++ b/tests/test_ncdev_v3/test_engine.py
@@ -0,0 +1,67 @@
+from __future__ import annotations
+
+from pathlib import Path
+from types import SimpleNamespace
+
+from ncdev.v3.engine import run_v3_full
+from ncdev.v3.models import (
+    CharterBundle,
+    FeatureQueueDoc,
+    FeatureStep,
+    StepResult,
+    StepStatus,
+    TargetProjectContract,
+    VerificationContract,
+)
+
+
+def _bundle(*features: FeatureStep) -> CharterBundle:
+    return CharterBundle(
+        contract=TargetProjectContract(project_name="proj", project_type="web"),
+        verification=VerificationContract(),
+        feature_queue=FeatureQueueDoc(project_name="proj", features=list(features)),
+    )
+
+
+def test_run_v3_full_persists_brownfield_skips_in_progress_state(tmp_path: Path, monkeypatch):
+    """State-scanner skips must show up immediately in persisted progress.
+
+    Before this fix, completed_steps/completed_features stayed at zero when
+    the scanner skipped features before the build loop ran, so a fully
+    brownfield/no-op run reported no completed work in state.json.
+    """
+    workspace = tmp_path / "ws"
+    workspace.mkdir()
+    source = workspace / "prd.md"
+    source.write_text("# PRD\n")
+    target = workspace / "target"
+    target.mkdir()
+
+    feature = FeatureStep(
+        feature_id="f1",
+        title="Already done",
+        description="",
+        acceptance_criteria=[],
+    )
+    bundle = _bundle(feature)
+
+    monkeypatch.setattr("ncdev.v3.engine.generate_charter", lambda **kwargs: (bundle, SimpleNamespace(summary=lambda: "ok")))
+    monkeypatch.setattr("ncdev.v3.engine.run_design_phase", lambda **kwargs: SimpleNamespace(skipped=True, hard_failed=False, design_doc=None))
+    monkeypatch.setattr("ncdev.v3.state_scanner.scan_completed_features", lambda target_path, features: ["f1"])
+    monkeypatch.setattr(
+        "ncdev.v3.state_scanner.build_skip_results",
+        lambda features, done_ids: [StepResult(feature_id="f1", status=StepStatus.SKIPPED)],
+    )
+
+    state = run_v3_full(
+        workspace=workspace,
+        source_path=source,
+        target_repo_path=target,
+        builder_model="claude-opus-4-6",
+    )
+
+    assert state.status == "passed"
+    assert state.completed_features == 1
+    assert len(state.completed_steps) == 1
+    assert state.completed_steps[0].status == StepStatus.SKIPPED
+
diff --git a/tests/unit/test_claude_executor.py b/tests/unit/test_claude_executor.py
index a08e209565101214bc64e0f710ac287b458bb03a..3261c2cbcac84262b510769fca4e661d2b9f008e
--- a/tests/unit/test_claude_executor.py
+++ b/tests/unit/test_claude_executor.py
@@ -294,6 +294,46 @@
     assert any("prohibited" in r.lower() for r in result.verification.failure_reasons)
 
 
+def test_legacy_prohibited_pattern_outside_touched_files_does_not_block_pass(tmp_path: Path):
+    """Post-hoc verification must stay feature-local.
+
+    A brownfield repo can contain an old TODO in some untouched file; that
+    should not fail a new clean feature, because the pre-commit hook only
+    guards staged content and the executor already scopes asset checks
+    feature-locally for the same reason.
+    """
+    target = tmp_path / "app"
+    target.mkdir()
+    _init_git(target)
+
+    # Legacy debt that predates this feature.
+    (target / "legacy.py").write_text("# TODO historical debt\n")
+    subprocess.run(["git", "add", "legacy.py"], cwd=str(target), check=True)
+    subprocess.run(["git", "commit", "-q", "-m", "feat(legacy): existing debt"],
+                   cwd=str(target), check=True)
+
+    def fake_session(prompt, **kwargs):  # noqa: ARG001
+        _seed_manifest(target, "f01-scaffold")
+        (target / "clean.py").write_text("x = 1\n")
+        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
+        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): clean"],
+                       cwd=str(target), check=True)
+        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)
+
+    bundle = _make_bundle()  # prohibited_patterns=["TODO"]
+    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):
+        result = execute_feature_claude_driven(
+            feature=_make_feature(),
+            target_path=target,
+            run_dir=tmp_path / "run",
+            charter_bundle=bundle,
+            prior_results=[],
+            project_id="myapp",
+        )
+
+    assert result.status == StepStatus.PASSED
+
+
 def test_verification_runs_backend_test_command_when_configured(tmp_path: Path):
     """New enforcement: backend_test_command actually runs, not just documented."""
     target = tmp_path / "app"

diff --git a/src/ncdev/cli.py b/src/ncdev/cli.py
index 78347ed18abd9502b64378f77fe7d52c8c01d42e..b9f4d9dd0e16042063902ff869cc2bbc5fd2d255
--- a/src/ncdev/cli.py
+++ b/src/ncdev/cli.py
@@ -373,7 +373,7 @@
             strict_deps=bool(getattr(args, "strict_deps", False)),
         )
         console.print(f"run_id={state.run_id} status={state.status}")
-        console.print(f"features: {state.completed_features}/{state.total_features} passed")
+        console.print(f"features: {state.completed_features}/{state.total_features} completed")
         console.print(f"run_dir={state.run_dir}")
         if state.status != "passed":
             return 1
diff --git a/src/ncdev/v3/claude_executor.py b/src/ncdev/v3/claude_executor.py
index 973459e5f764d4bf2d0bde198747c6949f216bd5..9fc826c2d005686dea54106495ec650aa569ce7b
--- a/src/ncdev/v3/claude_executor.py
+++ b/src/ncdev/v3/claude_executor.py
@@ -351,10 +351,13 @@
                 reasons.append(f"asset references without manifest: {missing[:5]}")
 
     # 3. Prohibited patterns (regex — treats entries in the contract as
-    #    patterns, falls back to literal match if the regex fails to compile)
+    #    patterns, falls back to literal match if the regex fails to compile).
+    #    Feature-local scope matters here for the same reason it matters for
+    #    asset manifests: one legacy TODO elsewhere in a brownfield repo should
+    #    not fail every future feature.
     patterns = bundle.verification.prohibited_patterns
     if patterns:
-        bad = _grep_for_prohibited(target_path, patterns)
+        bad = _grep_for_prohibited(target_path, patterns, touched_files=touched_files)
         if bad:
             reasons.append(f"prohibited patterns found: {bad[:5]}")
 
@@ -422,12 +425,20 @@
     return ver
 
 
-def _grep_for_prohibited(target_path: Path, patterns: list[str]) -> list[str]:
+def _grep_for_prohibited(
+    target_path: Path,
+    patterns: list[str],
+    *,
+    touched_files: list[str] | None = None,
+) -> list[str]:
     """Scan git-tracked files for prohibited patterns.
 
     Each entry is treated as a regular expression via ``re.search``. If
     a pattern fails to compile, falls back to a substring check so
     human-written entries like ``TODO`` still work.
+
+    When ``touched_files`` is provided, only scan that feature-local set.
+    This keeps brownfield legacy debt from failing unrelated future work.
     """
     compiled: list[tuple[str, re.Pattern[str] | None]] = []
     for pat in patterns:
@@ -444,10 +455,15 @@
         )
         if ls.returncode != 0:
             return []
-        files = [f for f in ls.stdout.splitlines() if f]
+        tracked_files = {f for f in ls.stdout.splitlines() if f}
     except (subprocess.TimeoutExpired, FileNotFoundError):
         return []
 
+    if touched_files is not None:
+        files = [f for f in touched_files if f in tracked_files]
+    else:
+        files = sorted(tracked_files)
+
     for f in files:
         fp = target_path / f
         try:
diff --git a/src/ncdev/v3/engine.py b/src/ncdev/v3/engine.py
index 86cebe171c78ff9d0fded0c142a6793f98ca4944..78a18f3debbfd201af46ad4254db8d29afbb8aa5
--- a/src/ncdev/v3/engine.py
+++ b/src/ncdev/v3/engine.py
@@ -207,6 +207,8 @@
 
         # Brownfield: skip features already implemented
         remaining = _filter_completed_features(target_path, features, completed)
+        _sync_progress_state(state, completed)
+        _persist_state(state, run_dir)
         console.print(f"\n[bold]Phase 5: Building {len(remaining)} features sequentially[/bold]")
 
         for feature in remaining:
@@ -231,7 +233,7 @@
                     status=StepStatus.BLOCKED,
                     error_message=reason,
                 ))
-                state.completed_steps = completed
+                _sync_progress_state(state, completed)
                 _persist_state(state, run_dir)
                 if strict_deps:
                     console.print("[red]--strict-deps set: halting run[/red]")
@@ -256,14 +258,7 @@
                 config=config,
             )
             completed.append(result)
-            state.completed_steps = completed
-            # Count PASSED + SKIPPED — both are "done from NC Dev's
-            # perspective". SKIPPED = brownfield state scanner already
-            # found them in the target repo; PASSED = built this run.
-            state.completed_features = len([
-                r for r in completed
-                if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
-            ])
+            _sync_progress_state(state, completed)
             _persist_state(state, run_dir)
 
             status_style = "green" if result.status == StepStatus.PASSED else "red"
@@ -362,3 +357,14 @@
 def _persist_state(state: V3RunState, run_dir: Path) -> None:
     run_dir.mkdir(parents=True, exist_ok=True)
     (run_dir / "state.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")
+
+
+def _sync_progress_state(state: V3RunState, completed: list[StepResult]) -> None:
+    """Keep persisted progress counters in sync with the completed list."""
+    state.completed_steps = list(completed)
+    # Count PASSED + SKIPPED — both are "done from NC Dev's perspective".
+    # SKIPPED means the brownfield state scanner found them already present;
+    # PASSED means they were built successfully during this run.
+    state.completed_features = sum(
+        1 for r in completed if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
+    )
diff --git a/tests/test_cli.py b/tests/test_cli.py
index 6e1d69ab2f720b5fd71b603de93f8d2967eb7c95..395d8c6e8ff314a3735129c59434f9c31c171365
--- a/tests/test_cli.py
+++ b/tests/test_cli.py
@@ -1,6 +1,8 @@
 from pathlib import Path
+from types import SimpleNamespace
+from unittest.mock import patch
 
-from ncdev.cli import _doctor_report, _quickstart_text, _resolve_target_repo, build_parser
+from ncdev.cli import _doctor_report, _quickstart_text, _resolve_target_repo, build_parser, main
 
 
 def test_cli_quickstart_parses() -> None:
@@ -87,3 +89,23 @@
     (tmp_path / ".git").mkdir()
     _, report = _doctor_report(tmp_path)
     assert "git repository" in report
+
+
+def test_cli_full_reports_completed_not_passed(tmp_path: Path) -> None:
+    source = tmp_path / "requirements.md"
+    source.write_text("x")
+    printed: list[str] = []
+    state = SimpleNamespace(
+        run_id="r1",
+        status="passed",
+        completed_features=2,
+        total_features=3,
+        run_dir="/tmp/run",
+    )
+
+    with patch("ncdev.cli.run_v3_full", return_value=state):
+        with patch("ncdev.cli.console.print", side_effect=lambda *args, **kwargs: printed.append(str(args[0]))):
+            with patch("sys.argv", ["ncdev", "full", "--source", str(source), "--dry-run"]):
+                assert main() == 0
+
+    assert any("features: 2/3 completed" in line for line in printed)
diff --git a/tests/test_ncdev_v3/test_engine.py b/tests/test_ncdev_v3/test_engine.py
new file mode 100644
index 0000000000000000000000000000000000000000..d4c48cda3f6e41c3ca90e7483dc2d8578b7a7940
--- /dev/null
+++ b/tests/test_ncdev_v3/test_engine.py
@@ -0,0 +1,67 @@
+from __future__ import annotations
+
+from pathlib import Path
+from types import SimpleNamespace
+
+from ncdev.v3.engine import run_v3_full
+from ncdev.v3.models import (
+    CharterBundle,
+    FeatureQueueDoc,
+    FeatureStep,
+    StepResult,
+    StepStatus,
+    TargetProjectContract,
+    VerificationContract,
+)
+
+
+def _bundle(*features: FeatureStep) -> CharterBundle:
+    return CharterBundle(
+        contract=TargetProjectContract(project_name="proj", project_type="web"),
+        verification=VerificationContract(),
+        feature_queue=FeatureQueueDoc(project_name="proj", features=list(features)),
+    )
+
+
+def test_run_v3_full_persists_brownfield_skips_in_progress_state(tmp_path: Path, monkeypatch):
+    """State-scanner skips must show up immediately in persisted progress.
+
+    Before this fix, completed_steps/completed_features stayed at zero when
+    the scanner skipped features before the build loop ran, so a fully
+    brownfield/no-op run reported no completed work in state.json.
+    """
+    workspace = tmp_path / "ws"
+    workspace.mkdir()
+    source = workspace / "prd.md"
+    source.write_text("# PRD\n")
+    target = workspace / "target"
+    target.mkdir()
+
+    feature = FeatureStep(
+        feature_id="f1",
+        title="Already done",
+        description="",
+        acceptance_criteria=[],
+    )
+    bundle = _bundle(feature)
+
+    monkeypatch.setattr("ncdev.v3.engine.generate_charter", lambda **kwargs: (bundle, SimpleNamespace(summary=lambda: "ok")))
+    monkeypatch.setattr("ncdev.v3.engine.run_design_phase", lambda **kwargs: SimpleNamespace(skipped=True, hard_failed=False, design_doc=None))
+    monkeypatch.setattr("ncdev.v3.state_scanner.scan_completed_features", lambda target_path, features: ["f1"])
+    monkeypatch.setattr(
+        "ncdev.v3.state_scanner.build_skip_results",
+        lambda features, done_ids: [StepResult(feature_id="f1", status=StepStatus.SKIPPED)],
+    )
+
+    state = run_v3_full(
+        workspace=workspace,
+        source_path=source,
+        target_repo_path=target,
+        builder_model="claude-opus-4-6",
+    )
+
+    assert state.status == "passed"
+    assert state.completed_features == 1
+    assert len(state.completed_steps) == 1
+    assert state.completed_steps[0].status == StepStatus.SKIPPED
+
diff --git a/tests/unit/test_claude_executor.py b/tests/unit/test_claude_executor.py
index a08e209565101214bc64e0f710ac287b458bb03a..3261c2cbcac84262b510769fca4e661d2b9f008e
--- a/tests/unit/test_claude_executor.py
+++ b/tests/unit/test_claude_executor.py
@@ -294,6 +294,46 @@
     assert any("prohibited" in r.lower() for r in result.verification.failure_reasons)
 
 
+def test_legacy_prohibited_pattern_outside_touched_files_does_not_block_pass(tmp_path: Path):
+    """Post-hoc verification must stay feature-local.
+
+    A brownfield repo can contain an old TODO in some untouched file; that
+    should not fail a new clean feature, because the pre-commit hook only
+    guards staged content and the executor already scopes asset checks
+    feature-locally for the same reason.
+    """
+    target = tmp_path / "app"
+    target.mkdir()
+    _init_git(target)
+
+    # Legacy debt that predates this feature.
+    (target / "legacy.py").write_text("# TODO historical debt\n")
+    subprocess.run(["git", "add", "legacy.py"], cwd=str(target), check=True)
+    subprocess.run(["git", "commit", "-q", "-m", "feat(legacy): existing debt"],
+                   cwd=str(target), check=True)
+
+    def fake_session(prompt, **kwargs):  # noqa: ARG001
+        _seed_manifest(target, "f01-scaffold")
+        (target / "clean.py").write_text("x = 1\n")
+        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
+        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): clean"],
+                       cwd=str(target), check=True)
+        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)
+
+    bundle = _make_bundle()  # prohibited_patterns=["TODO"]
+    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):
+        result = execute_feature_claude_driven(
+            feature=_make_feature(),
+            target_path=target,
+            run_dir=tmp_path / "run",
+            charter_bundle=bundle,
+            prior_results=[],
+            project_id="myapp",
+        )
+
+    assert result.status == StepStatus.PASSED
+
+
 def test_verification_runs_backend_test_command_when_configured(tmp_path: Path):
     """New enforcement: backend_test_command actually runs, not just documented."""
     target = tmp_path / "app"

 succeeded in 13442ms:
........................................................................ [ 16%]
........................................................................ [ 33%]
........................................................................ [ 50%]
........................................................................ [ 67%]
........................................................................ [ 83%]
.....................................................................    [100%]

diff --git a/src/ncdev/cli.py b/src/ncdev/cli.py
index 78347ed18abd9502b64378f77fe7d52c8c01d42e..b9f4d9dd0e16042063902ff869cc2bbc5fd2d255
--- a/src/ncdev/cli.py
+++ b/src/ncdev/cli.py
@@ -373,7 +373,7 @@
             strict_deps=bool(getattr(args, "strict_deps", False)),
         )
         console.print(f"run_id={state.run_id} status={state.status}")
-        console.print(f"features: {state.completed_features}/{state.total_features} passed")
+        console.print(f"features: {state.completed_features}/{state.total_features} completed")
         console.print(f"run_dir={state.run_dir}")
         if state.status != "passed":
             return 1
diff --git a/src/ncdev/v3/claude_executor.py b/src/ncdev/v3/claude_executor.py
index 973459e5f764d4bf2d0bde198747c6949f216bd5..9fc826c2d005686dea54106495ec650aa569ce7b
--- a/src/ncdev/v3/claude_executor.py
+++ b/src/ncdev/v3/claude_executor.py
@@ -351,10 +351,13 @@
                 reasons.append(f"asset references without manifest: {missing[:5]}")
 
     # 3. Prohibited patterns (regex — treats entries in the contract as
-    #    patterns, falls back to literal match if the regex fails to compile)
+    #    patterns, falls back to literal match if the regex fails to compile).
+    #    Feature-local scope matters here for the same reason it matters for
+    #    asset manifests: one legacy TODO elsewhere in a brownfield repo should
+    #    not fail every future feature.
     patterns = bundle.verification.prohibited_patterns
     if patterns:
-        bad = _grep_for_prohibited(target_path, patterns)
+        bad = _grep_for_prohibited(target_path, patterns, touched_files=touched_files)
         if bad:
             reasons.append(f"prohibited patterns found: {bad[:5]}")
 
@@ -422,12 +425,20 @@
     return ver
 
 
-def _grep_for_prohibited(target_path: Path, patterns: list[str]) -> list[str]:
+def _grep_for_prohibited(
+    target_path: Path,
+    patterns: list[str],
+    *,
+    touched_files: list[str] | None = None,
+) -> list[str]:
     """Scan git-tracked files for prohibited patterns.
 
     Each entry is treated as a regular expression via ``re.search``. If
     a pattern fails to compile, falls back to a substring check so
     human-written entries like ``TODO`` still work.
+
+    When ``touched_files`` is provided, only scan that feature-local set.
+    This keeps brownfield legacy debt from failing unrelated future work.
     """
     compiled: list[tuple[str, re.Pattern[str] | None]] = []
     for pat in patterns:
@@ -444,10 +455,15 @@
         )
         if ls.returncode != 0:
             return []
-        files = [f for f in ls.stdout.splitlines() if f]
+        tracked_files = {f for f in ls.stdout.splitlines() if f}
     except (subprocess.TimeoutExpired, FileNotFoundError):
         return []
 
+    if touched_files is not None:
+        files = [f for f in touched_files if f in tracked_files]
+    else:
+        files = sorted(tracked_files)
+
     for f in files:
         fp = target_path / f
         try:
diff --git a/src/ncdev/v3/engine.py b/src/ncdev/v3/engine.py
index 86cebe171c78ff9d0fded0c142a6793f98ca4944..78a18f3debbfd201af46ad4254db8d29afbb8aa5
--- a/src/ncdev/v3/engine.py
+++ b/src/ncdev/v3/engine.py
@@ -207,6 +207,8 @@
 
         # Brownfield: skip features already implemented
         remaining = _filter_completed_features(target_path, features, completed)
+        _sync_progress_state(state, completed)
+        _persist_state(state, run_dir)
         console.print(f"\n[bold]Phase 5: Building {len(remaining)} features sequentially[/bold]")
 
         for feature in remaining:
@@ -231,7 +233,7 @@
                     status=StepStatus.BLOCKED,
                     error_message=reason,
                 ))
-                state.completed_steps = completed
+                _sync_progress_state(state, completed)
                 _persist_state(state, run_dir)
                 if strict_deps:
                     console.print("[red]--strict-deps set: halting run[/red]")
@@ -256,14 +258,7 @@
                 config=config,
             )
             completed.append(result)
-            state.completed_steps = completed
-            # Count PASSED + SKIPPED — both are "done from NC Dev's
-            # perspective". SKIPPED = brownfield state scanner already
-            # found them in the target repo; PASSED = built this run.
-            state.completed_features = len([
-                r for r in completed
-                if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
-            ])
+            _sync_progress_state(state, completed)
             _persist_state(state, run_dir)
 
             status_style = "green" if result.status == StepStatus.PASSED else "red"
@@ -362,3 +357,14 @@
 def _persist_state(state: V3RunState, run_dir: Path) -> None:
     run_dir.mkdir(parents=True, exist_ok=True)
     (run_dir / "state.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")
+
+
+def _sync_progress_state(state: V3RunState, completed: list[StepResult]) -> None:
+    """Keep persisted progress counters in sync with the completed list."""
+    state.completed_steps = list(completed)
+    # Count PASSED + SKIPPED — both are "done from NC Dev's perspective".
+    # SKIPPED means the brownfield state scanner found them already present;
+    # PASSED means they were built successfully during this run.
+    state.completed_features = sum(
+        1 for r in completed if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
+    )
diff --git a/tests/test_cli.py b/tests/test_cli.py
index 6e1d69ab2f720b5fd71b603de93f8d2967eb7c95..395d8c6e8ff314a3735129c59434f9c31c171365
--- a/tests/test_cli.py
+++ b/tests/test_cli.py
@@ -1,6 +1,8 @@
 from pathlib import Path
+from types import SimpleNamespace
+from unittest.mock import patch
 
-from ncdev.cli import _doctor_report, _quickstart_text, _resolve_target_repo, build_parser
+from ncdev.cli import _doctor_report, _quickstart_text, _resolve_target_repo, build_parser, main
 
 
 def test_cli_quickstart_parses() -> None:
@@ -87,3 +89,23 @@
     (tmp_path / ".git").mkdir()
     _, report = _doctor_report(tmp_path)
     assert "git repository" in report
+
+
+def test_cli_full_reports_completed_not_passed(tmp_path: Path) -> None:
+    source = tmp_path / "requirements.md"
+    source.write_text("x")
+    printed: list[str] = []
+    state = SimpleNamespace(
+        run_id="r1",
+        status="passed",
+        completed_features=2,
+        total_features=3,
+        run_dir="/tmp/run",
+    )
+
+    with patch("ncdev.cli.run_v3_full", return_value=state):
+        with patch("ncdev.cli.console.print", side_effect=lambda *args, **kwargs: printed.append(str(args[0]))):
+            with patch("sys.argv", ["ncdev", "full", "--source", str(source), "--dry-run"]):
+                assert main() == 0
+
+    assert any("features: 2/3 completed" in line for line in printed)
diff --git a/tests/test_ncdev_v3/test_engine.py b/tests/test_ncdev_v3/test_engine.py
new file mode 100644
index 0000000000000000000000000000000000000000..d4c48cda3f6e41c3ca90e7483dc2d8578b7a7940
--- /dev/null
+++ b/tests/test_ncdev_v3/test_engine.py
@@ -0,0 +1,67 @@
+from __future__ import annotations
+
+from pathlib import Path
+from types import SimpleNamespace
+
+from ncdev.v3.engine import run_v3_full
+from ncdev.v3.models import (
+    CharterBundle,
+    FeatureQueueDoc,
+    FeatureStep,
+    StepResult,
+    StepStatus,
+    TargetProjectContract,
+    VerificationContract,
+)
+
+
+def _bundle(*features: FeatureStep) -> CharterBundle:
+    return CharterBundle(
+        contract=TargetProjectContract(project_name="proj", project_type="web"),
+        verification=VerificationContract(),
+        feature_queue=FeatureQueueDoc(project_name="proj", features=list(features)),
+    )
+
+
+def test_run_v3_full_persists_brownfield_skips_in_progress_state(tmp_path: Path, monkeypatch):
+    """State-scanner skips must show up immediately in persisted progress.
+
+    Before this fix, completed_steps/completed_features stayed at zero when
+    the scanner skipped features before the build loop ran, so a fully
+    brownfield/no-op run reported no completed work in state.json.
+    """
+    workspace = tmp_path / "ws"
+    workspace.mkdir()
+    source = workspace / "prd.md"
+    source.write_text("# PRD\n")
+    target = workspace / "target"
+    target.mkdir()
+
+    feature = FeatureStep(
+        feature_id="f1",
+        title="Already done",
+        description="",
+        acceptance_criteria=[],
+    )
+    bundle = _bundle(feature)
+
+    monkeypatch.setattr("ncdev.v3.engine.generate_charter", lambda **kwargs: (bundle, SimpleNamespace(summary=lambda: "ok")))
+    monkeypatch.setattr("ncdev.v3.engine.run_design_phase", lambda **kwargs: SimpleNamespace(skipped=True, hard_failed=False, design_doc=None))
+    monkeypatch.setattr("ncdev.v3.state_scanner.scan_completed_features", lambda target_path, features: ["f1"])
+    monkeypatch.setattr(
+        "ncdev.v3.state_scanner.build_skip_results",
+        lambda features, done_ids: [StepResult(feature_id="f1", status=StepStatus.SKIPPED)],
+    )
+
+    state = run_v3_full(
+        workspace=workspace,
+        source_path=source,
+        target_repo_path=target,
+        builder_model="claude-opus-4-6",
+    )
+
+    assert state.status == "passed"
+    assert state.completed_features == 1
+    assert len(state.completed_steps) == 1
+    assert state.completed_steps[0].status == StepStatus.SKIPPED
+
diff --git a/tests/unit/test_claude_executor.py b/tests/unit/test_claude_executor.py
index a08e209565101214bc64e0f710ac287b458bb03a..3261c2cbcac84262b510769fca4e661d2b9f008e
--- a/tests/unit/test_claude_executor.py
+++ b/tests/unit/test_claude_executor.py
@@ -294,6 +294,46 @@
     assert any("prohibited" in r.lower() for r in result.verification.failure_reasons)
 
 
+def test_legacy_prohibited_pattern_outside_touched_files_does_not_block_pass(tmp_path: Path):
+    """Post-hoc verification must stay feature-local.
+
+    A brownfield repo can contain an old TODO in some untouched file; that
+    should not fail a new clean feature, because the pre-commit hook only
+    guards staged content and the executor already scopes asset checks
+    feature-locally for the same reason.
+    """
+    target = tmp_path / "app"
+    target.mkdir()
+    _init_git(target)
+
+    # Legacy debt that predates this feature.
+    (target / "legacy.py").write_text("# TODO historical debt\n")
+    subprocess.run(["git", "add", "legacy.py"], cwd=str(target), check=True)
+    subprocess.run(["git", "commit", "-q", "-m", "feat(legacy): existing debt"],
+                   cwd=str(target), check=True)
+
+    def fake_session(prompt, **kwargs):  # noqa: ARG001
+        _seed_manifest(target, "f01-scaffold")
+        (target / "clean.py").write_text("x = 1\n")
+        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
+        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): clean"],
+                       cwd=str(target), check=True)
+        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)
+
+    bundle = _make_bundle()  # prohibited_patterns=["TODO"]
+    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):
+        result = execute_feature_claude_driven(
+            feature=_make_feature(),
+            target_path=target,
+            run_dir=tmp_path / "run",
+            charter_bundle=bundle,
+            prior_results=[],
+            project_id="myapp",
+        )
+
+    assert result.status == StepStatus.PASSED
+
+
 def test_verification_runs_backend_test_command_when_configured(tmp_path: Path):
     """New enforcement: backend_test_command actually runs, not just documented."""
     target = tmp_path / "app"

exec
/bin/zsh -lc 'python3 -m pytest --collect-only -q | tail -n 1' in /Users/nrupal/dev/yensi/dev/nc-dev-system
diff --git a/src/ncdev/cli.py b/src/ncdev/cli.py
index 78347ed18abd9502b64378f77fe7d52c8c01d42e..b9f4d9dd0e16042063902ff869cc2bbc5fd2d255
--- a/src/ncdev/cli.py
+++ b/src/ncdev/cli.py
@@ -373,7 +373,7 @@
             strict_deps=bool(getattr(args, "strict_deps", False)),
         )
         console.print(f"run_id={state.run_id} status={state.status}")
-        console.print(f"features: {state.completed_features}/{state.total_features} passed")
+        console.print(f"features: {state.completed_features}/{state.total_features} completed")
         console.print(f"run_dir={state.run_dir}")
         if state.status != "passed":
             return 1
diff --git a/src/ncdev/v3/claude_executor.py b/src/ncdev/v3/claude_executor.py
index 973459e5f764d4bf2d0bde198747c6949f216bd5..9fc826c2d005686dea54106495ec650aa569ce7b
--- a/src/ncdev/v3/claude_executor.py
+++ b/src/ncdev/v3/claude_executor.py
@@ -351,10 +351,13 @@
                 reasons.append(f"asset references without manifest: {missing[:5]}")
 
     # 3. Prohibited patterns (regex — treats entries in the contract as
-    #    patterns, falls back to literal match if the regex fails to compile)
+    #    patterns, falls back to literal match if the regex fails to compile).
+    #    Feature-local scope matters here for the same reason it matters for
+    #    asset manifests: one legacy TODO elsewhere in a brownfield repo should
+    #    not fail every future feature.
     patterns = bundle.verification.prohibited_patterns
     if patterns:
-        bad = _grep_for_prohibited(target_path, patterns)
+        bad = _grep_for_prohibited(target_path, patterns, touched_files=touched_files)
         if bad:
             reasons.append(f"prohibited patterns found: {bad[:5]}")
 
@@ -422,12 +425,20 @@
     return ver
 
 
-def _grep_for_prohibited(target_path: Path, patterns: list[str]) -> list[str]:
+def _grep_for_prohibited(
+    target_path: Path,
+    patterns: list[str],
+    *,
+    touched_files: list[str] | None = None,
+) -> list[str]:
     """Scan git-tracked files for prohibited patterns.
 
     Each entry is treated as a regular expression via ``re.search``. If
     a pattern fails to compile, falls back to a substring check so
     human-written entries like ``TODO`` still work.
+
+    When ``touched_files`` is provided, only scan that feature-local set.
+    This keeps brownfield legacy debt from failing unrelated future work.
     """
     compiled: list[tuple[str, re.Pattern[str] | None]] = []
     for pat in patterns:
@@ -444,10 +455,15 @@
         )
         if ls.returncode != 0:
             return []
-        files = [f for f in ls.stdout.splitlines() if f]
+        tracked_files = {f for f in ls.stdout.splitlines() if f}
     except (subprocess.TimeoutExpired, FileNotFoundError):
         return []
 
+    if touched_files is not None:
+        files = [f for f in touched_files if f in tracked_files]
+    else:
+        files = sorted(tracked_files)
+
     for f in files:
         fp = target_path / f
         try:
diff --git a/src/ncdev/v3/engine.py b/src/ncdev/v3/engine.py
index 86cebe171c78ff9d0fded0c142a6793f98ca4944..78a18f3debbfd201af46ad4254db8d29afbb8aa5
--- a/src/ncdev/v3/engine.py
+++ b/src/ncdev/v3/engine.py
@@ -207,6 +207,8 @@
 
         # Brownfield: skip features already implemented
         remaining = _filter_completed_features(target_path, features, completed)
+        _sync_progress_state(state, completed)
+        _persist_state(state, run_dir)
         console.print(f"\n[bold]Phase 5: Building {len(remaining)} features sequentially[/bold]")
 
         for feature in remaining:
@@ -231,7 +233,7 @@
                     status=StepStatus.BLOCKED,
                     error_message=reason,
                 ))
-                state.completed_steps = completed
+                _sync_progress_state(state, completed)
                 _persist_state(state, run_dir)
                 if strict_deps:
                     console.print("[red]--strict-deps set: halting run[/red]")
@@ -256,14 +258,7 @@
                 config=config,
             )
             completed.append(result)
-            state.completed_steps = completed
-            # Count PASSED + SKIPPED — both are "done from NC Dev's
-            # perspective". SKIPPED = brownfield state scanner already
-            # found them in the target repo; PASSED = built this run.
-            state.completed_features = len([
-                r for r in completed
-                if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
-            ])
+            _sync_progress_state(state, completed)
             _persist_state(state, run_dir)
 
             status_style = "green" if result.status == StepStatus.PASSED else "red"
@@ -362,3 +357,14 @@
 def _persist_state(state: V3RunState, run_dir: Path) -> None:
     run_dir.mkdir(parents=True, exist_ok=True)
     (run_dir / "state.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")
+
+
+def _sync_progress_state(state: V3RunState, completed: list[StepResult]) -> None:
+    """Keep persisted progress counters in sync with the completed list."""
+    state.completed_steps = list(completed)
+    # Count PASSED + SKIPPED — both are "done from NC Dev's perspective".
+    # SKIPPED means the brownfield state scanner found them already present;
+    # PASSED means they were built successfully during this run.
+    state.completed_features = sum(
+        1 for r in completed if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
+    )
diff --git a/tests/test_cli.py b/tests/test_cli.py
index 6e1d69ab2f720b5fd71b603de93f8d2967eb7c95..395d8c6e8ff314a3735129c59434f9c31c171365
--- a/tests/test_cli.py
+++ b/tests/test_cli.py
@@ -1,6 +1,8 @@
 from pathlib import Path
+from types import SimpleNamespace
+from unittest.mock import patch
 
-from ncdev.cli import _doctor_report, _quickstart_text, _resolve_target_repo, build_parser
+from ncdev.cli import _doctor_report, _quickstart_text, _resolve_target_repo, build_parser, main
 
 
 def test_cli_quickstart_parses() -> None:
@@ -87,3 +89,23 @@
     (tmp_path / ".git").mkdir()
     _, report = _doctor_report(tmp_path)
     assert "git repository" in report
+
+
+def test_cli_full_reports_completed_not_passed(tmp_path: Path) -> None:
+    source = tmp_path / "requirements.md"
+    source.write_text("x")
+    printed: list[str] = []
+    state = SimpleNamespace(
+        run_id="r1",
+        status="passed",
+        completed_features=2,
+        total_features=3,
+        run_dir="/tmp/run",
+    )
+
+    with patch("ncdev.cli.run_v3_full", return_value=state):
+        with patch("ncdev.cli.console.print", side_effect=lambda *args, **kwargs: printed.append(str(args[0]))):
+            with patch("sys.argv", ["ncdev", "full", "--source", str(source), "--dry-run"]):
+                assert main() == 0
+
+    assert any("features: 2/3 completed" in line for line in printed)
diff --git a/tests/test_ncdev_v3/test_engine.py b/tests/test_ncdev_v3/test_engine.py
new file mode 100644
index 0000000000000000000000000000000000000000..d4c48cda3f6e41c3ca90e7483dc2d8578b7a7940
--- /dev/null
+++ b/tests/test_ncdev_v3/test_engine.py
@@ -0,0 +1,67 @@
+from __future__ import annotations
+
+from pathlib import Path
+from types import SimpleNamespace
+
+from ncdev.v3.engine import run_v3_full
+from ncdev.v3.models import (
+    CharterBundle,
+    FeatureQueueDoc,
+    FeatureStep,
+    StepResult,
+    StepStatus,
+    TargetProjectContract,
+    VerificationContract,
+)
+
+
+def _bundle(*features: FeatureStep) -> CharterBundle:
+    return CharterBundle(
+        contract=TargetProjectContract(project_name="proj", project_type="web"),
+        verification=VerificationContract(),
+        feature_queue=FeatureQueueDoc(project_name="proj", features=list(features)),
+    )
+
+
+def test_run_v3_full_persists_brownfield_skips_in_progress_state(tmp_path: Path, monkeypatch):
+    """State-scanner skips must show up immediately in persisted progress.
+
+    Before this fix, completed_steps/completed_features stayed at zero when
+    the scanner skipped features before the build loop ran, so a fully
+    brownfield/no-op run reported no completed work in state.json.
+    """
+    workspace = tmp_path / "ws"
+    workspace.mkdir()
+    source = workspace / "prd.md"
+    source.write_text("# PRD\n")
+    target = workspace / "target"
+    target.mkdir()
+
+    feature = FeatureStep(
+        feature_id="f1",
+        title="Already done",
+        description="",
+        acceptance_criteria=[],
+    )
+    bundle = _bundle(feature)
+
+    monkeypatch.setattr("ncdev.v3.engine.generate_charter", lambda **kwargs: (bundle, SimpleNamespace(summary=lambda: "ok")))
+    monkeypatch.setattr("ncdev.v3.engine.run_design_phase", lambda **kwargs: SimpleNamespace(skipped=True, hard_failed=False, design_doc=None))
+    monkeypatch.setattr("ncdev.v3.state_scanner.scan_completed_features", lambda target_path, features: ["f1"])
+    monkeypatch.setattr(
+        "ncdev.v3.state_scanner.build_skip_results",
+        lambda features, done_ids: [StepResult(feature_id="f1", status=StepStatus.SKIPPED)],
+    )
+
+    state = run_v3_full(
+        workspace=workspace,
+        source_path=source,
+        target_repo_path=target,
+        builder_model="claude-opus-4-6",
+    )
+
+    assert state.status == "passed"
+    assert state.completed_features == 1
+    assert len(state.completed_steps) == 1
+    assert state.completed_steps[0].status == StepStatus.SKIPPED
+
diff --git a/tests/unit/test_claude_executor.py b/tests/unit/test_claude_executor.py
index a08e209565101214bc64e0f710ac287b458bb03a..3261c2cbcac84262b510769fca4e661d2b9f008e
--- a/tests/unit/test_claude_executor.py
+++ b/tests/unit/test_claude_executor.py
@@ -294,6 +294,46 @@
     assert any("prohibited" in r.lower() for r in result.verification.failure_reasons)
 
 
+def test_legacy_prohibited_pattern_outside_touched_files_does_not_block_pass(tmp_path: Path):
+    """Post-hoc verification must stay feature-local.
+
+    A brownfield repo can contain an old TODO in some untouched file; that
+    should not fail a new clean feature, because the pre-commit hook only
+    guards staged content and the executor already scopes asset checks
+    feature-locally for the same reason.
+    """
+    target = tmp_path / "app"
+    target.mkdir()
+    _init_git(target)
+
+    # Legacy debt that predates this feature.
+    (target / "legacy.py").write_text("# TODO historical debt\n")
+    subprocess.run(["git", "add", "legacy.py"], cwd=str(target), check=True)
+    subprocess.run(["git", "commit", "-q", "-m", "feat(legacy): existing debt"],
+                   cwd=str(target), check=True)
+
+    def fake_session(prompt, **kwargs):  # noqa: ARG001
+        _seed_manifest(target, "f01-scaffold")
+        (target / "clean.py").write_text("x = 1\n")
+        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
+        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): clean"],
+                       cwd=str(target), check=True)
+        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)
+
+    bundle = _make_bundle()  # prohibited_patterns=["TODO"]
+    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):
+        result = execute_feature_claude_driven(
+            feature=_make_feature(),
+            target_path=target,
+            run_dir=tmp_path / "run",
+            charter_bundle=bundle,
+            prior_results=[],
+            project_id="myapp",
+        )
+
+    assert result.status == StepStatus.PASSED
+
+
 def test_verification_runs_backend_test_command_when_configured(tmp_path: Path):
     """New enforcement: backend_test_command actually runs, not just documented."""
     target = tmp_path / "app"

 succeeded in 1014ms:
exec
/bin/zsh -lc 'python3 -m pytest --collect-only -q > /tmp/ncdev-pytest-collect.txt && tail -n 5 /tmp/ncdev-pytest-collect.txt && wc -l /tmp/ncdev-pytest-collect.txt' in /Users/nrupal/dev/yensi/dev/nc-dev-system
diff --git a/src/ncdev/cli.py b/src/ncdev/cli.py
index 78347ed18abd9502b64378f77fe7d52c8c01d42e..b9f4d9dd0e16042063902ff869cc2bbc5fd2d255
--- a/src/ncdev/cli.py
+++ b/src/ncdev/cli.py
@@ -373,7 +373,7 @@
             strict_deps=bool(getattr(args, "strict_deps", False)),
         )
         console.print(f"run_id={state.run_id} status={state.status}")
-        console.print(f"features: {state.completed_features}/{state.total_features} passed")
+        console.print(f"features: {state.completed_features}/{state.total_features} completed")
         console.print(f"run_dir={state.run_dir}")
         if state.status != "passed":
             return 1
diff --git a/src/ncdev/v3/claude_executor.py b/src/ncdev/v3/claude_executor.py
index 973459e5f764d4bf2d0bde198747c6949f216bd5..9fc826c2d005686dea54106495ec650aa569ce7b
--- a/src/ncdev/v3/claude_executor.py
+++ b/src/ncdev/v3/claude_executor.py
@@ -351,10 +351,13 @@
                 reasons.append(f"asset references without manifest: {missing[:5]}")
 
     # 3. Prohibited patterns (regex — treats entries in the contract as
-    #    patterns, falls back to literal match if the regex fails to compile)
+    #    patterns, falls back to literal match if the regex fails to compile).
+    #    Feature-local scope matters here for the same reason it matters for
+    #    asset manifests: one legacy TODO elsewhere in a brownfield repo should
+    #    not fail every future feature.
     patterns = bundle.verification.prohibited_patterns
     if patterns:
-        bad = _grep_for_prohibited(target_path, patterns)
+        bad = _grep_for_prohibited(target_path, patterns, touched_files=touched_files)
         if bad:
             reasons.append(f"prohibited patterns found: {bad[:5]}")
 
@@ -422,12 +425,20 @@
     return ver
 
 
-def _grep_for_prohibited(target_path: Path, patterns: list[str]) -> list[str]:
+def _grep_for_prohibited(
+    target_path: Path,
+    patterns: list[str],
+    *,
+    touched_files: list[str] | None = None,
+) -> list[str]:
     """Scan git-tracked files for prohibited patterns.
 
     Each entry is treated as a regular expression via ``re.search``. If
     a pattern fails to compile, falls back to a substring check so
     human-written entries like ``TODO`` still work.
+
+    When ``touched_files`` is provided, only scan that feature-local set.
+    This keeps brownfield legacy debt from failing unrelated future work.
     """
     compiled: list[tuple[str, re.Pattern[str] | None]] = []
     for pat in patterns:
@@ -444,10 +455,15 @@
         )
         if ls.returncode != 0:
             return []
-        files = [f for f in ls.stdout.splitlines() if f]
+        tracked_files = {f for f in ls.stdout.splitlines() if f}
     except (subprocess.TimeoutExpired, FileNotFoundError):
         return []
 
+    if touched_files is not None:
+        files = [f for f in touched_files if f in tracked_files]
+    else:
+        files = sorted(tracked_files)
+
     for f in files:
         fp = target_path / f
         try:
diff --git a/src/ncdev/v3/engine.py b/src/ncdev/v3/engine.py
index 86cebe171c78ff9d0fded0c142a6793f98ca4944..78a18f3debbfd201af46ad4254db8d29afbb8aa5
--- a/src/ncdev/v3/engine.py
+++ b/src/ncdev/v3/engine.py
@@ -207,6 +207,8 @@
 
         # Brownfield: skip features already implemented
         remaining = _filter_completed_features(target_path, features, completed)
+        _sync_progress_state(state, completed)
+        _persist_state(state, run_dir)
         console.print(f"\n[bold]Phase 5: Building {len(remaining)} features sequentially[/bold]")
 
         for feature in remaining:
@@ -231,7 +233,7 @@
                     status=StepStatus.BLOCKED,
                     error_message=reason,
                 ))
-                state.completed_steps = completed
+                _sync_progress_state(state, completed)
                 _persist_state(state, run_dir)
                 if strict_deps:
                     console.print("[red]--strict-deps set: halting run[/red]")
@@ -256,14 +258,7 @@
                 config=config,
             )
             completed.append(result)
-            state.completed_steps = completed
-            # Count PASSED + SKIPPED — both are "done from NC Dev's
-            # perspective". SKIPPED = brownfield state scanner already
-            # found them in the target repo; PASSED = built this run.
-            state.completed_features = len([
-                r for r in completed
-                if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
-            ])
+            _sync_progress_state(state, completed)
             _persist_state(state, run_dir)
 
             status_style = "green" if result.status == StepStatus.PASSED else "red"
@@ -362,3 +357,14 @@
 def _persist_state(state: V3RunState, run_dir: Path) -> None:
     run_dir.mkdir(parents=True, exist_ok=True)
     (run_dir / "state.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")
+
+
+def _sync_progress_state(state: V3RunState, completed: list[StepResult]) -> None:
+    """Keep persisted progress counters in sync with the completed list."""
+    state.completed_steps = list(completed)
+    # Count PASSED + SKIPPED — both are "done from NC Dev's perspective".
+    # SKIPPED means the brownfield state scanner found them already present;
+    # PASSED means they were built successfully during this run.
+    state.completed_features = sum(
+        1 for r in completed if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
+    )
diff --git a/tests/test_cli.py b/tests/test_cli.py
index 6e1d69ab2f720b5fd71b603de93f8d2967eb7c95..395d8c6e8ff314a3735129c59434f9c31c171365
--- a/tests/test_cli.py
+++ b/tests/test_cli.py
@@ -1,6 +1,8 @@
 from pathlib import Path
+from types import SimpleNamespace
+from unittest.mock import patch
 
-from ncdev.cli import _doctor_report, _quickstart_text, _resolve_target_repo, build_parser
+from ncdev.cli import _doctor_report, _quickstart_text, _resolve_target_repo, build_parser, main
 
 
 def test_cli_quickstart_parses() -> None:
@@ -87,3 +89,23 @@
     (tmp_path / ".git").mkdir()
     _, report = _doctor_report(tmp_path)
     assert "git repository" in report
+
+
+def test_cli_full_reports_completed_not_passed(tmp_path: Path) -> None:
+    source = tmp_path / "requirements.md"
+    source.write_text("x")
+    printed: list[str] = []
+    state = SimpleNamespace(
+        run_id="r1",
+        status="passed",
+        completed_features=2,
+        total_features=3,
+        run_dir="/tmp/run",
+    )
+
+    with patch("ncdev.cli.run_v3_full", return_value=state):
+        with patch("ncdev.cli.console.print", side_effect=lambda *args, **kwargs: printed.append(str(args[0]))):
+            with patch("sys.argv", ["ncdev", "full", "--source", str(source), "--dry-run"]):
+                assert main() == 0
+
+    assert any("features: 2/3 completed" in line for line in printed)
diff --git a/tests/test_ncdev_v3/test_engine.py b/tests/test_ncdev_v3/test_engine.py
new file mode 100644
index 0000000000000000000000000000000000000000..d4c48cda3f6e41c3ca90e7483dc2d8578b7a7940
--- /dev/null
+++ b/tests/test_ncdev_v3/test_engine.py
@@ -0,0 +1,67 @@
+from __future__ import annotations
+
+from pathlib import Path
+from types import SimpleNamespace
+
+from ncdev.v3.engine import run_v3_full
+from ncdev.v3.models import (
+    CharterBundle,
+    FeatureQueueDoc,
+    FeatureStep,
+    StepResult,
+    StepStatus,
+    TargetProjectContract,
+    VerificationContract,
+)
+
+
+def _bundle(*features: FeatureStep) -> CharterBundle:
+    return CharterBundle(
+        contract=TargetProjectContract(project_name="proj", project_type="web"),
+        verification=VerificationContract(),
+        feature_queue=FeatureQueueDoc(project_name="proj", features=list(features)),
+    )
+
+
+def test_run_v3_full_persists_brownfield_skips_in_progress_state(tmp_path: Path, monkeypatch):
+    """State-scanner skips must show up immediately in persisted progress.
+
+    Before this fix, completed_steps/completed_features stayed at zero when
+    the scanner skipped features before the build loop ran, so a fully
+    brownfield/no-op run reported no completed work in state.json.
+    """
+    workspace = tmp_path / "ws"
+    workspace.mkdir()
+    source = workspace / "prd.md"
+    source.write_text("# PRD\n")
+    target = workspace / "target"
+    target.mkdir()
+
+    feature = FeatureStep(
+        feature_id="f1",
+        title="Already done",
+        description="",
+        acceptance_criteria=[],
+    )
+    bundle = _bundle(feature)
+
+    monkeypatch.setattr("ncdev.v3.engine.generate_charter", lambda **kwargs: (bundle, SimpleNamespace(summary=lambda: "ok")))
+    monkeypatch.setattr("ncdev.v3.engine.run_design_phase", lambda **kwargs: SimpleNamespace(skipped=True, hard_failed=False, design_doc=None))
+    monkeypatch.setattr("ncdev.v3.state_scanner.scan_completed_features", lambda target_path, features: ["f1"])
+    monkeypatch.setattr(
+        "ncdev.v3.state_scanner.build_skip_results",
+        lambda features, done_ids: [StepResult(feature_id="f1", status=StepStatus.SKIPPED)],
+    )
+
+    state = run_v3_full(
+        workspace=workspace,
+        source_path=source,
+        target_repo_path=target,
+        builder_model="claude-opus-4-6",
+    )
+
+    assert state.status == "passed"
+    assert state.completed_features == 1
+    assert len(state.completed_steps) == 1
+    assert state.completed_steps[0].status == StepStatus.SKIPPED
+
diff --git a/tests/unit/test_claude_executor.py b/tests/unit/test_claude_executor.py
index a08e209565101214bc64e0f710ac287b458bb03a..3261c2cbcac84262b510769fca4e661d2b9f008e
--- a/tests/unit/test_claude_executor.py
+++ b/tests/unit/test_claude_executor.py
@@ -294,6 +294,46 @@
     assert any("prohibited" in r.lower() for r in result.verification.failure_reasons)
 
 
+def test_legacy_prohibited_pattern_outside_touched_files_does_not_block_pass(tmp_path: Path):
+    """Post-hoc verification must stay feature-local.
+
+    A brownfield repo can contain an old TODO in some untouched file; that
+    should not fail a new clean feature, because the pre-commit hook only
+    guards staged content and the executor already scopes asset checks
+    feature-locally for the same reason.
+    """
+    target = tmp_path / "app"
+    target.mkdir()
+    _init_git(target)
+
+    # Legacy debt that predates this feature.
+    (target / "legacy.py").write_text("# TODO historical debt\n")
+    subprocess.run(["git", "add", "legacy.py"], cwd=str(target), check=True)
+    subprocess.run(["git", "commit", "-q", "-m", "feat(legacy): existing debt"],
+                   cwd=str(target), check=True)
+
+    def fake_session(prompt, **kwargs):  # noqa: ARG001
+        _seed_manifest(target, "f01-scaffold")
+        (target / "clean.py").write_text("x = 1\n")
+        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
+        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): clean"],
+                       cwd=str(target), check=True)
+        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)
+
+    bundle = _make_bundle()  # prohibited_patterns=["TODO"]
+    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):
+        result = execute_feature_claude_driven(
+            feature=_make_feature(),
+            target_path=target,
+            run_dir=tmp_path / "run",
+            charter_bundle=bundle,
+            prior_results=[],
+            project_id="myapp",
+        )
+
+    assert result.status == StepStatus.PASSED
+
+
 def test_verification_runs_backend_test_command_when_configured(tmp_path: Path):
     """New enforcement: backend_test_command actually runs, not just documented."""
     target = tmp_path / "app"

 succeeded in 993ms:
tests/unit/test_manifest_generator.py: 8
tests/unit/test_orchestrator.py: 13
tests/unit/test_quality_gate_events.py: 14
tests/unit/test_quality_gate_models.py: 11

      35 /tmp/ncdev-pytest-collect.txt

exec
/bin/zsh -lc "python3 -m pytest --collect-only -q > /tmp/ncdev-pytest-collect.txt && python3 - <<'PY'
from pathlib import Path
import re
text=Path('/tmp/ncdev-pytest-collect.txt').read_text()
nums=[int(m.group(1)) for m in re.finditer(r':\\s+(\\d+)\\s*"'$'"', text, re.M)]
print(sum(nums))
PY" in /Users/nrupal/dev/yensi/dev/nc-dev-system
diff --git a/src/ncdev/cli.py b/src/ncdev/cli.py
index 78347ed18abd9502b64378f77fe7d52c8c01d42e..b9f4d9dd0e16042063902ff869cc2bbc5fd2d255
--- a/src/ncdev/cli.py
+++ b/src/ncdev/cli.py
@@ -373,7 +373,7 @@
             strict_deps=bool(getattr(args, "strict_deps", False)),
         )
         console.print(f"run_id={state.run_id} status={state.status}")
-        console.print(f"features: {state.completed_features}/{state.total_features} passed")
+        console.print(f"features: {state.completed_features}/{state.total_features} completed")
         console.print(f"run_dir={state.run_dir}")
         if state.status != "passed":
             return 1
diff --git a/src/ncdev/v3/claude_executor.py b/src/ncdev/v3/claude_executor.py
index 973459e5f764d4bf2d0bde198747c6949f216bd5..9fc826c2d005686dea54106495ec650aa569ce7b
--- a/src/ncdev/v3/claude_executor.py
+++ b/src/ncdev/v3/claude_executor.py
@@ -351,10 +351,13 @@
                 reasons.append(f"asset references without manifest: {missing[:5]}")
 
     # 3. Prohibited patterns (regex — treats entries in the contract as
-    #    patterns, falls back to literal match if the regex fails to compile)
+    #    patterns, falls back to literal match if the regex fails to compile).
+    #    Feature-local scope matters here for the same reason it matters for
+    #    asset manifests: one legacy TODO elsewhere in a brownfield repo should
+    #    not fail every future feature.
     patterns = bundle.verification.prohibited_patterns
     if patterns:
-        bad = _grep_for_prohibited(target_path, patterns)
+        bad = _grep_for_prohibited(target_path, patterns, touched_files=touched_files)
         if bad:
             reasons.append(f"prohibited patterns found: {bad[:5]}")
 
@@ -422,12 +425,20 @@
     return ver
 
 
-def _grep_for_prohibited(target_path: Path, patterns: list[str]) -> list[str]:
+def _grep_for_prohibited(
+    target_path: Path,
+    patterns: list[str],
+    *,
+    touched_files: list[str] | None = None,
+) -> list[str]:
     """Scan git-tracked files for prohibited patterns.
 
     Each entry is treated as a regular expression via ``re.search``. If
     a pattern fails to compile, falls back to a substring check so
     human-written entries like ``TODO`` still work.
+
+    When ``touched_files`` is provided, only scan that feature-local set.
+    This keeps brownfield legacy debt from failing unrelated future work.
     """
     compiled: list[tuple[str, re.Pattern[str] | None]] = []
     for pat in patterns:
@@ -444,10 +455,15 @@
         )
         if ls.returncode != 0:
             return []
-        files = [f for f in ls.stdout.splitlines() if f]
+        tracked_files = {f for f in ls.stdout.splitlines() if f}
     except (subprocess.TimeoutExpired, FileNotFoundError):
         return []
 
+    if touched_files is not None:
+        files = [f for f in touched_files if f in tracked_files]
+    else:
+        files = sorted(tracked_files)
+
     for f in files:
         fp = target_path / f
         try:
diff --git a/src/ncdev/v3/engine.py b/src/ncdev/v3/engine.py
index 86cebe171c78ff9d0fded0c142a6793f98ca4944..78a18f3debbfd201af46ad4254db8d29afbb8aa5
--- a/src/ncdev/v3/engine.py
+++ b/src/ncdev/v3/engine.py
@@ -207,6 +207,8 @@
 
         # Brownfield: skip features already implemented
         remaining = _filter_completed_features(target_path, features, completed)
+        _sync_progress_state(state, completed)
+        _persist_state(state, run_dir)
         console.print(f"\n[bold]Phase 5: Building {len(remaining)} features sequentially[/bold]")
 
         for feature in remaining:
@@ -231,7 +233,7 @@
                     status=StepStatus.BLOCKED,
                     error_message=reason,
                 ))
-                state.completed_steps = completed
+                _sync_progress_state(state, completed)
                 _persist_state(state, run_dir)
                 if strict_deps:
                     console.print("[red]--strict-deps set: halting run[/red]")
@@ -256,14 +258,7 @@
                 config=config,
             )
             completed.append(result)
-            state.completed_steps = completed
-            # Count PASSED + SKIPPED — both are "done from NC Dev's
-            # perspective". SKIPPED = brownfield state scanner already
-            # found them in the target repo; PASSED = built this run.
-            state.completed_features = len([
-                r for r in completed
-                if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
-            ])
+            _sync_progress_state(state, completed)
             _persist_state(state, run_dir)
 
             status_style = "green" if result.status == StepStatus.PASSED else "red"
@@ -362,3 +357,14 @@
 def _persist_state(state: V3RunState, run_dir: Path) -> None:
     run_dir.mkdir(parents=True, exist_ok=True)
     (run_dir / "state.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")
+
+
+def _sync_progress_state(state: V3RunState, completed: list[StepResult]) -> None:
+    """Keep persisted progress counters in sync with the completed list."""
+    state.completed_steps = list(completed)
+    # Count PASSED + SKIPPED — both are "done from NC Dev's perspective".
+    # SKIPPED means the brownfield state scanner found them already present;
+    # PASSED means they were built successfully during this run.
+    state.completed_features = sum(
+        1 for r in completed if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
+    )
diff --git a/tests/test_cli.py b/tests/test_cli.py
index 6e1d69ab2f720b5fd71b603de93f8d2967eb7c95..395d8c6e8ff314a3735129c59434f9c31c171365
--- a/tests/test_cli.py
+++ b/tests/test_cli.py
@@ -1,6 +1,8 @@
 from pathlib import Path
+from types import SimpleNamespace
+from unittest.mock import patch
 
-from ncdev.cli import _doctor_report, _quickstart_text, _resolve_target_repo, build_parser
+from ncdev.cli import _doctor_report, _quickstart_text, _resolve_target_repo, build_parser, main
 
 
 def test_cli_quickstart_parses() -> None:
@@ -87,3 +89,23 @@
     (tmp_path / ".git").mkdir()
     _, report = _doctor_report(tmp_path)
     assert "git repository" in report
+
+
+def test_cli_full_reports_completed_not_passed(tmp_path: Path) -> None:
+    source = tmp_path / "requirements.md"
+    source.write_text("x")
+    printed: list[str] = []
+    state = SimpleNamespace(
+        run_id="r1",
+        status="passed",
+        completed_features=2,
+        total_features=3,
+        run_dir="/tmp/run",
+    )
+
+    with patch("ncdev.cli.run_v3_full", return_value=state):
+        with patch("ncdev.cli.console.print", side_effect=lambda *args, **kwargs: printed.append(str(args[0]))):
+            with patch("sys.argv", ["ncdev", "full", "--source", str(source), "--dry-run"]):
+                assert main() == 0
+
+    assert any("features: 2/3 completed" in line for line in printed)
diff --git a/tests/test_ncdev_v3/test_engine.py b/tests/test_ncdev_v3/test_engine.py
new file mode 100644
index 0000000000000000000000000000000000000000..d4c48cda3f6e41c3ca90e7483dc2d8578b7a7940
--- /dev/null
+++ b/tests/test_ncdev_v3/test_engine.py
@@ -0,0 +1,67 @@
+from __future__ import annotations
+
+from pathlib import Path
+from types import SimpleNamespace
+
+from ncdev.v3.engine import run_v3_full
+from ncdev.v3.models import (
+    CharterBundle,
+    FeatureQueueDoc,
+    FeatureStep,
+    StepResult,
+    StepStatus,
+    TargetProjectContract,
+    VerificationContract,
+)
+
+
+def _bundle(*features: FeatureStep) -> CharterBundle:
+    return CharterBundle(
+        contract=TargetProjectContract(project_name="proj", project_type="web"),
+        verification=VerificationContract(),
+        feature_queue=FeatureQueueDoc(project_name="proj", features=list(features)),
+    )
+
+
+def test_run_v3_full_persists_brownfield_skips_in_progress_state(tmp_path: Path, monkeypatch):
+    """State-scanner skips must show up immediately in persisted progress.
+
+    Before this fix, completed_steps/completed_features stayed at zero when
+    the scanner skipped features before the build loop ran, so a fully
+    brownfield/no-op run reported no completed work in state.json.
+    """
+    workspace = tmp_path / "ws"
+    workspace.mkdir()
+    source = workspace / "prd.md"
+    source.write_text("# PRD\n")
+    target = workspace / "target"
+    target.mkdir()
+
+    feature = FeatureStep(
+        feature_id="f1",
+        title="Already done",
+        description="",
+        acceptance_criteria=[],
+    )
+    bundle = _bundle(feature)
+
+    monkeypatch.setattr("ncdev.v3.engine.generate_charter", lambda **kwargs: (bundle, SimpleNamespace(summary=lambda: "ok")))
+    monkeypatch.setattr("ncdev.v3.engine.run_design_phase", lambda **kwargs: SimpleNamespace(skipped=True, hard_failed=False, design_doc=None))
+    monkeypatch.setattr("ncdev.v3.state_scanner.scan_completed_features", lambda target_path, features: ["f1"])
+    monkeypatch.setattr(
+        "ncdev.v3.state_scanner.build_skip_results",
+        lambda features, done_ids: [StepResult(feature_id="f1", status=StepStatus.SKIPPED)],
+    )
+
+    state = run_v3_full(
+        workspace=workspace,
+        source_path=source,
+        target_repo_path=target,
+        builder_model="claude-opus-4-6",
+    )
+
+    assert state.status == "passed"
+    assert state.completed_features == 1
+    assert len(state.completed_steps) == 1
+    assert state.completed_steps[0].status == StepStatus.SKIPPED
+
diff --git a/tests/unit/test_claude_executor.py b/tests/unit/test_claude_executor.py
index a08e209565101214bc64e0f710ac287b458bb03a..3261c2cbcac84262b510769fca4e661d2b9f008e
--- a/tests/unit/test_claude_executor.py
+++ b/tests/unit/test_claude_executor.py
@@ -294,6 +294,46 @@
     assert any("prohibited" in r.lower() for r in result.verification.failure_reasons)
 
 
+def test_legacy_prohibited_pattern_outside_touched_files_does_not_block_pass(tmp_path: Path):
+    """Post-hoc verification must stay feature-local.
+
+    A brownfield repo can contain an old TODO in some untouched file; that
+    should not fail a new clean feature, because the pre-commit hook only
+    guards staged content and the executor already scopes asset checks
+    feature-locally for the same reason.
+    """
+    target = tmp_path / "app"
+    target.mkdir()
+    _init_git(target)
+
+    # Legacy debt that predates this feature.
+    (target / "legacy.py").write_text("# TODO historical debt\n")
+    subprocess.run(["git", "add", "legacy.py"], cwd=str(target), check=True)
+    subprocess.run(["git", "commit", "-q", "-m", "feat(legacy): existing debt"],
+                   cwd=str(target), check=True)
+
+    def fake_session(prompt, **kwargs):  # noqa: ARG001
+        _seed_manifest(target, "f01-scaffold")
+        (target / "clean.py").write_text("x = 1\n")
+        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
+        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): clean"],
+                       cwd=str(target), check=True)
+        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)
+
+    bundle = _make_bundle()  # prohibited_patterns=["TODO"]
+    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):
+        result = execute_feature_claude_driven(
+            feature=_make_feature(),
+            target_path=target,
+            run_dir=tmp_path / "run",
+            charter_bundle=bundle,
+            prior_results=[],
+            project_id="myapp",
+        )
+
+    assert result.status == StepStatus.PASSED
+
+
 def test_verification_runs_backend_test_command_when_configured(tmp_path: Path):
     """New enforcement: backend_test_command actually runs, not just documented."""
     target = tmp_path / "app"

 succeeded in 1070ms:
429

codex
The full suite is green. I’m doing one last pass over the touched surfaces for any stale migration artifacts or comment drift, then I’ll summarize exactly what changed and what I left alone.
apply patch
patch: completed
/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/ai_session.py
diff --git a/src/ncdev/ai_session.py b/src/ncdev/ai_session.py
index dd4ce818bb950f8ffe908b358ebc0556737004a6..5351963af41df2b75167d93a82f2a1252f923efd
--- a/src/ncdev/ai_session.py
+++ b/src/ncdev/ai_session.py
@@ -12,7 +12,8 @@
       Codex handles the whole task directly.
     * ``openrouter`` → raises ``NotImplementedError`` (API-only, no CLI
       tooling). Caller should fall back or surface to the user.
-    * ``custom`` → falls back to Claude orchestrator as a safe default.
+    * ``custom`` → resolves orchestrator + implementer from the
+      hand-tuned ``routing:`` block.
 
 The returned :class:`ClaudeSessionResult` is the common result shape
 across runners — ``skills_invoked`` and ``codex_invocations`` are
diff --git a/src/ncdev/cli.py b/src/ncdev/cli.py
index 78347ed18abd9502b64378f77fe7d52c8c01d42e..b9f4d9dd0e16042063902ff869cc2bbc5fd2d255
--- a/src/ncdev/cli.py
+++ b/src/ncdev/cli.py
@@ -373,7 +373,7 @@
             strict_deps=bool(getattr(args, "strict_deps", False)),
         )
         console.print(f"run_id={state.run_id} status={state.status}")
-        console.print(f"features: {state.completed_features}/{state.total_features} passed")
+        console.print(f"features: {state.completed_features}/{state.total_features} completed")
         console.print(f"run_dir={state.run_dir}")
         if state.status != "passed":
             return 1
diff --git a/src/ncdev/v3/claude_executor.py b/src/ncdev/v3/claude_executor.py
index 973459e5f764d4bf2d0bde198747c6949f216bd5..9fc826c2d005686dea54106495ec650aa569ce7b
--- a/src/ncdev/v3/claude_executor.py
+++ b/src/ncdev/v3/claude_executor.py
@@ -351,10 +351,13 @@
                 reasons.append(f"asset references without manifest: {missing[:5]}")
 
     # 3. Prohibited patterns (regex — treats entries in the contract as
-    #    patterns, falls back to literal match if the regex fails to compile)
+    #    patterns, falls back to literal match if the regex fails to compile).
+    #    Feature-local scope matters here for the same reason it matters for
+    #    asset manifests: one legacy TODO elsewhere in a brownfield repo should
+    #    not fail every future feature.
     patterns = bundle.verification.prohibited_patterns
     if patterns:
-        bad = _grep_for_prohibited(target_path, patterns)
+        bad = _grep_for_prohibited(target_path, patterns, touched_files=touched_files)
         if bad:
             reasons.append(f"prohibited patterns found: {bad[:5]}")
 
@@ -422,12 +425,20 @@
     return ver
 
 
-def _grep_for_prohibited(target_path: Path, patterns: list[str]) -> list[str]:
+def _grep_for_prohibited(
+    target_path: Path,
+    patterns: list[str],
+    *,
+    touched_files: list[str] | None = None,
+) -> list[str]:
     """Scan git-tracked files for prohibited patterns.
 
     Each entry is treated as a regular expression via ``re.search``. If
     a pattern fails to compile, falls back to a substring check so
     human-written entries like ``TODO`` still work.
+
+    When ``touched_files`` is provided, only scan that feature-local set.
+    This keeps brownfield legacy debt from failing unrelated future work.
     """
     compiled: list[tuple[str, re.Pattern[str] | None]] = []
     for pat in patterns:
@@ -444,10 +455,15 @@
         )
         if ls.returncode != 0:
             return []
-        files = [f for f in ls.stdout.splitlines() if f]
+        tracked_files = {f for f in ls.stdout.splitlines() if f}
     except (subprocess.TimeoutExpired, FileNotFoundError):
         return []
 
+    if touched_files is not None:
+        files = [f for f in touched_files if f in tracked_files]
+    else:
+        files = sorted(tracked_files)
+
     for f in files:
         fp = target_path / f
         try:
diff --git a/src/ncdev/v3/engine.py b/src/ncdev/v3/engine.py
index 86cebe171c78ff9d0fded0c142a6793f98ca4944..78a18f3debbfd201af46ad4254db8d29afbb8aa5
--- a/src/ncdev/v3/engine.py
+++ b/src/ncdev/v3/engine.py
@@ -207,6 +207,8 @@
 
         # Brownfield: skip features already implemented
         remaining = _filter_completed_features(target_path, features, completed)
+        _sync_progress_state(state, completed)
+        _persist_state(state, run_dir)
         console.print(f"\n[bold]Phase 5: Building {len(remaining)} features sequentially[/bold]")
 
         for feature in remaining:
@@ -231,7 +233,7 @@
                     status=StepStatus.BLOCKED,
                     error_message=reason,
                 ))
-                state.completed_steps = completed
+                _sync_progress_state(state, completed)
                 _persist_state(state, run_dir)
                 if strict_deps:
                     console.print("[red]--strict-deps set: halting run[/red]")
@@ -256,14 +258,7 @@
                 config=config,
             )
             completed.append(result)
-            state.completed_steps = completed
-            # Count PASSED + SKIPPED — both are "done from NC Dev's
-            # perspective". SKIPPED = brownfield state scanner already
-            # found them in the target repo; PASSED = built this run.
-            state.completed_features = len([
-                r for r in completed
-                if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
-            ])
+            _sync_progress_state(state, completed)
             _persist_state(state, run_dir)
 
             status_style = "green" if result.status == StepStatus.PASSED else "red"
@@ -362,3 +357,14 @@
 def _persist_state(state: V3RunState, run_dir: Path) -> None:
     run_dir.mkdir(parents=True, exist_ok=True)
     (run_dir / "state.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")
+
+
+def _sync_progress_state(state: V3RunState, completed: list[StepResult]) -> None:
+    """Keep persisted progress counters in sync with the completed list."""
+    state.completed_steps = list(completed)
+    # Count PASSED + SKIPPED — both are "done from NC Dev's perspective".
+    # SKIPPED means the brownfield state scanner found them already present;
+    # PASSED means they were built successfully during this run.
+    state.completed_features = sum(
+        1 for r in completed if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
+    )
diff --git a/tests/test_cli.py b/tests/test_cli.py
index 6e1d69ab2f720b5fd71b603de93f8d2967eb7c95..395d8c6e8ff314a3735129c59434f9c31c171365
--- a/tests/test_cli.py
+++ b/tests/test_cli.py
@@ -1,6 +1,8 @@
 from pathlib import Path
+from types import SimpleNamespace
+from unittest.mock import patch
 
-from ncdev.cli import _doctor_report, _quickstart_text, _resolve_target_repo, build_parser
+from ncdev.cli import _doctor_report, _quickstart_text, _resolve_target_repo, build_parser, main
 
 
 def test_cli_quickstart_parses() -> None:
@@ -87,3 +89,23 @@
     (tmp_path / ".git").mkdir()
     _, report = _doctor_report(tmp_path)
     assert "git repository" in report
+
+
+def test_cli_full_reports_completed_not_passed(tmp_path: Path) -> None:
+    source = tmp_path / "requirements.md"
+    source.write_text("x")
+    printed: list[str] = []
+    state = SimpleNamespace(
+        run_id="r1",
+        status="passed",
+        completed_features=2,
+        total_features=3,
+        run_dir="/tmp/run",
+    )
+
+    with patch("ncdev.cli.run_v3_full", return_value=state):
+        with patch("ncdev.cli.console.print", side_effect=lambda *args, **kwargs: printed.append(str(args[0]))):
+            with patch("sys.argv", ["ncdev", "full", "--source", str(source), "--dry-run"]):
+                assert main() == 0
+
+    assert any("features: 2/3 completed" in line for line in printed)
diff --git a/tests/test_ncdev_v3/test_engine.py b/tests/test_ncdev_v3/test_engine.py
new file mode 100644
index 0000000000000000000000000000000000000000..d4c48cda3f6e41c3ca90e7483dc2d8578b7a7940
--- /dev/null
+++ b/tests/test_ncdev_v3/test_engine.py
@@ -0,0 +1,67 @@
+from __future__ import annotations
+
+from pathlib import Path
+from types import SimpleNamespace
+
+from ncdev.v3.engine import run_v3_full
+from ncdev.v3.models import (
+    CharterBundle,
+    FeatureQueueDoc,
+    FeatureStep,
+    StepResult,
+    StepStatus,
+    TargetProjectContract,
+    VerificationContract,
+)
+
+
+def _bundle(*features: FeatureStep) -> CharterBundle:
+    return CharterBundle(
+        contract=TargetProjectContract(project_name="proj", project_type="web"),
+        verification=VerificationContract(),
+        feature_queue=FeatureQueueDoc(project_name="proj", features=list(features)),
+    )
+
+
+def test_run_v3_full_persists_brownfield_skips_in_progress_state(tmp_path: Path, monkeypatch):
+    """State-scanner skips must show up immediately in persisted progress.
+
+    Before this fix, completed_steps/completed_features stayed at zero when
+    the scanner skipped features before the build loop ran, so a fully
+    brownfield/no-op run reported no completed work in state.json.
+    """
+    workspace = tmp_path / "ws"
+    workspace.mkdir()
+    source = workspace / "prd.md"
+    source.write_text("# PRD\n")
+    target = workspace / "target"
+    target.mkdir()
+
+    feature = FeatureStep(
+        feature_id="f1",
+        title="Already done",
+        description="",
+        acceptance_criteria=[],
+    )
+    bundle = _bundle(feature)
+
+    monkeypatch.setattr("ncdev.v3.engine.generate_charter", lambda **kwargs: (bundle, SimpleNamespace(summary=lambda: "ok")))
+    monkeypatch.setattr("ncdev.v3.engine.run_design_phase", lambda **kwargs: SimpleNamespace(skipped=True, hard_failed=False, design_doc=None))
+    monkeypatch.setattr("ncdev.v3.state_scanner.scan_completed_features", lambda target_path, features: ["f1"])
+    monkeypatch.setattr(
+        "ncdev.v3.state_scanner.build_skip_results",
+        lambda features, done_ids: [StepResult(feature_id="f1", status=StepStatus.SKIPPED)],
+    )
+
+    state = run_v3_full(
+        workspace=workspace,
+        source_path=source,
+        target_repo_path=target,
+        builder_model="claude-opus-4-6",
+    )
+
+    assert state.status == "passed"
+    assert state.completed_features == 1
+    assert len(state.completed_steps) == 1
+    assert state.completed_steps[0].status == StepStatus.SKIPPED
+
diff --git a/tests/unit/test_claude_executor.py b/tests/unit/test_claude_executor.py
index a08e209565101214bc64e0f710ac287b458bb03a..3261c2cbcac84262b510769fca4e661d2b9f008e
--- a/tests/unit/test_claude_executor.py
+++ b/tests/unit/test_claude_executor.py
@@ -294,6 +294,46 @@
     assert any("prohibited" in r.lower() for r in result.verification.failure_reasons)
 
 
+def test_legacy_prohibited_pattern_outside_touched_files_does_not_block_pass(tmp_path: Path):
+    """Post-hoc verification must stay feature-local.
+
+    A brownfield repo can contain an old TODO in some untouched file; that
+    should not fail a new clean feature, because the pre-commit hook only
+    guards staged content and the executor already scopes asset checks
+    feature-locally for the same reason.
+    """
+    target = tmp_path / "app"
+    target.mkdir()
+    _init_git(target)
+
+    # Legacy debt that predates this feature.
+    (target / "legacy.py").write_text("# TODO historical debt\n")
+    subprocess.run(["git", "add", "legacy.py"], cwd=str(target), check=True)
+    subprocess.run(["git", "commit", "-q", "-m", "feat(legacy): existing debt"],
+                   cwd=str(target), check=True)
+
+    def fake_session(prompt, **kwargs):  # noqa: ARG001
+        _seed_manifest(target, "f01-scaffold")
+        (target / "clean.py").write_text("x = 1\n")
+        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
+        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): clean"],
+                       cwd=str(target), check=True)
+        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)
+
+    bundle = _make_bundle()  # prohibited_patterns=["TODO"]
+    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):
+        result = execute_feature_claude_driven(
+            feature=_make_feature(),
+            target_path=target,
+            run_dir=tmp_path / "run",
+            charter_bundle=bundle,
+            prior_results=[],
+            project_id="myapp",
+        )
+
+    assert result.status == StepStatus.PASSED
+
+
 def test_verification_runs_backend_test_command_when_configured(tmp_path: Path):
     """New enforcement: backend_test_command actually runs, not just documented."""
     target = tmp_path / "app"

diff --git a/src/ncdev/ai_session.py b/src/ncdev/ai_session.py
index dd4ce818bb950f8ffe908b358ebc0556737004a6..5351963af41df2b75167d93a82f2a1252f923efd
--- a/src/ncdev/ai_session.py
+++ b/src/ncdev/ai_session.py
@@ -12,7 +12,8 @@
       Codex handles the whole task directly.
     * ``openrouter`` → raises ``NotImplementedError`` (API-only, no CLI
       tooling). Caller should fall back or surface to the user.
-    * ``custom`` → falls back to Claude orchestrator as a safe default.
+    * ``custom`` → resolves orchestrator + implementer from the
+      hand-tuned ``routing:`` block.
 
 The returned :class:`ClaudeSessionResult` is the common result shape
 across runners — ``skills_invoked`` and ``codex_invocations`` are
diff --git a/src/ncdev/cli.py b/src/ncdev/cli.py
index 78347ed18abd9502b64378f77fe7d52c8c01d42e..b9f4d9dd0e16042063902ff869cc2bbc5fd2d255
--- a/src/ncdev/cli.py
+++ b/src/ncdev/cli.py
@@ -373,7 +373,7 @@
             strict_deps=bool(getattr(args, "strict_deps", False)),
         )
         console.print(f"run_id={state.run_id} status={state.status}")
-        console.print(f"features: {state.completed_features}/{state.total_features} passed")
+        console.print(f"features: {state.completed_features}/{state.total_features} completed")
         console.print(f"run_dir={state.run_dir}")
         if state.status != "passed":
             return 1
diff --git a/src/ncdev/v3/claude_executor.py b/src/ncdev/v3/claude_executor.py
index 973459e5f764d4bf2d0bde198747c6949f216bd5..9fc826c2d005686dea54106495ec650aa569ce7b
--- a/src/ncdev/v3/claude_executor.py
+++ b/src/ncdev/v3/claude_executor.py
@@ -351,10 +351,13 @@
                 reasons.append(f"asset references without manifest: {missing[:5]}")
 
     # 3. Prohibited patterns (regex — treats entries in the contract as
-    #    patterns, falls back to literal match if the regex fails to compile)
+    #    patterns, falls back to literal match if the regex fails to compile).
+    #    Feature-local scope matters here for the same reason it matters for
+    #    asset manifests: one legacy TODO elsewhere in a brownfield repo should
+    #    not fail every future feature.
     patterns = bundle.verification.prohibited_patterns
     if patterns:
-        bad = _grep_for_prohibited(target_path, patterns)
+        bad = _grep_for_prohibited(target_path, patterns, touched_files=touched_files)
         if bad:
             reasons.append(f"prohibited patterns found: {bad[:5]}")
 
@@ -422,12 +425,20 @@
     return ver
 
 
-def _grep_for_prohibited(target_path: Path, patterns: list[str]) -> list[str]:
+def _grep_for_prohibited(
+    target_path: Path,
+    patterns: list[str],
+    *,
+    touched_files: list[str] | None = None,
+) -> list[str]:
     """Scan git-tracked files for prohibited patterns.
 
     Each entry is treated as a regular expression via ``re.search``. If
     a pattern fails to compile, falls back to a substring check so
     human-written entries like ``TODO`` still work.
+
+    When ``touched_files`` is provided, only scan that feature-local set.
+    This keeps brownfield legacy debt from failing unrelated future work.
     """
     compiled: list[tuple[str, re.Pattern[str] | None]] = []
     for pat in patterns:
@@ -444,10 +455,15 @@
         )
         if ls.returncode != 0:
             return []
-        files = [f for f in ls.stdout.splitlines() if f]
+        tracked_files = {f for f in ls.stdout.splitlines() if f}
     except (subprocess.TimeoutExpired, FileNotFoundError):
         return []
 
+    if touched_files is not None:
+        files = [f for f in touched_files if f in tracked_files]
+    else:
+        files = sorted(tracked_files)
+
     for f in files:
         fp = target_path / f
         try:
diff --git a/src/ncdev/v3/engine.py b/src/ncdev/v3/engine.py
index 86cebe171c78ff9d0fded0c142a6793f98ca4944..78a18f3debbfd201af46ad4254db8d29afbb8aa5
--- a/src/ncdev/v3/engine.py
+++ b/src/ncdev/v3/engine.py
@@ -207,6 +207,8 @@
 
         # Brownfield: skip features already implemented
         remaining = _filter_completed_features(target_path, features, completed)
+        _sync_progress_state(state, completed)
+        _persist_state(state, run_dir)
         console.print(f"\n[bold]Phase 5: Building {len(remaining)} features sequentially[/bold]")
 
         for feature in remaining:
@@ -231,7 +233,7 @@
                     status=StepStatus.BLOCKED,
                     error_message=reason,
                 ))
-                state.completed_steps = completed
+                _sync_progress_state(state, completed)
                 _persist_state(state, run_dir)
                 if strict_deps:
                     console.print("[red]--strict-deps set: halting run[/red]")
@@ -256,14 +258,7 @@
                 config=config,
             )
             completed.append(result)
-            state.completed_steps = completed
-            # Count PASSED + SKIPPED — both are "done from NC Dev's
-            # perspective". SKIPPED = brownfield state scanner already
-            # found them in the target repo; PASSED = built this run.
-            state.completed_features = len([
-                r for r in completed
-                if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
-            ])
+            _sync_progress_state(state, completed)
             _persist_state(state, run_dir)
 
             status_style = "green" if result.status == StepStatus.PASSED else "red"
@@ -362,3 +357,14 @@
 def _persist_state(state: V3RunState, run_dir: Path) -> None:
     run_dir.mkdir(parents=True, exist_ok=True)
     (run_dir / "state.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")
+
+
+def _sync_progress_state(state: V3RunState, completed: list[StepResult]) -> None:
+    """Keep persisted progress counters in sync with the completed list."""
+    state.completed_steps = list(completed)
+    # Count PASSED + SKIPPED — both are "done from NC Dev's perspective".
+    # SKIPPED means the brownfield state scanner found them already present;
+    # PASSED means they were built successfully during this run.
+    state.completed_features = sum(
+        1 for r in completed if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
+    )
diff --git a/tests/test_cli.py b/tests/test_cli.py
index 6e1d69ab2f720b5fd71b603de93f8d2967eb7c95..395d8c6e8ff314a3735129c59434f9c31c171365
--- a/tests/test_cli.py
+++ b/tests/test_cli.py
@@ -1,6 +1,8 @@
 from pathlib import Path
+from types import SimpleNamespace
+from unittest.mock import patch
 
-from ncdev.cli import _doctor_report, _quickstart_text, _resolve_target_repo, build_parser
+from ncdev.cli import _doctor_report, _quickstart_text, _resolve_target_repo, build_parser, main
 
 
 def test_cli_quickstart_parses() -> None:
@@ -87,3 +89,23 @@
     (tmp_path / ".git").mkdir()
     _, report = _doctor_report(tmp_path)
     assert "git repository" in report
+
+
+def test_cli_full_reports_completed_not_passed(tmp_path: Path) -> None:
+    source = tmp_path / "requirements.md"
+    source.write_text("x")
+    printed: list[str] = []
+    state = SimpleNamespace(
+        run_id="r1",
+        status="passed",
+        completed_features=2,
+        total_features=3,
+        run_dir="/tmp/run",
+    )
+
+    with patch("ncdev.cli.run_v3_full", return_value=state):
+        with patch("ncdev.cli.console.print", side_effect=lambda *args, **kwargs: printed.append(str(args[0]))):
+            with patch("sys.argv", ["ncdev", "full", "--source", str(source), "--dry-run"]):
+                assert main() == 0
+
+    assert any("features: 2/3 completed" in line for line in printed)
diff --git a/tests/test_ncdev_v3/test_engine.py b/tests/test_ncdev_v3/test_engine.py
new file mode 100644
index 0000000000000000000000000000000000000000..d4c48cda3f6e41c3ca90e7483dc2d8578b7a7940
--- /dev/null
+++ b/tests/test_ncdev_v3/test_engine.py
@@ -0,0 +1,67 @@
+from __future__ import annotations
+
+from pathlib import Path
+from types import SimpleNamespace
+
+from ncdev.v3.engine import run_v3_full
+from ncdev.v3.models import (
+    CharterBundle,
+    FeatureQueueDoc,
+    FeatureStep,
+    StepResult,
+    StepStatus,
+    TargetProjectContract,
+    VerificationContract,
+)
+
+
+def _bundle(*features: FeatureStep) -> CharterBundle:
+    return CharterBundle(
+        contract=TargetProjectContract(project_name="proj", project_type="web"),
+        verification=VerificationContract(),
+        feature_queue=FeatureQueueDoc(project_name="proj", features=list(features)),
+    )
+
+
+def test_run_v3_full_persists_brownfield_skips_in_progress_state(tmp_path: Path, monkeypatch):
+    """State-scanner skips must show up immediately in persisted progress.
+
+    Before this fix, completed_steps/completed_features stayed at zero when
+    the scanner skipped features before the build loop ran, so a fully
+    brownfield/no-op run reported no completed work in state.json.
+    """
+    workspace = tmp_path / "ws"
+    workspace.mkdir()
+    source = workspace / "prd.md"
+    source.write_text("# PRD\n")
+    target = workspace / "target"
+    target.mkdir()
+
+    feature = FeatureStep(
+        feature_id="f1",
+        title="Already done",
+        description="",
+        acceptance_criteria=[],
+    )
+    bundle = _bundle(feature)
+
+    monkeypatch.setattr("ncdev.v3.engine.generate_charter", lambda **kwargs: (bundle, SimpleNamespace(summary=lambda: "ok")))
+    monkeypatch.setattr("ncdev.v3.engine.run_design_phase", lambda **kwargs: SimpleNamespace(skipped=True, hard_failed=False, design_doc=None))
+    monkeypatch.setattr("ncdev.v3.state_scanner.scan_completed_features", lambda target_path, features: ["f1"])
+    monkeypatch.setattr(
+        "ncdev.v3.state_scanner.build_skip_results",
+        lambda features, done_ids: [StepResult(feature_id="f1", status=StepStatus.SKIPPED)],
+    )
+
+    state = run_v3_full(
+        workspace=workspace,
+        source_path=source,
+        target_repo_path=target,
+        builder_model="claude-opus-4-6",
+    )
+
+    assert state.status == "passed"
+    assert state.completed_features == 1
+    assert len(state.completed_steps) == 1
+    assert state.completed_steps[0].status == StepStatus.SKIPPED
+
diff --git a/tests/unit/test_claude_executor.py b/tests/unit/test_claude_executor.py
index a08e209565101214bc64e0f710ac287b458bb03a..3261c2cbcac84262b510769fca4e661d2b9f008e
--- a/tests/unit/test_claude_executor.py
+++ b/tests/unit/test_claude_executor.py
@@ -294,6 +294,46 @@
     assert any("prohibited" in r.lower() for r in result.verification.failure_reasons)
 
 
+def test_legacy_prohibited_pattern_outside_touched_files_does_not_block_pass(tmp_path: Path):
+    """Post-hoc verification must stay feature-local.
+
+    A brownfield repo can contain an old TODO in some untouched file; that
+    should not fail a new clean feature, because the pre-commit hook only
+    guards staged content and the executor already scopes asset checks
+    feature-locally for the same reason.
+    """
+    target = tmp_path / "app"
+    target.mkdir()
+    _init_git(target)
+
+    # Legacy debt that predates this feature.
+    (target / "legacy.py").write_text("# TODO historical debt\n")
+    subprocess.run(["git", "add", "legacy.py"], cwd=str(target), check=True)
+    subprocess.run(["git", "commit", "-q", "-m", "feat(legacy): existing debt"],
+                   cwd=str(target), check=True)
+
+    def fake_session(prompt, **kwargs):  # noqa: ARG001
+        _seed_manifest(target, "f01-scaffold")
+        (target / "clean.py").write_text("x = 1\n")
+        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
+        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): clean"],
+                       cwd=str(target), check=True)
+        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)
+
+    bundle = _make_bundle()  # prohibited_patterns=["TODO"]
+    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):
+        result = execute_feature_claude_driven(
+            feature=_make_feature(),
+            target_path=target,
+            run_dir=tmp_path / "run",
+            charter_bundle=bundle,
+            prior_results=[],
+            project_id="myapp",
+        )
+
+    assert result.status == StepStatus.PASSED
+
+
 def test_verification_runs_backend_test_command_when_configured(tmp_path: Path):
     """New enforcement: backend_test_command actually runs, not just documented."""
     target = tmp_path / "app"

Patched feature-local prohibited-pattern verification, synchronized brownfield skip progress/state accounting, corrected CLI progress wording, added regression coverage, and ran the full pytest suite successfully.
  ✓ Read prior review notes and inspect current branch/test state
  ✓ Identify remaining defects in load-bearing V3/session/hook code
  ✓ Implement targeted fixes and add regression tests
  ✓ Run full pytest suite and verify clean pass
diff --git a/src/ncdev/ai_session.py b/src/ncdev/ai_session.py
index dd4ce818bb950f8ffe908b358ebc0556737004a6..5351963af41df2b75167d93a82f2a1252f923efd
--- a/src/ncdev/ai_session.py
+++ b/src/ncdev/ai_session.py
@@ -12,7 +12,8 @@
       Codex handles the whole task directly.
     * ``openrouter`` → raises ``NotImplementedError`` (API-only, no CLI
       tooling). Caller should fall back or surface to the user.
-    * ``custom`` → falls back to Claude orchestrator as a safe default.
+    * ``custom`` → resolves orchestrator + implementer from the
+      hand-tuned ``routing:`` block.
 
 The returned :class:`ClaudeSessionResult` is the common result shape
 across runners — ``skills_invoked`` and ``codex_invocations`` are
diff --git a/src/ncdev/cli.py b/src/ncdev/cli.py
index 78347ed18abd9502b64378f77fe7d52c8c01d42e..b9f4d9dd0e16042063902ff869cc2bbc5fd2d255
--- a/src/ncdev/cli.py
+++ b/src/ncdev/cli.py
@@ -373,7 +373,7 @@
             strict_deps=bool(getattr(args, "strict_deps", False)),
         )
         console.print(f"run_id={state.run_id} status={state.status}")
-        console.print(f"features: {state.completed_features}/{state.total_features} passed")
+        console.print(f"features: {state.completed_features}/{state.total_features} completed")
         console.print(f"run_dir={state.run_dir}")
         if state.status != "passed":
             return 1
diff --git a/src/ncdev/v3/claude_executor.py b/src/ncdev/v3/claude_executor.py
index 973459e5f764d4bf2d0bde198747c6949f216bd5..9fc826c2d005686dea54106495ec650aa569ce7b
--- a/src/ncdev/v3/claude_executor.py
+++ b/src/ncdev/v3/claude_executor.py
@@ -351,10 +351,13 @@
                 reasons.append(f"asset references without manifest: {missing[:5]}")
 
     # 3. Prohibited patterns (regex — treats entries in the contract as
-    #    patterns, falls back to literal match if the regex fails to compile)
+    #    patterns, falls back to literal match if the regex fails to compile).
+    #    Feature-local scope matters here for the same reason it matters for
+    #    asset manifests: one legacy TODO elsewhere in a brownfield repo should
+    #    not fail every future feature.
     patterns = bundle.verification.prohibited_patterns
     if patterns:
-        bad = _grep_for_prohibited(target_path, patterns)
+        bad = _grep_for_prohibited(target_path, patterns, touched_files=touched_files)
         if bad:
             reasons.append(f"prohibited patterns found: {bad[:5]}")
 
@@ -422,12 +425,20 @@
     return ver
 
 
-def _grep_for_prohibited(target_path: Path, patterns: list[str]) -> list[str]:
+def _grep_for_prohibited(
+    target_path: Path,
+    patterns: list[str],
+    *,
+    touched_files: list[str] | None = None,
+) -> list[str]:
     """Scan git-tracked files for prohibited patterns.
 
     Each entry is treated as a regular expression via ``re.search``. If
     a pattern fails to compile, falls back to a substring check so
     human-written entries like ``TODO`` still work.
+
+    When ``touched_files`` is provided, only scan that feature-local set.
+    This keeps brownfield legacy debt from failing unrelated future work.
     """
     compiled: list[tuple[str, re.Pattern[str] | None]] = []
     for pat in patterns:
@@ -444,10 +455,15 @@
         )
         if ls.returncode != 0:
             return []
-        files = [f for f in ls.stdout.splitlines() if f]
+        tracked_files = {f for f in ls.stdout.splitlines() if f}
     except (subprocess.TimeoutExpired, FileNotFoundError):
         return []
 
+    if touched_files is not None:
+        files = [f for f in touched_files if f in tracked_files]
+    else:
+        files = sorted(tracked_files)
+
     for f in files:
         fp = target_path / f
         try:
diff --git a/src/ncdev/v3/engine.py b/src/ncdev/v3/engine.py
index 86cebe171c78ff9d0fded0c142a6793f98ca4944..78a18f3debbfd201af46ad4254db8d29afbb8aa5
--- a/src/ncdev/v3/engine.py
+++ b/src/ncdev/v3/engine.py
@@ -207,6 +207,8 @@
 
         # Brownfield: skip features already implemented
         remaining = _filter_completed_features(target_path, features, completed)
+        _sync_progress_state(state, completed)
+        _persist_state(state, run_dir)
         console.print(f"\n[bold]Phase 5: Building {len(remaining)} features sequentially[/bold]")
 
         for feature in remaining:
@@ -231,7 +233,7 @@
                     status=StepStatus.BLOCKED,
                     error_message=reason,
                 ))
-                state.completed_steps = completed
+                _sync_progress_state(state, completed)
                 _persist_state(state, run_dir)
                 if strict_deps:
                     console.print("[red]--strict-deps set: halting run[/red]")
@@ -256,14 +258,7 @@
                 config=config,
             )
             completed.append(result)
-            state.completed_steps = completed
-            # Count PASSED + SKIPPED — both are "done from NC Dev's
-            # perspective". SKIPPED = brownfield state scanner already
-            # found them in the target repo; PASSED = built this run.
-            state.completed_features = len([
-                r for r in completed
-                if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
-            ])
+            _sync_progress_state(state, completed)
             _persist_state(state, run_dir)
 
             status_style = "green" if result.status == StepStatus.PASSED else "red"
@@ -362,3 +357,14 @@
 def _persist_state(state: V3RunState, run_dir: Path) -> None:
     run_dir.mkdir(parents=True, exist_ok=True)
     (run_dir / "state.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")
+
+
+def _sync_progress_state(state: V3RunState, completed: list[StepResult]) -> None:
+    """Keep persisted progress counters in sync with the completed list."""
+    state.completed_steps = list(completed)
+    # Count PASSED + SKIPPED — both are "done from NC Dev's perspective".
+    # SKIPPED means the brownfield state scanner found them already present;
+    # PASSED means they were built successfully during this run.
+    state.completed_features = sum(
+        1 for r in completed if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
+    )
diff --git a/tests/test_cli.py b/tests/test_cli.py
index 6e1d69ab2f720b5fd71b603de93f8d2967eb7c95..395d8c6e8ff314a3735129c59434f9c31c171365
--- a/tests/test_cli.py
+++ b/tests/test_cli.py
@@ -1,6 +1,8 @@
 from pathlib import Path
+from types import SimpleNamespace
+from unittest.mock import patch
 
-from ncdev.cli import _doctor_report, _quickstart_text, _resolve_target_repo, build_parser
+from ncdev.cli import _doctor_report, _quickstart_text, _resolve_target_repo, build_parser, main
 
 
 def test_cli_quickstart_parses() -> None:
@@ -87,3 +89,23 @@
     (tmp_path / ".git").mkdir()
     _, report = _doctor_report(tmp_path)
     assert "git repository" in report
+
+
+def test_cli_full_reports_completed_not_passed(tmp_path: Path) -> None:
+    source = tmp_path / "requirements.md"
+    source.write_text("x")
+    printed: list[str] = []
+    state = SimpleNamespace(
+        run_id="r1",
+        status="passed",
+        completed_features=2,
+        total_features=3,
+        run_dir="/tmp/run",
+    )
+
+    with patch("ncdev.cli.run_v3_full", return_value=state):
+        with patch("ncdev.cli.console.print", side_effect=lambda *args, **kwargs: printed.append(str(args[0]))):
+            with patch("sys.argv", ["ncdev", "full", "--source", str(source), "--dry-run"]):
+                assert main() == 0
+
+    assert any("features: 2/3 completed" in line for line in printed)
diff --git a/tests/test_ncdev_v3/test_engine.py b/tests/test_ncdev_v3/test_engine.py
new file mode 100644
index 0000000000000000000000000000000000000000..d4c48cda3f6e41c3ca90e7483dc2d8578b7a7940
--- /dev/null
+++ b/tests/test_ncdev_v3/test_engine.py
@@ -0,0 +1,67 @@
+from __future__ import annotations
+
+from pathlib import Path
+from types import SimpleNamespace
+
+from ncdev.v3.engine import run_v3_full
+from ncdev.v3.models import (
+    CharterBundle,
+    FeatureQueueDoc,
+    FeatureStep,
+    StepResult,
+    StepStatus,
+    TargetProjectContract,
+    VerificationContract,
+)
+
+
+def _bundle(*features: FeatureStep) -> CharterBundle:
+    return CharterBundle(
+        contract=TargetProjectContract(project_name="proj", project_type="web"),
+        verification=VerificationContract(),
+        feature_queue=FeatureQueueDoc(project_name="proj", features=list(features)),
+    )
+
+
+def test_run_v3_full_persists_brownfield_skips_in_progress_state(tmp_path: Path, monkeypatch):
+    """State-scanner skips must show up immediately in persisted progress.
+
+    Before this fix, completed_steps/completed_features stayed at zero when
+    the scanner skipped features before the build loop ran, so a fully
+    brownfield/no-op run reported no completed work in state.json.
+    """
+    workspace = tmp_path / "ws"
+    workspace.mkdir()
+    source = workspace / "prd.md"
+    source.write_text("# PRD\n")
+    target = workspace / "target"
+    target.mkdir()
+
+    feature = FeatureStep(
+        feature_id="f1",
+        title="Already done",
+        description="",
+        acceptance_criteria=[],
+    )
+    bundle = _bundle(feature)
+
+    monkeypatch.setattr("ncdev.v3.engine.generate_charter", lambda **kwargs: (bundle, SimpleNamespace(summary=lambda: "ok")))
+    monkeypatch.setattr("ncdev.v3.engine.run_design_phase", lambda **kwargs: SimpleNamespace(skipped=True, hard_failed=False, design_doc=None))
+    monkeypatch.setattr("ncdev.v3.state_scanner.scan_completed_features", lambda target_path, features: ["f1"])
+    monkeypatch.setattr(
+        "ncdev.v3.state_scanner.build_skip_results",
+        lambda features, done_ids: [StepResult(feature_id="f1", status=StepStatus.SKIPPED)],
+    )
+
+    state = run_v3_full(
+        workspace=workspace,
+        source_path=source,
+        target_repo_path=target,
+        builder_model="claude-opus-4-6",
+    )
+
+    assert state.status == "passed"
+    assert state.completed_features == 1
+    assert len(state.completed_steps) == 1
+    assert state.completed_steps[0].status == StepStatus.SKIPPED
+
diff --git a/tests/unit/test_claude_executor.py b/tests/unit/test_claude_executor.py
index a08e209565101214bc64e0f710ac287b458bb03a..3261c2cbcac84262b510769fca4e661d2b9f008e
--- a/tests/unit/test_claude_executor.py
+++ b/tests/unit/test_claude_executor.py
@@ -294,6 +294,46 @@
     assert any("prohibited" in r.lower() for r in result.verification.failure_reasons)
 
 
+def test_legacy_prohibited_pattern_outside_touched_files_does_not_block_pass(tmp_path: Path):
+    """Post-hoc verification must stay feature-local.
+
+    A brownfield repo can contain an old TODO in some untouched file; that
+    should not fail a new clean feature, because the pre-commit hook only
+    guards staged content and the executor already scopes asset checks
+    feature-locally for the same reason.
+    """
+    target = tmp_path / "app"
+    target.mkdir()
+    _init_git(target)
+
+    # Legacy debt that predates this feature.
+    (target / "legacy.py").write_text("# TODO historical debt\n")
+    subprocess.run(["git", "add", "legacy.py"], cwd=str(target), check=True)
+    subprocess.run(["git", "commit", "-q", "-m", "feat(legacy): existing debt"],
+                   cwd=str(target), check=True)
+
+    def fake_session(prompt, **kwargs):  # noqa: ARG001
+        _seed_manifest(target, "f01-scaffold")
+        (target / "clean.py").write_text("x = 1\n")
+        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
+        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): clean"],
+                       cwd=str(target), check=True)
+        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)
+
+    bundle = _make_bundle()  # prohibited_patterns=["TODO"]
+    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):
+        result = execute_feature_claude_driven(
+            feature=_make_feature(),
+            target_path=target,
+            run_dir=tmp_path / "run",
+            charter_bundle=bundle,
+            prior_results=[],
+            project_id="myapp",
+        )
+
+    assert result.status == StepStatus.PASSED
+
+
 def test_verification_runs_backend_test_command_when_configured(tmp_path: Path):
     """New enforcement: backend_test_command actually runs, not just documented."""
     target = tmp_path / "app"

exec
/bin/zsh -lc 'git status --short' in /Users/nrupal/dev/yensi/dev/nc-dev-system
exec
/bin/zsh -lc 'git diff --stat' in /Users/nrupal/dev/yensi/dev/nc-dev-system
diff --git a/src/ncdev/ai_session.py b/src/ncdev/ai_session.py
index dd4ce818bb950f8ffe908b358ebc0556737004a6..5351963af41df2b75167d93a82f2a1252f923efd
--- a/src/ncdev/ai_session.py
+++ b/src/ncdev/ai_session.py
@@ -12,7 +12,8 @@
       Codex handles the whole task directly.
     * ``openrouter`` → raises ``NotImplementedError`` (API-only, no CLI
       tooling). Caller should fall back or surface to the user.
-    * ``custom`` → falls back to Claude orchestrator as a safe default.
+    * ``custom`` → resolves orchestrator + implementer from the
+      hand-tuned ``routing:`` block.
 
 The returned :class:`ClaudeSessionResult` is the common result shape
 across runners — ``skills_invoked`` and ``codex_invocations`` are
diff --git a/src/ncdev/cli.py b/src/ncdev/cli.py
index 78347ed18abd9502b64378f77fe7d52c8c01d42e..b9f4d9dd0e16042063902ff869cc2bbc5fd2d255
--- a/src/ncdev/cli.py
+++ b/src/ncdev/cli.py
@@ -373,7 +373,7 @@
             strict_deps=bool(getattr(args, "strict_deps", False)),
         )
         console.print(f"run_id={state.run_id} status={state.status}")
-        console.print(f"features: {state.completed_features}/{state.total_features} passed")
+        console.print(f"features: {state.completed_features}/{state.total_features} completed")
         console.print(f"run_dir={state.run_dir}")
         if state.status != "passed":
             return 1
diff --git a/src/ncdev/v3/claude_executor.py b/src/ncdev/v3/claude_executor.py
index 973459e5f764d4bf2d0bde198747c6949f216bd5..9fc826c2d005686dea54106495ec650aa569ce7b
--- a/src/ncdev/v3/claude_executor.py
+++ b/src/ncdev/v3/claude_executor.py
@@ -351,10 +351,13 @@
                 reasons.append(f"asset references without manifest: {missing[:5]}")
 
     # 3. Prohibited patterns (regex — treats entries in the contract as
-    #    patterns, falls back to literal match if the regex fails to compile)
+    #    patterns, falls back to literal match if the regex fails to compile).
+    #    Feature-local scope matters here for the same reason it matters for
+    #    asset manifests: one legacy TODO elsewhere in a brownfield repo should
+    #    not fail every future feature.
     patterns = bundle.verification.prohibited_patterns
     if patterns:
-        bad = _grep_for_prohibited(target_path, patterns)
+        bad = _grep_for_prohibited(target_path, patterns, touched_files=touched_files)
         if bad:
             reasons.append(f"prohibited patterns found: {bad[:5]}")
 
@@ -422,12 +425,20 @@
     return ver
 
 
-def _grep_for_prohibited(target_path: Path, patterns: list[str]) -> list[str]:
+def _grep_for_prohibited(
+    target_path: Path,
+    patterns: list[str],
+    *,
+    touched_files: list[str] | None = None,
+) -> list[str]:
     """Scan git-tracked files for prohibited patterns.
 
     Each entry is treated as a regular expression via ``re.search``. If
     a pattern fails to compile, falls back to a substring check so
     human-written entries like ``TODO`` still work.
+
+    When ``touched_files`` is provided, only scan that feature-local set.
+    This keeps brownfield legacy debt from failing unrelated future work.
     """
     compiled: list[tuple[str, re.Pattern[str] | None]] = []
     for pat in patterns:
@@ -444,10 +455,15 @@
         )
         if ls.returncode != 0:
             return []
-        files = [f for f in ls.stdout.splitlines() if f]
+        tracked_files = {f for f in ls.stdout.splitlines() if f}
     except (subprocess.TimeoutExpired, FileNotFoundError):
         return []
 
+    if touched_files is not None:
+        files = [f for f in touched_files if f in tracked_files]
+    else:
+        files = sorted(tracked_files)
+
     for f in files:
         fp = target_path / f
         try:
diff --git a/src/ncdev/v3/engine.py b/src/ncdev/v3/engine.py
index 86cebe171c78ff9d0fded0c142a6793f98ca4944..78a18f3debbfd201af46ad4254db8d29afbb8aa5
--- a/src/ncdev/v3/engine.py
+++ b/src/ncdev/v3/engine.py
@@ -207,6 +207,8 @@
 
         # Brownfield: skip features already implemented
         remaining = _filter_completed_features(target_path, features, completed)
+        _sync_progress_state(state, completed)
+        _persist_state(state, run_dir)
         console.print(f"\n[bold]Phase 5: Building {len(remaining)} features sequentially[/bold]")
 
         for feature in remaining:
@@ -231,7 +233,7 @@
                     status=StepStatus.BLOCKED,
                     error_message=reason,
                 ))
-                state.completed_steps = completed
+                _sync_progress_state(state, completed)
                 _persist_state(state, run_dir)
                 if strict_deps:
                     console.print("[red]--strict-deps set: halting run[/red]")
@@ -256,14 +258,7 @@
                 config=config,
             )
             completed.append(result)
-            state.completed_steps = completed
-            # Count PASSED + SKIPPED — both are "done from NC Dev's
-            # perspective". SKIPPED = brownfield state scanner already
-            # found them in the target repo; PASSED = built this run.
-            state.completed_features = len([
-                r for r in completed
-                if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
-            ])
+            _sync_progress_state(state, completed)
             _persist_state(state, run_dir)
 
             status_style = "green" if result.status == StepStatus.PASSED else "red"
@@ -362,3 +357,14 @@
 def _persist_state(state: V3RunState, run_dir: Path) -> None:
     run_dir.mkdir(parents=True, exist_ok=True)
     (run_dir / "state.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")
+
+
+def _sync_progress_state(state: V3RunState, completed: list[StepResult]) -> None:
+    """Keep persisted progress counters in sync with the completed list."""
+    state.completed_steps = list(completed)
+    # Count PASSED + SKIPPED — both are "done from NC Dev's perspective".
+    # SKIPPED means the brownfield state scanner found them already present;
+    # PASSED means they were built successfully during this run.
+    state.completed_features = sum(
+        1 for r in completed if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
+    )
diff --git a/tests/test_cli.py b/tests/test_cli.py
index 6e1d69ab2f720b5fd71b603de93f8d2967eb7c95..395d8c6e8ff314a3735129c59434f9c31c171365
--- a/tests/test_cli.py
+++ b/tests/test_cli.py
@@ -1,6 +1,8 @@
 from pathlib import Path
+from types import SimpleNamespace
+from unittest.mock import patch
 
-from ncdev.cli import _doctor_report, _quickstart_text, _resolve_target_repo, build_parser
+from ncdev.cli import _doctor_report, _quickstart_text, _resolve_target_repo, build_parser, main
 
 
 def test_cli_quickstart_parses() -> None:
@@ -87,3 +89,23 @@
     (tmp_path / ".git").mkdir()
     _, report = _doctor_report(tmp_path)
     assert "git repository" in report
+
+
+def test_cli_full_reports_completed_not_passed(tmp_path: Path) -> None:
+    source = tmp_path / "requirements.md"
+    source.write_text("x")
+    printed: list[str] = []
+    state = SimpleNamespace(
+        run_id="r1",
+        status="passed",
+        completed_features=2,
+        total_features=3,
+        run_dir="/tmp/run",
+    )
+
+    with patch("ncdev.cli.run_v3_full", return_value=state):
+        with patch("ncdev.cli.console.print", side_effect=lambda *args, **kwargs: printed.append(str(args[0]))):
+            with patch("sys.argv", ["ncdev", "full", "--source", str(source), "--dry-run"]):
+                assert main() == 0
+
+    assert any("features: 2/3 completed" in line for line in printed)
diff --git a/tests/test_ncdev_v3/test_engine.py b/tests/test_ncdev_v3/test_engine.py
new file mode 100644
index 0000000000000000000000000000000000000000..d4c48cda3f6e41c3ca90e7483dc2d8578b7a7940
--- /dev/null
+++ b/tests/test_ncdev_v3/test_engine.py
@@ -0,0 +1,67 @@
+from __future__ import annotations
+
+from pathlib import Path
+from types import SimpleNamespace
+
+from ncdev.v3.engine import run_v3_full
+from ncdev.v3.models import (
+    CharterBundle,
+    FeatureQueueDoc,
+    FeatureStep,
+    StepResult,
+    StepStatus,
+    TargetProjectContract,
+    VerificationContract,
+)
+
+
+def _bundle(*features: FeatureStep) -> CharterBundle:
+    return CharterBundle(
+        contract=TargetProjectContract(project_name="proj", project_type="web"),
+        verification=VerificationContract(),
+        feature_queue=FeatureQueueDoc(project_name="proj", features=list(features)),
+    )
+
+
+def test_run_v3_full_persists_brownfield_skips_in_progress_state(tmp_path: Path, monkeypatch):
+    """State-scanner skips must show up immediately in persisted progress.
+
+    Before this fix, completed_steps/completed_features stayed at zero when
+    the scanner skipped features before the build loop ran, so a fully
+    brownfield/no-op run reported no completed work in state.json.
+    """
+    workspace = tmp_path / "ws"
+    workspace.mkdir()
+    source = workspace / "prd.md"
+    source.write_text("# PRD\n")
+    target = workspace / "target"
+    target.mkdir()
+
+    feature = FeatureStep(
+        feature_id="f1",
+        title="Already done",
+        description="",
+        acceptance_criteria=[],
+    )
+    bundle = _bundle(feature)
+
+    monkeypatch.setattr("ncdev.v3.engine.generate_charter", lambda **kwargs: (bundle, SimpleNamespace(summary=lambda: "ok")))
+    monkeypatch.setattr("ncdev.v3.engine.run_design_phase", lambda **kwargs: SimpleNamespace(skipped=True, hard_failed=False, design_doc=None))
+    monkeypatch.setattr("ncdev.v3.state_scanner.scan_completed_features", lambda target_path, features: ["f1"])
+    monkeypatch.setattr(
+        "ncdev.v3.state_scanner.build_skip_results",
+        lambda features, done_ids: [StepResult(feature_id="f1", status=StepStatus.SKIPPED)],
+    )
+
+    state = run_v3_full(
+        workspace=workspace,
+        source_path=source,
+        target_repo_path=target,
+        builder_model="claude-opus-4-6",
+    )
+
+    assert state.status == "passed"
+    assert state.completed_features == 1
+    assert len(state.completed_steps) == 1
+    assert state.completed_steps[0].status == StepStatus.SKIPPED
+
diff --git a/tests/unit/test_claude_executor.py b/tests/unit/test_claude_executor.py
index a08e209565101214bc64e0f710ac287b458bb03a..3261c2cbcac84262b510769fca4e661d2b9f008e
--- a/tests/unit/test_claude_executor.py
+++ b/tests/unit/test_claude_executor.py
@@ -294,6 +294,46 @@
     assert any("prohibited" in r.lower() for r in result.verification.failure_reasons)
 
 
+def test_legacy_prohibited_pattern_outside_touched_files_does_not_block_pass(tmp_path: Path):
+    """Post-hoc verification must stay feature-local.
+
+    A brownfield repo can contain an old TODO in some untouched file; that
+    should not fail a new clean feature, because the pre-commit hook only
+    guards staged content and the executor already scopes asset checks
+    feature-locally for the same reason.
+    """
+    target = tmp_path / "app"
+    target.mkdir()
+    _init_git(target)
+
+    # Legacy debt that predates this feature.
+    (target / "legacy.py").write_text("# TODO historical debt\n")
+    subprocess.run(["git", "add", "legacy.py"], cwd=str(target), check=True)
+    subprocess.run(["git", "commit", "-q", "-m", "feat(legacy): existing debt"],
+                   cwd=str(target), check=True)
+
+    def fake_session(prompt, **kwargs):  # noqa: ARG001
+        _seed_manifest(target, "f01-scaffold")
+        (target / "clean.py").write_text("x = 1\n")
+        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
+        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): clean"],
+                       cwd=str(target), check=True)
+        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)
+
+    bundle = _make_bundle()  # prohibited_patterns=["TODO"]
+    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):
+        result = execute_feature_claude_driven(
+            feature=_make_feature(),
+            target_path=target,
+            run_dir=tmp_path / "run",
+            charter_bundle=bundle,
+            prior_results=[],
+            project_id="myapp",
+        )
+
+    assert result.status == StepStatus.PASSED
+
+
 def test_verification_runs_backend_test_command_when_configured(tmp_path: Path):
     """New enforcement: backend_test_command actually runs, not just documented."""
     target = tmp_path / "app"

 succeeded in 961ms:
 src/ncdev/ai_session.py            |  3 ++-
 src/ncdev/cli.py                   |  2 +-
 src/ncdev/v3/claude_executor.py    | 24 +++++++++++++++++++----
 src/ncdev/v3/engine.py             | 24 ++++++++++++++---------
 tests/test_cli.py                  | 24 ++++++++++++++++++++++-
 tests/unit/test_claude_executor.py | 40 ++++++++++++++++++++++++++++++++++++++
 6 files changed, 101 insertions(+), 16 deletions(-)

 succeeded in 968ms:
 M src/ncdev/ai_session.py
 M src/ncdev/cli.py
 M src/ncdev/v3/claude_executor.py
 M src/ncdev/v3/engine.py
 M tests/test_cli.py
 M tests/unit/test_claude_executor.py
?? docs/codex-review/review-request-round4.md
?? docs/codex-review/review-response-round4.md
?? docs/codex-review/round4-sweep-log.md
?? docs/codex-review/round4-sweep-task.md
?? tests/test_ncdev_v3/test_engine.py

codex
**Changes made**
- [src/ncdev/v3/claude_executor.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py): scoped prohibited-pattern verification to `touched_files` instead of scanning the whole tracked repo, so a legacy `TODO` in untouched brownfield code no longer fails unrelated features.
- [src/ncdev/v3/engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py): added centralized progress-state syncing so brownfield skips are reflected immediately in `completed_steps` and `completed_features`, including runs where everything is skipped before the build loop.
- [src/ncdev/cli.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/cli.py): fixed the `full` command summary line from `passed` to `completed`, which now matches the engine semantics after skipped features count toward completion.
- [src/ncdev/ai_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/ai_session.py): corrected a stale migration artifact in the module docstring so `custom` mode is described as routing-driven, not Claude-defaulted.
- [tests/unit/test_claude_executor.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/tests/unit/test_claude_executor.py): added regression coverage for brownfield legacy prohibited patterns outside the feature diff.
- [tests/test_ncdev_v3/test_engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/tests/test_ncdev_v3/test_engine.py): added coverage for all-skipped brownfield runs so state/progress persistence can’t silently regress again.
- [tests/test_cli.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/tests/test_cli.py): pinned the CLI wording fix for `completed` vs `passed`.

**Tests added**
- Brownfield legacy prohibited text outside `touched_files` does not fail a clean feature.
- `run_v3_full()` persists skipped brownfield features into run state before any build step runs.
- CLI `full` output reports `completed` counts, not `passed` counts.

**Tests result**
- `python3 -m pytest -q`
- `429 passed`

**Anything deferred**
- I did not broaden this into design-phase policy changes or larger scanner heuristics. The remaining things I saw there are more about tolerance/brittleness tradeoffs than clear correctness bugs, and they did not justify widening this pass.
- I left the untracked round-4 review docs alone.

**Ready to inherit?**
- Yes. No remaining blocker from this sweep.
diff --git a/src/ncdev/ai_session.py b/src/ncdev/ai_session.py
index dd4ce818bb950f8ffe908b358ebc0556737004a6..5351963af41df2b75167d93a82f2a1252f923efd
--- a/src/ncdev/ai_session.py
+++ b/src/ncdev/ai_session.py
@@ -12,7 +12,8 @@
       Codex handles the whole task directly.
     * ``openrouter`` → raises ``NotImplementedError`` (API-only, no CLI
       tooling). Caller should fall back or surface to the user.
-    * ``custom`` → falls back to Claude orchestrator as a safe default.
+    * ``custom`` → resolves orchestrator + implementer from the
+      hand-tuned ``routing:`` block.
 
 The returned :class:`ClaudeSessionResult` is the common result shape
 across runners — ``skills_invoked`` and ``codex_invocations`` are
diff --git a/src/ncdev/cli.py b/src/ncdev/cli.py
index 78347ed18abd9502b64378f77fe7d52c8c01d42e..b9f4d9dd0e16042063902ff869cc2bbc5fd2d255
--- a/src/ncdev/cli.py
+++ b/src/ncdev/cli.py
@@ -373,7 +373,7 @@
             strict_deps=bool(getattr(args, "strict_deps", False)),
         )
         console.print(f"run_id={state.run_id} status={state.status}")
-        console.print(f"features: {state.completed_features}/{state.total_features} passed")
+        console.print(f"features: {state.completed_features}/{state.total_features} completed")
         console.print(f"run_dir={state.run_dir}")
         if state.status != "passed":
             return 1
diff --git a/src/ncdev/v3/claude_executor.py b/src/ncdev/v3/claude_executor.py
index 973459e5f764d4bf2d0bde198747c6949f216bd5..9fc826c2d005686dea54106495ec650aa569ce7b
--- a/src/ncdev/v3/claude_executor.py
+++ b/src/ncdev/v3/claude_executor.py
@@ -351,10 +351,13 @@
                 reasons.append(f"asset references without manifest: {missing[:5]}")
 
     # 3. Prohibited patterns (regex — treats entries in the contract as
-    #    patterns, falls back to literal match if the regex fails to compile)
+    #    patterns, falls back to literal match if the regex fails to compile).
+    #    Feature-local scope matters here for the same reason it matters for
+    #    asset manifests: one legacy TODO elsewhere in a brownfield repo should
+    #    not fail every future feature.
     patterns = bundle.verification.prohibited_patterns
     if patterns:
-        bad = _grep_for_prohibited(target_path, patterns)
+        bad = _grep_for_prohibited(target_path, patterns, touched_files=touched_files)
         if bad:
             reasons.append(f"prohibited patterns found: {bad[:5]}")
 
@@ -422,12 +425,20 @@
     return ver
 
 
-def _grep_for_prohibited(target_path: Path, patterns: list[str]) -> list[str]:
+def _grep_for_prohibited(
+    target_path: Path,
+    patterns: list[str],
+    *,
+    touched_files: list[str] | None = None,
+) -> list[str]:
     """Scan git-tracked files for prohibited patterns.
 
     Each entry is treated as a regular expression via ``re.search``. If
     a pattern fails to compile, falls back to a substring check so
     human-written entries like ``TODO`` still work.
+
+    When ``touched_files`` is provided, only scan that feature-local set.
+    This keeps brownfield legacy debt from failing unrelated future work.
     """
     compiled: list[tuple[str, re.Pattern[str] | None]] = []
     for pat in patterns:
@@ -444,10 +455,15 @@
         )
         if ls.returncode != 0:
             return []
-        files = [f for f in ls.stdout.splitlines() if f]
+        tracked_files = {f for f in ls.stdout.splitlines() if f}
     except (subprocess.TimeoutExpired, FileNotFoundError):
         return []
 
+    if touched_files is not None:
+        files = [f for f in touched_files if f in tracked_files]
+    else:
+        files = sorted(tracked_files)
+
     for f in files:
         fp = target_path / f
         try:
diff --git a/src/ncdev/v3/engine.py b/src/ncdev/v3/engine.py
index 86cebe171c78ff9d0fded0c142a6793f98ca4944..78a18f3debbfd201af46ad4254db8d29afbb8aa5
--- a/src/ncdev/v3/engine.py
+++ b/src/ncdev/v3/engine.py
@@ -207,6 +207,8 @@
 
         # Brownfield: skip features already implemented
         remaining = _filter_completed_features(target_path, features, completed)
+        _sync_progress_state(state, completed)
+        _persist_state(state, run_dir)
         console.print(f"\n[bold]Phase 5: Building {len(remaining)} features sequentially[/bold]")
 
         for feature in remaining:
@@ -231,7 +233,7 @@
                     status=StepStatus.BLOCKED,
                     error_message=reason,
                 ))
-                state.completed_steps = completed
+                _sync_progress_state(state, completed)
                 _persist_state(state, run_dir)
                 if strict_deps:
                     console.print("[red]--strict-deps set: halting run[/red]")
@@ -256,14 +258,7 @@
                 config=config,
             )
             completed.append(result)
-            state.completed_steps = completed
-            # Count PASSED + SKIPPED — both are "done from NC Dev's
-            # perspective". SKIPPED = brownfield state scanner already
-            # found them in the target repo; PASSED = built this run.
-            state.completed_features = len([
-                r for r in completed
-                if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
-            ])
+            _sync_progress_state(state, completed)
             _persist_state(state, run_dir)
 
             status_style = "green" if result.status == StepStatus.PASSED else "red"
@@ -362,3 +357,14 @@
 def _persist_state(state: V3RunState, run_dir: Path) -> None:
     run_dir.mkdir(parents=True, exist_ok=True)
     (run_dir / "state.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")
+
+
+def _sync_progress_state(state: V3RunState, completed: list[StepResult]) -> None:
+    """Keep persisted progress counters in sync with the completed list."""
+    state.completed_steps = list(completed)
+    # Count PASSED + SKIPPED — both are "done from NC Dev's perspective".
+    # SKIPPED means the brownfield state scanner found them already present;
+    # PASSED means they were built successfully during this run.
+    state.completed_features = sum(
+        1 for r in completed if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
+    )
diff --git a/tests/test_cli.py b/tests/test_cli.py
index 6e1d69ab2f720b5fd71b603de93f8d2967eb7c95..395d8c6e8ff314a3735129c59434f9c31c171365
--- a/tests/test_cli.py
+++ b/tests/test_cli.py
@@ -1,6 +1,8 @@
 from pathlib import Path
+from types import SimpleNamespace
+from unittest.mock import patch
 
-from ncdev.cli import _doctor_report, _quickstart_text, _resolve_target_repo, build_parser
+from ncdev.cli import _doctor_report, _quickstart_text, _resolve_target_repo, build_parser, main
 
 
 def test_cli_quickstart_parses() -> None:
@@ -87,3 +89,23 @@
     (tmp_path / ".git").mkdir()
     _, report = _doctor_report(tmp_path)
     assert "git repository" in report
+
+
+def test_cli_full_reports_completed_not_passed(tmp_path: Path) -> None:
+    source = tmp_path / "requirements.md"
+    source.write_text("x")
+    printed: list[str] = []
+    state = SimpleNamespace(
+        run_id="r1",
+        status="passed",
+        completed_features=2,
+        total_features=3,
+        run_dir="/tmp/run",
+    )
+
+    with patch("ncdev.cli.run_v3_full", return_value=state):
+        with patch("ncdev.cli.console.print", side_effect=lambda *args, **kwargs: printed.append(str(args[0]))):
+            with patch("sys.argv", ["ncdev", "full", "--source", str(source), "--dry-run"]):
+                assert main() == 0
+
+    assert any("features: 2/3 completed" in line for line in printed)
diff --git a/tests/test_ncdev_v3/test_engine.py b/tests/test_ncdev_v3/test_engine.py
new file mode 100644
index 0000000000000000000000000000000000000000..d4c48cda3f6e41c3ca90e7483dc2d8578b7a7940
--- /dev/null
+++ b/tests/test_ncdev_v3/test_engine.py
@@ -0,0 +1,67 @@
+from __future__ import annotations
+
+from pathlib import Path
+from types import SimpleNamespace
+
+from ncdev.v3.engine import run_v3_full
+from ncdev.v3.models import (
+    CharterBundle,
+    FeatureQueueDoc,
+    FeatureStep,
+    StepResult,
+    StepStatus,
+    TargetProjectContract,
+    VerificationContract,
+)
+
+
+def _bundle(*features: FeatureStep) -> CharterBundle:
+    return CharterBundle(
+        contract=TargetProjectContract(project_name="proj", project_type="web"),
+        verification=VerificationContract(),
+        feature_queue=FeatureQueueDoc(project_name="proj", features=list(features)),
+    )
+
+
+def test_run_v3_full_persists_brownfield_skips_in_progress_state(tmp_path: Path, monkeypatch):
+    """State-scanner skips must show up immediately in persisted progress.
+
+    Before this fix, completed_steps/completed_features stayed at zero when
+    the scanner skipped features before the build loop ran, so a fully
+    brownfield/no-op run reported no completed work in state.json.
+    """
+    workspace = tmp_path / "ws"
+    workspace.mkdir()
+    source = workspace / "prd.md"
+    source.write_text("# PRD\n")
+    target = workspace / "target"
+    target.mkdir()
+
+    feature = FeatureStep(
+        feature_id="f1",
+        title="Already done",
+        description="",
+        acceptance_criteria=[],
+    )
+    bundle = _bundle(feature)
+
+    monkeypatch.setattr("ncdev.v3.engine.generate_charter", lambda **kwargs: (bundle, SimpleNamespace(summary=lambda: "ok")))
+    monkeypatch.setattr("ncdev.v3.engine.run_design_phase", lambda **kwargs: SimpleNamespace(skipped=True, hard_failed=False, design_doc=None))
+    monkeypatch.setattr("ncdev.v3.state_scanner.scan_completed_features", lambda target_path, features: ["f1"])
+    monkeypatch.setattr(
+        "ncdev.v3.state_scanner.build_skip_results",
+        lambda features, done_ids: [StepResult(feature_id="f1", status=StepStatus.SKIPPED)],
+    )
+
+    state = run_v3_full(
+        workspace=workspace,
+        source_path=source,
+        target_repo_path=target,
+        builder_model="claude-opus-4-6",
+    )
+
+    assert state.status == "passed"
+    assert state.completed_features == 1
+    assert len(state.completed_steps) == 1
+    assert state.completed_steps[0].status == StepStatus.SKIPPED
+
diff --git a/tests/unit/test_claude_executor.py b/tests/unit/test_claude_executor.py
index a08e209565101214bc64e0f710ac287b458bb03a..3261c2cbcac84262b510769fca4e661d2b9f008e
--- a/tests/unit/test_claude_executor.py
+++ b/tests/unit/test_claude_executor.py
@@ -294,6 +294,46 @@
     assert any("prohibited" in r.lower() for r in result.verification.failure_reasons)
 
 
+def test_legacy_prohibited_pattern_outside_touched_files_does_not_block_pass(tmp_path: Path):
+    """Post-hoc verification must stay feature-local.
+
+    A brownfield repo can contain an old TODO in some untouched file; that
+    should not fail a new clean feature, because the pre-commit hook only
+    guards staged content and the executor already scopes asset checks
+    feature-locally for the same reason.
+    """
+    target = tmp_path / "app"
+    target.mkdir()
+    _init_git(target)
+
+    # Legacy debt that predates this feature.
+    (target / "legacy.py").write_text("# TODO historical debt\n")
+    subprocess.run(["git", "add", "legacy.py"], cwd=str(target), check=True)
+    subprocess.run(["git", "commit", "-q", "-m", "feat(legacy): existing debt"],
+                   cwd=str(target), check=True)
+
+    def fake_session(prompt, **kwargs):  # noqa: ARG001
+        _seed_manifest(target, "f01-scaffold")
+        (target / "clean.py").write_text("x = 1\n")
+        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
+        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): clean"],
+                       cwd=str(target), check=True)
+        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)
+
+    bundle = _make_bundle()  # prohibited_patterns=["TODO"]
+    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):
+        result = execute_feature_claude_driven(
+            feature=_make_feature(),
+            target_path=target,
+            run_dir=tmp_path / "run",
+            charter_bundle=bundle,
+            prior_results=[],
+            project_id="myapp",
+        )
+
+    assert result.status == StepStatus.PASSED
+
+
 def test_verification_runs_backend_test_command_when_configured(tmp_path: Path):
     """New enforcement: backend_test_command actually runs, not just documented."""
     target = tmp_path / "app"

tokens used
152,694
**Changes made**
- [src/ncdev/v3/claude_executor.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py): scoped prohibited-pattern verification to `touched_files` instead of scanning the whole tracked repo, so a legacy `TODO` in untouched brownfield code no longer fails unrelated features.
- [src/ncdev/v3/engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py): added centralized progress-state syncing so brownfield skips are reflected immediately in `completed_steps` and `completed_features`, including runs where everything is skipped before the build loop.
- [src/ncdev/cli.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/cli.py): fixed the `full` command summary line from `passed` to `completed`, which now matches the engine semantics after skipped features count toward completion.
- [src/ncdev/ai_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/ai_session.py): corrected a stale migration artifact in the module docstring so `custom` mode is described as routing-driven, not Claude-defaulted.
- [tests/unit/test_claude_executor.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/tests/unit/test_claude_executor.py): added regression coverage for brownfield legacy prohibited patterns outside the feature diff.
- [tests/test_ncdev_v3/test_engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/tests/test_ncdev_v3/test_engine.py): added coverage for all-skipped brownfield runs so state/progress persistence can’t silently regress again.
- [tests/test_cli.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/tests/test_cli.py): pinned the CLI wording fix for `completed` vs `passed`.

**Tests added**
- Brownfield legacy prohibited text outside `touched_files` does not fail a clean feature.
- `run_v3_full()` persists skipped brownfield features into run state before any build step runs.
- CLI `full` output reports `completed` counts, not `passed` counts.

**Tests result**
- `python3 -m pytest -q`
- `429 passed`

**Anything deferred**
- I did not broaden this into design-phase policy changes or larger scanner heuristics. The remaining things I saw there are more about tolerance/brittleness tradeoffs than clear correctness bugs, and they did not justify widening this pass.
- I left the untracked round-4 review docs alone.

**Ready to inherit?**
- Yes. No remaining blocker from this sweep.
