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
6846:## Missing
6852:## Test coverage gaps
6859:## Honest one-liner
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

- No resume-after-crash logic. If engine dies mid-feature, the
  `state.json` is stale. Should there be an `ncdev resume <run_id>`?
- No cost reporting aggregation. Each session has `total_cost_usd`,
  but no run-level roll-up. The user will want "how much did this
  PRD cost?"
- No way for a feature to depend on a feature that's currently in
  a `[BROKEN]` state — do we proceed anyway? Block? Skip?
- No provision for Claude refusing a task (e.g. the feature is
  unclear). Right now this returns success with "I need clarification"
  in the final text and we accept it.

**What's over-engineered**

- Tell me honestly. The user wanted a thin system. Am I carrying
  state I don't need? Modules that could fold? Tests that test the
  mock rather than the behaviour?

**Test quality**


exec
/bin/zsh -lc 'git show --stat --summary --oneline f19934b && git diff --stat a91fd24..f19934b' in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
f19934b fix(hardening): address all critical issues from Codex review
 docs/codex-review/review-request.md           |  271 +
 docs/codex-review/review-response.md          | 6860 +++++++++++++++++++++++++
 scripts/ncdev-hooks/pre_bash_guard.py         |   53 +-
 src/ncdev/ai_session.py                       |  241 +
 src/ncdev/claude_session.py                   |  160 +-
 src/ncdev/cli.py                              |    3 +
 src/ncdev/dev.py                              |   20 +-
 src/ncdev/v3/asset_manifest.py                |   50 +-
 src/ncdev/v3/charter.py                       |   20 +-
 src/ncdev/v3/claude_executor.py               |  249 +-
 src/ncdev/v3/design_phase.py                  |  125 +-
 src/ncdev/v3/engine.py                        |   62 +-
 tests/test_ncdev_v3/test_dependency_gating.py |   66 +
 tests/unit/test_ai_session.py                 |  238 +
 tests/unit/test_asset_manifest.py             |   38 +
 tests/unit/test_charter.py                    |   21 +-
 tests/unit/test_claude_executor.py            |  112 +-
 tests/unit/test_claude_session.py             |  148 +-
 tests/unit/test_design_phase.py               |  108 +-
 tests/unit/test_dev.py                        |   15 +-
 tests/unit/test_hooks.py                      |   39 +-
 21 files changed, 8736 insertions(+), 163 deletions(-)
 create mode 100644 docs/codex-review/review-request.md
 create mode 100644 docs/codex-review/review-response.md
 create mode 100644 src/ncdev/ai_session.py
 create mode 100644 tests/test_ncdev_v3/test_dependency_gating.py
 create mode 100644 tests/unit/test_ai_session.py
 docs/codex-review/review-request.md           |  271 +
 docs/codex-review/review-response.md          | 6860 +++++++++++++++++++++++++
 scripts/ncdev-hooks/pre_bash_guard.py         |   53 +-
 src/ncdev/ai_session.py                       |  241 +
 src/ncdev/claude_session.py                   |  160 +-
 src/ncdev/cli.py                              |    3 +
 src/ncdev/dev.py                              |   20 +-
 src/ncdev/v3/asset_manifest.py                |   50 +-
 src/ncdev/v3/charter.py                       |   20 +-
 src/ncdev/v3/claude_executor.py               |  249 +-
 src/ncdev/v3/design_phase.py                  |  125 +-
 src/ncdev/v3/engine.py                        |   62 +-
 tests/test_ncdev_v3/test_dependency_gating.py |   66 +
 tests/unit/test_ai_session.py                 |  238 +
 tests/unit/test_asset_manifest.py             |   38 +
 tests/unit/test_charter.py                    |   21 +-
 tests/unit/test_claude_executor.py            |  112 +-
 tests/unit/test_claude_session.py             |  148 +-
 tests/unit/test_design_phase.py               |  108 +-
 tests/unit/test_dev.py                        |   15 +-
 tests/unit/test_hooks.py                      |   39 +-
 21 files changed, 8736 insertions(+), 163 deletions(-)

codex
I’ve got the prior review and hardening diff loaded. Next I’m pulling the exact old critical/concerning findings and the current implementations in the targeted files side by side so I can check behavior instead of trusting the new tests.
exec
/bin/zsh -lc "sed -n '6763,6865p' docs/codex-review/review-response.md" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
## Architecture verdict
The migration is directionally right: deleting the old prompt/router ladder and treating Claude Code as the actual orchestrator is the correct simplification. The problem is that the new control plane still assumes happy-path agent behavior in places where it needs to be adversarial, so several of the guarantees in the README are weaker than advertised.

## Strengths
- Centralizing all Claude spawning in [claude_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/claude_session.py:112) is the right primitive. The rest of V3 now depends on one process boundary instead of several ad hoc ones.
- The feature prompt in [claude_executor.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:57) is much healthier than the old mega-prompts: it points Claude at on-disk artifacts instead of inlining huge policy blobs.
- The hard-fail principle for greenfield UI is explicit in [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:230). That is the right default if the product requirement is “no generic AI styling.”
- The asset-manifest requirement is conceptually good. Having Claude write intent while building in [asset_manifest.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/asset_manifest.py:88) is better than reconstructing intent after the fact.
- The hook logic being factored into a pure `evaluate()` function in [pre_bash_guard.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/scripts/ncdev-hooks/pre_bash_guard.py:130) is a good testing seam.

## Critical issues
- The session timeout is not real, and stderr can deadlock the process. [claude_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/claude_session.py:258) blocks on `for line in proc.stdout`, so if Claude hangs without closing stdout you never reach `wait(timeout=...)`. At the same time, stderr is piped but not drained until after stdout EOF at [claude_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/claude_session.py:296), so a noisy stderr stream can block the child. Suggested fix: nonblocking/select-based reads or a threaded reader for both pipes, with a wall-clock timeout enforced outside the stdout iterator.
- The charter prompt contradicts the architecture and will reject valid greenfield+Stitch runs. In [charter.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/charter.py:104) the instruction is effectively “greenfield UI must write `charter-error.json` unless designs already exist on disk,” but your actual design decision point lives in Phase C. Phase B cannot know whether Stitch is configured, so this prompt can hard-fail perfectly valid runs before design phase starts.
- Design phase failures can silently pass. In [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:245), [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:261), and [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:298), you return success-path results without requiring `session.success` or a valid `design-system.json`. Then [engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:155) happily continues with `source=?`. That will turn design failures into downstream build weirdness instead of a clean stop.
- The verification contract is mostly unenforced. [models.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/models.py:195) defines boot URLs, test commands, screenshot requirements, and minimum test count, but [_post_session_verification](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:287) only checks required files, asset manifests, and prohibited patterns. A feature can “pass” without NC Dev ever verifying tests, app boot, screenshots, or test count.
- Failed dependencies do not block downstream features. The engine just keeps iterating in [engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:197), and the executor only passes prior `PASSED` ids into prompts at [claude_executor.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:189). There is no enforcement that `depends_on_features` must already be green. That will compound failures and produce misleading later results.
- The advertised mode switch is not actually driving V3. `MODE_PRESETS` lives in [v2/config.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v2/config.py:36), but `run_v3_full()` hardcodes Claude in [engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:57) and `run_dev()` hardcodes Claude in [dev.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/dev.py:216). The CLI `dev --mode` in [cli.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/cli.py:315) is a workflow hint, not the budget/provider mode you describe. That is a user-facing contract bug.
- MCP availability is inferred from one settings source and execution uses another. `stitch_available()` probes user config in [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:72), but `run_claude_session()` unconditionally injects `--settings scripts/ncdev-hooks/settings.json` in [claude_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/claude_session.py:208). If Claude treats `--settings` as replacement rather than merge, you can “detect” Stitch and then spawn a session without Stitch.
- Asset-manifest verification is global, not feature-local. [verify_manifest_covers_references](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/asset_manifest.py:196) scans the whole repo every feature. One legacy missing asset in brownfield code will fail every future feature, even if that feature never touched assets.

## Concerning but not critical
- `_extract_event_signals()` in [claude_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/claude_session.py:352) only understands one stream shape: `assistant.message.content[].tool_use`. That is brittle for metrics and Codex-call detection across Claude Code versions.
- `_commit_broken()` in [claude_executor.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:409) does not check `git add` or `git commit` return codes. Your PreToolUse hook does not intercept this Python-side subprocess anyway, so if git identity or a real repo hook rejects the commit, recoverability silently disappears.
- `_extract_commit_message()` in [pre_bash_guard.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/scripts/ncdev-hooks/pre_bash_guard.py:108) misparses escaped quotes and intentionally gives up on `-F`/heredoc forms, so commit-message enforcement is easy to bypass.
- Prohibited-pattern semantics are inconsistent. `VerificationContract` includes regex-like `r"except:\s*pass"` in [models.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/models.py:217), but both the hook and post-hoc verifier do substring checks in [pre_bash_guard.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/scripts/ncdev-hooks/pre_bash_guard.py:100) and [claude_executor.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:348), so that rule never actually matches.
- There are a couple of plain bugs in design handling: `_stitch_prompt()` points Claude at `outputs/../feature-queue.json` in [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:133), which is the wrong file, and `existing_design_system_present()` in [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:96) treats any non-empty file under `docs/design-system` as a valid system.

## Over-engineered / could be deleted
- Keeping full raw `events` in memory while also writing JSONL in [claude_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/claude_session.py:222) is expensive and probably unnecessary outside debug mode.
- The retained V2 mode/routing stack is now mostly ceremonial for V3. If V3 is the product, either wire it in for real or stop advertising it as the control plane.
- `max_repair_attempts` is dead compatibility ballast in [engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:59).
- `DESIGN_TOOLS` in [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:45) is too broad for the brownfield summarizer path; giving it `Edit`, `Bash`, and `Task` undermines the “read and summarise only” contract.

## Missing
- A real `ncdev resume <run_id>` path. You already persist state in [engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:286); not having a reentry path is the obvious next gap.
- Run-level cost aggregation. You store per-session cost in `signals.json`, but the engine never rolls it up into state or summary.
- A first-class “needs clarification / refused / non-actionable” outcome. Right now success is inferred from git side effects, not from whether Claude actually completed the request.
- Actual dependency policy for failed features: stop, skip dependents, or continue only behind an explicit flag.

## Test coverage gaps
- I could not reproduce the claimed suite run here: `python -m pytest -q` fails because `python` is Python 2.7 with no `pytest`, and `python3 -m pytest -q` also fails because `pytest` is not installed for `python3`. So I did static review of the tests, not an executed green run.
- The core process tests are heavily mocked. `_FakeProc` in [test_claude_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/tests/unit/test_claude_session.py:33) cannot expose the real deadlock cases: blocked stdout iteration, stderr backpressure, pipe closure, or partial-line behavior.
- There is no test for the most dangerous design-phase bug: successful session with missing/invalid `design-system.json` still letting the engine continue.
- There is no test that a failed feature blocks a dependent feature.
- There is no test that the V3 engine actually honors the advertised provider mode switch, because right now it does not.

## Honest one-liner
I’d inherit this codebase after a hardening pass, not today: the simplification is right, but the guarantees around timeout, verification, dependency gating, and MCP/design availability are still softer than the docs claim.
tokens used
161,225
## Architecture verdict
The migration is directionally right: deleting the old prompt/router ladder and treating Claude Code as the actual orchestrator is the correct simplification. The problem is that the new control plane still assumes happy-path agent behavior in places where it needs to be adversarial, so several of the guarantees in the README are weaker than advertised.

## Strengths
- Centralizing all Claude spawning in [claude_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/claude_session.py:112) is the right primitive. The rest of V3 now depends on one process boundary instead of several ad hoc ones.
- The feature prompt in [claude_executor.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:57) is much healthier than the old mega-prompts: it points Claude at on-disk artifacts instead of inlining huge policy blobs.
- The hard-fail principle for greenfield UI is explicit in [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:230). That is the right default if the product requirement is “no generic AI styling.”
- The asset-manifest requirement is conceptually good. Having Claude write intent while building in [asset_manifest.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/asset_manifest.py:88) is better than reconstructing intent after the fact.
- The hook logic being factored into a pure `evaluate()` function in [pre_bash_guard.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/scripts/ncdev-hooks/pre_bash_guard.py:130) is a good testing seam.

## Critical issues
- The session timeout is not real, and stderr can deadlock the process. [claude_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/claude_session.py:258) blocks on `for line in proc.stdout`, so if Claude hangs without closing stdout you never reach `wait(timeout=...)`. At the same time, stderr is piped but not drained until after stdout EOF at [claude_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/claude_session.py:296), so a noisy stderr stream can block the child. Suggested fix: nonblocking/select-based reads or a threaded reader for both pipes, with a wall-clock timeout enforced outside the stdout iterator.
- The charter prompt contradicts the architecture and will reject valid greenfield+Stitch runs. In [charter.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/charter.py:104) the instruction is effectively “greenfield UI must write `charter-error.json` unless designs already exist on disk,” but your actual design decision point lives in Phase C. Phase B cannot know whether Stitch is configured, so this prompt can hard-fail perfectly valid runs before design phase starts.
- Design phase failures can silently pass. In [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:245), [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:261), and [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:298), you return success-path results without requiring `session.success` or a valid `design-system.json`. Then [engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:155) happily continues with `source=?`. That will turn design failures into downstream build weirdness instead of a clean stop.
- The verification contract is mostly unenforced. [models.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/models.py:195) defines boot URLs, test commands, screenshot requirements, and minimum test count, but [_post_session_verification](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:287) only checks required files, asset manifests, and prohibited patterns. A feature can “pass” without NC Dev ever verifying tests, app boot, screenshots, or test count.
- Failed dependencies do not block downstream features. The engine just keeps iterating in [engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:197), and the executor only passes prior `PASSED` ids into prompts at [claude_executor.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:189). There is no enforcement that `depends_on_features` must already be green. That will compound failures and produce misleading later results.
- The advertised mode switch is not actually driving V3. `MODE_PRESETS` lives in [v2/config.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v2/config.py:36), but `run_v3_full()` hardcodes Claude in [engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:57) and `run_dev()` hardcodes Claude in [dev.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/dev.py:216). The CLI `dev --mode` in [cli.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/cli.py:315) is a workflow hint, not the budget/provider mode you describe. That is a user-facing contract bug.
- MCP availability is inferred from one settings source and execution uses another. `stitch_available()` probes user config in [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:72), but `run_claude_session()` unconditionally injects `--settings scripts/ncdev-hooks/settings.json` in [claude_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/claude_session.py:208). If Claude treats `--settings` as replacement rather than merge, you can “detect” Stitch and then spawn a session without Stitch.
- Asset-manifest verification is global, not feature-local. [verify_manifest_covers_references](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/asset_manifest.py:196) scans the whole repo every feature. One legacy missing asset in brownfield code will fail every future feature, even if that feature never touched assets.

## Concerning but not critical
- `_extract_event_signals()` in [claude_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/claude_session.py:352) only understands one stream shape: `assistant.message.content[].tool_use`. That is brittle for metrics and Codex-call detection across Claude Code versions.
- `_commit_broken()` in [claude_executor.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:409) does not check `git add` or `git commit` return codes. Your PreToolUse hook does not intercept this Python-side subprocess anyway, so if git identity or a real repo hook rejects the commit, recoverability silently disappears.
- `_extract_commit_message()` in [pre_bash_guard.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/scripts/ncdev-hooks/pre_bash_guard.py:108) misparses escaped quotes and intentionally gives up on `-F`/heredoc forms, so commit-message enforcement is easy to bypass.
- Prohibited-pattern semantics are inconsistent. `VerificationContract` includes regex-like `r"except:\s*pass"` in [models.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/models.py:217), but both the hook and post-hoc verifier do substring checks in [pre_bash_guard.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/scripts/ncdev-hooks/pre_bash_guard.py:100) and [claude_executor.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:348), so that rule never actually matches.
- There are a couple of plain bugs in design handling: `_stitch_prompt()` points Claude at `outputs/../feature-queue.json` in [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:133), which is the wrong file, and `existing_design_system_present()` in [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:96) treats any non-empty file under `docs/design-system` as a valid system.

## Over-engineered / could be deleted
- Keeping full raw `events` in memory while also writing JSONL in [claude_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/claude_session.py:222) is expensive and probably unnecessary outside debug mode.
- The retained V2 mode/routing stack is now mostly ceremonial for V3. If V3 is the product, either wire it in for real or stop advertising it as the control plane.
- `max_repair_attempts` is dead compatibility ballast in [engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:59).
- `DESIGN_TOOLS` in [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:45) is too broad for the brownfield summarizer path; giving it `Edit`, `Bash`, and `Task` undermines the “read and summarise only” contract.

## Missing
- A real `ncdev resume <run_id>` path. You already persist state in [engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:286); not having a reentry path is the obvious next gap.
- Run-level cost aggregation. You store per-session cost in `signals.json`, but the engine never rolls it up into state or summary.
- A first-class “needs clarification / refused / non-actionable” outcome. Right now success is inferred from git side effects, not from whether Claude actually completed the request.
- Actual dependency policy for failed features: stop, skip dependents, or continue only behind an explicit flag.

## Test coverage gaps
- I could not reproduce the claimed suite run here: `python -m pytest -q` fails because `python` is Python 2.7 with no `pytest`, and `python3 -m pytest -q` also fails because `pytest` is not installed for `python3`. So I did static review of the tests, not an executed green run.
- The core process tests are heavily mocked. `_FakeProc` in [test_claude_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/tests/unit/test_claude_session.py:33) cannot expose the real deadlock cases: blocked stdout iteration, stderr backpressure, pipe closure, or partial-line behavior.
- There is no test for the most dangerous design-phase bug: successful session with missing/invalid `design-system.json` still letting the engine continue.
- There is no test that a failed feature blocks a dependent feature.
- There is no test that the V3 engine actually honors the advertised provider mode switch, because right now it does not.

## Honest one-liner
I’d inherit this codebase after a hardening pass, not today: the simplification is right, but the guarantees around timeout, verification, dependency gating, and MCP/design availability are still softer than the docs claim.

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
import shutil
import subprocess
import time
from pathlib import Path
from typing import Callable, Iterable

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
MODE_ORCHESTRATOR: dict[str, str] = {
    "claude_plan_codex_build": "claude",
    "claude_only": "claude",
    "codex_only": "codex",
    "openrouter": "openrouter",
    "custom": "claude",   # safe default — custom may still want Claude orchestration
}

# Mode → who actually writes code. Used by the Claude runner to decide
# whether to inject the Codex-via-Bash protocol (i.e. "delegate impl
# to Codex") vs do the work itself.
MODE_IMPLEMENTER: dict[str, str] = {
    "claude_plan_codex_build": "codex",
    "claude_only": "claude",
    "codex_only": "codex",
    "openrouter": "openrouter",
    "custom": "codex",
}


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
) -> ClaudeSessionResult:
    """Run a Codex session. No skills, no subagents, no NC Dev hooks.

    Codex handles planning + implementation + testing + committing in
    one shot per invocation. This is the "lean mode" — you lose skill
    machinery and cross-feature reasoning quality in exchange for speed
    and lower cost.
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

    start = time.time()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        duration = time.time() - start
        stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
        return ClaudeSessionResult(
            success=False,
            final_text=(exc.stdout or "") if isinstance(exc.stdout, str) else "",
            exit_code=-1,
            duration_seconds=duration,
            stderr=stderr,
            error=f"codex session timed out after {timeout}s",
        )
    except FileNotFoundError:
        return ClaudeSessionResult(
            success=False, final_text="", exit_code=-1,
            error="codex CLI disappeared mid-invocation",
        )

    duration = time.time() - start
    final_text = proc.stdout or ""

    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            f"RUNNER: codex\nEXIT: {proc.returncode}\nDURATION: {duration:.1f}s\n\n"
            f"STDOUT:\n{final_text}\n\nSTDERR:\n{proc.stderr or ''}\n",
            encoding="utf-8",
        )

    return ClaudeSessionResult(
        success=proc.returncode == 0,
        final_text=final_text,
        exit_code=proc.returncode,
        duration_seconds=duration,
        stderr=proc.stderr or "",
        error=None if proc.returncode == 0 else f"codex exited with code {proc.returncode}",
    )

exec
/bin/zsh -lc "sed -n '220,430p' src/ncdev/claude_session.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:

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
import re
import subprocess
import time
from pathlib import Path

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
    if session.success and made_commit and not dirty and verification.overall_passed:
        status = StepStatus.PASSED
    elif made_commit and verification.overall_passed:
        # Claude might have exited with non-zero for trivial reasons; if
        # the commit and verification are good, we accept.
        status = StepStatus.PASSED
    else:
        # Something is wrong. Commit whatever is there with [BROKEN] tag
        # so the next feature has context to build on.
        if dirty:
            _commit_broken(target_path, feature)
            post_commit = _git_head(target_path)
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
        error_message=session.error or "",
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

exec
/bin/zsh -lc "sed -n '360,620p' src/ncdev/v3/claude_executor.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
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

    # 7. Best-effort health probe — Claude may have left the app running;
    #    if so, we probe it. If it's down, treat as a soft signal, not
    #    a hard failure (feature may have been built to spec without
    #    leaving the app booted).
    if probe_health and bundle.verification.backend_health_url:
        reachable = _probe_health(
            bundle.verification.backend_health_url,
            timeout=bundle.verification.boot_timeout_seconds,
        )
        ver.app_boots = reachable
        # Not added to reasons — soft signal only. Explicit boot
        # enforcement requires the orchestrator to start the app itself,
        # which is out of scope for post-hoc verification.

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


def _probe_health(url: str, *, timeout: int) -> bool:
    """Best-effort HTTP GET — True if we get a 2xx response."""
    try:
        import httpx
        r = httpx.get(url, timeout=min(timeout, 10))
        return 200 <= r.status_code < 300
    except Exception:  # noqa: BLE001
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
            console.print(f"  [red]BROKEN-commit: git add failed[/red]: {add.stderr[:200]}")
            return False
        commit = subprocess.run(
            ["git", "commit", "-m",
             f"[BROKEN] {feature.feature_id}: {feature.title}\n\n"
             "Claude session did not reach a clean-tree final state. "
             "Committed for recoverability."],
            cwd=str(target_path), capture_output=True, text=True, timeout=10,
        )
        if commit.returncode != 0:
            console.print(
                f"  [red]BROKEN-commit: git commit failed[/red] "
                f"(rc={commit.returncode}): {(commit.stderr or commit.stdout)[:300]}"
            )
            return False
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        console.print(f"  [red]BROKEN-commit: {exc}[/red]")
        return False

codex
I’ve confirmed the old critical list. Now I’m checking the new dispatcher, design funnel, dep gating, and hook parsing against the actual call paths to see what still leaks.
exec
/bin/zsh -lc "sed -n '1,340p' src/ncdev/v3/design_phase.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
"""Phase C — Design system phase.

For any web / UI project, produces a design system in ``docs/design-system/``
and a summary :class:`DesignSystemDoc` artifact. Three paths:

    * ``source="stitch"``   — invoke a Claude session with the Stitch MCP
                              server exposed; Claude creates a Stitch
                              project, generates the design system, and
                              downloads tokens + screen HTML.
    * ``source="existing"`` — brownfield case: ``docs/design-system/`` is
                              already populated; Claude reads it and
                              summarises into the artifact.
    * ``source="claude_generated"`` — fallback when Stitch is
                              unavailable AND the project is brownfield.
                              Claude's ``frontend-design`` skill produces
                              the tokens itself.

Hard-fail rule (enforces the user's ask):

    Greenfield UI project + no Stitch available + no existing design
    system on disk → fail the run with an actionable error. We will NOT
    let a build proceed without defined designs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ncdev.ai_session import run_ai_session
from ncdev.claude_session import ClaudeSessionResult
from ncdev.v2.config import NCDevV2Config
from ncdev.v3.models import (
    DesignSystemDoc,
    TargetProjectContract,
)


# Tools for the Stitch / claude_generated branches — Claude needs to
# write tokens, invoke the frontend-design skill, and potentially shell
# to a Stitch CLI. Stitch MCP tools come through as ``mcp__stitch__*``
# names (environment-specific).
STITCH_DESIGN_TOOLS: tuple[str, ...] = (
    "Read",
    "Write",
    "Edit",
    "Glob",
    "Grep",
    "Bash",
    "Skill",
    "Task",
)

# Tools for the brownfield summariser — Claude reads the existing
# design system and writes ONE JSON artifact. No editing / shelling out.
SUMMARISE_DESIGN_TOOLS: tuple[str, ...] = (
    "Read",
    "Glob",
    "Grep",
    "Write",   # must write design-system.json — nothing else
)

# Backward-compat alias; older callers / tests may import this name.
DESIGN_TOOLS = STITCH_DESIGN_TOOLS


@dataclass
class DesignPhaseResult:
    """Outcome of the design phase."""
    skipped: bool = False           # non-UI project
    hard_failed: bool = False       # greenfield UI without designs and no Stitch
    design_doc: DesignSystemDoc | None = None
    session: ClaudeSessionResult | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Environment probes
# ---------------------------------------------------------------------------


def stitch_available() -> bool:
    """Return True if a Stitch MCP server appears to be configured.

    Detection is intentionally lightweight — we check for the presence of
    a ``stitch`` key in the user's Claude config, or the env var
    ``NCDEV_STITCH_MCP_CONFIG`` pointing at a valid path. A full probe
    would spawn Claude and ask; we avoid that here for speed.
    """
    import os
    if os.environ.get("NCDEV_STITCH_MCP_CONFIG"):
        return bool(Path(os.environ["NCDEV_STITCH_MCP_CONFIG"]).exists())
    # Check user-level Claude config for an mcpServer with "stitch" in name
    config_path = Path.home() / ".claude" / "settings.json"
    if config_path.exists():
        try:
            import json
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            servers = cfg.get("mcpServers", {})
            return any("stitch" in k.lower() for k in servers.keys())
        except Exception:  # noqa: BLE001
            return False
    return False


_TOKEN_FILE_NAMES: tuple[str, ...] = (
    "tokens.css",
    "tokens.scss",
    "tokens.json",
    "design-tokens.json",
    "tailwind.config.js",
    "tailwind.config.ts",
    "tailwind.config.cjs",
    "theme.ts",
    "theme.js",
    "theme.json",
    "colors.css",
    "colors.scss",
    "variables.css",
    "variables.scss",
    "_tokens.scss",
    "globals.css",
)


def existing_design_system_present(target_path: Path) -> bool:
    """True if ``target_path/docs/design-system/`` has real token files.

    A non-empty file is not sufficient — we check for known token file
    names so an accidental README or stray image doesn't count. Prevents
    silent acceptance of junk as a design system.
    """
    ds = target_path / "docs" / "design-system"
    if not ds.exists() or not ds.is_dir():
        return False
    for f in ds.rglob("*"):
        if not f.is_file():
            continue
        if f.name.lower() in _TOKEN_FILE_NAMES and f.stat().st_size > 0:
            return True
    return False


def is_ui_project(contract: TargetProjectContract) -> bool:
    return contract.project_type.lower() in ("web", "webapp", "frontend", "spa", "saas")


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------


def _stitch_prompt(contract: TargetProjectContract, target_path: Path, output_dir: Path) -> str:
    return f"""You are producing the design system for a new web project using Stitch
(Google's design tool, available via MCP).

## Project
- Name: {contract.project_name}
- Design archetype: {contract.design_archetype}
- Frontend framework: {contract.frontend_framework}
- Target repository: {target_path}

## Required workflow

1. Use the Stitch MCP tools to create a new Stitch project for
   "{contract.project_name}".
2. Generate a design system (colors, typography, spacing, corner
   rounding) aligned with the "{contract.design_archetype}" archetype.
3. Generate the key screens listed in
   ``{output_dir}/feature-queue.json`` (at least the ones marked as
   having UI).
4. Download the design tokens (CSS variables, Tailwind config, or the
   equivalent for {contract.frontend_framework}) into:
     {target_path}/docs/design-system/
5. Download HTML exports for each screen into:
     {target_path}/docs/design-system/screens/
6. Write a summary artifact at:
     {output_dir}/design-system.json
   Schema (DesignSystemDoc):
     {{
       "project_name": "{contract.project_name}",
       "design_archetype": "{contract.design_archetype}",
       "source": "stitch",
       "tokens_dir": "docs/design-system",
       "tokens_files": ["..."],
       "colors": {{ ... }},
       "typography": {{ ... }},
       "spacing": {{ ... }},
       "screens": [{{ "name": "...", "html_path": "...", "screenshot_path": "..." }}],
       "stitch_project_id": "..."
     }}

## Rules

- Do NOT write any application code. Tokens and HTML only.
- Prefer downloading real HTML from Stitch over screenshots — it
  preserves animations and layout metadata.
- If Stitch MCP tools are unavailable or fail, STOP and write
  ``{output_dir}/design-phase-error.json`` with an actionable message.
  Do not fall back to generating tokens yourself.

Return a one-sentence summary when done.
"""


def _brownfield_prompt(contract: TargetProjectContract, target_path: Path, output_dir: Path) -> str:
    return f"""This is a brownfield project. A design system already exists at:
  {target_path}/docs/design-system/

## Your job

1. Read the existing design system files.
2. Summarise them into ``{output_dir}/design-system.json`` using schema:
     {{
       "project_name": "{contract.project_name}",
       "design_archetype": "{contract.design_archetype}",
       "source": "existing",
       "tokens_dir": "docs/design-system",
       "tokens_files": ["..."],   # actual filenames found
       "colors": {{ ... }},         # extracted palette
       "typography": {{ ... }},     # font families / sizes found
       "spacing": {{ ... }},
       "screens": [{{ "name": "...", "html_path": "..." }}]
     }}

## Rules

- Do NOT modify any files under docs/design-system/ — you are only
  reading and summarising.
- Do not invoke Codex. Do not write implementation code.

Return a one-sentence summary when done.
"""


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_design_phase(
    contract: TargetProjectContract,
    target_path: Path,
    output_dir: Path,
    *,
    model: str | None = None,
    timeout: int = 1200,
    max_budget_usd: float | None = None,
    log_path: Path | None = None,
    stitch_probe: callable = stitch_available,
    config: NCDevV2Config | None = None,
) -> DesignPhaseResult:
    """Resolve the design system for this project.

    Returns a :class:`DesignPhaseResult`. The caller MUST check
    ``hard_failed`` and abort the pipeline when True.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Non-UI projects skip the design phase entirely.
    if not is_ui_project(contract):
        return DesignPhaseResult(skipped=True)

    has_existing = existing_design_system_present(target_path)
    has_stitch = stitch_probe()

    # --- Hard-fail: greenfield UI, no existing designs, no Stitch ----------
    if not contract.is_brownfield and not has_existing and not has_stitch:
        err_path = output_dir / "design-phase-error.json"
        err_path.write_text(
            '{"error": "greenfield UI project requires a design system",'
            ' "fix": "install and configure the Stitch MCP server, or '
            'supply docs/design-system/ with design tokens and sample pages"}',
            encoding="utf-8",
        )
        return DesignPhaseResult(
            hard_failed=True,
            error="greenfield UI project requires a design system (Stitch or docs/design-system)",
        )

    # --- Brownfield with existing design system ----------------------------
    if has_existing:
        prompt = _brownfield_prompt(contract, target_path, output_dir)
        session = run_ai_session(
            prompt,
            cwd=target_path,
            config=config,
            tools=SUMMARISE_DESIGN_TOOLS,   # read-only + write the summary JSON
            model=model,
            timeout=timeout,
            include_codex_protocol=False,
            max_budget_usd=max_budget_usd,
            log_path=log_path,
        )
        return _finalise_design_phase(session, output_dir)

    # --- Greenfield (or brownfield without designs) + Stitch available ----
    if has_stitch:
        prompt = _stitch_prompt(contract, target_path, output_dir)
        session = run_ai_session(
            prompt,
            cwd=target_path,
            config=config,
            tools=STITCH_DESIGN_TOOLS,
            model=model,
            timeout=timeout,
            include_codex_protocol=False,   # design phase does not build code
            max_budget_usd=max_budget_usd,
            log_path=log_path,
        )
        return _finalise_design_phase(session, output_dir)

    # --- Brownfield without existing designs and no Stitch: Claude decides --
    # Per the user's ruling: "brownfield or design-provided → Claude makes
    # the call". We spawn Claude with the frontend-design skill; it may
    # generate tokens itself.
    prompt = (
        f"This is a brownfield project '{contract.project_name}' without "
        f"a pre-existing design system and without Stitch MCP available. "
        f"Use the `frontend-design` skill to produce minimal design tokens "
        f"aligned with the '{contract.design_archetype}' archetype, "
        f"write them into {target_path}/docs/design-system/, and "
        f"summarise in {output_dir}/design-system.json with source='claude_generated'. "
        f"If you determine the project genuinely needs Stitch or external "
        f"designs to proceed, write design-phase-error.json instead."
    )
    session = run_ai_session(
        prompt,
        cwd=target_path,
        config=config,
        tools=STITCH_DESIGN_TOOLS,
        model=model,
        timeout=timeout,
        include_codex_protocol=False,
        max_budget_usd=max_budget_usd,
        log_path=log_path,
    )
    return _finalise_design_phase(session, output_dir)



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
                    f"[yellow]SKIP[/yellow] {feature.feature_id} — {reason}",
                    border_style="yellow",
                ))
                completed.append(StepResult(
                    feature_id=feature.feature_id,
                    status=StepStatus.SKIPPED,
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
            state.completed_features = len([r for r in completed if r.status == StepStatus.PASSED])
            _persist_state(state, run_dir)

            status_style = "green" if result.status == StepStatus.PASSED else "red"
            console.print(f"  [{status_style}]{result.status.value}[/{status_style}] — commit {result.commit_sha[:8] or '(none)'}")

    # ── Phase 6: Summary ─────────────────────────────────────────────────
    state.phase = "complete"
    passed = [r for r in completed if r.status == StepStatus.PASSED]
    failed = [r for r in completed if r.status == StepStatus.FAILED]
    state.status = "passed" if not failed else ("partial" if passed else "failed")

    _print_summary_table(completed)

    _persist_state(state, run_dir)
    return state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unmet_dependencies(feature, completed: list[StepResult]) -> list[str]:
    """Return the ids in ``feature.depends_on_features`` that are not PASSED.

    A feature id is "satisfied" when it appears in ``completed`` with
    status PASSED or SKIPPED (state scanner can mark a brownfield
    feature as already-implemented → SKIPPED, which counts as met).
    Missing ids (not in the completed list at all) are unmet.
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

exec
/bin/zsh -lc "sed -n '1,260p' scripts/ncdev-hooks/pre_bash_guard.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
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
    """Return a list of '<file>:<pattern>' violations found in staged diff."""
    hits: list[str] = []
    for path in _staged_file_list(cwd):
        # Diff the staged content only — we want to catch what's about
        # to land, not what's already in HEAD.
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
        for pat in patterns:
            if pat in blob:
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
/bin/zsh -lc "sed -n '1,220p' src/ncdev/v3/charter.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
"""Phase B — Charter generator.

Replaces the 9-artifact V2 discovery pipeline with a single Claude session
that reads the PRD (and optionally an existing repo) and emits three
artifacts:

    target-project-contract.json   # stack, language, DB, auth, ports — the hard constraints
    verification-contract.json     # what "done" means
    feature-queue.json             # ordered FeatureStep list

The Claude session is pointed at the ``writing-plans`` skill and constrained
to the :data:`ncdev.claude_session.DEFAULT_PLAN_TOOLS` allowlist — it can
read files and write JSON, but cannot edit code or invoke Codex. It produces
the three files directly into ``run_dir/outputs/``.
"""

from __future__ import annotations

import json
from pathlib import Path

from ncdev.ai_session import run_ai_session
from ncdev.claude_session import (
    DEFAULT_PLAN_TOOLS,
    ClaudeSessionResult,
)
from ncdev.v2.config import NCDevV2Config
from ncdev.v3.models import (
    CharterBundle,
    FeatureQueueDoc,
    TargetProjectContract,
    VerificationContract,
)


CHARTER_PROMPT_TEMPLATE = """You are producing the project charter for NC Dev's
sequential verified sprint engine. Your job is PLANNING only — do NOT write
application code, do NOT scaffold, do NOT run tests.

Use the `writing-plans` skill to structure your work.

## Input
- PRD file: {prd_path}
- Target repository (may be empty for greenfield, existing for brownfield):
  {target_repo}
- Project type detected: {project_type_hint}

## Required deliverables

Write exactly three JSON files into the directory:

  {output_dir}

### 1. target-project-contract.json

The hard architectural constraints for this project. These are the
invariants that must not change across future runs. Schema:

{contract_schema}

Rules:
- For greenfield, infer sane defaults from the PRD.
- For brownfield, DETECT from the existing repo — do not override what
  is there. Read package.json / pyproject.toml / docker-compose.yml etc.
- `design_archetype` must be one of: Cinematic Minimalism, Technical
  Elegance, Opinionated Darkness, Warm Playfulness, Developer Brutalism,
  Bold Brand Photography. Pick the one best matching the PRD's tone.
- `design_system_source` is "stitch" for new UIs unless the brownfield
  repo already has docs/design-system/ populated.
- `ports` should not collide with existing ports in the repo.

### 2. verification-contract.json

What "done" means for every feature built against this project. Schema:

{verification_schema}

Rules:
- `backend_test_command` / `frontend_test_command` — use the commands
  native to the detected frameworks (pytest, vitest, jest, etc.)
- `required_files` — the minimum file list that MUST exist after all
  features are built (Dockerfile, .env.example, README, etc.)
- `required_screenshots` — list the key pages/routes that must have a
  screenshot captured.
- Keep `prohibited_patterns` as-is unless the PRD explicitly calls out
  additions.

### 3. feature-queue.json

The ordered build list. Schema:

{feature_queue_schema}

Rules:
- Each feature must be independently verifiable (it has tests that run
  and pass in isolation).
- `feature_id` format: `fNN-slug` (f01-scaffold, f02-auth, ...).
- First feature is always `f01-scaffold` — boot skeleton + health check.
- `depends_on_features` must only reference earlier feature_ids.
- For BROWNFIELD with design tokens at docs/design-system/, feature f01
  may be "baseline verification" instead of scaffolding.
- Target 4–12 features for most PRDs. If the PRD is huge, group into
  logical features rather than listing every sub-task.

## Output format

Use the `Write` tool to create each file. Validate with `Read` that you
produced valid JSON. Return a one-sentence summary in your final
response. Do not output the JSON content in your response — just write
the files and confirm.
"""


def _schema_excerpt(model_cls) -> str:
    """Render a compact JSON-schema hint for a pydantic model."""
    schema = model_cls.model_json_schema()
    props = schema.get("properties", {})
    lines = []
    for key, spec in props.items():
        t = spec.get("type", "?")
        if t == "array":
            items = spec.get("items", {})
            t = f"array<{items.get('type', '?')}>"
        default = spec.get("default")
        desc = spec.get("description", "")
        tail = f"  # {desc}" if desc else ""
        if default is not None and not isinstance(default, (list, dict)):
            lines.append(f"  {key}: {t} = {default!r}{tail}")
        else:
            lines.append(f"  {key}: {t}{tail}")
    return "{\n" + "\n".join(lines) + "\n}"


def _feature_queue_schema_excerpt() -> str:
    return """{
  project_name: str
  features: array<FeatureStep>
}

FeatureStep = {
  feature_id: str            # "fNN-slug"
  title: str
  description: str
  acceptance_criteria: array<str>
  test_requirements: array<str>
  depends_on_features: array<str>
  priority: int
  estimated_complexity: "low" | "medium" | "high"
}"""


def build_charter_prompt(
    prd_path: Path,
    target_repo: Path | None,
    output_dir: Path,
    project_type_hint: str = "web",
) -> str:
    return CHARTER_PROMPT_TEMPLATE.format(
        prd_path=str(prd_path),
        target_repo=str(target_repo) if target_repo else "(none — greenfield)",
        output_dir=str(output_dir),
        project_type_hint=project_type_hint,
        contract_schema=_schema_excerpt(TargetProjectContract),
        verification_schema=_schema_excerpt(VerificationContract),
        feature_queue_schema=_feature_queue_schema_excerpt(),
    )


def generate_charter(
    prd_path: Path,
    output_dir: Path,
    *,
    target_repo: Path | None = None,
    project_type_hint: str = "web",
    model: str | None = None,
    timeout: int = 900,
    max_budget_usd: float | None = None,
    log_path: Path | None = None,
    config: NCDevV2Config | None = None,
) -> tuple[CharterBundle | None, ClaudeSessionResult]:
    """Run the charter Claude session and load the produced artifacts.

    Returns ``(bundle, session_result)``. ``bundle`` is None if the
    session failed, produced invalid JSON, or wrote a ``charter-error.json``
    (enforced hard-fail for greenfield UI without design system).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    prompt = build_charter_prompt(prd_path, target_repo, output_dir, project_type_hint)

    session = run_ai_session(
        prompt,
        cwd=output_dir,
        config=config,
        tools=DEFAULT_PLAN_TOOLS,
        model=model,
        timeout=timeout,
        include_codex_protocol=False,   # planning only — no Codex shell-out
        max_budget_usd=max_budget_usd,
        log_path=log_path,
    )

    # Hard-fail: greenfield UI without design system writes this file.
    error_path = output_dir / "charter-error.json"
    if error_path.exists():
        return None, session

    if not session.success:
        return None, session

    try:
        bundle = load_charter(output_dir)
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return None, session

    return bundle, session


def load_charter(output_dir: Path) -> CharterBundle:
    """Load the three charter artifacts from disk. Raises on missing/invalid."""
    contract_path = output_dir / "target-project-contract.json"

exec
/bin/zsh -lc "sed -n '340,460p' src/ncdev/v3/design_phase.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:

def _finalise_design_phase(session, output_dir: Path) -> DesignPhaseResult:
    """Enforce success + artifact presence for every non-skip branch.

    Required for a pass: the AI session must have exited cleanly AND a
    parseable design-system.json must exist on disk. A design-phase-error
    file written by the session is always a hard fail.
    """
    err_path = output_dir / "design-phase-error.json"
    if err_path.exists():
        return DesignPhaseResult(
            hard_failed=True,
            session=session,
            error=f"Design phase wrote error artifact at {err_path}",
        )
    if not session.success:
        return DesignPhaseResult(
            hard_failed=True,
            session=session,
            error=f"Design session exited unsuccessfully: {session.error or 'no detail'}",
        )
    doc = _load_design_doc(output_dir)
    if doc is None:
        return DesignPhaseResult(
            hard_failed=True,
            session=session,
            error=(
                "Design session reported success but no valid "
                f"{output_dir}/design-system.json was produced."
            ),
        )
    return DesignPhaseResult(design_doc=doc, session=session)


def _load_design_doc(output_dir: Path) -> DesignSystemDoc | None:
    path = output_dir / "design-system.json"
    if not path.exists():
        return None
    try:
        return DesignSystemDoc.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None

exec
/bin/zsh -lc "sed -n '1,260p' src/ncdev/v2/config.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator

from ncdev.v2.models import TaskType


# ---------------------------------------------------------------------------
# Routing task keys — single source of truth for RoutingConfig fields.
# ---------------------------------------------------------------------------

ROUTING_TASK_KEYS: tuple[str, ...] = (
    "source_ingest",
    "repo_analysis",
    "market_research",
    "feature_extraction",
    "design_brief",
    "implementation",
    "test_authoring",
    "review",
    "second_opinion",
    "sentinel_reproduce",
    "sentinel_fix",
)


def _uniform_preset(provider: str) -> dict[str, list[str]]:
    return {key: [provider] for key in ROUTING_TASK_KEYS}


# Named presets. Flipping `NCDevV2Config.mode` picks one. "custom" leaves
# RoutingConfig untouched so users can hand-tune it.
MODE_PRESETS: dict[str, dict[str, list[str]]] = {
    "codex_only": _uniform_preset("openai_codex"),
    "claude_only": _uniform_preset("anthropic_claude_code"),
    "openrouter": _uniform_preset("openrouter"),
    "claude_plan_codex_build": {
        "source_ingest": ["anthropic_claude_code"],
        "repo_analysis": ["anthropic_claude_code"],
        "market_research": ["anthropic_claude_code"],
        "feature_extraction": ["anthropic_claude_code"],
        "design_brief": ["anthropic_claude_code"],
        "implementation": ["openai_codex"],
        "test_authoring": ["openai_codex"],
        "review": ["anthropic_claude_code"],
        "second_opinion": ["anthropic_claude_code"],
        "sentinel_reproduce": ["anthropic_claude_code"],
        "sentinel_fix": ["openai_codex"],
    },
    "custom": {},
}

DEFAULT_MODE = "claude_plan_codex_build"


class ProviderPreferenceConfig(BaseModel):
    enabled: bool = True
    preferred_models: dict[str, str] = Field(default_factory=dict)
    defaults: dict[str, str] = Field(default_factory=dict)
    features: dict[str, bool] = Field(default_factory=dict)


class RoutingConfig(BaseModel):
    source_ingest: list[str] = Field(default_factory=lambda: ["anthropic_claude_code"])
    repo_analysis: list[str] = Field(default_factory=lambda: ["anthropic_claude_code"])
    market_research: list[str] = Field(default_factory=lambda: ["anthropic_claude_code"])
    feature_extraction: list[str] = Field(default_factory=lambda: ["anthropic_claude_code"])
    design_brief: list[str] = Field(default_factory=lambda: ["anthropic_claude_code"])
    implementation: list[str] = Field(default_factory=lambda: ["openai_codex"])
    test_authoring: list[str] = Field(default_factory=lambda: ["openai_codex"])
    review: list[str] = Field(default_factory=lambda: ["anthropic_claude_code"])
    second_opinion: list[str] = Field(default_factory=lambda: ["anthropic_claude_code"])
    sentinel_reproduce: list[str] = Field(default_factory=lambda: ["anthropic_claude_code"])
    sentinel_fix: list[str] = Field(default_factory=lambda: ["openai_codex"])

    def providers_for(self, task_type: TaskType) -> list[str]:
        mapping = {
            TaskType.SOURCE_INGEST: self.source_ingest,
            TaskType.REPO_ANALYSIS: self.repo_analysis,
            TaskType.MARKET_RESEARCH: self.market_research,
            TaskType.FEATURE_EXTRACTION: self.feature_extraction,
            TaskType.DESIGN_BRIEF: self.design_brief,
            TaskType.BUILD_BATCH: self.implementation,
            TaskType.TEST_AUTHORING: self.test_authoring,
            TaskType.SENTINEL_REPRODUCE: self.sentinel_reproduce,
            TaskType.SENTINEL_FIX: self.sentinel_fix,
        }
        return mapping.get(task_type, self.review)


class SentinelServiceConfig(BaseModel):
    repo_path: str = ""
    git_remote: str = ""
    default_branch: str = "main"
    language: str = "python"
    test_commands: dict[str, str] = Field(default_factory=dict)
    pr_labels: list[str] = Field(default_factory=lambda: ["sentinel-auto", "bug"])
    auto_deploy: bool = False


class SentinelIntakeConfig(BaseModel):
    enabled: bool = True
    port: int = 16650
    api_key: str = ""
    max_concurrent_runs: int = 3
    queue_max_size: int = 50


class SentinelRateLimitConfig(BaseModel):
    max_fixes_per_hour: int = 10
    max_fixes_per_service_per_hour: int = 5
    cooldown_after_failure_seconds: int = 300


class SentinelCallbackConfig(BaseModel):
    enabled: bool = True
    url: str = ""
    api_key: str = ""
    retry_count: int = 3
    retry_delay_seconds: int = 5


class SentinelGitConfig(BaseModel):
    branch_prefix: str = "sentinel/fix/"
    commit_prefix: str = "[sentinel-fix]"
    pr_label: str = "sentinel-auto"


class SentinelConfig(BaseModel):
    intake: SentinelIntakeConfig = Field(default_factory=SentinelIntakeConfig)
    rate_limits: SentinelRateLimitConfig = Field(default_factory=SentinelRateLimitConfig)
    services: dict[str, SentinelServiceConfig] = Field(default_factory=dict)
    callback: SentinelCallbackConfig = Field(default_factory=SentinelCallbackConfig)
    git: SentinelGitConfig = Field(default_factory=SentinelGitConfig)


class QualityGateConfig(BaseModel):
    require_local_harness: bool = True
    require_artifacts: bool = True
    require_human_release: bool = True


class NCDevV2Config(BaseModel):
    mode: str = Field(
        default=DEFAULT_MODE,
        description=(
            "Named routing preset. One of: "
            + ", ".join(sorted(MODE_PRESETS.keys()))
            + ". Flipping this is the main budget switch — "
            "claude_plan_codex_build (default) uses Claude for planning + "
            "review and delegates implementation to Codex via Bash; "
            "codex_only skips Claude entirely for token-lean days; "
            "claude_only keeps everything on Claude; openrouter routes all "
            "tasks through the OpenRouter API. Use 'custom' to hand-tune."
        ),
    )
    providers: dict[str, ProviderPreferenceConfig] = Field(
        default_factory=lambda: {
            "anthropic_claude_code": ProviderPreferenceConfig(
                enabled=True,
                preferred_models={"planning": "opus", "review": "opus"},
                features={"use_subagents": True, "use_hooks": True, "use_mcp": True},
            ),
            "openai_codex": ProviderPreferenceConfig(
                enabled=True,
                preferred_models={"implementation": "gpt-5.4", "test_implementation": "gpt-5.4"},
                defaults={"reasoning_effort": "high"},
            ),
            "openrouter": ProviderPreferenceConfig(
                enabled=False,
                preferred_models={"planning": "anthropic/claude-opus-4-6"},
                defaults={"base_url": "https://openrouter.ai/api/v1"},
            ),
            "gemini_cli": ProviderPreferenceConfig(enabled=False),
        }
    )
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    quality_gates: QualityGateConfig = Field(default_factory=QualityGateConfig)
    sentinel: SentinelConfig = Field(default_factory=SentinelConfig)

    @model_validator(mode="after")
    def _apply_mode_preset(self) -> "NCDevV2Config":
        preset = MODE_PRESETS.get(self.mode)
        if preset is None:
            raise ValueError(
                f"Unknown mode '{self.mode}'. Known modes: "
                + ", ".join(sorted(MODE_PRESETS.keys()))
            )
        if not preset:
            # "custom" — leave RoutingConfig as declared.
            return self
        for field, providers in preset.items():
            setattr(self.routing, field, list(providers))
        return self

    def to_yaml_dict(self) -> dict[str, object]:
        return self.model_dump(mode="python")


def load_v2_config(workspace: Path) -> NCDevV2Config:
    config_path = workspace / ".nc-dev" / "v2" / "config.yaml"
    if not config_path.exists():
        return NCDevV2Config()
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return NCDevV2Config.model_validate(raw)


def ensure_default_v2_config(workspace: Path) -> NCDevV2Config:
    workspace.mkdir(parents=True, exist_ok=True)
    config = load_v2_config(workspace)
    config_path = workspace / ".nc-dev" / "v2" / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if not config_path.exists():
        yaml.safe_dump(config.to_yaml_dict(), config_path.open("w", encoding="utf-8"), sort_keys=False)
    return config

exec
/bin/zsh -lc "sed -n '1,320p' tests/unit/test_ai_session.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
"""Tests for the mode-aware AI session dispatcher."""

from __future__ import annotations

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


def test_mode_tables_cover_every_preset():
    """If we add a new mode preset, these maps must have entries for it."""
    from ncdev.v2.config import MODE_PRESETS
    expected = set(MODE_PRESETS.keys())
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


def test_custom_mode_defaults_to_claude(tmp_path: Path):
    cfg = NCDevV2Config(mode="custom")
    captured: dict = {}

    def fake_claude(prompt, **kwargs):
        captured.update(kwargs)
        return _claude_result()

    with patch("ncdev.ai_session.run_claude_session", side_effect=fake_claude):
        run_ai_session("x", cwd=tmp_path, config=cfg)
    # custom → claude orchestrator, codex implementer → protocol on
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


def test_run_codex_session_builds_correct_argv(tmp_path: Path):
    captured: dict = {}

    class FakeProc:
        returncode = 0
        stdout = "codex output"
        stderr = ""

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return FakeProc()

    with patch("ncdev.ai_session.shutil.which", return_value="/usr/bin/codex"):
        with patch("ncdev.ai_session.subprocess.run", side_effect=fake_run):
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


def test_run_codex_session_honours_timeout(tmp_path: Path):
    import subprocess as sp

    def fake_run(cmd, **kwargs):
        raise sp.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout", 0))

    with patch("ncdev.ai_session.shutil.which", return_value="/usr/bin/codex"):
        with patch("ncdev.ai_session.subprocess.run", side_effect=fake_run):
            result = run_codex_session("x", cwd=tmp_path, timeout=5)
    assert result.success is False
    assert "timed out" in (result.error or "")


def test_run_codex_session_writes_log(tmp_path: Path):
    class FakeProc:
        returncode = 0
        stdout = "the work"
        stderr = ""

    log_path = tmp_path / "logs" / "codex.log"

    with patch("ncdev.ai_session.shutil.which", return_value="/usr/bin/codex"):
        with patch("ncdev.ai_session.subprocess.run", return_value=FakeProc()):
            run_codex_session("x", cwd=tmp_path, log_path=log_path)

    assert log_path.exists()
    body = log_path.read_text(encoding="utf-8")
    assert "RUNNER: codex" in body
    assert "the work" in body

exec
/bin/zsh -lc "sed -n '1,320p' tests/unit/test_claude_session.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
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

exec
/bin/zsh -lc "sed -n '1,320p' tests/unit/test_design_phase.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
"""Tests for Phase C design system phase."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from ncdev.claude_session import ClaudeSessionResult
from ncdev.v3.design_phase import (
    DESIGN_TOOLS,
    DesignPhaseResult,
    existing_design_system_present,
    is_ui_project,
    run_design_phase,
    stitch_available,
)
from ncdev.v3.models import DesignSystemDoc, TargetProjectContract


def _web_contract(**overrides) -> TargetProjectContract:
    defaults = dict(
        project_name="myapp",
        project_type="web",
        frontend_framework="react",
        design_archetype="Technical Elegance",
        is_brownfield=False,
    )
    defaults.update(overrides)
    return TargetProjectContract(**defaults)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def test_is_ui_project_detects_web_types():
    assert is_ui_project(_web_contract(project_type="web"))
    assert is_ui_project(_web_contract(project_type="webapp"))
    assert is_ui_project(_web_contract(project_type="saas"))


def test_is_ui_project_false_for_cli_and_library():
    assert not is_ui_project(_web_contract(project_type="cli"))
    assert not is_ui_project(_web_contract(project_type="library"))


def test_existing_design_system_detects_populated_dir(tmp_path: Path):
    ds = tmp_path / "docs" / "design-system"
    ds.mkdir(parents=True)
    (ds / "tokens.css").write_text(":root { --brand: #000; }")
    assert existing_design_system_present(tmp_path) is True


def test_existing_design_system_false_for_empty_or_missing(tmp_path: Path):
    assert existing_design_system_present(tmp_path) is False
    ds = tmp_path / "docs" / "design-system"
    ds.mkdir(parents=True)
    assert existing_design_system_present(tmp_path) is False


def test_existing_design_system_rejects_junk_files(tmp_path: Path):
    """A README or a stray image doesn't make a valid design system."""
    ds = tmp_path / "docs" / "design-system"
    ds.mkdir(parents=True)
    (ds / "README.md").write_text("coming soon")
    (ds / "screenshot.png").write_bytes(b"\x89PNG")
    # Must not falsely claim a design system is present
    assert existing_design_system_present(tmp_path) is False

    # Now drop a real token file — should flip to True
    (ds / "tokens.css").write_text(":root { --brand: #000; }")
    assert existing_design_system_present(tmp_path) is True


def test_stitch_available_via_env_var(tmp_path: Path, monkeypatch):
    fake_cfg = tmp_path / "stitch.json"
    fake_cfg.write_text("{}")
    monkeypatch.setenv("NCDEV_STITCH_MCP_CONFIG", str(fake_cfg))
    assert stitch_available() is True


def test_stitch_available_false_when_env_missing_and_no_config(monkeypatch, tmp_path):
    monkeypatch.delenv("NCDEV_STITCH_MCP_CONFIG", raising=False)
    # Point HOME at a temp dir that has no claude config
    monkeypatch.setenv("HOME", str(tmp_path))
    # Path.home() reads HOME on *nix — this should make it see no config
    assert stitch_available() is False


# ---------------------------------------------------------------------------
# Non-UI skip path
# ---------------------------------------------------------------------------


def test_cli_project_skips_design_phase(tmp_path: Path):
    contract = _web_contract(project_type="cli")
    result = run_design_phase(contract, tmp_path, tmp_path / "out")
    assert result.skipped is True
    assert result.hard_failed is False
    assert result.design_doc is None


# ---------------------------------------------------------------------------
# Hard-fail path
# ---------------------------------------------------------------------------


def test_greenfield_ui_without_stitch_or_designs_hard_fails(tmp_path: Path):
    contract = _web_contract(is_brownfield=False)
    output_dir = tmp_path / "out"

    result = run_design_phase(
        contract, tmp_path, output_dir,
        stitch_probe=lambda: False,   # no Stitch
    )

    assert result.hard_failed is True
    assert result.error is not None
    assert "greenfield" in result.error.lower() or "design" in result.error.lower()
    # Error artifact written for downstream processing / human
    err = output_dir / "design-phase-error.json"
    assert err.exists()
    payload = json.loads(err.read_text(encoding="utf-8"))
    assert "error" in payload
    assert "fix" in payload


# ---------------------------------------------------------------------------
# Brownfield with existing design system
# ---------------------------------------------------------------------------


def test_brownfield_with_design_system_runs_summariser(tmp_path: Path):
    contract = _web_contract(is_brownfield=True)
    # Seed existing design system
    ds = tmp_path / "docs" / "design-system"
    ds.mkdir(parents=True)
    (ds / "tokens.css").write_text(":root { --brand: #abcdef; }")

    output_dir = tmp_path / "out"
    captured: dict = {}

    def fake_session(prompt, **kwargs):
        captured["prompt"] = prompt
        captured.update(kwargs)
        doc = DesignSystemDoc(
            project_name="myapp",
            design_archetype="Technical Elegance",
            source="existing",
            tokens_files=["tokens.css"],
        )
        (output_dir / "design-system.json").write_text(
            doc.model_dump_json(indent=2), encoding="utf-8",
        )
        return ClaudeSessionResult(success=True, final_text="summarised", exit_code=0)

    with patch("ncdev.v3.design_phase.run_ai_session", side_effect=fake_session):
        result = run_design_phase(
            contract, tmp_path, output_dir,
            stitch_probe=lambda: False,   # doesn't matter, existing wins
        )

    assert result.hard_failed is False
    assert result.design_doc is not None
    assert result.design_doc.source == "existing"
    # Prompt must be the brownfield-summariser variant
    assert "read the existing" in captured["prompt"].lower()
    assert "Do NOT modify" in captured["prompt"]


# ---------------------------------------------------------------------------
# Stitch path
# ---------------------------------------------------------------------------


def test_greenfield_with_stitch_runs_stitch_prompt(tmp_path: Path):
    contract = _web_contract(is_brownfield=False)
    output_dir = tmp_path / "out"
    captured: dict = {}

    def fake_session(prompt, **kwargs):
        captured["prompt"] = prompt
        doc = DesignSystemDoc(
            project_name="myapp",
            design_archetype="Technical Elegance",
            source="stitch",
            stitch_project_id="stitch-abc",
            tokens_files=["tokens.css", "tailwind.config.js"],
        )
        (output_dir / "design-system.json").write_text(
            doc.model_dump_json(indent=2), encoding="utf-8",
        )
        return ClaudeSessionResult(success=True, final_text="stitch done", exit_code=0)

    with patch("ncdev.v3.design_phase.run_ai_session", side_effect=fake_session):
        result = run_design_phase(
            contract, tmp_path, output_dir,
            stitch_probe=lambda: True,
        )

    assert result.hard_failed is False
    assert result.design_doc is not None
    assert result.design_doc.source == "stitch"
    assert result.design_doc.stitch_project_id == "stitch-abc"
    # Stitch prompt
    assert "Stitch" in captured["prompt"]
    assert "MCP" in captured["prompt"]


def test_stitch_phase_that_writes_error_file_is_hard_failed(tmp_path: Path):
    contract = _web_contract(is_brownfield=False)
    output_dir = tmp_path / "out"

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "design-phase-error.json").write_text(
            '{"error": "Stitch auth failed", "fix": "re-auth"}', encoding="utf-8",
        )
        return ClaudeSessionResult(success=True, final_text="stitch unreachable", exit_code=0)

    with patch("ncdev.v3.design_phase.run_ai_session", side_effect=fake_session):
        result = run_design_phase(
            contract, tmp_path, output_dir,
            stitch_probe=lambda: True,
        )

    assert result.hard_failed is True
    assert "error artifact" in (result.error or "")


# ---------------------------------------------------------------------------
# Brownfield without designs + no Stitch: Claude decides
# ---------------------------------------------------------------------------


def test_brownfield_without_designs_and_no_stitch_lets_claude_decide(tmp_path: Path):
    contract = _web_contract(is_brownfield=True)
    output_dir = tmp_path / "out"
    captured: dict = {}

    def fake_session(prompt, **kwargs):
        captured["prompt"] = prompt
        doc = DesignSystemDoc(
            project_name="myapp",
            design_archetype="Technical Elegance",
            source="claude_generated",
        )
        (output_dir / "design-system.json").write_text(
            doc.model_dump_json(indent=2), encoding="utf-8",
        )
        return ClaudeSessionResult(success=True, final_text="ok", exit_code=0)

    with patch("ncdev.v3.design_phase.run_ai_session", side_effect=fake_session):
        result = run_design_phase(
            contract, tmp_path, output_dir,
            stitch_probe=lambda: False,
        )

    assert result.hard_failed is False
    assert result.design_doc is not None
    assert result.design_doc.source == "claude_generated"
    # Prompt instructs Claude it MAY hard-fail itself if it thinks Stitch needed
    assert "frontend-design" in captured["prompt"]
    assert "design-phase-error.json" in captured["prompt"]


def test_design_phase_fails_loud_when_session_succeeds_but_no_doc_produced(tmp_path: Path):
    """Codex flagged: session.success=True with no design-system.json
    must NOT be silently accepted as passing — it must hard-fail."""
    contract = _web_contract(is_brownfield=True)
    ds = tmp_path / "docs" / "design-system"
    ds.mkdir(parents=True)
    (ds / "tokens.css").write_text(":root {}")
    output_dir = tmp_path / "out"

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        # "Claude" exits clean but forgets to write design-system.json
        return ClaudeSessionResult(success=True, final_text="I forgot", exit_code=0)

    with patch("ncdev.v3.design_phase.run_ai_session", side_effect=fake_session):
        result = run_design_phase(
            contract, tmp_path, output_dir,
            stitch_probe=lambda: False,
        )

    assert result.hard_failed is True
    assert "design-system.json" in (result.error or "")


def test_design_phase_fails_when_session_exits_unsuccessfully(tmp_path: Path):
    """Codex flagged: session.success=False must hard-fail even if the
    session wrote a valid design-system.json by accident."""
    contract = _web_contract(is_brownfield=True)
    ds = tmp_path / "docs" / "design-system"
    ds.mkdir(parents=True)
    (ds / "tokens.css").write_text(":root {}")
    output_dir = tmp_path / "out"

    def fake_session(prompt, **kwargs):  # noqa: ARG001
        doc = DesignSystemDoc(
            project_name="myapp",
            design_archetype="Technical Elegance",
            source="existing",
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "design-system.json").write_text(doc.model_dump_json(), encoding="utf-8")
        return ClaudeSessionResult(success=False, final_text="crashed", exit_code=1,
                                    error="session timed out")

    with patch("ncdev.v3.design_phase.run_ai_session", side_effect=fake_session):
        result = run_design_phase(
            contract, tmp_path, output_dir,
            stitch_probe=lambda: False,
        )

    assert result.hard_failed is True

exec
/bin/zsh -lc "sed -n '1,240p' tests/test_ncdev_v3/test_dependency_gating.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
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


def test_dependency_skipped_counts_as_satisfied():
    """Brownfield state scanner marks already-implemented features as
    SKIPPED — those should still count as satisfying a dep."""
    f = _feat("f02", deps=["f01"])
    completed = [StepResult(feature_id="f01", status=StepStatus.SKIPPED)]
    assert _unmet_dependencies(f, completed=completed) == []


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
/bin/zsh -lc "sed -n '1,260p' tests/unit/test_hooks.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
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
/bin/zsh -lc "sed -n '1,260p' tests/unit/test_claude_executor.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
"""Tests for Phase E Claude-driven feature executor."""

from __future__ import annotations

import subprocess
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

exec
/bin/zsh -lc "sed -n '260,520p' tests/unit/test_claude_executor.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
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

exec
/bin/zsh -lc "sed -n '1,320p' src/ncdev/v3/asset_manifest.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
"""Phase D — Asset manifest.

Every Claude feature-build session must emit
``.ncdev/assets-needed/<feature_id>.json`` describing the images, GIFs,
SVGs, videos, icons, or audio clips the feature needs but couldn't
generate itself. The manifest is produced **during** the build (Claude
writes it as it codes — it knows its own intent), never after.

Downstream systems (Nano Banana 2, a stock-image service, or a human)
read the aggregate ``_all.json`` and populate each asset.

Verification step: scan the committed code for asset references. Every
reference must be present in a manifest entry, or the feature fails
verification. Manifest entries with ``status="pending"`` are OK — the
asset simply hasn't been populated yet. The code shipping without any
manifest is what we reject.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from ncdev.v3.models import AssetManifest, AssetManifestEntry


# Directory layout (project-relative):
#   .ncdev/assets-needed/<feature_id>.json
#   .ncdev/assets-needed/_all.json
ASSETS_DIR = ".ncdev/assets-needed"


# ---------------------------------------------------------------------------
# Load / save / aggregate
# ---------------------------------------------------------------------------


def load_feature_manifest(project_root: Path, feature_id: str) -> AssetManifest | None:
    """Load one feature's manifest, or None if it doesn't exist."""
    path = project_root / ASSETS_DIR / f"{feature_id}.json"
    if not path.exists():
        return None
    try:
        return AssetManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def save_feature_manifest(project_root: Path, manifest: AssetManifest) -> Path:
    """Write a feature manifest. Used by tests; Claude writes its own in real runs."""
    out = project_root / ASSETS_DIR / f"{manifest.feature_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return out


def aggregate_manifests(project_root: Path) -> AssetManifest:
    """Merge all per-feature manifests into ``_all.json`` and return it."""
    dir_ = project_root / ASSETS_DIR
    all_assets: list[AssetManifestEntry] = []
    seen: set[str] = set()
    if dir_.exists():
        for path in sorted(dir_.glob("*.json")):
            if path.name in ("_all.json", "_summary.json"):
                continue
            try:
                m = AssetManifest.model_validate_json(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            for asset in m.assets:
                if asset.id in seen:
                    continue
                seen.add(asset.id)
                all_assets.append(asset)
    aggregate = AssetManifest(feature_id="_all", assets=all_assets)
    out = dir_ / "_all.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(aggregate.model_dump_json(indent=2), encoding="utf-8")
    return aggregate


# ---------------------------------------------------------------------------
# Prompt helper — spliced into every feature build prompt
# ---------------------------------------------------------------------------


def manifest_prompt_section(feature_id: str) -> str:
    """Return the prompt snippet every feature build must include.

    Tells Claude how to emit the asset manifest for this feature as it
    builds. The snippet includes schema and path. Keep short — we embed
    this in every feature prompt.
    """
    return f"""## Asset manifest requirement

While building this feature, identify every image, GIF, SVG, video,
icon, or audio clip you reference in the code but cannot generate
yourself. Write them to:

    {ASSETS_DIR}/{feature_id}.json

Schema (AssetManifest):

    {{
      "feature_id": "{feature_id}",
      "assets": [
        {{
          "id": "hero-bg",                         # unique slug
          "name": "Hero background image",
          "type": "image",                         # image | gif | svg | video | icon | audio
          "description": "Full-bleed gradient banner for the landing hero.",
          "generation_prompt": "Abstract gradient mesh, deep purples and blues, cinematic.",
          "suggested_dimensions": "2400x1200",
          "referenced_in": ["frontend/src/pages/Home.tsx:42"],
          "target_path": "frontend/public/images/hero-bg.webp",
          "status": "pending"
        }}
      ]
    }}

Rules:
- Write this file BEFORE your last commit. No trailing manifests.
- If the feature needs zero assets, write an empty assets array — do
  not skip the file.
- For every <img>, background-image, <video>, <audio>, SVG reference,
  or icon name your code introduces, there MUST be a manifest entry
  unless the asset already exists in the repo.
- Prefer referencing existing assets over inventing new ones. Only add
  manifest entries for genuinely-missing files.
"""


# ---------------------------------------------------------------------------
# Verification — scan code for asset references, cross-check manifest
# ---------------------------------------------------------------------------


# Patterns that signal an asset reference in source code
_ASSET_REFERENCE_PATTERNS: tuple[re.Pattern, ...] = (
    # HTML/JSX: <img src="...">, <video src="...">, poster="..."
    re.compile(r"""<(?:img|video|audio|source)\s+[^>]*(?:src|poster)\s*=\s*["']([^"']+)["']""", re.IGNORECASE),
    # JSX/TS import of image: import foo from "./foo.png"
    re.compile(r"""import\s+\w+\s+from\s+["']([^"']+\.(?:png|jpe?g|webp|gif|svg|mp4|webm|mp3|wav|ogg|ico))["']""", re.IGNORECASE),
    # CSS: background(-image): url("...")
    re.compile(r"""url\(\s*["']?([^"')\s]+\.(?:png|jpe?g|webp|gif|svg|mp4|webm|ico))["']?\s*\)""", re.IGNORECASE),
    # Next/Image src, React require: require("./foo.png")
    re.compile(r"""require\(\s*["']([^"']+\.(?:png|jpe?g|webp|gif|svg|mp4|webm|mp3|wav|ogg|ico))["']\s*\)""", re.IGNORECASE),
)

_CODE_EXTENSIONS: tuple[str, ...] = (
    ".tsx", ".ts", ".jsx", ".js", ".vue", ".svelte", ".html",
    ".css", ".scss", ".sass", ".less",
    ".py", ".go", ".rs", ".rb",
)


def scan_code_for_asset_references(
    project_root: Path,
    *,
    include_dirs: Iterable[str] = ("frontend", "src", "app", "pages", "public"),
) -> list[tuple[str, str, int]]:
    """Scan code files for asset references.

    Returns list of tuples ``(file_path, referenced_asset, line_number)``.
    Paths are project-relative.
    """
    hits: list[tuple[str, str, int]] = []
    candidates: list[Path] = []
    for d in include_dirs:
        dir_path = project_root / d
        if dir_path.exists():
            for ext in _CODE_EXTENSIONS:
                candidates.extend(dir_path.rglob(f"*{ext}"))
    # Also scan top-level code files
    for ext in _CODE_EXTENSIONS:
        candidates.extend(project_root.glob(f"*{ext}"))

    for fp in candidates:
        try:
            text = fp.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = str(fp.relative_to(project_root))
        for lineno, line in enumerate(text.splitlines(), start=1):
            for pat in _ASSET_REFERENCE_PATTERNS:
                for m in pat.finditer(line):
                    ref = m.group(1)
                    # Skip absolute URLs — they're external, not repo assets
                    if ref.startswith(("http://", "https://", "data:", "//")):
                        continue
                    hits.append((rel, ref, lineno))
    return hits


def scan_files_for_asset_references(
    project_root: Path,
    files: Iterable[str],
) -> list[tuple[str, str, int]]:
    """Variant of :func:`scan_code_for_asset_references` scoped to a
    specific file list. Paths are project-relative.
    """
    hits: list[tuple[str, str, int]] = []
    for rel in files:
        fp = project_root / rel
        if not fp.exists() or not fp.is_file():
            continue
        # Only code files — skip binaries, images, etc.
        if fp.suffix.lower() not in _CODE_EXTENSIONS:
            continue
        try:
            text = fp.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for pat in _ASSET_REFERENCE_PATTERNS:
                for m in pat.finditer(line):
                    ref = m.group(1)
                    if ref.startswith(("http://", "https://", "data:", "//")):
                        continue
                    hits.append((rel, ref, lineno))
    return hits


def verify_manifest_covers_references(
    project_root: Path,
    feature_id: str,
    *,
    include_dirs: Iterable[str] = ("frontend", "src", "app", "pages", "public"),
    touched_files: Iterable[str] | None = None,
) -> tuple[bool, list[str]]:
    """Verify every asset reference is accounted for.

    An asset reference is "accounted for" when:
      - a file at the referenced path exists in the repo, OR
      - a manifest entry (in any per-feature manifest) points at that
        path or has an id/name matching the filename.

    Returns ``(ok, missing_list)``. When manifest-not-written, ok=False
    and missing_list=["<no-manifest>"].

    Scanning scope:
      - If ``touched_files`` is given, scan only those files (feature-local
        verification — the caller passes files_created + files_modified
        from git diff). This is the preferred call shape: one legacy
        unmanaged asset elsewhere won't fail every future feature.
      - Otherwise, fall back to scanning ``include_dirs`` globally. Kept
        for callers that don't know which files changed.
    """
    manifest = load_feature_manifest(project_root, feature_id)
    aggregate = aggregate_manifests(project_root)

    if manifest is None:
        return False, ["<no-manifest>"]

    all_entries = aggregate.assets
    managed_paths: set[str] = {
        entry.target_path.lstrip("./") for entry in all_entries if entry.target_path
    }
    managed_ids: set[str] = {entry.id for entry in all_entries}

    if touched_files is not None:
        refs = scan_files_for_asset_references(project_root, touched_files)
    else:
        refs = scan_code_for_asset_references(project_root, include_dirs=include_dirs)

    missing: list[str] = []
    for file_ref, asset_ref, lineno in refs:
        normalised = asset_ref.lstrip("./").lstrip("/")
        candidates = [
            project_root / normalised,
            project_root / "public" / normalised,
            project_root / "frontend" / "public" / normalised,
            project_root / "frontend" / "src" / normalised,
            project_root / "src" / normalised,
        ]
        if any(p.exists() for p in candidates):
            continue
        if normalised in managed_paths:
            continue
        base = normalised.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        if base in managed_ids:
            continue
        missing.append(f"{file_ref}:{lineno} -> {asset_ref}")

    return (len(missing) == 0), missing

exec
/bin/zsh -lc "sed -n '1,260p' src/ncdev/dev.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
#!/usr/bin/env python3
"""NC Dev System — thin orchestrator for autonomous development.

This module is deliberately small. It spawns a single Claude session per
task and lets Claude drive everything via skills + Codex delegation. The
old 5-step plan/build/verify/fix ladder is gone — Claude's
:skill:`test-driven-development`, :skill:`verification-before-completion`,
and :skill:`systematic-debugging` skills handle that loop internally.

NC Dev's only responsibilities in this file:

1. Preflight (git repo, Citex reachable, claude + codex CLIs on PATH).
2. Ensure the target project is a git repo (and has a remote for greenfield).
3. Compose a short task prompt referencing the project + Citex.
4. Run one Claude session with full tool access (Bash so Claude can shell
   to Codex, Skill so it can invoke skills, Task so it can dispatch subagents).
5. Commit any dirty leftovers with ``[BROKEN]`` if Claude exited without
   committing (recoverability guarantee).
6. Store a short run summary in Citex.

For PRD-scale work, use :mod:`ncdev.v3.engine` (full pipeline) or the
``ncdev full`` command. This ``dev`` command is the freeform
``--task "whatever"`` entry point.
"""

from __future__ import annotations

import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel

from ncdev.ai_session import run_ai_session
from ncdev.claude_session import DEFAULT_BUILD_TOOLS
from ncdev.preflight import require_citex
from ncdev.v2.config import NCDevV2Config, load_v2_config

console = Console()

# ── Citex Integration ───────────────────────────────────────────────────
CITEX_API = "http://localhost:20161"


def citex_store(project_id: str, content: str, metadata: dict) -> bool:
    """Store a short run summary in Citex."""
    try:
        import httpx
        resp = httpx.post(
            f"{CITEX_API}/api/v1/documents/ingest",
            json={"project_id": project_id, "content": content, "metadata": metadata},
            timeout=30,
        )
        return resp.status_code < 400
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Failed to store context in Citex at {CITEX_API}") from exc


def citex_query(project_id: str, query: str, limit: int = 10) -> str:
    """Query Citex for relevant project context."""
    try:
        import httpx
        resp = httpx.post(
            f"{CITEX_API}/api/v1/retrieval/query",
            json={"project_id": project_id, "query": query, "limit": limit},
            timeout=30,
        )
        if resp.status_code < 400:
            results = resp.json()
            parts = []
            for r in results.get("results", results.get("documents", [])):
                content = r.get("content", r.get("text", ""))
                if content:
                    parts.append(content[:2000])
            return "\n\n---\n\n".join(parts) if parts else ""
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Failed to query Citex at {CITEX_API}") from exc
    return ""


# ── Git / GitHub setup ──────────────────────────────────────────────────


def _ensure_git_repo(project_path: Path, mode: str) -> None:
    """Ensure the project is a git repo (and has a remote for greenfield)."""
    git_dir = project_path / ".git"
    if not git_dir.exists():
        subprocess.run(["git", "init"], cwd=str(project_path),
                       capture_output=True, timeout=10)
        subprocess.run(["git", "add", "-A"], cwd=str(project_path),
                       capture_output=True, timeout=10)
        subprocess.run(
            ["git", "commit", "-q", "-m", "chore: initial commit"],
            cwd=str(project_path), capture_output=True, timeout=10,
        )
    subprocess.run(["git", "config", "pull.rebase", "true"],
                   cwd=str(project_path), capture_output=True, timeout=5)

    if mode in ("greenfield", "auto"):
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=str(project_path), capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            project_name = project_path.name
            console.print(f"  [yellow]Creating GitHub repo: yensi-solutions/{project_name}...[/yellow]")
            gh_result = subprocess.run(
                ["gh", "repo", "create", f"yensi-solutions/{project_name}",
                 "--private", "--source", str(project_path), "--push"],
                cwd=str(project_path), capture_output=True, text=True, timeout=30,
            )
            if gh_result.returncode == 0:
                console.print(f"  [green]✓[/green] GitHub repo created: yensi-solutions/{project_name}")
            else:
                subprocess.run(
                    ["git", "remote", "add", "origin",
                     f"git@github.com:yensi-solutions/{project_name}.git"],
                    cwd=str(project_path), capture_output=True, timeout=5,
                )


def _git_head(project_path: Path) -> str:
    r = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(project_path), capture_output=True, text=True, timeout=5,
    )
    return r.stdout.strip() if r.returncode == 0 else ""


def _git_working_tree_dirty(project_path: Path) -> bool:
    r = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(project_path), capture_output=True, text=True, timeout=5,
    )
    return r.returncode == 0 and bool(r.stdout.strip())


def _commit_broken_leftovers(project_path: Path, task: str) -> str:
    """Commit leftover dirty tree with [BROKEN] tag for recoverability."""
    subprocess.run(["git", "add", "-A"],
                   cwd=str(project_path), capture_output=True, timeout=10)
    r = subprocess.run(
        ["git", "commit", "-m",
         f"[BROKEN] ncdev dev: {task[:80]}\n\n"
         "Claude session exited without a clean working tree. "
         "Committed for recoverability."],
        cwd=str(project_path), capture_output=True, timeout=10,
    )
    if r.returncode != 0:
        return ""
    return _git_head(project_path)


# ── Prompt composition (short, contract-driven) ─────────────────────────


def _build_task_prompt(task: str, project_path: Path, project_id: str, mode: str) -> str:
    """Compose the short prompt for a freeform dev task.

    Deliberately terse — the Codex protocol is injected via
    ``--append-system-prompt`` by :func:`run_claude_session`, and Claude
    can read the repo itself with the Read tool. We do not pre-gather
    file trees or README content here; Claude is better at deciding
    what to look at.
    """
    return f"""# Task for this ncdev dev session

Mode: {mode}
Project: {project_path}
Citex project ID: {project_id}
Citex URL: {CITEX_API}

## What the user wants

{task}

## Your workflow

You are the engineer. Drive the full cycle yourself using the skill
machinery available to you. Codex is your implementation peer — see
the Codex protocol in your system prompt.

1. Explore the project using Read/Glob/Grep. Query Citex (via HTTP
   or any CLI it exposes) for prior context.
2. If this is non-trivial, use the `writing-plans` skill.
3. Use `test-driven-development` for any behavioural change.
4. Delegate raw implementation and test writing to Codex via Bash:
   `codex exec --full-auto --sandbox danger-full-access "<scoped task>"`.
5. Use `verification-before-completion` — run the project's tests,
   boot the app, check a health endpoint if one exists. No claiming
   done without evidence.
6. On failure, use `systematic-debugging` — root-cause first, don't
   loop blindly.
7. Commit your work using Conventional Commits. Leave the working
   tree clean.

## What success looks like

- Tests exist and pass for any behavioural change.
- Working tree is clean, all changes committed.
- One-paragraph summary in your final response.

Begin.
"""


# ── Main Entry Point ────────────────────────────────────────────────────


def run_dev(
    project_path: Path,
    task: str,
    mode: str = "auto",
    *,
    model: str | None = None,
    timeout: int = 3600,
    max_budget_usd: float | None = None,
    config: NCDevV2Config | None = None,
) -> dict[str, Any]:
    """Run a single ncdev dev session.

    This is thin glue. Claude does the actual work; NC Dev handles:
    preflight, git repo setup, session orchestration, broken-tag
    fallback on failure, Citex ingestion of the run summary.
    """
    start = time.time()
    project_id = project_path.name
    run_id = f"dev-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"

    require_citex(CITEX_API)

    console.print(Panel(
        f"[bold cyan]NC Dev System — thin orchestrator[/bold cyan]\n"
        f"Project: {project_path}\n"
        f"Task:    {task}\n"
        f"Mode:    {mode}\n"
        f"Run:     {run_id}",
        border_style="cyan",
    ))

    _ensure_git_repo(project_path, mode)

    pre_head = _git_head(project_path)

    # Load mode-aware config so the session dispatcher knows which CLI to run.
    effective_config = config
    if effective_config is None:
        try:
            effective_config = load_v2_config(project_path)
        except Exception:  # noqa: BLE001
            effective_config = NCDevV2Config()
    console.print(f"\n[bold]Running session (mode={effective_config.mode})...[/bold]")
    log_path = project_path / ".ncdev" / "runs" / run_id / "session.jsonl"
    prompt = _build_task_prompt(task, project_path, project_id, mode)
    session = run_ai_session(
        prompt,
        cwd=project_path,

exec
/bin/zsh -lc "rg -n \"run_ai_session\\(|run_codex_session\\(|generate_charter\\(|run_design_phase\\(|execute_feature_claude_driven\\(\" src | sed -n '1,240p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
src/ncdev/dev.py:258:    session = run_ai_session(
src/ncdev/ai_session.py:3:``run_ai_session()`` is the single entry point every phase of NC Dev
src/ncdev/ai_session.py:78:def run_ai_session(
src/ncdev/ai_session.py:118:        return run_codex_session(
src/ncdev/ai_session.py:155:def run_codex_session(
src/ncdev/v3/claude_executor.py:171:def execute_feature_claude_driven(
src/ncdev/v3/claude_executor.py:211:    session = run_ai_session(
src/ncdev/v3/design_phase.py:241:def run_design_phase(
src/ncdev/v3/design_phase.py:284:        session = run_ai_session(
src/ncdev/v3/design_phase.py:300:        session = run_ai_session(
src/ncdev/v3/design_phase.py:327:    session = run_ai_session(
src/ncdev/v3/engine.py:109:        bundle, charter_session = generate_charter(
src/ncdev/v3/engine.py:147:        design = run_design_phase(
src/ncdev/v3/engine.py:246:            result = execute_feature_claude_driven(
src/ncdev/v3/charter.py:169:def generate_charter(
src/ncdev/v3/charter.py:190:    session = run_ai_session(

exec
/bin/zsh -lc "rg -n \"get_provider_for|providers_for|routing\" src/ncdev | sed -n '1,240p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
src/ncdev/provider_dispatch.py:3:Bridges :mod:`ncdev.v2.config` routing (keys like ``design_brief``,
src/ncdev/provider_dispatch.py:6:preset/routing in ``.nc-dev/v2/config.yaml`` decides which CLI or API backs it.
src/ncdev/provider_dispatch.py:21:# Long routing names → short registry keys used in ai_provider.py
src/ncdev/provider_dispatch.py:60:def resolve_provider_name(routing_name: str) -> str:
src/ncdev/provider_dispatch.py:61:    """Translate a v2 routing provider name (or short alias) to registry key."""
src/ncdev/provider_dispatch.py:62:    short = PROVIDER_ALIASES.get(routing_name)
src/ncdev/provider_dispatch.py:65:            f"Unknown provider routing name '{routing_name}'. "
src/ncdev/provider_dispatch.py:79:    routing = getattr(cfg.routing, task_key, None)
src/ncdev/provider_dispatch.py:80:    if not routing:
src/ncdev/provider_dispatch.py:82:            f"No providers configured for routing task '{task_key}'"
src/ncdev/provider_dispatch.py:84:    return resolve_provider_name(routing[0])
src/ncdev/provider_dispatch.py:87:def get_provider_for(
src/ncdev/provider_dispatch.py:93:    """Return the :class:`AIProvider` assigned to ``task_key`` by routing."""
src/ncdev/provider_dispatch.py:111:    routing = getattr(cfg.routing, task_key, None)
src/ncdev/provider_dispatch.py:112:    if not routing:
src/ncdev/provider_dispatch.py:114:    long_name = routing[0]
src/ncdev/v3/engine.py:4:+ per-task-routing + parallel-builder pipeline with a thin outer loop:
src/ncdev/v3/context_ingestion.py:228:    Codex, or OpenRouter) is resolved from ``source_ingest`` routing.
src/ncdev/v3/context_ingestion.py:241:    from ncdev.provider_dispatch import get_provider_for, preferred_model_for
src/ncdev/v3/context_ingestion.py:244:        provider = get_provider_for("source_ingest")
src/ncdev/v2/routing.py:37:def resolve_routing_plan(config: NCDevV2Config, registry: dict[str, ProviderAdapter]) -> RoutingPlanDoc:
src/ncdev/v2/routing.py:53:        configured = config.routing.providers_for(task_type)
src/ncdev/v2/routing.py:79:                rationale=f"Selected from routing config for {task_type.value}.",
src/ncdev/v2/routing.py:85:        generator="ncdev.v2.routing",
src/ncdev/v2/models.py:467:    schema_id: str = "routing-plan.v2"
src/ncdev/v2/config.py:79:    def providers_for(self, task_type: TaskType) -> list[str]:
src/ncdev/v2/config.py:150:            "Named routing preset. One of: "
src/ncdev/v2/config.py:180:    routing: RoutingConfig = Field(default_factory=RoutingConfig)
src/ncdev/v2/config.py:196:            setattr(self.routing, field, list(providers))
src/ncdev/artifacts/state.py:61:        "routing-plan.v2.json": RoutingPlanDoc.model_json_schema(),

exec
/bin/zsh -lc "sed -n '1,180p' src/ncdev/provider_dispatch.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
"""Config-driven AI provider dispatch.

Bridges :mod:`ncdev.v2.config` routing (keys like ``design_brief``,
``implementation``) to :mod:`ncdev.ai_provider` (short names like ``claude``,
``codex``, ``openrouter``). Callers ask for a provider by task key — the
preset/routing in ``.nc-dev/v2/config.yaml`` decides which CLI or API backs it.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from ncdev.ai_provider import AIProvider, get_provider
from ncdev.v2.config import NCDevV2Config, load_v2_config

logger = logging.getLogger(__name__)

# Long routing names → short registry keys used in ai_provider.py
PROVIDER_ALIASES: dict[str, str] = {
    "anthropic_claude_code": "claude",
    "openai_codex": "codex",
    "openrouter": "openrouter",
    # Pass-through short names
    "claude": "claude",
    "codex": "codex",
}

_config_cache: dict[str, NCDevV2Config] = {}


def _workspace_root(workspace: Path | None) -> Path:
    if workspace is not None:
        return Path(workspace)
    env = os.environ.get("NCDEV_WORKSPACE")
    if env:
        return Path(env)
    return Path.cwd()


def load_config(workspace: Path | None = None) -> NCDevV2Config:
    """Load (and cache) the v2 config for the given workspace."""
    root = _workspace_root(workspace)
    key = str(root.resolve())
    cached = _config_cache.get(key)
    if cached is not None:
        return cached
    cfg = load_v2_config(root)
    _config_cache[key] = cfg
    return cfg


def reset_cache() -> None:
    """Clear cached configs (useful between tests)."""
    _config_cache.clear()


def resolve_provider_name(routing_name: str) -> str:
    """Translate a v2 routing provider name (or short alias) to registry key."""
    short = PROVIDER_ALIASES.get(routing_name)
    if short is None:
        raise ValueError(
            f"Unknown provider routing name '{routing_name}'. "
            f"Known: {', '.join(sorted(PROVIDER_ALIASES))}"
        )
    return short


def provider_name_for(
    task_key: str,
    *,
    workspace: Path | None = None,
    config: NCDevV2Config | None = None,
) -> str:
    """Return the registry short name of the provider for ``task_key``."""
    cfg = config if config is not None else load_config(workspace)
    routing = getattr(cfg.routing, task_key, None)
    if not routing:
        raise ValueError(
            f"No providers configured for routing task '{task_key}'"
        )
    return resolve_provider_name(routing[0])


def get_provider_for(
    task_key: str,
    *,
    workspace: Path | None = None,
    config: NCDevV2Config | None = None,
) -> AIProvider:
    """Return the :class:`AIProvider` assigned to ``task_key`` by routing."""
    short = provider_name_for(task_key, workspace=workspace, config=config)
    return get_provider(short)


def preferred_model_for(
    task_key: str,
    model_key: str,
    *,
    workspace: Path | None = None,
    config: NCDevV2Config | None = None,
) -> Optional[str]:
    """Look up the preferred model name for a task on its assigned provider.

    Example: ``preferred_model_for("design_brief", "planning")``.
    Returns ``None`` if no preference is configured.
    """
    cfg = config if config is not None else load_config(workspace)
    routing = getattr(cfg.routing, task_key, None)
    if not routing:
        return None
    long_name = routing[0]
    prov_cfg = cfg.providers.get(long_name)
    if prov_cfg is None:
        return None
    return prov_cfg.preferred_models.get(model_key)

exec
/bin/zsh -lc "sed -n '1,240p' src/ncdev/claude_session.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
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


exec
/bin/zsh -lc "sed -n '430,620p' src/ncdev/claude_session.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
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
/bin/zsh -lc "rg -n \"console =|Console\\(\" src/ncdev/v3/claude_executor.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 exited 1 in 0ms:
codex
I found one concrete regression already: `_commit_broken()` now calls `console.print(...)`, but `console` is not defined anywhere in `claude_executor.py`. I’m checking whether that turns recoverability failures into a crash on the failure path.
exec
/bin/zsh -lc "rg -n \"console\\.print|Console\\(\" src/ncdev/v3/claude_executor.py && python3 - <<'PY'
import ast, pathlib
p=pathlib.Path('src/ncdev/v3/claude_executor.py')
mod=ast.parse(p.read_text())
print(sorted({n.id for n in ast.walk(mod) if isinstance(n, ast.Name) and n.id=='console'}))
PY" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
596:            console.print(f"  [red]BROKEN-commit: git add failed[/red]: {add.stderr[:200]}")
606:            console.print(
613:        console.print(f"  [red]BROKEN-commit: {exc}[/red]")
['console']

codex
I’ve got enough context to pin exact regressions. I’m pulling line numbers for the failure cases so the review is precise: the broken dependency semantics, the unused `_commit_broken()` return path, the undefined `console`, the partial verification claim, and the `custom`-mode routing mismatch.
exec
/bin/zsh -lc "nl -ba src/ncdev/v3/engine.py | sed -n '190,320p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
   190	            else:
   191	                console.print("  [yellow]Citex unreachable — feature builds will run without RAG grounding[/yellow]")
   192	        except Exception as exc:  # noqa: BLE001
   193	            console.print(f"  [yellow]Citex ingestion failed: {exc} — continuing without RAG[/yellow]")
   194	    else:
   195	        console.print("\n[dim]Phase 4: Context ingestion skipped (greenfield or dry run)[/dim]")
   196	
   197	    # ── Phase 5: Sequential feature execution ────────────────────────────
   198	    state.phase = "building"
   199	    completed: list[StepResult] = []
   200	
   201	    if dry_run or bundle is None:
   202	        console.print("\n[dim]Phase 5: Feature execution skipped (dry run)[/dim]")
   203	    else:
   204	        features = bundle.feature_queue.features
   205	        state.feature_queue = bundle.feature_queue
   206	        state.total_features = len(features)
   207	
   208	        # Brownfield: skip features already implemented
   209	        remaining = _filter_completed_features(target_path, features, completed)
   210	        console.print(f"\n[bold]Phase 5: Building {len(remaining)} features sequentially[/bold]")
   211	
   212	        for feature in remaining:
   213	            state.current_step = feature.feature_id
   214	            _persist_state(state, run_dir)
   215	
   216	            # Dependency gate: a feature whose depends_on_features contains
   217	            # any non-PASSED id is skipped rather than built. In strict mode,
   218	            # halt the whole run at the first broken dep.
   219	            unmet = _unmet_dependencies(feature, completed)
   220	            if unmet:
   221	                reason = (
   222	                    f"dependency not satisfied: {', '.join(unmet)} "
   223	                    "(required feature(s) are not in PASSED state)"
   224	                )
   225	                console.print(Panel(
   226	                    f"[yellow]SKIP[/yellow] {feature.feature_id} — {reason}",
   227	                    border_style="yellow",
   228	                ))
   229	                completed.append(StepResult(
   230	                    feature_id=feature.feature_id,
   231	                    status=StepStatus.SKIPPED,
   232	                    error_message=reason,
   233	                ))
   234	                state.completed_steps = completed
   235	                _persist_state(state, run_dir)
   236	                if strict_deps:
   237	                    console.print("[red]--strict-deps set: halting run[/red]")
   238	                    break
   239	                continue
   240	
   241	            console.print(Panel(
   242	                f"[cyan]{feature.feature_id}[/cyan] — {feature.title}",
   243	                border_style="blue",
   244	            ))
   245	
   246	            result = execute_feature_claude_driven(
   247	                feature=feature,
   248	                target_path=target_path,
   249	                run_dir=run_dir,
   250	                charter_bundle=bundle,
   251	                prior_results=completed,
   252	                project_id=bundle.contract.project_name,
   253	                model=builder_model,
   254	                timeout=builder_timeout,
   255	                max_budget_usd=max_budget_usd,
   256	                config=config,
   257	            )
   258	            completed.append(result)
   259	            state.completed_steps = completed
   260	            state.completed_features = len([r for r in completed if r.status == StepStatus.PASSED])
   261	            _persist_state(state, run_dir)
   262	
   263	            status_style = "green" if result.status == StepStatus.PASSED else "red"
   264	            console.print(f"  [{status_style}]{result.status.value}[/{status_style}] — commit {result.commit_sha[:8] or '(none)'}")
   265	
   266	    # ── Phase 6: Summary ─────────────────────────────────────────────────
   267	    state.phase = "complete"
   268	    passed = [r for r in completed if r.status == StepStatus.PASSED]
   269	    failed = [r for r in completed if r.status == StepStatus.FAILED]
   270	    state.status = "passed" if not failed else ("partial" if passed else "failed")
   271	
   272	    _print_summary_table(completed)
   273	
   274	    _persist_state(state, run_dir)
   275	    return state
   276	
   277	
   278	# ---------------------------------------------------------------------------
   279	# Helpers
   280	# ---------------------------------------------------------------------------
   281	
   282	
   283	def _unmet_dependencies(feature, completed: list[StepResult]) -> list[str]:
   284	    """Return the ids in ``feature.depends_on_features`` that are not PASSED.
   285	
   286	    A feature id is "satisfied" when it appears in ``completed`` with
   287	    status PASSED or SKIPPED (state scanner can mark a brownfield
   288	    feature as already-implemented → SKIPPED, which counts as met).
   289	    Missing ids (not in the completed list at all) are unmet.
   290	    """
   291	    acceptable = {
   292	        r.feature_id for r in completed
   293	        if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
   294	    }
   295	    return [dep for dep in feature.depends_on_features if dep not in acceptable]
   296	
   297	
   298	def _filter_completed_features(target_path: Path, features, completed: list[StepResult]):
   299	    """Brownfield skip: drop features already implemented in the target repo."""
   300	    try:
   301	        from ncdev.v3.state_scanner import build_skip_results, scan_completed_features
   302	    except ImportError:
   303	        return features
   304	    try:
   305	        done_ids = set(scan_completed_features(target_path, features))
   306	    except Exception:  # noqa: BLE001
   307	        return features
   308	    if not done_ids:
   309	        return features
   310	    skipped = build_skip_results(features, done_ids)
   311	    completed.extend(skipped)
   312	    remaining = [f for f in features if f.feature_id not in done_ids]
   313	    console.print(f"  [dim]Skipping {len(done_ids)} features already implemented[/dim]")
   314	    return remaining
   315	
   316	
   317	def _print_summary_table(completed: list[StepResult]) -> None:
   318	    if not completed:
   319	        return
   320	    table = Table(title="V3 Build Summary")

exec
/bin/zsh -lc "nl -ba src/ncdev/v3/claude_executor.py | sed -n '210,320p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
   210	    start = time.time()
   211	    session = run_ai_session(
   212	        prompt,
   213	        cwd=target_path,
   214	        config=config,
   215	        workspace=run_dir.parent.parent.parent if run_dir.parent.parent.parent.exists() else None,
   216	        tools=DEFAULT_BUILD_TOOLS,
   217	        model=model,
   218	        timeout=timeout,
   219	        permission_mode="acceptEdits",
   220	        max_budget_usd=max_budget_usd,
   221	        log_path=step_dir / "session.jsonl",
   222	    )
   223	    build_duration = time.time() - start
   224	
   225	    # Save session summary for debugging
   226	    (step_dir / "session-summary.txt").write_text(session.summary(), encoding="utf-8")
   227	    if session.final_text:
   228	        (step_dir / "final-response.md").write_text(session.final_text, encoding="utf-8")
   229	
   230	    post_commit = _git_head(target_path)
   231	    made_commit = bool(post_commit and post_commit != pre_commit)
   232	    dirty = _git_working_tree_dirty(target_path)
   233	
   234	    # Files the feature actually touched — used for feature-local asset
   235	    # manifest verification so one legacy unmanaged asset elsewhere in
   236	    # the repo doesn't fail every future feature.
   237	    feature_files_created, feature_files_modified = _diff_since(target_path, pre_commit)
   238	    touched = feature_files_created + feature_files_modified
   239	
   240	    # Post-hoc verification (Claude's own verification-before-completion
   241	    # skill should have caught most things; this is our belt-and-braces)
   242	    verification = _post_session_verification(
   243	        target_path, feature, charter_bundle,
   244	        run_test_commands=run_test_commands,
   245	        probe_health=probe_health,
   246	        touched_files=touched,
   247	    )
   248	
   249	    # Decide status
   250	    if session.success and made_commit and not dirty and verification.overall_passed:
   251	        status = StepStatus.PASSED
   252	    elif made_commit and verification.overall_passed:
   253	        # Claude might have exited with non-zero for trivial reasons; if
   254	        # the commit and verification are good, we accept.
   255	        status = StepStatus.PASSED
   256	    else:
   257	        # Something is wrong. Commit whatever is there with [BROKEN] tag
   258	        # so the next feature has context to build on.
   259	        if dirty:
   260	            _commit_broken(target_path, feature)
   261	            post_commit = _git_head(target_path)
   262	        status = StepStatus.FAILED
   263	
   264	    # Reuse the diff — or recompute if a [BROKEN] commit was made above
   265	    files_created = feature_files_created
   266	    files_modified = feature_files_modified
   267	    if status == StepStatus.FAILED and dirty:
   268	        files_created, files_modified = _diff_since(target_path, pre_commit)
   269	
   270	    result = StepResult(
   271	        feature_id=feature.feature_id,
   272	        status=status,
   273	        build_duration_seconds=build_duration,
   274	        verify_duration_seconds=0.0,  # Claude's in-session verification is bundled into build time
   275	        repair_attempts=0,   # Claude handles repair internally via skills
   276	        verification=verification,
   277	        files_created=files_created,
   278	        files_modified=files_modified,
   279	        commit_sha=post_commit or "",
   280	        error_message=session.error or "",
   281	        builder_output=(session.final_text or "")[:2000],
   282	    )
   283	    # Persist the session cost + skills in metadata for metrics
   284	    (step_dir / "result.json").write_text(
   285	        result.model_dump_json(indent=2), encoding="utf-8",
   286	    )
   287	    (step_dir / "signals.json").write_text(json.dumps({
   288	        "success": session.success,
   289	        "made_commit": made_commit,
   290	        "dirty_after": dirty,
   291	        "skills_invoked": session.skills_invoked,
   292	        "subagents_dispatched": session.subagents_dispatched,
   293	        "codex_invocations": len(session.codex_invocations),
   294	        "tool_calls": len(session.tool_calls),
   295	        "total_cost_usd": session.total_cost_usd,
   296	        "duration_seconds": session.duration_seconds,
   297	    }, indent=2), encoding="utf-8")
   298	
   299	    return result
   300	
   301	
   302	# ---------------------------------------------------------------------------
   303	# Post-session verification (light — Claude does the heavy lifting)
   304	# ---------------------------------------------------------------------------
   305	
   306	
   307	def _post_session_verification(
   308	    target_path: Path,
   309	    feature: FeatureStep,
   310	    bundle: CharterBundle,
   311	    *,
   312	    run_test_commands: bool = True,
   313	    probe_health: bool = True,
   314	    touched_files: list[str] | None = None,
   315	) -> StepVerification:
   316	    """Enforce every clause of the verification contract.
   317	
   318	    Belt-and-braces to Claude's in-session ``verification-before-completion``
   319	    skill — we don't trust "claimed done" to mean "actually done".
   320	    """

exec
/bin/zsh -lc "nl -ba src/ncdev/ai_session.py | sed -n '35,150p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
    35	    NCDEV_HOOKS_SETTINGS,
    36	    run_claude_session,
    37	)
    38	from ncdev.v2.config import NCDevV2Config, load_v2_config
    39	
    40	logger = logging.getLogger(__name__)
    41	
    42	
    43	# Mode → which provider runs the main orchestrator session.
    44	MODE_ORCHESTRATOR: dict[str, str] = {
    45	    "claude_plan_codex_build": "claude",
    46	    "claude_only": "claude",
    47	    "codex_only": "codex",
    48	    "openrouter": "openrouter",
    49	    "custom": "claude",   # safe default — custom may still want Claude orchestration
    50	}
    51	
    52	# Mode → who actually writes code. Used by the Claude runner to decide
    53	# whether to inject the Codex-via-Bash protocol (i.e. "delegate impl
    54	# to Codex") vs do the work itself.
    55	MODE_IMPLEMENTER: dict[str, str] = {
    56	    "claude_plan_codex_build": "codex",
    57	    "claude_only": "claude",
    58	    "codex_only": "codex",
    59	    "openrouter": "openrouter",
    60	    "custom": "codex",
    61	}
    62	
    63	
    64	def _resolve_config(
    65	    config: NCDevV2Config | None,
    66	    workspace: Path | None,
    67	) -> NCDevV2Config:
    68	    if config is not None:
    69	        return config
    70	    if workspace is not None:
    71	        try:
    72	            return load_v2_config(workspace)
    73	        except Exception:  # noqa: BLE001
    74	            pass
    75	    return NCDevV2Config()
    76	
    77	
    78	def run_ai_session(
    79	    prompt: str,
    80	    *,
    81	    cwd: Path,
    82	    config: NCDevV2Config | None = None,
    83	    workspace: Path | None = None,
    84	    tools: Iterable[str] = DEFAULT_BUILD_TOOLS,
    85	    model: str | None = None,
    86	    timeout: int = 1800,
    87	    permission_mode: str = "acceptEdits",
    88	    append_system_prompt: str | None = None,
    89	    include_codex_protocol: bool | None = None,
    90	    max_budget_usd: float | None = None,
    91	    log_path: Path | None = None,
    92	    on_event: Callable[[dict], None] | None = None,
    93	    extra_args: list[str] | None = None,
    94	    settings_path: Path | None = None,
    95	    enable_ncdev_hooks: bool = True,
    96	) -> ClaudeSessionResult:
    97	    """Run an AI session, dispatching on the active mode.
    98	
    99	    ``include_codex_protocol`` defaults to ``True`` when the mode's
   100	    implementer is Codex (i.e. Claude should delegate), ``False`` when
   101	    implementer is Claude. Explicit values win.
   102	    """
   103	    cfg = _resolve_config(config, workspace)
   104	    orch = MODE_ORCHESTRATOR.get(cfg.mode, "claude")
   105	    impl = MODE_IMPLEMENTER.get(cfg.mode, "codex")
   106	
   107	    logger.info("run_ai_session mode=%s orch=%s impl=%s cwd=%s", cfg.mode, orch, impl, cwd)
   108	
   109	    if orch == "openrouter":
   110	        raise NotImplementedError(
   111	            "openrouter mode is API-only and cannot spawn a file-editing "
   112	            "session. Install and configure the Claude or Codex CLI and "
   113	            "pick a CLI mode (claude_plan_codex_build, claude_only, or "
   114	            "codex_only)."
   115	        )
   116	
   117	    if orch == "codex":
   118	        return run_codex_session(
   119	            prompt,
   120	            cwd=cwd,
   121	            timeout=timeout,
   122	            model=model,
   123	            log_path=log_path,
   124	            extra_args=extra_args,
   125	        )
   126	
   127	    # orch == "claude"
   128	    if include_codex_protocol is None:
   129	        include_codex_protocol = (impl == "codex")
   130	
   131	    effective_model = model or "claude-opus-4-6"
   132	    return run_claude_session(
   133	        prompt,
   134	        cwd=cwd,
   135	        tools=tools,
   136	        model=effective_model,
   137	        timeout=timeout,
   138	        permission_mode=permission_mode,
   139	        append_system_prompt=append_system_prompt,
   140	        include_codex_protocol=include_codex_protocol,
   141	        max_budget_usd=max_budget_usd,
   142	        log_path=log_path,
   143	        on_event=on_event,
   144	        extra_args=extra_args,
   145	        settings_path=settings_path,
   146	        enable_ncdev_hooks=enable_ncdev_hooks,
   147	    )
   148	
   149	
   150	# ---------------------------------------------------------------------------

exec
/bin/zsh -lc "nl -ba src/ncdev/v3/claude_executor.py | sed -n '580,620p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
   580	
   581	
   582	def _commit_broken(target_path: Path, feature: FeatureStep) -> bool:
   583	    """Commit leftover dirty tree with [BROKEN] tag. Returns True on success.
   584	
   585	    Explicitly checks git return codes and surfaces failure so the
   586	    caller knows whether recoverability actually worked. If pre-commit
   587	    hooks reject the commit (e.g. the repo has its own guards), we bail
   588	    cleanly and let the orchestrator handle it.
   589	    """
   590	    try:
   591	        add = subprocess.run(
   592	            ["git", "add", "-A"],
   593	            cwd=str(target_path), capture_output=True, text=True, timeout=10,
   594	        )
   595	        if add.returncode != 0:
   596	            console.print(f"  [red]BROKEN-commit: git add failed[/red]: {add.stderr[:200]}")
   597	            return False
   598	        commit = subprocess.run(
   599	            ["git", "commit", "-m",
   600	             f"[BROKEN] {feature.feature_id}: {feature.title}\n\n"
   601	             "Claude session did not reach a clean-tree final state. "
   602	             "Committed for recoverability."],
   603	            cwd=str(target_path), capture_output=True, text=True, timeout=10,
   604	        )
   605	        if commit.returncode != 0:
   606	            console.print(
   607	                f"  [red]BROKEN-commit: git commit failed[/red] "
   608	                f"(rc={commit.returncode}): {(commit.stderr or commit.stdout)[:300]}"
   609	            )
   610	            return False
   611	        return True
   612	    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
   613	        console.print(f"  [red]BROKEN-commit: {exc}[/red]")
   614	        return False

exec
/bin/zsh -lc "nl -ba src/ncdev/ai_session.py | sed -n '150,240p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
   150	# ---------------------------------------------------------------------------
   151	# Codex runner — used by codex_only mode
   152	# ---------------------------------------------------------------------------
   153	
   154	
   155	def run_codex_session(
   156	    prompt: str,
   157	    *,
   158	    cwd: Path,
   159	    timeout: int = 1800,
   160	    model: str | None = None,
   161	    log_path: Path | None = None,
   162	    extra_args: list[str] | None = None,
   163	) -> ClaudeSessionResult:
   164	    """Run a Codex session. No skills, no subagents, no NC Dev hooks.
   165	
   166	    Codex handles planning + implementation + testing + committing in
   167	    one shot per invocation. This is the "lean mode" — you lose skill
   168	    machinery and cross-feature reasoning quality in exchange for speed
   169	    and lower cost.
   170	    """
   171	    if shutil.which("codex") is None:
   172	        return ClaudeSessionResult(
   173	            success=False, final_text="", exit_code=-1,
   174	            error="codex CLI not found on PATH",
   175	        )
   176	
   177	    # Codex prompt must be scoped — no Claude skill references.
   178	    codex_prompt = (
   179	        prompt
   180	        + "\n\n---\n\n"
   181	        + "You are running in codex_only mode (no Claude orchestrator). "
   182	        "Produce a plan, implement, write tests, and commit with "
   183	        "Conventional Commits. Leave the working tree clean when done."
   184	    )
   185	
   186	    cmd: list[str] = [
   187	        "codex", "exec",
   188	        "--full-auto",
   189	        "--sandbox", "danger-full-access",
   190	    ]
   191	    if model:
   192	        cmd += ["--model", model]
   193	    if extra_args:
   194	        cmd += list(extra_args)
   195	    cmd.append(codex_prompt)
   196	
   197	    start = time.time()
   198	    try:
   199	        proc = subprocess.run(
   200	            cmd,
   201	            cwd=str(cwd),
   202	            capture_output=True,
   203	            text=True,
   204	            timeout=timeout,
   205	        )
   206	    except subprocess.TimeoutExpired as exc:
   207	        duration = time.time() - start
   208	        stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
   209	        return ClaudeSessionResult(
   210	            success=False,
   211	            final_text=(exc.stdout or "") if isinstance(exc.stdout, str) else "",
   212	            exit_code=-1,
   213	            duration_seconds=duration,
   214	            stderr=stderr,
   215	            error=f"codex session timed out after {timeout}s",
   216	        )
   217	    except FileNotFoundError:
   218	        return ClaudeSessionResult(
   219	            success=False, final_text="", exit_code=-1,
   220	            error="codex CLI disappeared mid-invocation",
   221	        )
   222	
   223	    duration = time.time() - start
   224	    final_text = proc.stdout or ""
   225	
   226	    if log_path is not None:
   227	        log_path.parent.mkdir(parents=True, exist_ok=True)
   228	        log_path.write_text(
   229	            f"RUNNER: codex\nEXIT: {proc.returncode}\nDURATION: {duration:.1f}s\n\n"
   230	            f"STDOUT:\n{final_text}\n\nSTDERR:\n{proc.stderr or ''}\n",
   231	            encoding="utf-8",
   232	        )
   233	
   234	    return ClaudeSessionResult(
   235	        success=proc.returncode == 0,
   236	        final_text=final_text,
   237	        exit_code=proc.returncode,
   238	        duration_seconds=duration,
   239	        stderr=proc.stderr or "",
   240	        error=None if proc.returncode == 0 else f"codex exited with code {proc.returncode}",

exec
/bin/zsh -lc "nl -ba src/ncdev/claude_session.py | sed -n '240,360p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
   240	
   241	    subproc_env = os.environ.copy()
   242	    subproc_env.update(env_overrides)
   243	    popen_kwargs: dict = dict(
   244	        cwd=str(cwd),
   245	        stdout=subprocess.PIPE,
   246	        stderr=subprocess.PIPE,
   247	        text=True,
   248	        bufsize=1,
   249	        env=subproc_env,
   250	    )
   251	    if IS_POSIX:
   252	        # Own process group so we can SIGKILL the whole tree on timeout.
   253	        popen_kwargs["start_new_session"] = True
   254	
   255	    try:
   256	        proc = subprocess.Popen(cmd, **popen_kwargs)
   257	    except (FileNotFoundError, OSError) as exc:
   258	        if log_fh:
   259	            log_fh.close()
   260	        return ClaudeSessionResult(
   261	            success=False, final_text="", exit_code=-1,
   262	            error=f"failed to spawn claude: {exc}",
   263	        )
   264	
   265	    final_text = ""
   266	    skills: list[str] = []
   267	    tool_calls: list[ToolCallRecord] = []
   268	    codex_calls: list[str] = []
   269	    subagents: list[str] = []
   270	    files_touched: set[str] = set()
   271	    total_cost: float | None = None
   272	    stderr_chunks: list[str] = []
   273	
   274	    # Thread-based pipe readers prevent the two classes of hang Codex
   275	    # called out:
   276	    #   1. stderr pipe fills and backpressures the child — drain it.
   277	    #   2. stdout iteration blocks forever if Claude hangs without
   278	    #      closing stdout — watchdog sends SIGTERM/SIGKILL on timeout.
   279	    assert proc.stdout is not None and proc.stderr is not None
   280	
   281	    stderr_done = threading.Event()
   282	
   283	    def _drain_stderr() -> None:
   284	        try:
   285	            for line in proc.stderr:  # type: ignore[union-attr]
   286	                stderr_chunks.append(line)
   287	        except Exception:  # noqa: BLE001
   288	            pass
   289	        finally:
   290	            stderr_done.set()
   291	
   292	    stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
   293	    stderr_thread.start()
   294	
   295	    # Watchdog — hard kill on wall-clock expiry.
   296	    timeout_fired = threading.Event()
   297	
   298	    def _watchdog() -> None:
   299	        if timeout <= 0:
   300	            return
   301	        if proc.poll() is None:
   302	            time.sleep(timeout)
   303	        if proc.poll() is None:
   304	            timeout_fired.set()
   305	            _kill_process_tree(proc)
   306	
   307	    watchdog_thread = threading.Thread(target=_watchdog, daemon=True)
   308	    watchdog_thread.start()
   309	
   310	    try:
   311	        for line in proc.stdout:
   312	            line = line.strip()
   313	            if not line:
   314	                continue
   315	            try:
   316	                event = json.loads(line)
   317	            except json.JSONDecodeError:
   318	                if log_fh:
   319	                    log_fh.write(json.dumps({"_raw": line}) + "\n")
   320	                continue
   321	
   322	            if retain_events:
   323	                events.append(event)
   324	            else:
   325	                # Keep a small ring buffer for the final_text fallback path.
   326	                events.append(event)
   327	                if len(events) > 20:
   328	                    events.pop(0)
   329	            if log_fh:
   330	                log_fh.write(json.dumps(event) + "\n")
   331	                log_fh.flush()
   332	
   333	            _extract_event_signals(
   334	                event,
   335	                skills=skills,
   336	                tool_calls=tool_calls,
   337	                codex_calls=codex_calls,
   338	                subagents=subagents,
   339	                files_touched=files_touched,
   340	            )
   341	
   342	            if event.get("type") == "result":
   343	                final_text = event.get("result") or event.get("text") or final_text
   344	                total_cost = event.get("total_cost_usd", total_cost)
   345	
   346	            if on_event is not None:
   347	                try:
   348	                    on_event(event)
   349	                except Exception:  # noqa: BLE001
   350	                    pass
   351	    finally:
   352	        # Always wait for the process and join the stderr reader so we
   353	        # capture its output and don't leave zombies. The watchdog will
   354	        # have killed on timeout already.
   355	        try:
   356	            proc.wait(timeout=30)
   357	        except subprocess.TimeoutExpired:
   358	            _kill_process_tree(proc)
   359	            try:
   360	                proc.wait(timeout=5)

exec
/bin/zsh -lc "nl -ba src/ncdev/v3/design_phase.py | sed -n '250,360p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
   250	    stitch_probe: callable = stitch_available,
   251	    config: NCDevV2Config | None = None,
   252	) -> DesignPhaseResult:
   253	    """Resolve the design system for this project.
   254	
   255	    Returns a :class:`DesignPhaseResult`. The caller MUST check
   256	    ``hard_failed`` and abort the pipeline when True.
   257	    """
   258	    output_dir.mkdir(parents=True, exist_ok=True)
   259	
   260	    # Non-UI projects skip the design phase entirely.
   261	    if not is_ui_project(contract):
   262	        return DesignPhaseResult(skipped=True)
   263	
   264	    has_existing = existing_design_system_present(target_path)
   265	    has_stitch = stitch_probe()
   266	
   267	    # --- Hard-fail: greenfield UI, no existing designs, no Stitch ----------
   268	    if not contract.is_brownfield and not has_existing and not has_stitch:
   269	        err_path = output_dir / "design-phase-error.json"
   270	        err_path.write_text(
   271	            '{"error": "greenfield UI project requires a design system",'
   272	            ' "fix": "install and configure the Stitch MCP server, or '
   273	            'supply docs/design-system/ with design tokens and sample pages"}',
   274	            encoding="utf-8",
   275	        )
   276	        return DesignPhaseResult(
   277	            hard_failed=True,
   278	            error="greenfield UI project requires a design system (Stitch or docs/design-system)",
   279	        )
   280	
   281	    # --- Brownfield with existing design system ----------------------------
   282	    if has_existing:
   283	        prompt = _brownfield_prompt(contract, target_path, output_dir)
   284	        session = run_ai_session(
   285	            prompt,
   286	            cwd=target_path,
   287	            config=config,
   288	            tools=SUMMARISE_DESIGN_TOOLS,   # read-only + write the summary JSON
   289	            model=model,
   290	            timeout=timeout,
   291	            include_codex_protocol=False,
   292	            max_budget_usd=max_budget_usd,
   293	            log_path=log_path,
   294	        )
   295	        return _finalise_design_phase(session, output_dir)
   296	
   297	    # --- Greenfield (or brownfield without designs) + Stitch available ----
   298	    if has_stitch:
   299	        prompt = _stitch_prompt(contract, target_path, output_dir)
   300	        session = run_ai_session(
   301	            prompt,
   302	            cwd=target_path,
   303	            config=config,
   304	            tools=STITCH_DESIGN_TOOLS,
   305	            model=model,
   306	            timeout=timeout,
   307	            include_codex_protocol=False,   # design phase does not build code
   308	            max_budget_usd=max_budget_usd,
   309	            log_path=log_path,
   310	        )
   311	        return _finalise_design_phase(session, output_dir)
   312	
   313	    # --- Brownfield without existing designs and no Stitch: Claude decides --
   314	    # Per the user's ruling: "brownfield or design-provided → Claude makes
   315	    # the call". We spawn Claude with the frontend-design skill; it may
   316	    # generate tokens itself.
   317	    prompt = (
   318	        f"This is a brownfield project '{contract.project_name}' without "
   319	        f"a pre-existing design system and without Stitch MCP available. "
   320	        f"Use the `frontend-design` skill to produce minimal design tokens "
   321	        f"aligned with the '{contract.design_archetype}' archetype, "
   322	        f"write them into {target_path}/docs/design-system/, and "
   323	        f"summarise in {output_dir}/design-system.json with source='claude_generated'. "
   324	        f"If you determine the project genuinely needs Stitch or external "
   325	        f"designs to proceed, write design-phase-error.json instead."
   326	    )
   327	    session = run_ai_session(
   328	        prompt,
   329	        cwd=target_path,
   330	        config=config,
   331	        tools=STITCH_DESIGN_TOOLS,
   332	        model=model,
   333	        timeout=timeout,
   334	        include_codex_protocol=False,
   335	        max_budget_usd=max_budget_usd,
   336	        log_path=log_path,
   337	    )
   338	    return _finalise_design_phase(session, output_dir)
   339	
   340	
   341	def _finalise_design_phase(session, output_dir: Path) -> DesignPhaseResult:
   342	    """Enforce success + artifact presence for every non-skip branch.
   343	
   344	    Required for a pass: the AI session must have exited cleanly AND a
   345	    parseable design-system.json must exist on disk. A design-phase-error
   346	    file written by the session is always a hard fail.
   347	    """
   348	    err_path = output_dir / "design-phase-error.json"
   349	    if err_path.exists():
   350	        return DesignPhaseResult(
   351	            hard_failed=True,
   352	            session=session,
   353	            error=f"Design phase wrote error artifact at {err_path}",
   354	        )
   355	    if not session.success:
   356	        return DesignPhaseResult(
   357	            hard_failed=True,
   358	            session=session,
   359	            error=f"Design session exited unsuccessfully: {session.error or 'no detail'}",
   360	        )

exec
/bin/zsh -lc "nl -ba scripts/ncdev-hooks/pre_bash_guard.py | sed -n '95,155p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
    95	        added = [
    96	            line[1:] for line in r.stdout.splitlines()
    97	            if line.startswith("+") and not line.startswith("+++")
    98	        ]
    99	        blob = "\n".join(added)
   100	        for pat in patterns:
   101	            if pat in blob:
   102	                hits.append(f"{path}:{pat}")
   103	                if len(hits) > 20:
   104	                    return hits
   105	    return hits
   106	
   107	
   108	_HEREDOC_SENTINEL = re.compile(r"<<-?\s*['\"]?(\w+)")
   109	
   110	
   111	def _extract_commit_message(cmd: str) -> tuple[str | None, str]:
   112	    """Pull the ``-m`` argument out of a git-commit command.
   113	
   114	    Returns ``(message, parse_mode)`` where ``parse_mode`` is:
   115	        * "literal"   — we parsed a plain quoted string cleanly
   116	        * "heredoc"   — message is being supplied via a HEREDOC
   117	        * "file"      — ``-F <file>`` used; message is in a file
   118	        * "unknown"   — we don't know what the message is
   119	
   120	    Callers can treat "unknown" as "can't enforce, allow through" to
   121	    avoid breaking legitimate non-inline commit flows.
   122	    """
   123	    # -F <file> — message read from a file
   124	    if re.search(r"(?:^|\s)(?:-F|--file)\s+\S+", cmd):
   125	        return None, "file"
   126	
   127	    # HEREDOC substitution — e.g. git commit -m "$(cat <<'EOF' ... EOF )"
   128	    if _HEREDOC_SENTINEL.search(cmd):
   129	        return None, "heredoc"
   130	
   131	    # Plain quoted message. Handles escaped quotes inside the value by
   132	    # looking for the matching close quote that isn't preceded by a
   133	    # backslash. Double-quote and single-quote variants.
   134	    for quote in ("'", '"'):
   135	        pattern = rf"""-m\s+{quote}((?:\\.|(?!{quote}).)*){quote}"""
   136	        m = re.search(pattern, cmd, flags=re.DOTALL)
   137	        if m:
   138	            raw = m.group(1)
   139	            # Un-escape the quotes so downstream callers see the real message
   140	            raw = raw.replace(f"\\{quote}", quote)
   141	            return raw, "literal"
   142	
   143	    return None, "unknown"
   144	
   145	
   146	def _is_force_push_to_protected(cmd: str) -> bool:
   147	    if "git push" not in cmd:
   148	        return False
   149	    if "--force" not in cmd and "-f " not in cmd and not cmd.rstrip().endswith("-f"):
   150	        return False
   151	    # protected refs
   152	    for ref in ("main", "master", "production", "prod"):
   153	        if re.search(rf"\b{ref}\b", cmd):
   154	            return True
   155	    return False

exec
/bin/zsh -lc "nl -ba src/ncdev/v3/claude_executor.py | sed -n '320,430p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
   320	    """
   321	    ver = StepVerification()
   322	    reasons: list[str] = []
   323	
   324	    # 1. Required files from the verification contract must all exist
   325	    for req in bundle.verification.required_files:
   326	        if not (target_path / req).exists():
   327	            reasons.append(f"required file missing: {req}")
   328	
   329	    # 2. Asset manifest must exist and cover code references
   330	    if bundle.verification.assets_manifest_required:
   331	        ok, missing = verify_manifest_covers_references(
   332	            target_path, feature.feature_id,
   333	            touched_files=touched_files,
   334	        )
   335	        if not ok:
   336	            if missing == ["<no-manifest>"]:
   337	                reasons.append(f"asset manifest not written for {feature.feature_id}")
   338	            else:
   339	                reasons.append(f"asset references without manifest: {missing[:5]}")
   340	
   341	    # 3. Prohibited patterns (regex — treats entries in the contract as
   342	    #    patterns, falls back to literal match if the regex fails to compile)
   343	    patterns = bundle.verification.prohibited_patterns
   344	    if patterns:
   345	        bad = _grep_for_prohibited(target_path, patterns)
   346	        if bad:
   347	            reasons.append(f"prohibited patterns found: {bad[:5]}")
   348	
   349	    # 4. Required screenshots must exist on disk
   350	    for shot in bundle.verification.required_screenshots:
   351	        if not _screenshot_exists(target_path, shot):
   352	            reasons.append(f"required screenshot not captured: {shot}")
   353	
   354	    # 5. Minimum test count — prevents "0 tests, all green" gaming
   355	    if bundle.verification.minimum_test_count > 0:
   356	        count = _count_test_files(target_path)
   357	        ver.unit_tests = TestResult(suite="unit", passed=count, success=count > 0)
   358	        if count < bundle.verification.minimum_test_count:
   359	            reasons.append(
   360	                f"test file count {count} below minimum "
   361	                f"{bundle.verification.minimum_test_count}"
   362	            )
   363	
   364	    # 6. Run the declared test commands
   365	    if run_test_commands:
   366	        if bundle.verification.backend_test_command:
   367	            ok, out = _run_shell(
   368	                bundle.verification.backend_test_command,
   369	                cwd=target_path, timeout=600,
   370	            )
   371	            ver.integration_tests = TestResult(
   372	                suite="backend", passed=1 if ok else 0,
   373	                failed=0 if ok else 1, success=ok, output=out[:2000],
   374	            )
   375	            if not ok:
   376	                reasons.append(f"backend tests failed: {_last_line(out)}")
   377	        if bundle.verification.frontend_test_command:
   378	            ok, out = _run_shell(
   379	                bundle.verification.frontend_test_command,
   380	                cwd=target_path, timeout=600,
   381	            )
   382	            ver.e2e_tests = TestResult(
   383	                suite="frontend", passed=1 if ok else 0,
   384	                failed=0 if ok else 1, success=ok, output=out[:2000],
   385	            )
   386	            if not ok:
   387	                reasons.append(f"frontend tests failed: {_last_line(out)}")
   388	
   389	    # 7. Best-effort health probe — Claude may have left the app running;
   390	    #    if so, we probe it. If it's down, treat as a soft signal, not
   391	    #    a hard failure (feature may have been built to spec without
   392	    #    leaving the app booted).
   393	    if probe_health and bundle.verification.backend_health_url:
   394	        reachable = _probe_health(
   395	            bundle.verification.backend_health_url,
   396	            timeout=bundle.verification.boot_timeout_seconds,
   397	        )
   398	        ver.app_boots = reachable
   399	        # Not added to reasons — soft signal only. Explicit boot
   400	        # enforcement requires the orchestrator to start the app itself,
   401	        # which is out of scope for post-hoc verification.
   402	
   403	    ver.failure_reasons = reasons
   404	    ver.overall_passed = not reasons
   405	    ver.prohibited_patterns = [r for r in reasons if "prohibited" in r.lower()]
   406	    return ver
   407	
   408	
   409	def _grep_for_prohibited(target_path: Path, patterns: list[str]) -> list[str]:
   410	    """Scan git-tracked files for prohibited patterns.
   411	
   412	    Each entry is treated as a regular expression via ``re.search``. If
   413	    a pattern fails to compile, falls back to a substring check so
   414	    human-written entries like ``TODO`` still work.
   415	    """
   416	    compiled: list[tuple[str, re.Pattern[str] | None]] = []
   417	    for pat in patterns:
   418	        try:
   419	            compiled.append((pat, re.compile(pat)))
   420	        except re.error:
   421	            compiled.append((pat, None))
   422	
   423	    hits: list[str] = []
   424	    try:
   425	        ls = subprocess.run(
   426	            ["git", "ls-files"],
   427	            cwd=str(target_path), capture_output=True, text=True, timeout=10,
   428	        )
   429	        if ls.returncode != 0:
   430	            return []

exec
/bin/zsh -lc "nl -ba tests/test_ncdev_v3/test_dependency_gating.py | sed -n '1,120p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
     1	"""Tests for Fix 4 — dependency gating in the engine feature loop."""
     2	
     3	from __future__ import annotations
     4	
     5	from ncdev.v3.engine import _unmet_dependencies
     6	from ncdev.v3.models import FeatureStep, StepResult, StepStatus
     7	
     8	
     9	def _feat(fid: str, deps: list[str] | None = None) -> FeatureStep:
    10	    return FeatureStep(
    11	        feature_id=fid,
    12	        title=fid,
    13	        description="",
    14	        acceptance_criteria=[],
    15	        depends_on_features=deps or [],
    16	    )
    17	
    18	
    19	def test_no_deps_is_always_satisfied():
    20	    f = _feat("f05", deps=[])
    21	    assert _unmet_dependencies(f, completed=[]) == []
    22	
    23	
    24	def test_dependency_not_yet_built_is_unmet():
    25	    f = _feat("f02", deps=["f01"])
    26	    assert _unmet_dependencies(f, completed=[]) == ["f01"]
    27	
    28	
    29	def test_dependency_passed_is_satisfied():
    30	    f = _feat("f02", deps=["f01"])
    31	    completed = [StepResult(feature_id="f01", status=StepStatus.PASSED)]
    32	    assert _unmet_dependencies(f, completed=completed) == []
    33	
    34	
    35	def test_dependency_failed_is_unmet():
    36	    """A failed dependency is NOT satisfied — downstream must skip."""
    37	    f = _feat("f02", deps=["f01"])
    38	    completed = [StepResult(feature_id="f01", status=StepStatus.FAILED)]
    39	    assert _unmet_dependencies(f, completed=completed) == ["f01"]
    40	
    41	
    42	def test_dependency_skipped_counts_as_satisfied():
    43	    """Brownfield state scanner marks already-implemented features as
    44	    SKIPPED — those should still count as satisfying a dep."""
    45	    f = _feat("f02", deps=["f01"])
    46	    completed = [StepResult(feature_id="f01", status=StepStatus.SKIPPED)]
    47	    assert _unmet_dependencies(f, completed=completed) == []
    48	
    49	
    50	def test_multiple_deps_partial_satisfaction():
    51	    f = _feat("f03", deps=["f01", "f02"])
    52	    completed = [
    53	        StepResult(feature_id="f01", status=StepStatus.PASSED),
    54	        StepResult(feature_id="f02", status=StepStatus.FAILED),
    55	    ]
    56	    assert _unmet_dependencies(f, completed=completed) == ["f02"]
    57	
    58	
    59	def test_dep_returns_all_unmet_in_order():
    60	    f = _feat("f05", deps=["f01", "f02", "f03", "f04"])
    61	    completed = [
    62	        StepResult(feature_id="f01", status=StepStatus.PASSED),
    63	        StepResult(feature_id="f03", status=StepStatus.PASSED),
    64	    ]
    65	    # f02 and f04 missing entirely — both unmet, order preserved
    66	    assert _unmet_dependencies(f, completed=completed) == ["f02", "f04"]

exec
/bin/zsh -lc "nl -ba tests/unit/test_hooks.py | sed -n '70,150p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
    70	])
    71	def test_conventional_messages_pass(tmp_path: Path, good: str):
    72	    _init_git_with_staged(tmp_path, {"foo.py": "x = 1\n"})
    73	    cmd = f'git commit -m "{good}"'
    74	    decision, reason = pre_bash_guard.evaluate("Bash", {"command": cmd}, cwd=str(tmp_path))
    75	    assert decision == "allow", reason
    76	
    77	
    78	@pytest.mark.parametrize("bad", [
    79	    "updated stuff",
    80	    "WIP",
    81	    "quick fix",
    82	    "Added feature",
    83	])
    84	def test_non_conventional_messages_blocked(tmp_path: Path, bad: str):
    85	    _init_git_with_staged(tmp_path, {"foo.py": "x = 1\n"})
    86	    cmd = f'git commit -m "{bad}"'
    87	    decision, reason = pre_bash_guard.evaluate("Bash", {"command": cmd}, cwd=str(tmp_path))
    88	    assert decision == "block"
    89	    assert "Conventional Commits" in reason
    90	
    91	
    92	def test_commit_with_F_file_flag_is_allowed(tmp_path: Path):
    93	    """-F <file> — message is in a file; we can't introspect, allow."""
    94	    _init_git_with_staged(tmp_path, {"foo.py": "x = 1\n"})
    95	    decision, _ = pre_bash_guard.evaluate(
    96	        "Bash",
    97	        {"command": 'git commit -F message.txt'},
    98	        cwd=str(tmp_path),
    99	    )
   100	    assert decision == "allow"
   101	
   102	
   103	def test_commit_with_heredoc_is_allowed(tmp_path: Path):
   104	    """HEREDOC substitution — can't parse the message cheaply, allow."""
   105	    _init_git_with_staged(tmp_path, {"foo.py": "x = 1\n"})
   106	    cmd = '''git commit -m "$(cat <<'EOF'
   107	feat: add heredoc support
   108	EOF
   109	)"'''
   110	    decision, _ = pre_bash_guard.evaluate(
   111	        "Bash", {"command": cmd}, cwd=str(tmp_path),
   112	    )
   113	    assert decision == "allow"
   114	
   115	
   116	def test_commit_message_with_escaped_quotes_parses_correctly(tmp_path: Path):
   117	    """Codex flag: escaped inner quotes broke the extractor. Verify fix."""
   118	    _init_git_with_staged(tmp_path, {"foo.py": "x = 1\n"})
   119	    cmd = 'git commit -m "feat: handle \\"escaped\\" quotes"'
   120	    decision, reason = pre_bash_guard.evaluate(
   121	        "Bash", {"command": cmd}, cwd=str(tmp_path),
   122	    )
   123	    # The message starts with "feat:" so Conventional Commits accepts it
   124	    assert decision == "allow", reason
   125	
   126	
   127	def test_bad_message_with_escaped_quotes_still_blocked(tmp_path: Path):
   128	    """Extractor must not be tricked into missing a bad message by escapes."""
   129	    _init_git_with_staged(tmp_path, {"foo.py": "x = 1\n"})
   130	    cmd = 'git commit -m "updated \\"thing\\" again"'
   131	    decision, reason = pre_bash_guard.evaluate(
   132	        "Bash", {"command": cmd}, cwd=str(tmp_path),
   133	    )
   134	    assert decision == "block"
   135	    assert "Conventional Commits" in reason
   136	
   137	
   138	# ---------------------------------------------------------------------------
   139	# Prohibited patterns
   140	# ---------------------------------------------------------------------------
   141	
   142	
   143	def test_staged_content_with_todo_is_blocked(tmp_path: Path):
   144	    _init_git_with_staged(tmp_path, {
   145	        "src/app.py": "def run():\n    # TODO implement\n    pass\n",
   146	    })
   147	    decision, reason = pre_bash_guard.evaluate(
   148	        "Bash",
   149	        {"command": 'git commit -m "feat: initial"'},
   150	        cwd=str(tmp_path),

exec
/bin/zsh -lc "nl -ba tests/unit/test_ai_session.py | sed -n '120,170p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
   120	
   121	
   122	def test_claude_only_does_not_call_codex(tmp_path: Path):
   123	    cfg = NCDevV2Config(mode="claude_only")
   124	
   125	    def fake_codex(*a, **k):  # noqa: ARG001
   126	        raise AssertionError("Codex session must not be invoked in claude_only mode")
   127	
   128	    with patch("ncdev.ai_session.run_codex_session", side_effect=fake_codex):
   129	        with patch("ncdev.ai_session.run_claude_session", return_value=_claude_result()):
   130	            run_ai_session("x", cwd=tmp_path, config=cfg)
   131	
   132	
   133	def test_openrouter_raises_not_implemented(tmp_path: Path):
   134	    cfg = NCDevV2Config(mode="openrouter")
   135	    with pytest.raises(NotImplementedError, match="API-only"):
   136	        run_ai_session("x", cwd=tmp_path, config=cfg)
   137	
   138	
   139	def test_custom_mode_defaults_to_claude(tmp_path: Path):
   140	    cfg = NCDevV2Config(mode="custom")
   141	    captured: dict = {}
   142	
   143	    def fake_claude(prompt, **kwargs):
   144	        captured.update(kwargs)
   145	        return _claude_result()
   146	
   147	    with patch("ncdev.ai_session.run_claude_session", side_effect=fake_claude):
   148	        run_ai_session("x", cwd=tmp_path, config=cfg)
   149	    # custom → claude orchestrator, codex implementer → protocol on
   150	    assert captured["include_codex_protocol"] is True
   151	
   152	
   153	def test_explicit_include_codex_protocol_wins_over_mode_default(tmp_path: Path):
   154	    """Caller can override the mode-inferred default."""
   155	    cfg = NCDevV2Config(mode="claude_plan_codex_build")  # would default True
   156	    captured: dict = {}
   157	
   158	    def fake_claude(prompt, **kwargs):
   159	        captured.update(kwargs)
   160	        return _claude_result()
   161	
   162	    with patch("ncdev.ai_session.run_claude_session", side_effect=fake_claude):
   163	        run_ai_session(
   164	            "x", cwd=tmp_path, config=cfg, include_codex_protocol=False,
   165	        )
   166	    assert captured["include_codex_protocol"] is False
   167	
   168	
   169	# ---------------------------------------------------------------------------
   170	# run_codex_session

codex
I’m doing one quick verification pass on the affected test files with the local runner if it’s available. If the environment still can’t run pytest, I’ll call that out and keep this as a static review.
exec
/bin/zsh -lc 'rg -n "pytest|tool.pytest|uv" pyproject.toml requirements*.txt setup.cfg . && (python3 -m pytest -q tests/unit/test_ai_session.py tests/unit/test_design_phase.py tests/test_ncdev_v3/test_dependency_gating.py >/tmp/ncdev_pytest.out 2>&1; echo $? )' in /Users/nrupal/dev/yensi/dev/nc-dev-system
 exited 1 in 0ms:
zsh:1: no matches found: requirements*.txt

exec
/bin/zsh -lc 'cat /tmp/ncdev_pytest.out' in /Users/nrupal/dev/yensi/dev/nc-dev-system
 exited 1 in 0ms:
cat: /tmp/ncdev_pytest.out: No such file or directory

codex
The first test command tripped on shell globbing, so I’m rerunning it cleanly. If pytest still isn’t installed, that will settle quickly.
exec
/bin/zsh -lc 'rg -n "pytest|tool.pytest|uv" pyproject.toml setup.cfg requirements.txt requirements-dev.txt 2>/dev/null' in /Users/nrupal/dev/yensi/dev/nc-dev-system
 exited 2 in 0ms:
pyproject.toml:24:  "pytest>=8.3,<9",
pyproject.toml:25:  "pytest-asyncio>=0.23",
pyproject.toml:26:  "pytest-cov>=5.0",
pyproject.toml:27:  "pytest-mock>=3.12",
pyproject.toml:28:  "pytest-timeout>=2.2",
pyproject.toml:40:[tool.pytest.ini_options]

exec
/bin/zsh -lc 'python3 -m pytest -q tests/unit/test_ai_session.py tests/unit/test_design_phase.py tests/test_ncdev_v3/test_dependency_gating.py' in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 4755ms:
........................................                                 [100%]

codex
## Architecture verdict
The hardening pass moved the code materially forward: the Claude runner is now much harder to wedge, the design phase now fails where it should, and V3 finally respects the mode switch for the normal presets. But this is not “all critical issues resolved.” One fix regressed dependency semantics badly, recoverability is still overstated, and `custom` mode still violates the config contract.

## Fixes verified (the good)
- The mode switch now actually reaches V3 for the non-`custom` presets. [engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:74), [engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:109), [engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:147), and [engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:246) now thread `config` through, and [ai_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/ai_session.py:103) dispatches `claude_only` / `codex_only` / `openrouter` correctly.
- The charter/design boundary is fixed. Charter no longer tries to hard-fail greenfield UI, and design phase owns that decision where it belongs. The non-skip branches all funnel through [_finalise_design_phase()`](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:341), and non-UI projects still skip cleanly at [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:260).
- The Claude subprocess hardening is real. The stderr drain thread and watchdog kill path at [claude_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/claude_session.py:281) and [claude_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/claude_session.py:351) address the deadlock/timeout problem I flagged.
- The ring buffer is fine for the specific case you called out. `final_text` is captured inline on `result` events at [claude_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/claude_session.py:342), so trimming that event later does not lose the final result.
- Feature-local asset verification landed correctly. The executor now scopes verification to touched files at [claude_executor.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:234), and the manifest verifier honors that at [asset_manifest.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/asset_manifest.py:231).
- The escaped-quote commit-message bug is fixed in the hook parser at [pre_bash_guard.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/scripts/ncdev-hooks/pre_bash_guard.py:131).
- The post-hoc prohibited-pattern check now really supports regex patterns at [claude_executor.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:341).

## Fixes that didn't land
- “Verification contract is enforced” is still too strong. Tests, screenshots, and minimum test count are now enforced, but app boot is explicitly not gating: [claude_executor.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:389) records `app_boots` as a soft signal only. That means one of the central clauses from the contract is still advisory.
- `_commit_broken()` “no more silent recoverability loss” did not actually land. The helper returns `bool`, but the caller ignores it at [claude_executor.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:259). Even if it failed cleanly, orchestration would not react.
- `custom` mode is still wrong. `v2/config.py` explicitly says `custom` preserves hand-tuned routing at [config.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v2/config.py:29) and [config.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v2/config.py:186), but [ai_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/ai_session.py:44) hardcodes `custom -> claude orchestrator + codex implementer`. The new test at [test_ai_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/tests/unit/test_ai_session.py:139) locks in that mismatch instead of catching it.

## New issues introduced
- The dependency gate is now semantically wrong. `_unmet_dependencies()` treats every `SKIPPED` dependency as satisfied at [engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:283). That conflates “already implemented in brownfield, safe to skip” with “skipped because an upstream dependency failed.” So `f03` can run even when `f02` never built. The new test at [test_dependency_gating.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/tests/test_ncdev_v3/test_dependency_gating.py:42) codifies the bug.
- `--strict-deps` can still report success after halting on dependency failure. The loop appends a `SKIPPED` result and `break`s at [engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:229), but final run status only looks for `FAILED` results at [engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:267). A run can stop early on broken deps and still finish `"passed"`.
- `_commit_broken()` now has a new failure-path crash: it calls `console.print(...)` at [claude_executor.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:596), [claude_executor.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:606), and [claude_executor.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:613), but `console` is not defined anywhere in the module.

## Previously concerning, still concerning
- The hook and the post-hoc verifier still disagree on prohibited-pattern semantics. The verifier does regex matching at [claude_executor.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:341), but the hook still does literal substring checks only at [pre_bash_guard.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/scripts/ncdev-hooks/pre_bash_guard.py:95). So some bad patterns are still caught only after the commit path.
- Commit-message enforcement is still easy to sidestep with non-literal `-m` forms. `_extract_commit_message()` falls back to `"unknown"` at [pre_bash_guard.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/scripts/ncdev-hooks/pre_bash_guard.py:143), and `evaluate()` allows that path through.
- `_extract_event_signals()` is still brittle observability code. It only understands tool use nested under `assistant.message.content[].tool_use` at [claude_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/claude_session.py:452). The runner is safer now, but the metrics are still schema-fragile.
- `run_codex_session()` does not have the Claude deadlock bug, because `subprocess.run(..., capture_output=True)` drains both pipes, but it is still an unbounded memory buffer at [ai_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/ai_session.py:199). A very chatty Codex run can still blow RAM or produce huge logs.

## Now truly over-engineered
- The filename whitelist in `existing_design_system_present()` at [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:96) fixes the old false-positive bug, but it does it with a brittle policy list instead of validating token content. That is maintenance-heavy and easy to false-negative on legitimate brownfield systems.
- `ai_session.py` now duplicates mode/routing policy that already exists in `v2/config.py`. That duplication is exactly why `custom` drifted.

## Honest one-liner
Not yet. I’d inherit the runner and the design-phase hardening, but I would not trust the dependency gate or the recoverability path in the current state.

I also ran the targeted tests for `test_ai_session.py`, `test_design_phase.py`, and `test_dependency_gating.py`; they pass. That does not change the review, because one of those passing tests is locking in the bad `SKIPPED == satisfied` dependency behavior.
tokens used
147,971
## Architecture verdict
The hardening pass moved the code materially forward: the Claude runner is now much harder to wedge, the design phase now fails where it should, and V3 finally respects the mode switch for the normal presets. But this is not “all critical issues resolved.” One fix regressed dependency semantics badly, recoverability is still overstated, and `custom` mode still violates the config contract.

## Fixes verified (the good)
- The mode switch now actually reaches V3 for the non-`custom` presets. [engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:74), [engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:109), [engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:147), and [engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:246) now thread `config` through, and [ai_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/ai_session.py:103) dispatches `claude_only` / `codex_only` / `openrouter` correctly.
- The charter/design boundary is fixed. Charter no longer tries to hard-fail greenfield UI, and design phase owns that decision where it belongs. The non-skip branches all funnel through [_finalise_design_phase()`](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:341), and non-UI projects still skip cleanly at [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:260).
- The Claude subprocess hardening is real. The stderr drain thread and watchdog kill path at [claude_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/claude_session.py:281) and [claude_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/claude_session.py:351) address the deadlock/timeout problem I flagged.
- The ring buffer is fine for the specific case you called out. `final_text` is captured inline on `result` events at [claude_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/claude_session.py:342), so trimming that event later does not lose the final result.
- Feature-local asset verification landed correctly. The executor now scopes verification to touched files at [claude_executor.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:234), and the manifest verifier honors that at [asset_manifest.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/asset_manifest.py:231).
- The escaped-quote commit-message bug is fixed in the hook parser at [pre_bash_guard.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/scripts/ncdev-hooks/pre_bash_guard.py:131).
- The post-hoc prohibited-pattern check now really supports regex patterns at [claude_executor.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:341).

## Fixes that didn't land
- “Verification contract is enforced” is still too strong. Tests, screenshots, and minimum test count are now enforced, but app boot is explicitly not gating: [claude_executor.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:389) records `app_boots` as a soft signal only. That means one of the central clauses from the contract is still advisory.
- `_commit_broken()` “no more silent recoverability loss” did not actually land. The helper returns `bool`, but the caller ignores it at [claude_executor.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:259). Even if it failed cleanly, orchestration would not react.
- `custom` mode is still wrong. `v2/config.py` explicitly says `custom` preserves hand-tuned routing at [config.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v2/config.py:29) and [config.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v2/config.py:186), but [ai_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/ai_session.py:44) hardcodes `custom -> claude orchestrator + codex implementer`. The new test at [test_ai_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/tests/unit/test_ai_session.py:139) locks in that mismatch instead of catching it.

## New issues introduced
- The dependency gate is now semantically wrong. `_unmet_dependencies()` treats every `SKIPPED` dependency as satisfied at [engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:283). That conflates “already implemented in brownfield, safe to skip” with “skipped because an upstream dependency failed.” So `f03` can run even when `f02` never built. The new test at [test_dependency_gating.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/tests/test_ncdev_v3/test_dependency_gating.py:42) codifies the bug.
- `--strict-deps` can still report success after halting on dependency failure. The loop appends a `SKIPPED` result and `break`s at [engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:229), but final run status only looks for `FAILED` results at [engine.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:267). A run can stop early on broken deps and still finish `"passed"`.
- `_commit_broken()` now has a new failure-path crash: it calls `console.print(...)` at [claude_executor.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:596), [claude_executor.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:606), and [claude_executor.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:613), but `console` is not defined anywhere in the module.

## Previously concerning, still concerning
- The hook and the post-hoc verifier still disagree on prohibited-pattern semantics. The verifier does regex matching at [claude_executor.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:341), but the hook still does literal substring checks only at [pre_bash_guard.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/scripts/ncdev-hooks/pre_bash_guard.py:95). So some bad patterns are still caught only after the commit path.
- Commit-message enforcement is still easy to sidestep with non-literal `-m` forms. `_extract_commit_message()` falls back to `"unknown"` at [pre_bash_guard.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/scripts/ncdev-hooks/pre_bash_guard.py:143), and `evaluate()` allows that path through.
- `_extract_event_signals()` is still brittle observability code. It only understands tool use nested under `assistant.message.content[].tool_use` at [claude_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/claude_session.py:452). The runner is safer now, but the metrics are still schema-fragile.
- `run_codex_session()` does not have the Claude deadlock bug, because `subprocess.run(..., capture_output=True)` drains both pipes, but it is still an unbounded memory buffer at [ai_session.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/ai_session.py:199). A very chatty Codex run can still blow RAM or produce huge logs.

## Now truly over-engineered
- The filename whitelist in `existing_design_system_present()` at [design_phase.py](/Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/design_phase.py:96) fixes the old false-positive bug, but it does it with a brittle policy list instead of validating token content. That is maintenance-heavy and easy to false-negative on legitimate brownfield systems.
- `ai_session.py` now duplicates mode/routing policy that already exists in `v2/config.py`. That duplication is exactly why `custom` drifted.

## Honest one-liner
Not yet. I’d inherit the runner and the design-phase hardening, but I would not trust the dependency gate or the recoverability path in the current state.

I also ran the targeted tests for `test_ai_session.py`, `test_design_phase.py`, and `test_dependency_gating.py`; they pass. That does not change the review, because one of those passing tests is locking in the bad `SKIPPED == satisfied` dependency behavior.
