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
/bin/zsh -lc 'git diff --stat f19934b..4a5a0f7 && git diff --name-only f19934b..4a5a0f7' in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
 docs/codex-review/review-request-round2.md    |  210 +
 docs/codex-review/review-response-round2.md   | 7134 +++++++++++++++++++++++++
 scripts/ncdev-hooks/pre_bash_guard.py         |   22 +-
 src/ncdev/ai_session.py                       |  231 +-
 src/ncdev/v3/claude_executor.py               |   49 +-
 src/ncdev/v3/engine.py                        |   36 +-
 src/ncdev/v3/models.py                        |    3 +-
 tests/test_ncdev_v3/test_dependency_gating.py |   16 +-
 tests/unit/test_ai_session.py                 |  188 +-
 tests/unit/test_claude_executor.py            |   66 +
 tests/unit/test_hooks.py                      |   18 +
 11 files changed, 7871 insertions(+), 102 deletions(-)
docs/codex-review/review-request-round2.md
docs/codex-review/review-response-round2.md
scripts/ncdev-hooks/pre_bash_guard.py
src/ncdev/ai_session.py
src/ncdev/v3/claude_executor.py
src/ncdev/v3/engine.py
src/ncdev/v3/models.py
tests/test_ncdev_v3/test_dependency_gating.py
tests/unit/test_ai_session.py
tests/unit/test_claude_executor.py
tests/unit/test_hooks.py

codex
I’ve got the change surface. Next I’m checking the exact code paths you called out in `4a5a0f7`, then I’ll reconcile them against what round 2 said was still broken.
exec
/bin/zsh -lc 'rg -n "''^## " docs/codex-review/review-response-round2.md && sed -n '"'6760,6860p' docs/codex-review/review-response-round2.md" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
35:## What I changed (commit `f19934b`)
128:## Numbers
135:## Files to look at this round
160:## Specific questions
194:## Output shape
200:## Architecture verdict
203:## Fixes verified (the good)
206:## Fixes that didn't land
209:## New issues introduced
212:## Previously concerning, still concerning
215:## Now truly over-engineered
218:## Honest one-liner
285:## Context — what this repo is
303:## What I just migrated it to
353:## Mode switch (the user's budget lever)
366:## Hooks
382:## The four migration commits
402:## Files to read (in roughly this order)
452:## Specific questions I want answered
564:## Architecture verdict
567:## Strengths
574:## Critical issues
584:## Concerning but not critical
591:## Over-engineered / could be deleted
597:## Missing
603:## Test coverage gaps
610:## Honest one-liner
614:## Architecture verdict
617:## Strengths
624:## Critical issues
634:## Concerning but not critical
641:## Over-engineered / could be deleted
647:## Missing
653:## Test coverage gaps
660:## Honest one-liner
1213:## Context
1225:## Your feature spec
1242:## Required workflow
1269:## What success looks like
1278:## What failure looks like (avoid)
1907:## Project
1913:## Required workflow
1943:## Rules
1960:## Your job
1976:## Rules
2694:## Input
2700:## Required deliverables
2757:## Output format
5256:## What the user wants
5260:## Your workflow
5280:## What success looks like
7061:## Architecture verdict
7064:## Fixes verified (the good)
7073:## Fixes that didn't land
7078:## New issues introduced
7083:## Previously concerning, still concerning
7089:## Now truly over-engineered
7093:## Honest one-liner
7099:## Architecture verdict
7102:## Fixes verified (the good)
7111:## Fixes that didn't land
7116:## New issues introduced
7121:## Previously concerning, still concerning
7127:## Now truly over-engineered
7131:## Honest one-liner
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

exec
/bin/zsh -lc 'git diff f19934b..4a5a0f7 -- src/ncdev/v3/claude_executor.py src/ncdev/v3/engine.py src/ncdev/v3/models.py src/ncdev/ai_session.py scripts/ncdev-hooks/pre_bash_guard.py tests/test_ncdev_v3/test_dependency_gating.py tests/unit/test_ai_session.py tests/unit/test_claude_executor.py tests/unit/test_hooks.py' in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
diff --git a/scripts/ncdev-hooks/pre_bash_guard.py b/scripts/ncdev-hooks/pre_bash_guard.py
index cda4962..5017ce0 100755
--- a/scripts/ncdev-hooks/pre_bash_guard.py
+++ b/scripts/ncdev-hooks/pre_bash_guard.py
@@ -80,11 +80,22 @@ def _staged_file_list(cwd: str | None) -> list[str]:
 def _check_staged_for_prohibited(
     cwd: str | None, patterns: Iterable[str],
 ) -> list[str]:
-    """Return a list of '<file>:<pattern>' violations found in staged diff."""
+    """Return a list of '<file>:<pattern>' violations found in staged diff.
+
+    Each pattern is tried as a compiled regex first (via ``re.search``);
+    if that fails to compile, we fall back to literal substring match.
+    This matches the semantics of claude_executor._grep_for_prohibited
+    — identical rules on both sides of the commit boundary.
+    """
+    compiled: list[tuple[str, re.Pattern[str] | None]] = []
+    for pat in patterns:
+        try:
+            compiled.append((pat, re.compile(pat)))
+        except re.error:
+            compiled.append((pat, None))
+
     hits: list[str] = []
     for path in _staged_file_list(cwd):
-        # Diff the staged content only — we want to catch what's about
-        # to land, not what's already in HEAD.
         r = subprocess.run(
             ["git", "diff", "--cached", "--", path],
             cwd=cwd, capture_output=True, text=True, timeout=5,
@@ -97,8 +108,9 @@ def _check_staged_for_prohibited(
             if line.startswith("+") and not line.startswith("+++")
         ]
         blob = "\n".join(added)
-        for pat in patterns:
-            if pat in blob:
+        for pat, regex in compiled:
+            hit = regex.search(blob) if regex is not None else (pat in blob)
+            if hit:
                 hits.append(f"{path}:{pat}")
                 if len(hits) > 20:
                     return hits
diff --git a/src/ncdev/ai_session.py b/src/ncdev/ai_session.py
index 0695dbc..dbd9ab6 100644
--- a/src/ncdev/ai_session.py
+++ b/src/ncdev/ai_session.py
@@ -22,12 +22,23 @@ populated only when they applied.
 from __future__ import annotations
 
 import logging
+import os
 import shutil
+import signal
 import subprocess
+import sys
+import threading
 import time
 from pathlib import Path
 from typing import Callable, Iterable
 
+_IS_POSIX = sys.platform != "win32"
+
+# Upper bound per stream for run_codex_session capture. A chatty codex
+# run can produce a lot — we keep the tail (recent output is more
+# useful than the head) and note truncation.
+_CODEX_CAPTURE_MAX_BYTES = 4 * 1024 * 1024   # 4 MB per stream
+
 from ncdev.claude_session import (
     DEFAULT_BUILD_TOOLS,
     ClaudeSessionResult,
@@ -41,12 +52,13 @@ logger = logging.getLogger(__name__)
 
 
 # Mode → which provider runs the main orchestrator session.
+# "custom" is intentionally absent — it's handled by consulting the
+# user's hand-tuned routing via provider_dispatch instead.
 MODE_ORCHESTRATOR: dict[str, str] = {
     "claude_plan_codex_build": "claude",
     "claude_only": "claude",
     "codex_only": "codex",
     "openrouter": "openrouter",
-    "custom": "claude",   # safe default — custom may still want Claude orchestration
 }
 
 # Mode → who actually writes code. Used by the Claude runner to decide
@@ -57,10 +69,30 @@ MODE_IMPLEMENTER: dict[str, str] = {
     "claude_only": "claude",
     "codex_only": "codex",
     "openrouter": "openrouter",
-    "custom": "codex",
 }
 
 
+def _resolve_custom_providers(cfg: NCDevV2Config) -> tuple[str, str]:
+    """For ``mode=custom``, read orchestrator + implementer from routing.
+
+    Honours the contract stated in v2/config.py: ``custom`` preserves
+    the user's hand-tuned ``routing:`` block. We use routing.review to
+    pick the orchestrator (review is the "who reasons about code" task)
+    and routing.implementation to pick the implementer.
+
+    Both are mapped through :func:`provider_dispatch.resolve_provider_name`
+    so long names like ``anthropic_claude_code`` become short
+    registry keys (``claude``, ``codex``, ``openrouter``).
+    """
+    from ncdev.provider_dispatch import resolve_provider_name
+
+    review_chain = cfg.routing.review or ["anthropic_claude_code"]
+    impl_chain = cfg.routing.implementation or ["openai_codex"]
+    orch = resolve_provider_name(review_chain[0])
+    impl = resolve_provider_name(impl_chain[0])
+    return orch, impl
+
+
 def _resolve_config(
     config: NCDevV2Config | None,
     workspace: Path | None,
@@ -101,8 +133,14 @@ def run_ai_session(
     implementer is Claude. Explicit values win.
     """
     cfg = _resolve_config(config, workspace)
-    orch = MODE_ORCHESTRATOR.get(cfg.mode, "claude")
-    impl = MODE_IMPLEMENTER.get(cfg.mode, "codex")
+
+    if cfg.mode == "custom":
+        # Honour the hand-tuned routing block — this is exactly what
+        # "custom" means per the config contract.
+        orch, impl = _resolve_custom_providers(cfg)
+    else:
+        orch = MODE_ORCHESTRATOR.get(cfg.mode, "claude")
+        impl = MODE_IMPLEMENTER.get(cfg.mode, "codex")
 
     logger.info("run_ai_session mode=%s orch=%s impl=%s cwd=%s", cfg.mode, orch, impl, cwd)
 
@@ -160,13 +198,16 @@ def run_codex_session(
     model: str | None = None,
     log_path: Path | None = None,
     extra_args: list[str] | None = None,
+    max_bytes_per_stream: int = _CODEX_CAPTURE_MAX_BYTES,
 ) -> ClaudeSessionResult:
     """Run a Codex session. No skills, no subagents, no NC Dev hooks.
 
-    Codex handles planning + implementation + testing + committing in
-    one shot per invocation. This is the "lean mode" — you lose skill
-    machinery and cross-feature reasoning quality in exchange for speed
-    and lower cost.
+    Uses the same safety primitives as :func:`run_claude_session`:
+    thread-per-pipe readers so backpressure can't deadlock the child,
+    watchdog that kills the process group on wall-clock timeout, and
+    a tail-bounded byte buffer per stream so a chatty Codex run
+    doesn't blow RAM. Returns the same :class:`ClaudeSessionResult`
+    shape (common result type across runners).
     """
     if shutil.which("codex") is None:
         return ClaudeSessionResult(
@@ -194,48 +235,168 @@ def run_codex_session(
         cmd += list(extra_args)
     cmd.append(codex_prompt)
 
+    popen_kwargs: dict = dict(
+        cwd=str(cwd),
+        stdout=subprocess.PIPE,
+        stderr=subprocess.PIPE,
+        text=True,
+        bufsize=1,
+    )
+    if _IS_POSIX:
+        popen_kwargs["start_new_session"] = True
+
     start = time.time()
     try:
-        proc = subprocess.run(
-            cmd,
-            cwd=str(cwd),
-            capture_output=True,
-            text=True,
-            timeout=timeout,
-        )
-    except subprocess.TimeoutExpired as exc:
-        duration = time.time() - start
-        stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
-        return ClaudeSessionResult(
-            success=False,
-            final_text=(exc.stdout or "") if isinstance(exc.stdout, str) else "",
-            exit_code=-1,
-            duration_seconds=duration,
-            stderr=stderr,
-            error=f"codex session timed out after {timeout}s",
-        )
-    except FileNotFoundError:
+        proc = subprocess.Popen(cmd, **popen_kwargs)
+    except (FileNotFoundError, OSError) as exc:
         return ClaudeSessionResult(
             success=False, final_text="", exit_code=-1,
-            error="codex CLI disappeared mid-invocation",
+            error=f"failed to spawn codex: {exc}",
         )
 
+    stdout_buf = _TailBuffer(max_bytes_per_stream)
+    stderr_buf = _TailBuffer(max_bytes_per_stream)
+
+    def _drain(stream, buf: "_TailBuffer") -> None:
+        try:
+            for line in stream:
+                buf.append(line)
+        except Exception:  # noqa: BLE001
+            pass
+
+    stdout_thread = threading.Thread(
+        target=_drain, args=(proc.stdout, stdout_buf), daemon=True,
+    )
+    stderr_thread = threading.Thread(
+        target=_drain, args=(proc.stderr, stderr_buf), daemon=True,
+    )
+    stdout_thread.start()
+    stderr_thread.start()
+
+    timeout_fired = threading.Event()
+
+    def _watchdog() -> None:
+        if timeout <= 0:
+            return
+        if proc.poll() is None:
+            time.sleep(timeout)
+        if proc.poll() is None:
+            timeout_fired.set()
+            _kill_process_tree(proc)
+
+    threading.Thread(target=_watchdog, daemon=True).start()
+
+    try:
+        proc.wait(timeout=timeout + 30)
+    except subprocess.TimeoutExpired:
+        _kill_process_tree(proc)
+        try:
+            proc.wait(timeout=5)
+        except subprocess.TimeoutExpired:
+            pass
+
+    # Drain final bytes
+    stdout_thread.join(timeout=2.0)
+    stderr_thread.join(timeout=2.0)
+
     duration = time.time() - start
-    final_text = proc.stdout or ""
+    final_text = stdout_buf.text()
+    stderr_text = stderr_buf.text()
+    exit_code = proc.returncode if proc.returncode is not None else -1
 
     if log_path is not None:
         log_path.parent.mkdir(parents=True, exist_ok=True)
+        truncation_note = ""
+        if stdout_buf.truncated or stderr_buf.truncated:
+            truncation_note = (
+                f"\n(NOTE: output tail-truncated to {max_bytes_per_stream} "
+                "bytes per stream)\n"
+            )
         log_path.write_text(
-            f"RUNNER: codex\nEXIT: {proc.returncode}\nDURATION: {duration:.1f}s\n\n"
-            f"STDOUT:\n{final_text}\n\nSTDERR:\n{proc.stderr or ''}\n",
+            f"RUNNER: codex\nEXIT: {exit_code}\nDURATION: {duration:.1f}s"
+            f"{truncation_note}\n\n"
+            f"STDOUT:\n{final_text}\n\nSTDERR:\n{stderr_text}\n",
             encoding="utf-8",
         )
 
+    if timeout_fired.is_set():
+        return ClaudeSessionResult(
+            success=False,
+            final_text=final_text,
+            exit_code=exit_code,
+            duration_seconds=duration,
+            stderr=stderr_text,
+            error=f"codex session timed out after {timeout}s",
+        )
+
     return ClaudeSessionResult(
-        success=proc.returncode == 0,
+        success=exit_code == 0,
         final_text=final_text,
-        exit_code=proc.returncode,
+        exit_code=exit_code,
         duration_seconds=duration,
-        stderr=proc.stderr or "",
-        error=None if proc.returncode == 0 else f"codex exited with code {proc.returncode}",
+        stderr=stderr_text,
+        error=None if exit_code == 0 else f"codex exited with code {exit_code}",
     )
+
+
+# ---------------------------------------------------------------------------
+# Helpers (shared)
+# ---------------------------------------------------------------------------
+
+
+class _TailBuffer:
+    """Accumulate text but keep only the tail of ``max_bytes``.
+
+    Recent output is more useful than the head when debugging a builder
+    that went off the rails. ``truncated`` flips True once we start
+    dropping bytes so callers can surface that to users / logs.
+    """
+
+    __slots__ = ("_chunks", "_size", "_max", "truncated")
+
+    def __init__(self, max_bytes: int) -> None:
+        self._chunks: list[str] = []
+        self._size = 0
+        self._max = max_bytes
+        self.truncated = False
+
+    def append(self, chunk: str) -> None:
+        if not chunk:
+            return
+        enc = len(chunk.encode("utf-8", errors="ignore"))
+        self._chunks.append(chunk)
+        self._size += enc
+        while self._size > self._max and self._chunks:
+            head = self._chunks.pop(0)
+            self._size -= len(head.encode("utf-8", errors="ignore"))
+            self.truncated = True
+
+    def text(self) -> str:
+        return "".join(self._chunks)
+
+
+def _kill_process_tree(proc: subprocess.Popen) -> None:
+    """Kill a process and its children. Mirror of claude_session's helper."""
+    if proc.poll() is not None:
+        return
+    try:
+        if _IS_POSIX:
+            try:
+                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
+            except (ProcessLookupError, PermissionError):
+                proc.terminate()
+            try:
+                proc.wait(timeout=3)
+            except subprocess.TimeoutExpired:
+                try:
+                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
+                except (ProcessLookupError, PermissionError):
+                    proc.kill()
+        else:
+            proc.terminate()
+            try:
+                proc.wait(timeout=3)
+            except subprocess.TimeoutExpired:
+                proc.kill()
+    except Exception:  # noqa: BLE001
+        pass
diff --git a/src/ncdev/v3/claude_executor.py b/src/ncdev/v3/claude_executor.py
index 2ac4b74..cfd3019 100644
--- a/src/ncdev/v3/claude_executor.py
+++ b/src/ncdev/v3/claude_executor.py
@@ -27,11 +27,14 @@ Claude shells out to Codex via Bash for implementation and test writing
 from __future__ import annotations
 
 import json
+import logging
 import re
 import subprocess
 import time
 from pathlib import Path
 
+logger = logging.getLogger(__name__)
+
 from ncdev.ai_session import run_ai_session
 from ncdev.claude_session import (
     DEFAULT_BUILD_TOOLS,
@@ -247,6 +250,7 @@ def execute_feature_claude_driven(
     )
 
     # Decide status
+    recoverability_note = ""
     if session.success and made_commit and not dirty and verification.overall_passed:
         status = StepStatus.PASSED
     elif made_commit and verification.overall_passed:
@@ -255,10 +259,18 @@ def execute_feature_claude_driven(
         status = StepStatus.PASSED
     else:
         # Something is wrong. Commit whatever is there with [BROKEN] tag
-        # so the next feature has context to build on.
+        # so the next feature has context to build on. If that commit
+        # itself fails (repo hook blocks it, git identity missing, etc.)
+        # we surface it explicitly — recoverability is a guarantee we
+        # promise in the docs, silent failure is not acceptable.
         if dirty:
-            _commit_broken(target_path, feature)
-            post_commit = _git_head(target_path)
+            if _commit_broken(target_path, feature):
+                post_commit = _git_head(target_path)
+            else:
+                recoverability_note = (
+                    " | recoverability: [BROKEN] commit failed — dirty "
+                    "working tree remains; see log for git error"
+                )
         status = StepStatus.FAILED
 
     # Reuse the diff — or recompute if a [BROKEN] commit was made above
@@ -277,7 +289,7 @@ def execute_feature_claude_driven(
         files_created=files_created,
         files_modified=files_modified,
         commit_sha=post_commit or "",
-        error_message=session.error or "",
+        error_message=(session.error or "") + recoverability_note,
         builder_output=(session.final_text or "")[:2000],
     )
     # Persist the session cost + skills in metadata for metrics
@@ -386,19 +398,23 @@ def _post_session_verification(
             if not ok:
                 reasons.append(f"frontend tests failed: {_last_line(out)}")
 
-    # 7. Best-effort health probe — Claude may have left the app running;
-    #    if so, we probe it. If it's down, treat as a soft signal, not
-    #    a hard failure (feature may have been built to spec without
-    #    leaving the app booted).
+    # 7. Health probe — if the contract declares a backend_health_url,
+    #    the feature is only "done" when that URL responds. Leaving
+    #    backend_health_url empty in the contract disables the probe
+    #    (common for CLI/library projects). Codex R2 flagged: if the
+    #    user put the URL there, they meant it.
     if probe_health and bundle.verification.backend_health_url:
         reachable = _probe_health(
             bundle.verification.backend_health_url,
             timeout=bundle.verification.boot_timeout_seconds,
         )
         ver.app_boots = reachable
-        # Not added to reasons — soft signal only. Explicit boot
-        # enforcement requires the orchestrator to start the app itself,
-        # which is out of scope for post-hoc verification.
+        if not reachable:
+            reasons.append(
+                f"backend health URL unreachable: "
+                f"{bundle.verification.backend_health_url} — the feature "
+                "must leave the app in a runnable state"
+            )
 
     ver.failure_reasons = reasons
     ver.overall_passed = not reasons
@@ -593,7 +609,7 @@ def _commit_broken(target_path: Path, feature: FeatureStep) -> bool:
             cwd=str(target_path), capture_output=True, text=True, timeout=10,
         )
         if add.returncode != 0:
-            console.print(f"  [red]BROKEN-commit: git add failed[/red]: {add.stderr[:200]}")
+            logger.warning("BROKEN-commit: git add failed: %s", add.stderr[:200])
             return False
         commit = subprocess.run(
             ["git", "commit", "-m",
@@ -603,12 +619,13 @@ def _commit_broken(target_path: Path, feature: FeatureStep) -> bool:
             cwd=str(target_path), capture_output=True, text=True, timeout=10,
         )
         if commit.returncode != 0:
-            console.print(
-                f"  [red]BROKEN-commit: git commit failed[/red] "
-                f"(rc={commit.returncode}): {(commit.stderr or commit.stdout)[:300]}"
+            logger.warning(
+                "BROKEN-commit: git commit failed (rc=%d): %s",
+                commit.returncode,
+                (commit.stderr or commit.stdout)[:300],
             )
             return False
         return True
     except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
-        console.print(f"  [red]BROKEN-commit: {exc}[/red]")
+        logger.warning("BROKEN-commit: %s", exc)
         return False
diff --git a/src/ncdev/v3/engine.py b/src/ncdev/v3/engine.py
index 58b0ffb..61ba796 100644
--- a/src/ncdev/v3/engine.py
+++ b/src/ncdev/v3/engine.py
@@ -223,12 +223,12 @@ def run_v3_full(
                     "(required feature(s) are not in PASSED state)"
                 )
                 console.print(Panel(
-                    f"[yellow]SKIP[/yellow] {feature.feature_id} — {reason}",
-                    border_style="yellow",
+                    f"[red]BLOCKED[/red] {feature.feature_id} — {reason}",
+                    border_style="red",
                 ))
                 completed.append(StepResult(
                     feature_id=feature.feature_id,
-                    status=StepStatus.SKIPPED,
+                    status=StepStatus.BLOCKED,
                     error_message=reason,
                 ))
                 state.completed_steps = completed
@@ -266,8 +266,14 @@ def run_v3_full(
     # ── Phase 6: Summary ─────────────────────────────────────────────────
     state.phase = "complete"
     passed = [r for r in completed if r.status == StepStatus.PASSED]
-    failed = [r for r in completed if r.status == StepStatus.FAILED]
-    state.status = "passed" if not failed else ("partial" if passed else "failed")
+    # Both FAILED (tried and broke) and BLOCKED (couldn't try because a dep
+    # broke) count as run-level failures. Without this, a --strict-deps halt
+    # would report "passed" despite halting because of broken deps.
+    unsuccessful = [
+        r for r in completed
+        if r.status in (StepStatus.FAILED, StepStatus.BLOCKED)
+    ]
+    state.status = "passed" if not unsuccessful else ("partial" if passed else "failed")
 
     _print_summary_table(completed)
 
@@ -281,12 +287,19 @@ def run_v3_full(
 
 
 def _unmet_dependencies(feature, completed: list[StepResult]) -> list[str]:
-    """Return the ids in ``feature.depends_on_features`` that are not PASSED.
-
-    A feature id is "satisfied" when it appears in ``completed`` with
-    status PASSED or SKIPPED (state scanner can mark a brownfield
-    feature as already-implemented → SKIPPED, which counts as met).
-    Missing ids (not in the completed list at all) are unmet.
+    """Return the ids in ``feature.depends_on_features`` that are not met.
+
+    A dep is "met" when it appears in ``completed`` with status:
+      * PASSED  — built successfully this run
+      * SKIPPED — brownfield state-scanner determined it was already
+                  implemented in the target repo before this run started
+    A dep is "unmet" when it:
+      * is missing from the completed list (never attempted), OR
+      * has status FAILED (we tried and it broke), OR
+      * has status BLOCKED (its own dep was unmet — cascading failure).
+
+    The BLOCKED distinction stops feature-N-blocked from being treated
+    as "already done" and letting feature N+1 sail through.
     """
     acceptable = {
         r.feature_id for r in completed
@@ -327,6 +340,7 @@ def _print_summary_table(completed: list[StepResult]) -> None:
         colour = {
             StepStatus.PASSED: "green",
             StepStatus.FAILED: "red",
+            StepStatus.BLOCKED: "red",
             StepStatus.SKIPPED: "yellow",
         }.get(r.status, "white")
         table.add_row(
diff --git a/src/ncdev/v3/models.py b/src/ncdev/v3/models.py
index 12425df..fbd6217 100644
--- a/src/ncdev/v3/models.py
+++ b/src/ncdev/v3/models.py
@@ -46,7 +46,8 @@ class StepStatus(str, Enum):
     REPAIRING = "repairing"
     PASSED = "passed"
     FAILED = "failed"
-    SKIPPED = "skipped"
+    SKIPPED = "skipped"   # brownfield state-scanner: feature already implemented
+    BLOCKED = "blocked"   # dependency failed / blocked — we did NOT try
 
 
 class TestResult(BaseModel):
diff --git a/tests/test_ncdev_v3/test_dependency_gating.py b/tests/test_ncdev_v3/test_dependency_gating.py
index e038a82..3d6d98c 100644
--- a/tests/test_ncdev_v3/test_dependency_gating.py
+++ b/tests/test_ncdev_v3/test_dependency_gating.py
@@ -39,14 +39,26 @@ def test_dependency_failed_is_unmet():
     assert _unmet_dependencies(f, completed=completed) == ["f01"]
 
 
-def test_dependency_skipped_counts_as_satisfied():
+def test_brownfield_skipped_dep_counts_as_satisfied():
     """Brownfield state scanner marks already-implemented features as
-    SKIPPED — those should still count as satisfying a dep."""
+    SKIPPED — those count as satisfying a dep (they're really done)."""
     f = _feat("f02", deps=["f01"])
     completed = [StepResult(feature_id="f01", status=StepStatus.SKIPPED)]
     assert _unmet_dependencies(f, completed=completed) == []
 
 
+def test_blocked_dep_does_NOT_count_as_satisfied():
+    """Codex R2 flagged: a dependency that was BLOCKED (its own dep
+    failed) must not count as met. Otherwise cascading failures break
+    through the gate."""
+    f = _feat("f03", deps=["f02"])
+    completed = [
+        StepResult(feature_id="f01", status=StepStatus.FAILED),
+        StepResult(feature_id="f02", status=StepStatus.BLOCKED),
+    ]
+    assert _unmet_dependencies(f, completed=completed) == ["f02"]
+
+
 def test_multiple_deps_partial_satisfaction():
     f = _feat("f03", deps=["f01", "f02"])
     completed = [
diff --git a/tests/unit/test_ai_session.py b/tests/unit/test_ai_session.py
index 3acfaaf..983a199 100644
--- a/tests/unit/test_ai_session.py
+++ b/tests/unit/test_ai_session.py
@@ -2,6 +2,7 @@
 
 from __future__ import annotations
 
+import time
 from pathlib import Path
 from unittest.mock import patch
 
@@ -23,10 +24,12 @@ from ncdev.v2.config import NCDevV2Config
 # ---------------------------------------------------------------------------
 
 
-def test_mode_tables_cover_every_preset():
-    """If we add a new mode preset, these maps must have entries for it."""
+def test_mode_tables_cover_every_preset_except_custom():
+    """Every non-custom preset must have an orchestrator/implementer
+    entry. 'custom' is deliberately absent — it's resolved from the
+    user's hand-tuned routing via _resolve_custom_providers."""
     from ncdev.v2.config import MODE_PRESETS
-    expected = set(MODE_PRESETS.keys())
+    expected = set(MODE_PRESETS.keys()) - {"custom"}
     assert set(MODE_ORCHESTRATOR.keys()) == expected
     assert set(MODE_IMPLEMENTER.keys()) == expected
 
@@ -136,8 +139,18 @@ def test_openrouter_raises_not_implemented(tmp_path: Path):
         run_ai_session("x", cwd=tmp_path, config=cfg)
 
 
-def test_custom_mode_defaults_to_claude(tmp_path: Path):
-    cfg = NCDevV2Config(mode="custom")
+def test_custom_mode_honours_hand_tuned_routing_claude_everywhere(tmp_path: Path):
+    """Codex R2 flagged: custom was hardcoded to claude+codex, ignoring
+    the user's routing: block. Verify: user routes everything to
+    anthropic_claude_code → Claude orchestrator, Claude implementer,
+    protocol OFF (Claude isn't delegating)."""
+    cfg = NCDevV2Config(
+        mode="custom",
+        routing={
+            "review": ["anthropic_claude_code"],
+            "implementation": ["anthropic_claude_code"],
+        },
+    )
     captured: dict = {}
 
     def fake_claude(prompt, **kwargs):
@@ -146,7 +159,59 @@ def test_custom_mode_defaults_to_claude(tmp_path: Path):
 
     with patch("ncdev.ai_session.run_claude_session", side_effect=fake_claude):
         run_ai_session("x", cwd=tmp_path, config=cfg)
-    # custom → claude orchestrator, codex implementer → protocol on
+
+    # orchestrator=claude, implementer=claude → NO codex protocol
+    assert captured["include_codex_protocol"] is False
+
+
+def test_custom_mode_routes_to_codex_when_user_requests_it(tmp_path: Path):
+    """User flips everything to codex via custom — must actually route
+    to codex runner, not fall back to Claude."""
+    cfg = NCDevV2Config(
+        mode="custom",
+        routing={
+            "review": ["openai_codex"],
+            "implementation": ["openai_codex"],
+        },
+    )
+    called = {"claude": False, "codex": False}
+
+    def fake_claude(*a, **k):  # noqa: ARG001
+        called["claude"] = True
+        return _claude_result()
+
+    def fake_codex(*a, **k):  # noqa: ARG001
+        called["codex"] = True
+        return _codex_result()
+
+    with patch("ncdev.ai_session.run_claude_session", side_effect=fake_claude):
+        with patch("ncdev.ai_session.run_codex_session", side_effect=fake_codex):
+            run_ai_session("x", cwd=tmp_path, config=cfg)
+
+    assert called["codex"] is True, "custom mode must route to codex when user routes review+impl to codex"
+    assert called["claude"] is False
+
+
+def test_custom_mode_plan_codex_build_like_routing(tmp_path: Path):
+    """User configures custom to mimic claude_plan_codex_build: review=
+    claude, implementation=codex → Claude orch WITH codex protocol."""
+    cfg = NCDevV2Config(
+        mode="custom",
+        routing={
+            "review": ["anthropic_claude_code"],
+            "implementation": ["openai_codex"],
+        },
+    )
+    captured: dict = {}
+
+    def fake_claude(prompt, **kwargs):
+        captured.update(kwargs)
+        return _claude_result()
+
+    with patch("ncdev.ai_session.run_claude_session", side_effect=fake_claude):
+        run_ai_session("x", cwd=tmp_path, config=cfg)
+
+    # Claude orchestrates, Codex implements → protocol ON
     assert captured["include_codex_protocol"] is True
 
 
@@ -178,21 +243,41 @@ def test_run_codex_session_errors_when_cli_missing(tmp_path: Path):
     assert "codex CLI not found" in (result.error or "")
 
 
+class _FakeCodexProc:
+    """Minimal Popen stand-in: stdout + stderr iterable, immediate exit."""
+
+    _next_pid = 9000
+
+    def __init__(self, stdout: str = "codex output\n", stderr: str = "", returncode: int = 0):
+        _FakeCodexProc._next_pid += 1
+        self.pid = _FakeCodexProc._next_pid
+        self.stdout = iter([stdout] if stdout else [])
+        self.stderr = iter([stderr] if stderr else [])
+        self.returncode = returncode
+
+    def poll(self):
+        return self.returncode
+
+    def wait(self, timeout=None):  # noqa: ARG002
+        return self.returncode
+
+    def kill(self):
+        pass
+
+    def terminate(self):
+        pass
+
+
 def test_run_codex_session_builds_correct_argv(tmp_path: Path):
     captured: dict = {}
 
-    class FakeProc:
-        returncode = 0
-        stdout = "codex output"
-        stderr = ""
-
-    def fake_run(cmd, **kwargs):
+    def fake_popen(cmd, **kwargs):
         captured["cmd"] = cmd
         captured["kwargs"] = kwargs
-        return FakeProc()
+        return _FakeCodexProc(stdout="codex output\n")
 
     with patch("ncdev.ai_session.shutil.which", return_value="/usr/bin/codex"):
-        with patch("ncdev.ai_session.subprocess.run", side_effect=fake_run):
+        with patch("ncdev.ai_session.subprocess.Popen", side_effect=fake_popen):
             result = run_codex_session("build feature X", cwd=tmp_path)
 
     cmd = captured["cmd"]
@@ -205,34 +290,73 @@ def test_run_codex_session_builds_correct_argv(tmp_path: Path):
     assert "build feature X" in cmd[-1]
     assert "codex_only mode" in cmd[-1]
     assert result.success is True
-
-
-def test_run_codex_session_honours_timeout(tmp_path: Path):
-    import subprocess as sp
-
-    def fake_run(cmd, **kwargs):
-        raise sp.TimeoutExpired(cmd=cmd, timeout=kwargs.get("timeout", 0))
-
-    with patch("ncdev.ai_session.shutil.which", return_value="/usr/bin/codex"):
-        with patch("ncdev.ai_session.subprocess.run", side_effect=fake_run):
-            result = run_codex_session("x", cwd=tmp_path, timeout=5)
-    assert result.success is False
-    assert "timed out" in (result.error or "")
+    assert "codex output" in result.final_text
 
 
 def test_run_codex_session_writes_log(tmp_path: Path):
-    class FakeProc:
-        returncode = 0
-        stdout = "the work"
-        stderr = ""
+    def fake_popen(cmd, **kwargs):  # noqa: ARG001
+        return _FakeCodexProc(stdout="the work\n", stderr="")
 
     log_path = tmp_path / "logs" / "codex.log"
 
     with patch("ncdev.ai_session.shutil.which", return_value="/usr/bin/codex"):
-        with patch("ncdev.ai_session.subprocess.run", return_value=FakeProc()):
+        with patch("ncdev.ai_session.subprocess.Popen", side_effect=fake_popen):
             run_codex_session("x", cwd=tmp_path, log_path=log_path)
 
     assert log_path.exists()
     body = log_path.read_text(encoding="utf-8")
     assert "RUNNER: codex" in body
     assert "the work" in body
+
+
+def test_run_codex_session_truncates_huge_stream(tmp_path: Path):
+    """Codex R2 flagged: unbounded capture_output can blow RAM.
+    Verify the tail-buffer caps memory for chatty runs."""
+    huge = "x" * 1024   # 1KB per line
+    lines = [huge + "\n"] * 200  # 200 KB total
+
+    class HugeProc(_FakeCodexProc):
+        def __init__(self):
+            super().__init__(stdout="", returncode=0)
+            self.stdout = iter(lines)
+
+    with patch("ncdev.ai_session.shutil.which", return_value="/usr/bin/codex"):
+        with patch("ncdev.ai_session.subprocess.Popen", side_effect=lambda *a, **k: HugeProc()):
+            # Cap at 50 KB — result must be capped, no crash
+            result = run_codex_session(
+                "x", cwd=tmp_path, max_bytes_per_stream=50_000,
+            )
+
+    assert result.success is True
+    assert len(result.final_text.encode("utf-8")) <= 60_000  # some tolerance
+
+
+def test_run_codex_session_watchdog_kills_hung_child(tmp_path: Path):
+    """Integration: actual hung child must be killed by the watchdog,
+    same guarantee as run_claude_session."""
+    import sys as _sys
+
+    fake_cli = tmp_path / "fake-codex"
+    fake_cli.write_text(
+        "#!/usr/bin/env python3\nimport time\n"
+        "while True:\n    time.sleep(1)\n",
+        encoding="utf-8",
+    )
+    fake_cli.chmod(0o755)
+
+    import subprocess as _sp
+    orig_popen = _sp.Popen
+
+    def fake_popen(cmd, **kwargs):
+        new_cmd = [_sys.executable, str(fake_cli)] + list(cmd[1:])
+        return orig_popen(new_cmd, **kwargs)
+
+    start = time.time()
+    with patch("ncdev.ai_session.shutil.which", return_value=str(fake_cli)):
+        with patch("ncdev.ai_session.subprocess.Popen", side_effect=fake_popen):
+            result = run_codex_session("x", cwd=tmp_path, timeout=2)
+    elapsed = time.time() - start
+
+    assert elapsed < 15, f"codex watchdog failed: {elapsed:.1f}s"
+    assert result.success is False
+    assert "timed out" in (result.error or "")
diff --git a/tests/unit/test_claude_executor.py b/tests/unit/test_claude_executor.py
index e8eca5f..62dc259 100644
--- a/tests/unit/test_claude_executor.py
+++ b/tests/unit/test_claude_executor.py
@@ -326,6 +326,72 @@ def test_verification_runs_backend_test_command_when_configured(tmp_path: Path):
     assert any("backend tests failed" in r for r in reasons)
 
 
+def test_health_probe_failure_blocks_pass_when_url_set(tmp_path: Path):
+    """Codex R2: boot probe was soft-signal only. When the contract
+    declares backend_health_url, we must enforce it — the user put
+    the URL there intentionally."""
+    target = tmp_path / "app"
+    target.mkdir()
+    _init_git(target)
+
+    def fake_session(prompt, **kwargs):  # noqa: ARG001
+        _seed_manifest(target, "f01-scaffold")
+        (target / "a.py").write_text("x=1")
+        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
+        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): a"],
+                       cwd=str(target), check=True)
+        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)
+
+    bundle = _make_bundle()
+    # Set a URL that definitely doesn't respond
+    bundle.verification.backend_health_url = "http://127.0.0.1:1/health"
+    bundle.verification.boot_timeout_seconds = 1
+
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
+    assert result.status == StepStatus.FAILED
+    reasons = result.verification.failure_reasons
+    assert any("health URL unreachable" in r for r in reasons)
+
+
+def test_health_probe_not_run_when_url_empty(tmp_path: Path):
+    """Empty URL means contract says 'no web boot check' — skip probe."""
+    target = tmp_path / "app"
+    target.mkdir()
+    _init_git(target)
+
+    def fake_session(prompt, **kwargs):  # noqa: ARG001
+        _seed_manifest(target, "f01-scaffold")
+        (target / "a.py").write_text("x=1")
+        subprocess.run(["git", "add", "-A"], cwd=str(target), check=True)
+        subprocess.run(["git", "commit", "-q", "-m", "feat(f01): a"],
+                       cwd=str(target), check=True)
+        return ClaudeSessionResult(success=True, final_text="done", exit_code=0)
+
+    bundle = _make_bundle()  # backend_health_url="" by default in _make_bundle
+    assert bundle.verification.backend_health_url == ""
+
+    with patch("ncdev.v3.claude_executor.run_ai_session", side_effect=fake_session):
+        result = execute_feature_claude_driven(
+            feature=_make_feature(),
+            target_path=target,
+            run_dir=tmp_path / "run",
+            charter_bundle=bundle,
+            prior_results=[],
+            project_id="myapp",
+        )
+    # No health-URL failure — probe was skipped
+    assert result.status == StepStatus.PASSED
+
+
 def test_verification_enforces_minimum_test_count(tmp_path: Path):
     target = tmp_path / "app"
     target.mkdir()
diff --git a/tests/unit/test_hooks.py b/tests/unit/test_hooks.py
index 14c3659..f2c169f 100644
--- a/tests/unit/test_hooks.py
+++ b/tests/unit/test_hooks.py
@@ -154,6 +154,24 @@ def test_staged_content_with_todo_is_blocked(tmp_path: Path):
     assert "src/app.py" in reason
 
 
+def test_regex_prohibited_pattern_matches_at_hook_level(tmp_path: Path, monkeypatch):
+    """Codex R2: hook used substring only; regex entries from the
+    verification contract never fired at commit time. Parity check."""
+    config = tmp_path / "hooks.json"
+    config.write_text('{"prohibited_patterns": ["except:\\\\s*pass"]}')
+    monkeypatch.setenv("NCDEV_HOOKS_CONFIG", str(config))
+
+    _init_git_with_staged(tmp_path, {
+        "bad.py": "try:\n    x = 1\nexcept:    pass\n",
+    })
+    decision, reason = pre_bash_guard.evaluate(
+        "Bash", {"command": 'git commit -m "feat: add thing"'},
+        cwd=str(tmp_path),
+    )
+    assert decision == "block"
+    assert "except:" in reason or "pass" in reason
+
+
 def test_staged_content_with_console_log_is_blocked(tmp_path: Path):
     _init_git_with_staged(tmp_path, {
         "frontend/app.tsx": 'export const x = () => { console.log("hi"); };\n',

codex
The code changes are narrow enough now that I’m tracing the exact status flow and failure paths rather than re-reading the whole branch. I’m specifically checking whether `BLOCKED` is consistently modeled and whether the Codex runner hardening introduced concurrency or signaling bugs.
exec
/bin/zsh -lc "rg -n \"StepStatus\\.|status == StepStatus|status in \\(\" src tests" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
tests/test_ncdev_v3/test_state_scanner.py:66:    assert results[0].status == StepStatus.PASSED
tests/test_ncdev_v3/test_dependency_gating.py:31:    completed = [StepResult(feature_id="f01", status=StepStatus.PASSED)]
tests/test_ncdev_v3/test_dependency_gating.py:38:    completed = [StepResult(feature_id="f01", status=StepStatus.FAILED)]
tests/test_ncdev_v3/test_dependency_gating.py:46:    completed = [StepResult(feature_id="f01", status=StepStatus.SKIPPED)]
tests/test_ncdev_v3/test_dependency_gating.py:56:        StepResult(feature_id="f01", status=StepStatus.FAILED),
tests/test_ncdev_v3/test_dependency_gating.py:57:        StepResult(feature_id="f02", status=StepStatus.BLOCKED),
tests/test_ncdev_v3/test_dependency_gating.py:65:        StepResult(feature_id="f01", status=StepStatus.PASSED),
tests/test_ncdev_v3/test_dependency_gating.py:66:        StepResult(feature_id="f02", status=StepStatus.FAILED),
tests/test_ncdev_v3/test_dependency_gating.py:74:        StepResult(feature_id="f01", status=StepStatus.PASSED),
tests/test_ncdev_v3/test_dependency_gating.py:75:        StepResult(feature_id="f03", status=StepStatus.PASSED),
tests/unit/test_claude_executor.py:169:    assert result.status == StepStatus.PASSED
tests/unit/test_claude_executor.py:203:    assert result.status == StepStatus.FAILED
tests/unit/test_claude_executor.py:228:    assert result.status == StepStatus.FAILED
tests/unit/test_claude_executor.py:264:    assert result.status == StepStatus.FAILED
tests/unit/test_claude_executor.py:292:    assert result.status == StepStatus.FAILED
tests/unit/test_claude_executor.py:324:    assert result.status == StepStatus.FAILED
tests/unit/test_claude_executor.py:360:    assert result.status == StepStatus.FAILED
tests/unit/test_claude_executor.py:392:    assert result.status == StepStatus.PASSED
tests/unit/test_claude_executor.py:419:    assert result.status == StepStatus.FAILED
tests/unit/test_claude_executor.py:449:    assert result.status == StepStatus.FAILED
tests/unit/test_claude_executor.py:477:    assert result.status == StepStatus.FAILED
tests/test_ncdev_v3/test_context_ingestion.py:76:    result = StepResult(feature_id="f2", status=StepStatus.PASSED, files_created=["a.py"], files_modified=["b.py"], repair_attempts=1)
tests/test_ncdev_v3/test_metrics.py:16:        completed_steps=[_make_result("f1", StepStatus.PASSED), _make_result("f2", StepStatus.PASSED), _make_result("f3", StepStatus.PASSED)],
tests/test_ncdev_v3/test_metrics.py:31:            _make_result("f1", StepStatus.PASSED, 0),
tests/test_ncdev_v3/test_metrics.py:32:            _make_result("f2", StepStatus.PASSED, 2),
tests/test_ncdev_v3/test_metrics.py:33:            _make_result("f3", StepStatus.FAILED, 2),
tests/test_ncdev_v3/test_metrics.py:34:            _make_result("f4", StepStatus.PASSED, 0),
tests/test_ncdev_v3/test_metrics.py:51:            _make_result("f1", StepStatus.PASSED, 0, build_s=80, verify_s=20),
tests/test_ncdev_v3/test_metrics.py:52:            _make_result("f2", StepStatus.PASSED, 0, build_s=120, verify_s=30),
tests/test_ncdev_v3/test_metrics.py:62:        completed_steps=[_make_result("f1", StepStatus.PASSED, 0)],
tests/test_ncdev_v3/test_metrics.py:83:        completed_steps=[_make_result("f1", StepStatus.PASSED)],
src/ncdev/v3/state_scanner.py:62:            status=StepStatus.PASSED,
src/ncdev/v3/metrics.py:58:    passed = [s for s in steps if s.status == StepStatus.PASSED]
src/ncdev/v3/metrics.py:59:    failed = [s for s in steps if s.status == StepStatus.FAILED]
src/ncdev/v3/metrics.py:76:            passed_first_try=(s.status == StepStatus.PASSED and s.repair_attempts == 0),
src/ncdev/v3/engine.py:231:                    status=StepStatus.BLOCKED,
src/ncdev/v3/engine.py:260:            state.completed_features = len([r for r in completed if r.status == StepStatus.PASSED])
src/ncdev/v3/engine.py:263:            status_style = "green" if result.status == StepStatus.PASSED else "red"
src/ncdev/v3/engine.py:268:    passed = [r for r in completed if r.status == StepStatus.PASSED]
src/ncdev/v3/engine.py:274:        if r.status in (StepStatus.FAILED, StepStatus.BLOCKED)
src/ncdev/v3/engine.py:306:        if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
src/ncdev/v3/engine.py:341:            StepStatus.PASSED: "green",
src/ncdev/v3/engine.py:342:            StepStatus.FAILED: "red",
src/ncdev/v3/engine.py:343:            StepStatus.BLOCKED: "red",
src/ncdev/v3/engine.py:344:            StepStatus.SKIPPED: "yellow",
src/ncdev/v3/claude_executor.py:198:    prior_ids = [r.feature_id for r in prior_results if r.status == StepStatus.PASSED]
src/ncdev/v3/claude_executor.py:255:        status = StepStatus.PASSED
src/ncdev/v3/claude_executor.py:259:        status = StepStatus.PASSED
src/ncdev/v3/claude_executor.py:274:        status = StepStatus.FAILED
src/ncdev/v3/claude_executor.py:279:    if status == StepStatus.FAILED and dirty:

exec
/bin/zsh -lc "nl -ba src/ncdev/ai_session.py | sed -n '1,340p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
     1	"""Unified AI session runner — dispatches on mode.
     2	
     3	``run_ai_session()`` is the single entry point every phase of NC Dev
     4	calls when it needs an AI-driven session. It reads ``NCDevV2Config.mode``
     5	and dispatches to the right concrete runner:
     6	
     7	    * ``claude_plan_codex_build`` → Claude session, Codex protocol
     8	      injected so Claude shells to ``codex exec`` for implementation.
     9	    * ``claude_only`` → Claude session, Codex protocol NOT injected;
    10	      Claude does implementation itself.
    11	    * ``codex_only`` → Codex CLI session, no skills / subagents / hooks;
    12	      Codex handles the whole task directly.
    13	    * ``openrouter`` → raises ``NotImplementedError`` (API-only, no CLI
    14	      tooling). Caller should fall back or surface to the user.
    15	    * ``custom`` → falls back to Claude orchestrator as a safe default.
    16	
    17	The returned :class:`ClaudeSessionResult` is the common result shape
    18	across runners — ``skills_invoked`` and ``codex_invocations`` are
    19	populated only when they applied.
    20	"""
    21	
    22	from __future__ import annotations
    23	
    24	import logging
    25	import os
    26	import shutil
    27	import signal
    28	import subprocess
    29	import sys
    30	import threading
    31	import time
    32	from pathlib import Path
    33	from typing import Callable, Iterable
    34	
    35	_IS_POSIX = sys.platform != "win32"
    36	
    37	# Upper bound per stream for run_codex_session capture. A chatty codex
    38	# run can produce a lot — we keep the tail (recent output is more
    39	# useful than the head) and note truncation.
    40	_CODEX_CAPTURE_MAX_BYTES = 4 * 1024 * 1024   # 4 MB per stream
    41	
    42	from ncdev.claude_session import (
    43	    DEFAULT_BUILD_TOOLS,
    44	    ClaudeSessionResult,
    45	    NCDEV_HOOKS_DIR,
    46	    NCDEV_HOOKS_SETTINGS,
    47	    run_claude_session,
    48	)
    49	from ncdev.v2.config import NCDevV2Config, load_v2_config
    50	
    51	logger = logging.getLogger(__name__)
    52	
    53	
    54	# Mode → which provider runs the main orchestrator session.
    55	# "custom" is intentionally absent — it's handled by consulting the
    56	# user's hand-tuned routing via provider_dispatch instead.
    57	MODE_ORCHESTRATOR: dict[str, str] = {
    58	    "claude_plan_codex_build": "claude",
    59	    "claude_only": "claude",
    60	    "codex_only": "codex",
    61	    "openrouter": "openrouter",
    62	}
    63	
    64	# Mode → who actually writes code. Used by the Claude runner to decide
    65	# whether to inject the Codex-via-Bash protocol (i.e. "delegate impl
    66	# to Codex") vs do the work itself.
    67	MODE_IMPLEMENTER: dict[str, str] = {
    68	    "claude_plan_codex_build": "codex",
    69	    "claude_only": "claude",
    70	    "codex_only": "codex",
    71	    "openrouter": "openrouter",
    72	}
    73	
    74	
    75	def _resolve_custom_providers(cfg: NCDevV2Config) -> tuple[str, str]:
    76	    """For ``mode=custom``, read orchestrator + implementer from routing.
    77	
    78	    Honours the contract stated in v2/config.py: ``custom`` preserves
    79	    the user's hand-tuned ``routing:`` block. We use routing.review to
    80	    pick the orchestrator (review is the "who reasons about code" task)
    81	    and routing.implementation to pick the implementer.
    82	
    83	    Both are mapped through :func:`provider_dispatch.resolve_provider_name`
    84	    so long names like ``anthropic_claude_code`` become short
    85	    registry keys (``claude``, ``codex``, ``openrouter``).
    86	    """
    87	    from ncdev.provider_dispatch import resolve_provider_name
    88	
    89	    review_chain = cfg.routing.review or ["anthropic_claude_code"]
    90	    impl_chain = cfg.routing.implementation or ["openai_codex"]
    91	    orch = resolve_provider_name(review_chain[0])
    92	    impl = resolve_provider_name(impl_chain[0])
    93	    return orch, impl
    94	
    95	
    96	def _resolve_config(
    97	    config: NCDevV2Config | None,
    98	    workspace: Path | None,
    99	) -> NCDevV2Config:
   100	    if config is not None:
   101	        return config
   102	    if workspace is not None:
   103	        try:
   104	            return load_v2_config(workspace)
   105	        except Exception:  # noqa: BLE001
   106	            pass
   107	    return NCDevV2Config()
   108	
   109	
   110	def run_ai_session(
   111	    prompt: str,
   112	    *,
   113	    cwd: Path,
   114	    config: NCDevV2Config | None = None,
   115	    workspace: Path | None = None,
   116	    tools: Iterable[str] = DEFAULT_BUILD_TOOLS,
   117	    model: str | None = None,
   118	    timeout: int = 1800,
   119	    permission_mode: str = "acceptEdits",
   120	    append_system_prompt: str | None = None,
   121	    include_codex_protocol: bool | None = None,
   122	    max_budget_usd: float | None = None,
   123	    log_path: Path | None = None,
   124	    on_event: Callable[[dict], None] | None = None,
   125	    extra_args: list[str] | None = None,
   126	    settings_path: Path | None = None,
   127	    enable_ncdev_hooks: bool = True,
   128	) -> ClaudeSessionResult:
   129	    """Run an AI session, dispatching on the active mode.
   130	
   131	    ``include_codex_protocol`` defaults to ``True`` when the mode's
   132	    implementer is Codex (i.e. Claude should delegate), ``False`` when
   133	    implementer is Claude. Explicit values win.
   134	    """
   135	    cfg = _resolve_config(config, workspace)
   136	
   137	    if cfg.mode == "custom":
   138	        # Honour the hand-tuned routing block — this is exactly what
   139	        # "custom" means per the config contract.
   140	        orch, impl = _resolve_custom_providers(cfg)
   141	    else:
   142	        orch = MODE_ORCHESTRATOR.get(cfg.mode, "claude")
   143	        impl = MODE_IMPLEMENTER.get(cfg.mode, "codex")
   144	
   145	    logger.info("run_ai_session mode=%s orch=%s impl=%s cwd=%s", cfg.mode, orch, impl, cwd)
   146	
   147	    if orch == "openrouter":
   148	        raise NotImplementedError(
   149	            "openrouter mode is API-only and cannot spawn a file-editing "
   150	            "session. Install and configure the Claude or Codex CLI and "
   151	            "pick a CLI mode (claude_plan_codex_build, claude_only, or "
   152	            "codex_only)."
   153	        )
   154	
   155	    if orch == "codex":
   156	        return run_codex_session(
   157	            prompt,
   158	            cwd=cwd,
   159	            timeout=timeout,
   160	            model=model,
   161	            log_path=log_path,
   162	            extra_args=extra_args,
   163	        )
   164	
   165	    # orch == "claude"
   166	    if include_codex_protocol is None:
   167	        include_codex_protocol = (impl == "codex")
   168	
   169	    effective_model = model or "claude-opus-4-6"
   170	    return run_claude_session(
   171	        prompt,
   172	        cwd=cwd,
   173	        tools=tools,
   174	        model=effective_model,
   175	        timeout=timeout,
   176	        permission_mode=permission_mode,
   177	        append_system_prompt=append_system_prompt,
   178	        include_codex_protocol=include_codex_protocol,
   179	        max_budget_usd=max_budget_usd,
   180	        log_path=log_path,
   181	        on_event=on_event,
   182	        extra_args=extra_args,
   183	        settings_path=settings_path,
   184	        enable_ncdev_hooks=enable_ncdev_hooks,
   185	    )
   186	
   187	
   188	# ---------------------------------------------------------------------------
   189	# Codex runner — used by codex_only mode
   190	# ---------------------------------------------------------------------------
   191	
   192	
   193	def run_codex_session(
   194	    prompt: str,
   195	    *,
   196	    cwd: Path,
   197	    timeout: int = 1800,
   198	    model: str | None = None,
   199	    log_path: Path | None = None,
   200	    extra_args: list[str] | None = None,
   201	    max_bytes_per_stream: int = _CODEX_CAPTURE_MAX_BYTES,
   202	) -> ClaudeSessionResult:
   203	    """Run a Codex session. No skills, no subagents, no NC Dev hooks.
   204	
   205	    Uses the same safety primitives as :func:`run_claude_session`:
   206	    thread-per-pipe readers so backpressure can't deadlock the child,
   207	    watchdog that kills the process group on wall-clock timeout, and
   208	    a tail-bounded byte buffer per stream so a chatty Codex run
   209	    doesn't blow RAM. Returns the same :class:`ClaudeSessionResult`
   210	    shape (common result type across runners).
   211	    """
   212	    if shutil.which("codex") is None:
   213	        return ClaudeSessionResult(
   214	            success=False, final_text="", exit_code=-1,
   215	            error="codex CLI not found on PATH",
   216	        )
   217	
   218	    # Codex prompt must be scoped — no Claude skill references.
   219	    codex_prompt = (
   220	        prompt
   221	        + "\n\n---\n\n"
   222	        + "You are running in codex_only mode (no Claude orchestrator). "
   223	        "Produce a plan, implement, write tests, and commit with "
   224	        "Conventional Commits. Leave the working tree clean when done."
   225	    )
   226	
   227	    cmd: list[str] = [
   228	        "codex", "exec",
   229	        "--full-auto",
   230	        "--sandbox", "danger-full-access",
   231	    ]
   232	    if model:
   233	        cmd += ["--model", model]
   234	    if extra_args:
   235	        cmd += list(extra_args)
   236	    cmd.append(codex_prompt)
   237	
   238	    popen_kwargs: dict = dict(
   239	        cwd=str(cwd),
   240	        stdout=subprocess.PIPE,
   241	        stderr=subprocess.PIPE,
   242	        text=True,
   243	        bufsize=1,
   244	    )
   245	    if _IS_POSIX:
   246	        popen_kwargs["start_new_session"] = True
   247	
   248	    start = time.time()
   249	    try:
   250	        proc = subprocess.Popen(cmd, **popen_kwargs)
   251	    except (FileNotFoundError, OSError) as exc:
   252	        return ClaudeSessionResult(
   253	            success=False, final_text="", exit_code=-1,
   254	            error=f"failed to spawn codex: {exc}",
   255	        )
   256	
   257	    stdout_buf = _TailBuffer(max_bytes_per_stream)
   258	    stderr_buf = _TailBuffer(max_bytes_per_stream)
   259	
   260	    def _drain(stream, buf: "_TailBuffer") -> None:
   261	        try:
   262	            for line in stream:
   263	                buf.append(line)
   264	        except Exception:  # noqa: BLE001
   265	            pass
   266	
   267	    stdout_thread = threading.Thread(
   268	        target=_drain, args=(proc.stdout, stdout_buf), daemon=True,
   269	    )
   270	    stderr_thread = threading.Thread(
   271	        target=_drain, args=(proc.stderr, stderr_buf), daemon=True,
   272	    )
   273	    stdout_thread.start()
   274	    stderr_thread.start()
   275	
   276	    timeout_fired = threading.Event()
   277	
   278	    def _watchdog() -> None:
   279	        if timeout <= 0:
   280	            return
   281	        if proc.poll() is None:
   282	            time.sleep(timeout)
   283	        if proc.poll() is None:
   284	            timeout_fired.set()
   285	            _kill_process_tree(proc)
   286	
   287	    threading.Thread(target=_watchdog, daemon=True).start()
   288	
   289	    try:
   290	        proc.wait(timeout=timeout + 30)
   291	    except subprocess.TimeoutExpired:
   292	        _kill_process_tree(proc)
   293	        try:
   294	            proc.wait(timeout=5)
   295	        except subprocess.TimeoutExpired:
   296	            pass
   297	
   298	    # Drain final bytes
   299	    stdout_thread.join(timeout=2.0)
   300	    stderr_thread.join(timeout=2.0)
   301	
   302	    duration = time.time() - start
   303	    final_text = stdout_buf.text()
   304	    stderr_text = stderr_buf.text()
   305	    exit_code = proc.returncode if proc.returncode is not None else -1
   306	
   307	    if log_path is not None:
   308	        log_path.parent.mkdir(parents=True, exist_ok=True)
   309	        truncation_note = ""
   310	        if stdout_buf.truncated or stderr_buf.truncated:
   311	            truncation_note = (
   312	                f"\n(NOTE: output tail-truncated to {max_bytes_per_stream} "
   313	                "bytes per stream)\n"
   314	            )
   315	        log_path.write_text(
   316	            f"RUNNER: codex\nEXIT: {exit_code}\nDURATION: {duration:.1f}s"
   317	            f"{truncation_note}\n\n"
   318	            f"STDOUT:\n{final_text}\n\nSTDERR:\n{stderr_text}\n",
   319	            encoding="utf-8",
   320	        )
   321	
   322	    if timeout_fired.is_set():
   323	        return ClaudeSessionResult(
   324	            success=False,
   325	            final_text=final_text,
   326	            exit_code=exit_code,
   327	            duration_seconds=duration,
   328	            stderr=stderr_text,
   329	            error=f"codex session timed out after {timeout}s",
   330	        )
   331	
   332	    return ClaudeSessionResult(
   333	        success=exit_code == 0,
   334	        final_text=final_text,
   335	        exit_code=exit_code,
   336	        duration_seconds=duration,
   337	        stderr=stderr_text,
   338	        error=None if exit_code == 0 else f"codex exited with code {exit_code}",
   339	    )
   340	

exec
/bin/zsh -lc "nl -ba src/ncdev/v3/engine.py | sed -n '1,380p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
     1	"""V3 Engine — sequential verified sprint pipeline (Claude-orchestrated).
     2	
     3	This is the PRD-scale entry point. Replaces the old 9-artifact discovery
     4	+ per-task-routing + parallel-builder pipeline with a thin outer loop:
     5	
     6	    Phase 1 — Preflight                        (this module)
     7	    Phase 2 — Charter generation                (v3.charter)
     8	    Phase 3 — Design system                     (v3.design_phase)
     9	    Phase 4 — Context ingestion into Citex      (v3.context_ingestion — brownfield)
    10	    Phase 5 — Sequential feature execution      (v3.claude_executor)
    11	    Phase 6 — Summary + metrics                 (this module)
    12	
    13	Each phase is a Claude session (or a no-op for greenfield/skipped cases).
    14	NC Dev itself just:
    15	
    16	    * checks preconditions (git, claude, codex, Citex)
    17	    * hands artifacts between phases
    18	    * enforces hard-fail on Phase C for greenfield UI without designs
    19	    * commits on pass, tags [BROKEN] on exhaustion
    20	    * rolls up metrics at the end
    21	
    22	The old run_v3_full() interface is preserved so the ``ncdev full`` CLI
    23	command doesn't need to change.
    24	"""
    25	
    26	from __future__ import annotations
    27	
    28	import json
    29	import time
    30	from pathlib import Path
    31	
    32	from rich.console import Console
    33	from rich.panel import Panel
    34	from rich.table import Table
    35	
    36	from ncdev.utils import make_run_id, write_json
    37	from ncdev.v2.config import NCDevV2Config, ensure_default_v2_config, load_v2_config
    38	from ncdev.v3.charter import generate_charter, load_charter, write_charter
    39	from ncdev.v3.claude_executor import execute_feature_claude_driven
    40	from ncdev.v3.design_phase import run_design_phase
    41	from ncdev.v3.models import (
    42	    CharterBundle,
    43	    StepResult,
    44	    StepStatus,
    45	    V3RunState,
    46	)
    47	
    48	console = Console()
    49	
    50	
    51	def run_v3_full(
    52	    workspace: Path,
    53	    source_path: Path,
    54	    base_url: str = "http://localhost:23000",
    55	    dry_run: bool = False,
    56	    target_repo_path: Path | None = None,
    57	    run_id: str | None = None,
    58	    builder_model: str | None = None,
    59	    builder_timeout: int = 3600,
    60	    max_budget_usd: float | None = None,
    61	    config: NCDevV2Config | None = None,
    62	    strict_deps: bool = False,
    63	    # Retained for CLI signature compat; Claude's systematic-debugging
    64	    # skill handles repair now, so this is a no-op.
    65	    max_repair_attempts: int | None = None,
    66	) -> V3RunState:
    67	    """Run the full V3 pipeline on a PRD.
    68	
    69	    Entry point for ``ncdev full --source <prd>``.
    70	    """
    71	    # ── Phase 1: Preflight + workspace setup ─────────────────────────────
    72	    run_id = run_id or make_run_id("v3")
    73	    run_dir = workspace / ".nc-dev" / "v2" / "runs" / run_id
    74	    outputs_dir = run_dir / "outputs"
    75	    outputs_dir.mkdir(parents=True, exist_ok=True)
    76	
    77	    # Mode-aware config: single source of truth for which CLI runs each
    78	    # session. Load once, pass through every phase.
    79	    if config is None:
    80	        try:
    81	            config = ensure_default_v2_config(workspace)
    82	        except Exception:  # noqa: BLE001
    83	            config = NCDevV2Config()
    84	
    85	    state = V3RunState(
    86	        run_id=run_id,
    87	        workspace=str(workspace),
    88	        run_dir=str(run_dir),
    89	        target_path=str(target_repo_path) if target_repo_path else "",
    90	        phase="init",
    91	    )
    92	
    93	    console.print(Panel(
    94	        f"[bold cyan]NC Dev V3 — {config.mode} mode[/bold cyan]\n"
    95	        f"Run ID: {run_id}\n"
    96	        f"Source: {source_path}\n"
    97	        f"Target: {target_repo_path or '(greenfield)'}",
    98	        border_style="cyan",
    99	    ))
   100	
   101	    # ── Phase 2: Charter ─────────────────────────────────────────────────
   102	    state.phase = "charter"
   103	    console.print("\n[bold]Phase 2: Charter (Claude planning session)[/bold]")
   104	
   105	    if dry_run:
   106	        console.print("  [dim]Dry run — skipping charter generation[/dim]")
   107	        bundle = None
   108	    else:
   109	        bundle, charter_session = generate_charter(
   110	            prd_path=source_path,
   111	            output_dir=outputs_dir,
   112	            target_repo=target_repo_path,
   113	            model=builder_model,
   114	            max_budget_usd=max_budget_usd,
   115	            log_path=run_dir / "logs" / "charter.jsonl",
   116	            config=config,
   117	        )
   118	        if bundle is None:
   119	            console.print(Panel(
   120	                f"[bold red]Charter generation failed[/bold red]\n"
   121	                f"Session: {charter_session.summary()}\n"
   122	                f"See: {outputs_dir}/charter-error.json (if present) "
   123	                f"or run log at {run_dir}/logs/charter.jsonl",
   124	                border_style="red",
   125	            ))
   126	            state.phase = "failed"
   127	            state.status = "failed"
   128	            _persist_state(state, run_dir)
   129	            return state
   130	        console.print(f"  [green]✓[/green] Charter: {len(bundle.feature_queue.features)} features queued")
   131	
   132	    # Resolve target path now that we have the charter
   133	    target_path = (
   134	        Path(bundle.contract.existing_repo_path).expanduser().resolve()
   135	        if bundle and bundle.contract.existing_repo_path
   136	        else (target_repo_path or (workspace / (bundle.contract.project_name if bundle else "project"))).resolve()
   137	    )
   138	    target_path.mkdir(parents=True, exist_ok=True)
   139	    state.target_path = str(target_path)
   140	
   141	    # ── Phase 3: Design system ───────────────────────────────────────────
   142	    state.phase = "design"
   143	    console.print("\n[bold]Phase 3: Design system[/bold]")
   144	    if dry_run or bundle is None:
   145	        console.print("  [dim]Skipped[/dim]")
   146	    else:
   147	        design = run_design_phase(
   148	            contract=bundle.contract,
   149	            target_path=target_path,
   150	            output_dir=outputs_dir,
   151	            model=builder_model,
   152	            max_budget_usd=max_budget_usd,
   153	            log_path=run_dir / "logs" / "design.jsonl",
   154	            config=config,
   155	        )
   156	        if design.skipped:
   157	            console.print("  [dim]Non-UI project — design phase skipped[/dim]")
   158	        elif design.hard_failed:
   159	            console.print(Panel(
   160	                f"[bold red]Design phase HARD FAILED[/bold red]\n"
   161	                f"{design.error}\n"
   162	                f"See: {outputs_dir}/design-phase-error.json",
   163	                border_style="red",
   164	            ))
   165	            state.phase = "failed"
   166	            state.status = "failed"
   167	            _persist_state(state, run_dir)
   168	            return state
   169	        else:
   170	            src = design.design_doc.source if design.design_doc else "?"
   171	            console.print(f"  [green]✓[/green] Design system ready (source={src})")
   172	
   173	    # ── Phase 4: Brownfield context ingestion ────────────────────────────
   174	    state.phase = "ingestion"
   175	    if bundle and bundle.contract.is_brownfield and bundle.contract.uses_citex and not dry_run:
   176	        console.print("\n[bold]Phase 4: Ingest existing code into Citex[/bold]")
   177	        try:
   178	            from ncdev.v3.citex_client import CitexClient
   179	            from ncdev.v3.context_ingestion import ingest_project_context
   180	            project_id = bundle.contract.project_name
   181	            citex = CitexClient(project_id=project_id)
   182	            if citex.health_check():
   183	                report = ingest_project_context(
   184	                    run_dir=run_dir,
   185	                    target_path=target_path,
   186	                    feature_queue=bundle.feature_queue,
   187	                    project_id=project_id,
   188	                )
   189	                console.print(f"  [green]✓[/green] Ingested {report.successful}/{report.total_documents} docs")
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
   226	                    f"[red]BLOCKED[/red] {feature.feature_id} — {reason}",
   227	                    border_style="red",
   228	                ))
   229	                completed.append(StepResult(
   230	                    feature_id=feature.feature_id,
   231	                    status=StepStatus.BLOCKED,
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
   269	    # Both FAILED (tried and broke) and BLOCKED (couldn't try because a dep
   270	    # broke) count as run-level failures. Without this, a --strict-deps halt
   271	    # would report "passed" despite halting because of broken deps.
   272	    unsuccessful = [
   273	        r for r in completed
   274	        if r.status in (StepStatus.FAILED, StepStatus.BLOCKED)
   275	    ]
   276	    state.status = "passed" if not unsuccessful else ("partial" if passed else "failed")
   277	
   278	    _print_summary_table(completed)
   279	
   280	    _persist_state(state, run_dir)
   281	    return state
   282	
   283	
   284	# ---------------------------------------------------------------------------
   285	# Helpers
   286	# ---------------------------------------------------------------------------
   287	
   288	
   289	def _unmet_dependencies(feature, completed: list[StepResult]) -> list[str]:
   290	    """Return the ids in ``feature.depends_on_features`` that are not met.
   291	
   292	    A dep is "met" when it appears in ``completed`` with status:
   293	      * PASSED  — built successfully this run
   294	      * SKIPPED — brownfield state-scanner determined it was already
   295	                  implemented in the target repo before this run started
   296	    A dep is "unmet" when it:
   297	      * is missing from the completed list (never attempted), OR
   298	      * has status FAILED (we tried and it broke), OR
   299	      * has status BLOCKED (its own dep was unmet — cascading failure).
   300	
   301	    The BLOCKED distinction stops feature-N-blocked from being treated
   302	    as "already done" and letting feature N+1 sail through.
   303	    """
   304	    acceptable = {
   305	        r.feature_id for r in completed
   306	        if r.status in (StepStatus.PASSED, StepStatus.SKIPPED)
   307	    }
   308	    return [dep for dep in feature.depends_on_features if dep not in acceptable]
   309	
   310	
   311	def _filter_completed_features(target_path: Path, features, completed: list[StepResult]):
   312	    """Brownfield skip: drop features already implemented in the target repo."""
   313	    try:
   314	        from ncdev.v3.state_scanner import build_skip_results, scan_completed_features
   315	    except ImportError:
   316	        return features
   317	    try:
   318	        done_ids = set(scan_completed_features(target_path, features))
   319	    except Exception:  # noqa: BLE001
   320	        return features
   321	    if not done_ids:
   322	        return features
   323	    skipped = build_skip_results(features, done_ids)
   324	    completed.extend(skipped)
   325	    remaining = [f for f in features if f.feature_id not in done_ids]
   326	    console.print(f"  [dim]Skipping {len(done_ids)} features already implemented[/dim]")
   327	    return remaining
   328	
   329	
   330	def _print_summary_table(completed: list[StepResult]) -> None:
   331	    if not completed:
   332	        return
   333	    table = Table(title="V3 Build Summary")
   334	    table.add_column("Feature", style="cyan")
   335	    table.add_column("Status", style="bold")
   336	    table.add_column("Duration", justify="right")
   337	    table.add_column("Files", justify="right")
   338	    table.add_column("Commit", justify="right")
   339	    for r in completed:
   340	        colour = {
   341	            StepStatus.PASSED: "green",
   342	            StepStatus.FAILED: "red",
   343	            StepStatus.BLOCKED: "red",
   344	            StepStatus.SKIPPED: "yellow",
   345	        }.get(r.status, "white")
   346	        table.add_row(
   347	            r.feature_id,
   348	            f"[{colour}]{r.status.value}[/{colour}]",
   349	            f"{r.build_duration_seconds:.0f}s",
   350	            str(len(r.files_created) + len(r.files_modified)),
   351	            r.commit_sha[:8] if r.commit_sha else "",
   352	        )
   353	    console.print(table)
   354	
   355	
   356	def _persist_state(state: V3RunState, run_dir: Path) -> None:
   357	    run_dir.mkdir(parents=True, exist_ok=True)
   358	    (run_dir / "state.json").write_text(state.model_dump_json(indent=2), encoding="utf-8")

exec
/bin/zsh -lc "nl -ba src/ncdev/v3/claude_executor.py | sed -n '220,700p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
   220	        model=model,
   221	        timeout=timeout,
   222	        permission_mode="acceptEdits",
   223	        max_budget_usd=max_budget_usd,
   224	        log_path=step_dir / "session.jsonl",
   225	    )
   226	    build_duration = time.time() - start
   227	
   228	    # Save session summary for debugging
   229	    (step_dir / "session-summary.txt").write_text(session.summary(), encoding="utf-8")
   230	    if session.final_text:
   231	        (step_dir / "final-response.md").write_text(session.final_text, encoding="utf-8")
   232	
   233	    post_commit = _git_head(target_path)
   234	    made_commit = bool(post_commit and post_commit != pre_commit)
   235	    dirty = _git_working_tree_dirty(target_path)
   236	
   237	    # Files the feature actually touched — used for feature-local asset
   238	    # manifest verification so one legacy unmanaged asset elsewhere in
   239	    # the repo doesn't fail every future feature.
   240	    feature_files_created, feature_files_modified = _diff_since(target_path, pre_commit)
   241	    touched = feature_files_created + feature_files_modified
   242	
   243	    # Post-hoc verification (Claude's own verification-before-completion
   244	    # skill should have caught most things; this is our belt-and-braces)
   245	    verification = _post_session_verification(
   246	        target_path, feature, charter_bundle,
   247	        run_test_commands=run_test_commands,
   248	        probe_health=probe_health,
   249	        touched_files=touched,
   250	    )
   251	
   252	    # Decide status
   253	    recoverability_note = ""
   254	    if session.success and made_commit and not dirty and verification.overall_passed:
   255	        status = StepStatus.PASSED
   256	    elif made_commit and verification.overall_passed:
   257	        # Claude might have exited with non-zero for trivial reasons; if
   258	        # the commit and verification are good, we accept.
   259	        status = StepStatus.PASSED
   260	    else:
   261	        # Something is wrong. Commit whatever is there with [BROKEN] tag
   262	        # so the next feature has context to build on. If that commit
   263	        # itself fails (repo hook blocks it, git identity missing, etc.)
   264	        # we surface it explicitly — recoverability is a guarantee we
   265	        # promise in the docs, silent failure is not acceptable.
   266	        if dirty:
   267	            if _commit_broken(target_path, feature):
   268	                post_commit = _git_head(target_path)
   269	            else:
   270	                recoverability_note = (
   271	                    " | recoverability: [BROKEN] commit failed — dirty "
   272	                    "working tree remains; see log for git error"
   273	                )
   274	        status = StepStatus.FAILED
   275	
   276	    # Reuse the diff — or recompute if a [BROKEN] commit was made above
   277	    files_created = feature_files_created
   278	    files_modified = feature_files_modified
   279	    if status == StepStatus.FAILED and dirty:
   280	        files_created, files_modified = _diff_since(target_path, pre_commit)
   281	
   282	    result = StepResult(
   283	        feature_id=feature.feature_id,
   284	        status=status,
   285	        build_duration_seconds=build_duration,
   286	        verify_duration_seconds=0.0,  # Claude's in-session verification is bundled into build time
   287	        repair_attempts=0,   # Claude handles repair internally via skills
   288	        verification=verification,
   289	        files_created=files_created,
   290	        files_modified=files_modified,
   291	        commit_sha=post_commit or "",
   292	        error_message=(session.error or "") + recoverability_note,
   293	        builder_output=(session.final_text or "")[:2000],
   294	    )
   295	    # Persist the session cost + skills in metadata for metrics
   296	    (step_dir / "result.json").write_text(
   297	        result.model_dump_json(indent=2), encoding="utf-8",
   298	    )
   299	    (step_dir / "signals.json").write_text(json.dumps({
   300	        "success": session.success,
   301	        "made_commit": made_commit,
   302	        "dirty_after": dirty,
   303	        "skills_invoked": session.skills_invoked,
   304	        "subagents_dispatched": session.subagents_dispatched,
   305	        "codex_invocations": len(session.codex_invocations),
   306	        "tool_calls": len(session.tool_calls),
   307	        "total_cost_usd": session.total_cost_usd,
   308	        "duration_seconds": session.duration_seconds,
   309	    }, indent=2), encoding="utf-8")
   310	
   311	    return result
   312	
   313	
   314	# ---------------------------------------------------------------------------
   315	# Post-session verification (light — Claude does the heavy lifting)
   316	# ---------------------------------------------------------------------------
   317	
   318	
   319	def _post_session_verification(
   320	    target_path: Path,
   321	    feature: FeatureStep,
   322	    bundle: CharterBundle,
   323	    *,
   324	    run_test_commands: bool = True,
   325	    probe_health: bool = True,
   326	    touched_files: list[str] | None = None,
   327	) -> StepVerification:
   328	    """Enforce every clause of the verification contract.
   329	
   330	    Belt-and-braces to Claude's in-session ``verification-before-completion``
   331	    skill — we don't trust "claimed done" to mean "actually done".
   332	    """
   333	    ver = StepVerification()
   334	    reasons: list[str] = []
   335	
   336	    # 1. Required files from the verification contract must all exist
   337	    for req in bundle.verification.required_files:
   338	        if not (target_path / req).exists():
   339	            reasons.append(f"required file missing: {req}")
   340	
   341	    # 2. Asset manifest must exist and cover code references
   342	    if bundle.verification.assets_manifest_required:
   343	        ok, missing = verify_manifest_covers_references(
   344	            target_path, feature.feature_id,
   345	            touched_files=touched_files,
   346	        )
   347	        if not ok:
   348	            if missing == ["<no-manifest>"]:
   349	                reasons.append(f"asset manifest not written for {feature.feature_id}")
   350	            else:
   351	                reasons.append(f"asset references without manifest: {missing[:5]}")
   352	
   353	    # 3. Prohibited patterns (regex — treats entries in the contract as
   354	    #    patterns, falls back to literal match if the regex fails to compile)
   355	    patterns = bundle.verification.prohibited_patterns
   356	    if patterns:
   357	        bad = _grep_for_prohibited(target_path, patterns)
   358	        if bad:
   359	            reasons.append(f"prohibited patterns found: {bad[:5]}")
   360	
   361	    # 4. Required screenshots must exist on disk
   362	    for shot in bundle.verification.required_screenshots:
   363	        if not _screenshot_exists(target_path, shot):
   364	            reasons.append(f"required screenshot not captured: {shot}")
   365	
   366	    # 5. Minimum test count — prevents "0 tests, all green" gaming
   367	    if bundle.verification.minimum_test_count > 0:
   368	        count = _count_test_files(target_path)
   369	        ver.unit_tests = TestResult(suite="unit", passed=count, success=count > 0)
   370	        if count < bundle.verification.minimum_test_count:
   371	            reasons.append(
   372	                f"test file count {count} below minimum "
   373	                f"{bundle.verification.minimum_test_count}"
   374	            )
   375	
   376	    # 6. Run the declared test commands
   377	    if run_test_commands:
   378	        if bundle.verification.backend_test_command:
   379	            ok, out = _run_shell(
   380	                bundle.verification.backend_test_command,
   381	                cwd=target_path, timeout=600,
   382	            )
   383	            ver.integration_tests = TestResult(
   384	                suite="backend", passed=1 if ok else 0,
   385	                failed=0 if ok else 1, success=ok, output=out[:2000],
   386	            )
   387	            if not ok:
   388	                reasons.append(f"backend tests failed: {_last_line(out)}")
   389	        if bundle.verification.frontend_test_command:
   390	            ok, out = _run_shell(
   391	                bundle.verification.frontend_test_command,
   392	                cwd=target_path, timeout=600,
   393	            )
   394	            ver.e2e_tests = TestResult(
   395	                suite="frontend", passed=1 if ok else 0,
   396	                failed=0 if ok else 1, success=ok, output=out[:2000],
   397	            )
   398	            if not ok:
   399	                reasons.append(f"frontend tests failed: {_last_line(out)}")
   400	
   401	    # 7. Health probe — if the contract declares a backend_health_url,
   402	    #    the feature is only "done" when that URL responds. Leaving
   403	    #    backend_health_url empty in the contract disables the probe
   404	    #    (common for CLI/library projects). Codex R2 flagged: if the
   405	    #    user put the URL there, they meant it.
   406	    if probe_health and bundle.verification.backend_health_url:
   407	        reachable = _probe_health(
   408	            bundle.verification.backend_health_url,
   409	            timeout=bundle.verification.boot_timeout_seconds,
   410	        )
   411	        ver.app_boots = reachable
   412	        if not reachable:
   413	            reasons.append(
   414	                f"backend health URL unreachable: "
   415	                f"{bundle.verification.backend_health_url} — the feature "
   416	                "must leave the app in a runnable state"
   417	            )
   418	
   419	    ver.failure_reasons = reasons
   420	    ver.overall_passed = not reasons
   421	    ver.prohibited_patterns = [r for r in reasons if "prohibited" in r.lower()]
   422	    return ver
   423	
   424	
   425	def _grep_for_prohibited(target_path: Path, patterns: list[str]) -> list[str]:
   426	    """Scan git-tracked files for prohibited patterns.
   427	
   428	    Each entry is treated as a regular expression via ``re.search``. If
   429	    a pattern fails to compile, falls back to a substring check so
   430	    human-written entries like ``TODO`` still work.
   431	    """
   432	    compiled: list[tuple[str, re.Pattern[str] | None]] = []
   433	    for pat in patterns:
   434	        try:
   435	            compiled.append((pat, re.compile(pat)))
   436	        except re.error:
   437	            compiled.append((pat, None))
   438	
   439	    hits: list[str] = []
   440	    try:
   441	        ls = subprocess.run(
   442	            ["git", "ls-files"],
   443	            cwd=str(target_path), capture_output=True, text=True, timeout=10,
   444	        )
   445	        if ls.returncode != 0:
   446	            return []
   447	        files = [f for f in ls.stdout.splitlines() if f]
   448	    except (subprocess.TimeoutExpired, FileNotFoundError):
   449	        return []
   450	
   451	    for f in files:
   452	        fp = target_path / f
   453	        try:
   454	            if fp.stat().st_size > 1_000_000:
   455	                continue
   456	            text = fp.read_text(encoding="utf-8", errors="ignore")
   457	        except OSError:
   458	            continue
   459	        for pat, regex in compiled:
   460	            hit = regex.search(text) if regex is not None else (pat in text)
   461	            if hit:
   462	                hits.append(f"{f} contains '{pat}'")
   463	                if len(hits) > 20:
   464	                    return hits
   465	                break   # one hit per file is enough
   466	    return hits
   467	
   468	
   469	# ---------------------------------------------------------------------------
   470	# Verification helpers
   471	# ---------------------------------------------------------------------------
   472	
   473	
   474	def _screenshot_exists(target_path: Path, name: str) -> bool:
   475	    """True if a file matching the screenshot name exists under the repo.
   476	
   477	    Matches common conventions: <name>.png, <name>-desktop.png, name-*.png,
   478	    under evidence/screenshots/, .ncdev/evidence/, or docs/screenshots/.
   479	    """
   480	    slug = name.replace(" ", "-").replace("/", "-").lower()
   481	    candidate_dirs = [
   482	        target_path / ".ncdev" / "evidence",
   483	        target_path / "evidence" / "screenshots",
   484	        target_path / "docs" / "screenshots",
   485	    ]
   486	    for d in candidate_dirs:
   487	        if not d.exists():
   488	            continue
   489	        for f in d.rglob("*.png"):
   490	            if slug in f.name.lower():
   491	                return True
   492	    return False
   493	
   494	
   495	def _count_test_files(target_path: Path) -> int:
   496	    patterns = (
   497	        "tests/**/test_*.py",
   498	        "tests/**/*_test.py",
   499	        "**/*.test.ts",
   500	        "**/*.test.tsx",
   501	        "**/*.spec.ts",
   502	        "**/*.spec.tsx",
   503	        "backend/tests/**/*.py",
   504	        "frontend/tests/**/*.ts",
   505	        "frontend/tests/**/*.tsx",
   506	    )
   507	    seen: set[Path] = set()
   508	    for pat in patterns:
   509	        for p in target_path.glob(pat):
   510	            if p.is_file() and "node_modules" not in p.parts:
   511	                seen.add(p.resolve())
   512	    return len(seen)
   513	
   514	
   515	def _run_shell(cmd: str, *, cwd: Path, timeout: int) -> tuple[bool, str]:
   516	    """Run ``cmd`` in a shell. Returns (success, combined_output)."""
   517	    try:
   518	        r = subprocess.run(
   519	            cmd, shell=True, cwd=str(cwd),
   520	            capture_output=True, text=True, timeout=timeout,
   521	        )
   522	        return r.returncode == 0, (r.stdout + "\n" + r.stderr)
   523	    except subprocess.TimeoutExpired as exc:
   524	        return False, f"timed out after {timeout}s: {exc}"
   525	    except Exception as exc:  # noqa: BLE001
   526	        return False, f"exec error: {exc}"
   527	
   528	
   529	def _last_line(text: str) -> str:
   530	    lines = [l for l in text.strip().splitlines() if l.strip()]
   531	    return lines[-1][:200] if lines else "(no output)"
   532	
   533	
   534	def _probe_health(url: str, *, timeout: int) -> bool:
   535	    """Best-effort HTTP GET — True if we get a 2xx response."""
   536	    try:
   537	        import httpx
   538	        r = httpx.get(url, timeout=min(timeout, 10))
   539	        return 200 <= r.status_code < 300
   540	    except Exception:  # noqa: BLE001
   541	        return False
   542	
   543	
   544	# ---------------------------------------------------------------------------
   545	# Git helpers
   546	# ---------------------------------------------------------------------------
   547	
   548	
   549	def _git_head(target_path: Path) -> str:
   550	    try:
   551	        r = subprocess.run(
   552	            ["git", "rev-parse", "HEAD"],
   553	            cwd=str(target_path), capture_output=True, text=True, timeout=5,
   554	        )
   555	        return r.stdout.strip() if r.returncode == 0 else ""
   556	    except (subprocess.TimeoutExpired, FileNotFoundError):
   557	        return ""
   558	
   559	
   560	def _git_working_tree_dirty(target_path: Path) -> bool:
   561	    try:
   562	        r = subprocess.run(
   563	            ["git", "status", "--porcelain"],
   564	            cwd=str(target_path), capture_output=True, text=True, timeout=5,
   565	        )
   566	        return r.returncode == 0 and bool(r.stdout.strip())
   567	    except (subprocess.TimeoutExpired, FileNotFoundError):
   568	        return False
   569	
   570	
   571	def _diff_since(target_path: Path, ref: str) -> tuple[list[str], list[str]]:
   572	    if not ref:
   573	        return [], []
   574	    try:
   575	        r = subprocess.run(
   576	            ["git", "diff", "--name-status", f"{ref}..HEAD"],
   577	            cwd=str(target_path), capture_output=True, text=True, timeout=10,
   578	        )
   579	        if r.returncode != 0:
   580	            return [], []
   581	    except (subprocess.TimeoutExpired, FileNotFoundError):
   582	        return [], []
   583	
   584	    created: list[str] = []
   585	    modified: list[str] = []
   586	    for line in r.stdout.splitlines():
   587	        parts = line.split("\t")
   588	        if len(parts) < 2:
   589	            continue
   590	        flag, path = parts[0], parts[-1]
   591	        if flag == "A":
   592	            created.append(path)
   593	        elif flag in ("M", "R", "C"):
   594	            modified.append(path)
   595	    return created, modified
   596	
   597	
   598	def _commit_broken(target_path: Path, feature: FeatureStep) -> bool:
   599	    """Commit leftover dirty tree with [BROKEN] tag. Returns True on success.
   600	
   601	    Explicitly checks git return codes and surfaces failure so the
   602	    caller knows whether recoverability actually worked. If pre-commit
   603	    hooks reject the commit (e.g. the repo has its own guards), we bail
   604	    cleanly and let the orchestrator handle it.
   605	    """
   606	    try:
   607	        add = subprocess.run(
   608	            ["git", "add", "-A"],
   609	            cwd=str(target_path), capture_output=True, text=True, timeout=10,
   610	        )
   611	        if add.returncode != 0:
   612	            logger.warning("BROKEN-commit: git add failed: %s", add.stderr[:200])
   613	            return False
   614	        commit = subprocess.run(
   615	            ["git", "commit", "-m",
   616	             f"[BROKEN] {feature.feature_id}: {feature.title}\n\n"
   617	             "Claude session did not reach a clean-tree final state. "
   618	             "Committed for recoverability."],
   619	            cwd=str(target_path), capture_output=True, text=True, timeout=10,
   620	        )
   621	        if commit.returncode != 0:
   622	            logger.warning(
   623	                "BROKEN-commit: git commit failed (rc=%d): %s",
   624	                commit.returncode,
   625	                (commit.stderr or commit.stdout)[:300],
   626	            )
   627	            return False
   628	        return True
   629	    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
   630	        logger.warning("BROKEN-commit: %s", exc)
   631	        return False

exec
/bin/zsh -lc "nl -ba src/ncdev/v3/metrics.py | sed -n '1,220p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
     1	"""Run-level build metrics for the V3 pipeline."""
     2	from __future__ import annotations
     3	
     4	from datetime import datetime
     5	
     6	from pydantic import BaseModel, Field
     7	
     8	from ncdev.v3.models import StepStatus, V3RunState
     9	
    10	
    11	class FeatureMetric(BaseModel):
    12	    """Per-feature effectiveness metrics."""
    13	
    14	    feature_id: str
    15	    status: str
    16	    passed_first_try: bool
    17	    repair_attempts: int = 0
    18	    build_duration_seconds: float = 0.0
    19	    verify_duration_seconds: float = 0.0
    20	    files_created: int = 0
    21	    files_modified: int = 0
    22	
    23	
    24	class RunMetrics(BaseModel):
    25	    """Aggregate metrics for one V3 run."""
    26	
    27	    run_id: str
    28	    project_name: str = ""
    29	    started_at: str = ""
    30	    completed_at: str = ""
    31	    total_duration_seconds: float = 0.0
    32	    total_features: int = 0
    33	    passed_features: int = 0
    34	    failed_features: int = 0
    35	    first_pass_success_rate: float = 0.0
    36	    repair_rate: float = 0.0
    37	    mean_repair_attempts: float = 0.0
    38	    build_efficiency: float = 0.0
    39	    feature_throughput_per_hour: float = 0.0
    40	    features: list[FeatureMetric] = Field(default_factory=list)
    41	    builder_primary: str = "codex"
    42	    builder_model: str = "gpt-5.4"
    43	    citex_documents_ingested: int = 0
    44	    citex_queries_by_codex: int = 0
    45	
    46	
    47	def compute_run_metrics(
    48	    state: V3RunState,
    49	    ingestion_doc_count: int = 0,
    50	) -> RunMetrics:
    51	    """Compute aggregate run metrics from the current V3 run state."""
    52	    steps = state.completed_steps
    53	    total = len(steps)
    54	
    55	    if total == 0:
    56	        return RunMetrics(run_id=state.run_id, started_at=state.started_at)
    57	
    58	    passed = [s for s in steps if s.status == StepStatus.PASSED]
    59	    failed = [s for s in steps if s.status == StepStatus.FAILED]
    60	    first_pass = [s for s in passed if s.repair_attempts == 0]
    61	    repaired = [s for s in steps if s.repair_attempts > 0]
    62	
    63	    build_sum = sum(s.build_duration_seconds for s in steps)
    64	    verify_sum = sum(s.verify_duration_seconds for s in steps)
    65	    total_active_time = build_sum + verify_sum
    66	
    67	    started = _parse_iso(state.started_at)
    68	    completed_at = state.updated_at or state.started_at
    69	    completed = _parse_iso(completed_at)
    70	    total_duration_seconds = max((completed - started).total_seconds(), 0.0)
    71	
    72	    feature_metrics = [
    73	        FeatureMetric(
    74	            feature_id=s.feature_id,
    75	            status=s.status.value,
    76	            passed_first_try=(s.status == StepStatus.PASSED and s.repair_attempts == 0),
    77	            repair_attempts=s.repair_attempts,
    78	            build_duration_seconds=s.build_duration_seconds,
    79	            verify_duration_seconds=s.verify_duration_seconds,
    80	            files_created=len(s.files_created),
    81	            files_modified=len(s.files_modified),
    82	        )
    83	        for s in steps
    84	    ]
    85	
    86	    return RunMetrics(
    87	        run_id=state.run_id,
    88	        project_name=_resolve_project_name(state),
    89	        started_at=state.started_at,
    90	        completed_at=completed_at,
    91	        total_duration_seconds=total_duration_seconds,
    92	        total_features=total,
    93	        passed_features=len(passed),
    94	        failed_features=len(failed),
    95	        first_pass_success_rate=len(first_pass) / total,
    96	        repair_rate=len(repaired) / total,
    97	        mean_repair_attempts=(
    98	            sum(s.repair_attempts for s in repaired) / len(repaired)
    99	            if repaired else 0.0
   100	        ),
   101	        build_efficiency=build_sum / total_active_time if total_active_time > 0 else 0.0,
   102	        feature_throughput_per_hour=(
   103	            len(passed) / (total_duration_seconds / 3600.0) if total_duration_seconds > 0 else 0.0
   104	        ),
   105	        features=feature_metrics,
   106	        citex_documents_ingested=ingestion_doc_count,
   107	        citex_queries_by_codex=int(state.metadata.get("citex_queries_by_codex", 0)),
   108	    )
   109	
   110	
   111	def _parse_iso(value: str) -> datetime:
   112	    return datetime.fromisoformat(value.replace("Z", "+00:00"))
   113	
   114	
   115	def _resolve_project_name(state: V3RunState) -> str:
   116	    if state.feature_queue and state.feature_queue.project_name:
   117	        return state.feature_queue.project_name
   118	    return str(state.metadata.get("project_id", "")) or "unknown"

exec
/bin/zsh -lc "nl -ba src/ncdev/v3/state_scanner.py | sed -n '1,180p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
     1	"""Project state scanner — determines which features are already implemented.
     2	
     3	Scans the target repo's git history, file tree, and test results to figure out
     4	what's already built, so the engine can skip completed work and resume from
     5	where the previous run left off.
     6	"""
     7	from __future__ import annotations
     8	
     9	import re
    10	import subprocess
    11	import sys
    12	from pathlib import Path
    13	
    14	from rich.console import Console
    15	
    16	from ncdev.v3.models import FeatureStep, StepResult, StepStatus
    17	
    18	console = Console()
    19	
    20	
    21	def scan_completed_features(
    22	    target_path: Path,
    23	    feature_queue: list[FeatureStep],
    24	) -> list[str]:
    25	    """Scan the target repo and return feature_ids that are already done.
    26	
    27	    A feature is considered done if:
    28	    1. It appears in a git commit message (feat(feature_id): ...), OR
    29	    2. Key files described by its title/description exist in the repo, AND
    30	    3. The project's tests pass (basic smoke check)
    31	    """
    32	    if not (target_path / ".git").exists():
    33	        return []
    34	
    35	    git_log = _get_git_log(target_path)
    36	    file_tree = _get_file_set(target_path)
    37	    tests_pass = _run_smoke_test(target_path)
    38	
    39	    completed: list[str] = []
    40	
    41	    for feature in feature_queue:
    42	        # Check 1: Is this feature in the git history?
    43	        in_git = _feature_in_git_history(feature, git_log)
    44	
    45	        # Check 2: Do files related to this feature exist?
    46	        has_files = _feature_has_files(feature, file_tree)
    47	
    48	        if tests_pass and (in_git or has_files):
    49	            completed.append(feature.feature_id)
    50	
    51	    return completed
    52	
    53	
    54	def build_skip_results(
    55	    feature_queue: list[FeatureStep],
    56	    completed_ids: set[str],
    57	) -> list[StepResult]:
    58	    """Create SKIPPED StepResults for already-completed features."""
    59	    return [
    60	        StepResult(
    61	            feature_id=f.feature_id,
    62	            status=StepStatus.PASSED,
    63	            error_message="Skipped — already implemented in target repo",
    64	        )
    65	        for f in feature_queue
    66	        if f.feature_id in completed_ids
    67	    ]
    68	
    69	
    70	def _get_git_log(target_path: Path) -> str:
    71	    """Get full git log with commit messages."""
    72	    try:
    73	        result = subprocess.run(
    74	            ["git", "log", "--oneline", "--all", "-200"],
    75	            cwd=str(target_path),
    76	            capture_output=True, text=True, timeout=10,
    77	        )
    78	        return result.stdout.lower() if result.returncode == 0 else ""
    79	    except Exception:
    80	        return ""
    81	
    82	
    83	def _get_file_set(target_path: Path) -> set[str]:
    84	    """Get set of all file paths in the repo (relative, lowercase)."""
    85	    try:
    86	        result = subprocess.run(
    87	            ["git", "ls-files"],
    88	            cwd=str(target_path),
    89	            capture_output=True, text=True, timeout=10,
    90	        )
    91	        if result.returncode == 0:
    92	            return {line.strip().lower() for line in result.stdout.splitlines() if line.strip()}
    93	    except Exception:
    94	        pass
    95	    return set()
    96	
    97	
    98	def _run_smoke_test(target_path: Path) -> bool:
    99	    """Quick check: do backend tests pass? (or at least not crash)"""
   100	    backend = target_path / "backend"
   101	    if not backend.exists():
   102	        # Maybe tests are at root level
   103	        backend = target_path
   104	
   105	    has_tests = any(backend.rglob("test_*.py")) or any(backend.rglob("*_test.py"))
   106	    if not has_tests:
   107	        return True
   108	
   109	    try:
   110	        result = subprocess.run(
   111	            [sys.executable, "-m", "pytest", "-q", "-x", "--no-header"],
   112	            cwd=str(backend),
   113	            capture_output=True, text=True, timeout=60,
   114	        )
   115	        # Accept green runs and partially green runs that still discovered passing tests.
   116	        if result.returncode == 0 or "passed" in result.stdout:
   117	            return True
   118	
   119	        combined_output = f"{result.stdout}\n{result.stderr}".lower()
   120	
   121	        # Brownfield repos often do not have pytest wired yet. That should not block
   122	        # feature detection entirely.
   123	        non_blocking_markers = [
   124	            "no tests ran",
   125	            "collected 0 items",
   126	            "unrecognized arguments: --timeout=30",
   127	            "module named pytest",
   128	        ]
   129	        return any(marker in combined_output for marker in non_blocking_markers)
   130	    except Exception:
   131	        return False
   132	
   133	
   134	def _feature_in_git_history(feature: FeatureStep, git_log: str) -> bool:
   135	    """Check if a feature appears in git commit messages."""
   136	    feature_id_lower = feature.feature_id.lower()
   137	    title_lower = feature.title.lower()
   138	
   139	    # Direct feature ID match: feat(sprint-0):, feat(feature-01):, [feature-01]
   140	    if feature_id_lower in git_log:
   141	        return True
   142	
   143	    # Title keywords match (at least 3 significant words from title in same commit line)
   144	    title_words = [w for w in re.split(r'\W+', title_lower) if len(w) > 3]
   145	    if len(title_words) >= 2:
   146	        for line in git_log.splitlines():
   147	            matches = sum(1 for w in title_words if w in line)
   148	            if matches >= min(3, len(title_words)):
   149	                return True
   150	
   151	    return False
   152	
   153	
   154	def _feature_has_files(feature: FeatureStep, file_tree: set[str]) -> bool:
   155	    """Check if files related to the feature exist in the repo.
   156	
   157	    For sprint-0 (scaffold): check for fundamental files.
   158	    For other features: check for feature-specific files using title keywords.
   159	    """
   160	    fid = feature.feature_id.lower()
   161	
   162	    # Sprint-0: scaffold is done if basic project structure exists
   163	    if "sprint-0" in fid or "scaffold" in feature.title.lower():
   164	        scaffold_markers = [
   165	            "backend/app/main.py",
   166	            "backend/requirements.txt",
   167	            "docker-compose.yml",
   168	        ]
   169	        found = sum(1 for m in scaffold_markers if m in file_tree)
   170	        return found >= 2
   171	
   172	    # For other features: extract keywords from title and check file tree
   173	    title_words = [w.lower() for w in re.split(r'\W+', feature.title) if len(w) > 3]
   174	    if not title_words:
   175	        return False
   176	
   177	    # Check if any file path contains feature keywords (prefix match for stems)
   178	    keyword_hits = 0
   179	    for word in title_words:
   180	        # Use first 4+ chars as stem to match "auth" in path against "authentication" in title

exec
/bin/zsh -lc "nl -ba src/ncdev/v3/models.py | sed -n '1,220p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
exec
/bin/zsh -lc "sed -n '1,220p' tests/test_ncdev_v3/test_metrics.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
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


def test_ingestion_count_passed_through():
    state = V3RunState(
        run_id="t6", started_at="2026-04-11T10:00:00+00:00", updated_at="2026-04-11T10:30:00+00:00",
        completed_steps=[_make_result("f1", StepStatus.PASSED)],
        metadata={"citex_queries_by_codex": 7},
    )
    m = compute_run_metrics(state, ingestion_doc_count=12)
    assert m.citex_documents_ingested == 12
    assert m.citex_queries_by_codex == 7

 succeeded in 0ms:
     1	"""V3 models — sequential verified sprint engine."""
     2	
     3	from __future__ import annotations
     4	
     5	from datetime import datetime, timezone
     6	from enum import Enum
     7	from pathlib import Path
     8	from typing import Any
     9	
    10	from pydantic import BaseModel, Field
    11	
    12	
    13	class FeatureStep(BaseModel):
    14	    """A single feature to implement in sequence."""
    15	
    16	    feature_id: str
    17	    title: str
    18	    description: str
    19	    acceptance_criteria: list[str]
    20	    test_requirements: list[str] = Field(default_factory=list)
    21	    depends_on_features: list[str] = Field(default_factory=list)
    22	    priority: int = 0
    23	    estimated_complexity: str = "medium"  # low, medium, high
    24	
    25	
    26	class FeatureQueueDoc(BaseModel):
    27	    """Ordered list of features to implement sequentially."""
    28	
    29	    version: str = "v3"
    30	    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    31	    generator: str = "ncdev.v3.feature_queue"
    32	    project_name: str = ""
    33	    features: list[FeatureStep] = Field(default_factory=list)
    34	    sprint_zero_criteria: list[str] = Field(default_factory=lambda: [
    35	        "App installs without errors",
    36	        "App boots and health endpoint returns OK",
    37	        "Empty test suite runs",
    38	        "First screenshot captured",
    39	    ])
    40	
    41	
    42	class StepStatus(str, Enum):
    43	    PENDING = "pending"
    44	    BUILDING = "building"
    45	    VERIFYING = "verifying"
    46	    REPAIRING = "repairing"
    47	    PASSED = "passed"
    48	    FAILED = "failed"
    49	    SKIPPED = "skipped"   # brownfield state-scanner: feature already implemented
    50	    BLOCKED = "blocked"   # dependency failed / blocked — we did NOT try
    51	
    52	
    53	class TestResult(BaseModel):
    54	    """Result of running a test suite."""
    55	
    56	    suite: str  # "unit", "integration", "e2e"
    57	    passed: int = 0
    58	    failed: int = 0
    59	    errors: int = 0
    60	    skipped: int = 0
    61	    output: str = ""
    62	    success: bool = False
    63	    duration_seconds: float = 0.0
    64	
    65	
    66	class ScreenshotEvidence(BaseModel):
    67	    """A screenshot captured during verification."""
    68	
    69	    path: str
    70	    description: str
    71	    viewport: str = "desktop"  # desktop, mobile
    72	    captured_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    73	
    74	
    75	class StepVerification(BaseModel):
    76	    """Verification results for a single feature step."""
    77	
    78	    lint_passed: bool = False
    79	    lint_output: str = ""
    80	    unit_tests: TestResult | None = None
    81	    integration_tests: TestResult | None = None
    82	    e2e_tests: TestResult | None = None
    83	    screenshots: list[ScreenshotEvidence] = Field(default_factory=list)
    84	    prohibited_patterns: list[str] = Field(default_factory=list)
    85	    app_boots: bool = False
    86	    overall_passed: bool = False
    87	    failure_reasons: list[str] = Field(default_factory=list)
    88	
    89	
    90	class StepResult(BaseModel):
    91	    """Result of executing one feature step."""
    92	
    93	    feature_id: str
    94	    status: StepStatus
    95	    build_duration_seconds: float = 0.0
    96	    verify_duration_seconds: float = 0.0
    97	    repair_attempts: int = 0
    98	    verification: StepVerification | None = None
    99	    files_created: list[str] = Field(default_factory=list)
   100	    files_modified: list[str] = Field(default_factory=list)
   101	    commit_sha: str = ""
   102	    error_message: str = ""
   103	    builder_output: str = ""
   104	
   105	
   106	class V3RunState(BaseModel):
   107	    """Overall state of a V3 pipeline run."""
   108	
   109	    run_id: str
   110	    command: str = "full"
   111	    workspace: str = ""
   112	    run_dir: str = ""
   113	    target_path: str = ""
   114	    phase: str = "init"
   115	    status: str = "running"
   116	    started_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
   117	    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
   118	    feature_queue: FeatureQueueDoc | None = None
   119	    completed_steps: list[StepResult] = Field(default_factory=list)
   120	    current_step: str = ""
   121	    total_features: int = 0
   122	    completed_features: int = 0
   123	    metadata: dict[str, Any] = Field(default_factory=dict)
   124	
   125	
   126	class IngestionRecord(BaseModel):
   127	    """One document ingested into Citex."""
   128	    category: str
   129	    char_count: int
   130	    success: bool
   131	
   132	
   133	class IngestionReport(BaseModel):
   134	    """Summary of context ingestion into Citex."""
   135	    project_id: str
   136	    total_documents: int = 0
   137	    successful: int = 0
   138	    failed: int = 0
   139	    records: list[IngestionRecord] = Field(default_factory=list)
   140	
   141	
   142	# ---------------------------------------------------------------------------
   143	# Charter artifacts — the 3 files that replace the old 9-artifact pipeline.
   144	# ---------------------------------------------------------------------------
   145	
   146	
   147	class TargetProjectContract(BaseModel):
   148	    """Hard architectural constraints. The 'don't override' bag.
   149	
   150	    Fields the user controls: stack, language, DB, auth, deployment target,
   151	    ports, design archetype. Claude may infer defaults from the PRD but
   152	    must NOT change these after the first session — they're the invariants.
   153	    """
   154	
   155	    version: str = "v3"
   156	    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
   157	    project_name: str
   158	    project_type: str = "web"  # web | cli | library | api
   159	    is_brownfield: bool = False
   160	    existing_repo_path: str = ""
   161	
   162	    # Stack — each field optional; "none" means explicitly not used.
   163	    backend_framework: str = ""     # fastapi | django | express | none
   164	    frontend_framework: str = ""    # react | vue | svelte | none
   165	    database: str = ""              # mongodb | postgres | sqlite | none
   166	    auth_system: str = ""           # keycloak | jwt | none
   167	    language_backend: str = ""
   168	    language_frontend: str = ""
   169	
   170	    # Deployment
   171	    deployment_target: str = "docker"   # docker | k8s | serverless
   172	    ports: dict[str, int] = Field(default_factory=dict)
   173	
   174	    # Design
   175	    design_archetype: str = ""  # See user's global CLAUDE.md for values
   176	    design_system_source: str = "stitch"   # stitch | existing | claude
   177	    design_system_path: str = "docs/design-system"
   178	
   179	    # Other invariants the orchestrator or verification must know
   180	    uses_citex: bool = True
   181	    uses_mock_apis: bool = True
   182	    production_readiness_required: bool = True
   183	
   184	
   185	class VerificationContract(BaseModel):
   186	    """What 'done' means for this project.
   187	
   188	    The Claude feature-executor session must satisfy every clause before
   189	    committing. Hooks enforce where possible; post-hoc checks cover the rest.
   190	    """
   191	
   192	    version: str = "v3"
   193	    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
   194	
   195	    # App must boot
   196	    backend_health_url: str = ""       # e.g. http://localhost:23001/api/health
   197	    frontend_url: str = ""
   198	    boot_timeout_seconds: int = 60
   199	
   200	    # Tests must exist and pass
   201	    backend_test_command: str = ""     # e.g. "cd backend && python -m pytest -q"
   202	    frontend_test_command: str = ""    # e.g. "cd frontend && npm test -- --run"
   203	    e2e_test_command: str = ""         # e.g. "cd frontend && npx playwright test"
   204	    minimum_test_count: int = 1
   205	
   206	    # Screenshots
   207	    required_screenshots: list[str] = Field(default_factory=list)
   208	    screenshot_viewports: list[str] = Field(default_factory=lambda: ["desktop", "mobile"])
   209	
   210	    # Files that must exist
   211	    required_files: list[str] = Field(default_factory=list)
   212	
   213	    # Assets
   214	    assets_manifest_required: bool = True
   215	    assets_manifest_path: str = ".ncdev/assets-needed"
   216	
   217	    # Prohibited patterns (grep-able — hooks enforce these on commit)
   218	    prohibited_patterns: list[str] = Field(default_factory=lambda: [
   219	        "TODO",
   220	        "FIXME",

codex
I found one likely gap already outside the files you named: run metrics still only count `FAILED`, not `BLOCKED`. I’m verifying whether that’s just reporting drift or whether it affects any control flow or summaries downstream.
exec
/bin/zsh -lc 'rg -n "resolve_provider_name|provider_dispatch" -S src' in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
src/ncdev/provider_dispatch.py:60:def resolve_provider_name(routing_name: str) -> str:
src/ncdev/provider_dispatch.py:84:    return resolve_provider_name(routing[0])
src/ncdev/ai_session.py:56:# user's hand-tuned routing via provider_dispatch instead.
src/ncdev/ai_session.py:83:    Both are mapped through :func:`provider_dispatch.resolve_provider_name`
src/ncdev/ai_session.py:87:    from ncdev.provider_dispatch import resolve_provider_name
src/ncdev/ai_session.py:91:    orch = resolve_provider_name(review_chain[0])
src/ncdev/ai_session.py:92:    impl = resolve_provider_name(impl_chain[0])
src/ncdev/v3/context_ingestion.py:241:    from ncdev.provider_dispatch import get_provider_for, preferred_model_for

exec
/bin/zsh -lc "nl -ba src/ncdev/provider_dispatch.py | sed -n '1,220p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
     1	"""Config-driven AI provider dispatch.
     2	
     3	Bridges :mod:`ncdev.v2.config` routing (keys like ``design_brief``,
     4	``implementation``) to :mod:`ncdev.ai_provider` (short names like ``claude``,
     5	``codex``, ``openrouter``). Callers ask for a provider by task key — the
     6	preset/routing in ``.nc-dev/v2/config.yaml`` decides which CLI or API backs it.
     7	"""
     8	
     9	from __future__ import annotations
    10	
    11	import logging
    12	import os
    13	from pathlib import Path
    14	from typing import Optional
    15	
    16	from ncdev.ai_provider import AIProvider, get_provider
    17	from ncdev.v2.config import NCDevV2Config, load_v2_config
    18	
    19	logger = logging.getLogger(__name__)
    20	
    21	# Long routing names → short registry keys used in ai_provider.py
    22	PROVIDER_ALIASES: dict[str, str] = {
    23	    "anthropic_claude_code": "claude",
    24	    "openai_codex": "codex",
    25	    "openrouter": "openrouter",
    26	    # Pass-through short names
    27	    "claude": "claude",
    28	    "codex": "codex",
    29	}
    30	
    31	_config_cache: dict[str, NCDevV2Config] = {}
    32	
    33	
    34	def _workspace_root(workspace: Path | None) -> Path:
    35	    if workspace is not None:
    36	        return Path(workspace)
    37	    env = os.environ.get("NCDEV_WORKSPACE")
    38	    if env:
    39	        return Path(env)
    40	    return Path.cwd()
    41	
    42	
    43	def load_config(workspace: Path | None = None) -> NCDevV2Config:
    44	    """Load (and cache) the v2 config for the given workspace."""
    45	    root = _workspace_root(workspace)
    46	    key = str(root.resolve())
    47	    cached = _config_cache.get(key)
    48	    if cached is not None:
    49	        return cached
    50	    cfg = load_v2_config(root)
    51	    _config_cache[key] = cfg
    52	    return cfg
    53	
    54	
    55	def reset_cache() -> None:
    56	    """Clear cached configs (useful between tests)."""
    57	    _config_cache.clear()
    58	
    59	
    60	def resolve_provider_name(routing_name: str) -> str:
    61	    """Translate a v2 routing provider name (or short alias) to registry key."""
    62	    short = PROVIDER_ALIASES.get(routing_name)
    63	    if short is None:
    64	        raise ValueError(
    65	            f"Unknown provider routing name '{routing_name}'. "
    66	            f"Known: {', '.join(sorted(PROVIDER_ALIASES))}"
    67	        )
    68	    return short
    69	
    70	
    71	def provider_name_for(
    72	    task_key: str,
    73	    *,
    74	    workspace: Path | None = None,
    75	    config: NCDevV2Config | None = None,
    76	) -> str:
    77	    """Return the registry short name of the provider for ``task_key``."""
    78	    cfg = config if config is not None else load_config(workspace)
    79	    routing = getattr(cfg.routing, task_key, None)
    80	    if not routing:
    81	        raise ValueError(
    82	            f"No providers configured for routing task '{task_key}'"
    83	        )
    84	    return resolve_provider_name(routing[0])
    85	
    86	
    87	def get_provider_for(
    88	    task_key: str,
    89	    *,
    90	    workspace: Path | None = None,
    91	    config: NCDevV2Config | None = None,
    92	) -> AIProvider:
    93	    """Return the :class:`AIProvider` assigned to ``task_key`` by routing."""
    94	    short = provider_name_for(task_key, workspace=workspace, config=config)
    95	    return get_provider(short)
    96	
    97	
    98	def preferred_model_for(
    99	    task_key: str,
   100	    model_key: str,
   101	    *,
   102	    workspace: Path | None = None,
   103	    config: NCDevV2Config | None = None,
   104	) -> Optional[str]:
   105	    """Look up the preferred model name for a task on its assigned provider.
   106	
   107	    Example: ``preferred_model_for("design_brief", "planning")``.
   108	    Returns ``None`` if no preference is configured.
   109	    """
   110	    cfg = config if config is not None else load_config(workspace)
   111	    routing = getattr(cfg.routing, task_key, None)
   112	    if not routing:
   113	        return None
   114	    long_name = routing[0]
   115	    prov_cfg = cfg.providers.get(long_name)
   116	    if prov_cfg is None:
   117	        return None
   118	    return prov_cfg.preferred_models.get(model_key)

exec
/bin/zsh -lc "rg -n \"failed_features|status = \\\"passed\\\"|state.status|partial|blocked\" src tests" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
src/ncdev/claude_session.py:210:        "--include-partial-messages",
src/ncdev/dev.py:275:    status = "passed"
src/ncdev/v3/state_scanner.py:115:        # Accept green runs and partially green runs that still discovered passing tests.
src/ncdev/v3/engine.py:127:            state.status = "failed"
src/ncdev/v3/engine.py:166:            state.status = "failed"
src/ncdev/v3/engine.py:276:    state.status = "passed" if not unsuccessful else ("partial" if passed else "failed")
src/ncdev/v3/engine.py:301:    The BLOCKED distinction stops feature-N-blocked from being treated
src/ncdev/v3/models.py:50:    BLOCKED = "blocked"   # dependency failed / blocked — we did NOT try
src/ncdev/v3/metrics.py:34:    failed_features: int = 0
src/ncdev/v3/metrics.py:94:        failed_features=len(failed),
src/ncdev/cli.py:375:        console.print(f"run_id={state.run_id} status={state.status}")
src/ncdev/cli.py:378:        if state.status != "passed":
src/ncdev/v2/engine.py:65:        f"run_id={state.run_id} phase={state.phase.value} status={state.status.value} "
src/ncdev/v2/engine.py:96:        state.status = V2TaskStatus.BLOCKED
src/ncdev/v2/engine.py:112:        state.status = V2TaskStatus.BLOCKED
src/ncdev/v2/engine.py:151:        state.status = V2TaskStatus.PASSED
src/ncdev/v2/engine.py:158:    state.status = V2TaskStatus.PASSED
src/ncdev/v2/models.py:19:    BLOCKED = "blocked"
src/ncdev/v2/models.py:27:    BLOCKED = "blocked"
src/ncdev/v2/models.py:68:    BLOCKED = "blocked"
src/ncdev/v2/models.py:666:    readiness_decision: str = "blocked"
tests/test_ncdev_v2/test_sentinel_models.py:78:            "blocked",
tests/test_ncdev_v3/test_metrics.py:22:    assert m.failed_features == 0
tests/test_ncdev_v3/test_metrics.py:42:    assert m.failed_features == 1
tests/test_ncdev_v3/test_dependency_gating.py:50:def test_blocked_dep_does_NOT_count_as_satisfied():
tests/test_ncdev_v3/test_dependency_gating.py:62:def test_multiple_deps_partial_satisfaction():
tests/test_ncdev_v2/test_sentinel_engine.py:126:        assert state.status == V2TaskStatus.BLOCKED
tests/test_ncdev_v2/test_sentinel_engine.py:143:        assert state.status == V2TaskStatus.BLOCKED
tests/test_ncdev_v2/test_sentinel_engine.py:158:        assert state.status == V2TaskStatus.BLOCKED
tests/unit/test_claude_session.py:359:    events = [{"type": "result", "result": "partial"}]
tests/unit/test_hooks.py:84:def test_non_conventional_messages_blocked(tmp_path: Path, bad: str):
tests/unit/test_hooks.py:127:def test_bad_message_with_escaped_quotes_still_blocked(tmp_path: Path):
tests/unit/test_hooks.py:143:def test_staged_content_with_todo_is_blocked(tmp_path: Path):
tests/unit/test_hooks.py:175:def test_staged_content_with_console_log_is_blocked(tmp_path: Path):
tests/unit/test_hooks.py:227:def test_force_push_to_main_blocked(tmp_path: Path, monkeypatch):
src/project-template-api/phased_development_plan.md:409:- Implement partial state updates for efficiency

exec
/bin/zsh -lc "sed -n '7061,7098p' docs/codex-review/review-response-round2.md" in /Users/nrupal/dev/yensi/dev/nc-dev-system
exec
/bin/zsh -lc "sed -n '7099,7136p' docs/codex-review/review-response-round2.md" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
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

 succeeded in 0ms:
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

exec
/bin/zsh -lc "nl -ba scripts/ncdev-hooks/pre_bash_guard.py | sed -n '1,280p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
     1	#!/usr/bin/env python3
     2	"""Claude Code PreToolUse hook — guards ``Bash`` commands.
     3	
     4	Wired in via ``scripts/ncdev-hooks/settings.json`` when NC Dev spawns a
     5	Claude session.  Runs on every Bash tool call and enforces:
     6	
     7	    * ``git commit`` commands cannot land files containing prohibited
     8	      patterns (TODO, FIXME, console.log, bare ``except: pass``,
     9	      "Not yet implemented") in the staged tree.
    10	    * ``git commit`` messages must follow Conventional Commits
    11	      (feat/fix/test/chore/refactor/docs/perf/style/build/ci/revert).
    12	    * ``git push --force`` to protected branches (main/master) is blocked
    13	      unless the user-level allowlist env var is set.
    14	
    15	The hook reads a JSON event from stdin with the tool name and input,
    16	writes a decision JSON to stdout, and exits 0 always — the decision
    17	(allow/block + reason) is conveyed in the JSON body so Claude sees
    18	the structured feedback.
    19	"""
    20	
    21	from __future__ import annotations
    22	
    23	import json
    24	import os
    25	import re
    26	import subprocess
    27	import sys
    28	from pathlib import Path
    29	from typing import Iterable
    30	
    31	# Default prohibited patterns — may be overridden per-project by placing
    32	# a JSON file at $NCDEV_HOOKS_CONFIG.
    33	DEFAULT_PROHIBITED: tuple[str, ...] = (
    34	    "TODO",
    35	    "FIXME",
    36	    "console.log(",
    37	    "Not yet implemented",
    38	    "Coming soon",
    39	)
    40	
    41	CONVENTIONAL_RE = re.compile(
    42	    r"^(feat|fix|test|chore|refactor|docs|perf|style|build|ci|revert)"
    43	    r"(\([^)]+\))?:\s+.+",
    44	    re.MULTILINE,
    45	)
    46	
    47	
    48	def _emit(decision: str, reason: str = "") -> None:
    49	    """Write hook decision JSON and exit cleanly."""
    50	    payload = {"decision": decision}
    51	    if reason:
    52	        payload["reason"] = reason
    53	    sys.stdout.write(json.dumps(payload) + "\n")
    54	    sys.exit(0)
    55	
    56	
    57	def _load_prohibited() -> tuple[str, ...]:
    58	    config_path = os.environ.get("NCDEV_HOOKS_CONFIG")
    59	    if config_path and Path(config_path).exists():
    60	        try:
    61	            cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
    62	            pats = cfg.get("prohibited_patterns")
    63	            if isinstance(pats, list) and all(isinstance(p, str) for p in pats):
    64	                return tuple(pats)
    65	        except Exception:  # noqa: BLE001
    66	            pass
    67	    return DEFAULT_PROHIBITED
    68	
    69	
    70	def _staged_file_list(cwd: str | None) -> list[str]:
    71	    r = subprocess.run(
    72	        ["git", "diff", "--cached", "--name-only"],
    73	        cwd=cwd, capture_output=True, text=True, timeout=5,
    74	    )
    75	    if r.returncode != 0:
    76	        return []
    77	    return [line for line in r.stdout.splitlines() if line]
    78	
    79	
    80	def _check_staged_for_prohibited(
    81	    cwd: str | None, patterns: Iterable[str],
    82	) -> list[str]:
    83	    """Return a list of '<file>:<pattern>' violations found in staged diff.
    84	
    85	    Each pattern is tried as a compiled regex first (via ``re.search``);
    86	    if that fails to compile, we fall back to literal substring match.
    87	    This matches the semantics of claude_executor._grep_for_prohibited
    88	    — identical rules on both sides of the commit boundary.
    89	    """
    90	    compiled: list[tuple[str, re.Pattern[str] | None]] = []
    91	    for pat in patterns:
    92	        try:
    93	            compiled.append((pat, re.compile(pat)))
    94	        except re.error:
    95	            compiled.append((pat, None))
    96	
    97	    hits: list[str] = []
    98	    for path in _staged_file_list(cwd):
    99	        r = subprocess.run(
   100	            ["git", "diff", "--cached", "--", path],
   101	            cwd=cwd, capture_output=True, text=True, timeout=5,
   102	        )
   103	        if r.returncode != 0:
   104	            continue
   105	        # Only inspect added lines (prefixed with "+" but not "+++").
   106	        added = [
   107	            line[1:] for line in r.stdout.splitlines()
   108	            if line.startswith("+") and not line.startswith("+++")
   109	        ]
   110	        blob = "\n".join(added)
   111	        for pat, regex in compiled:
   112	            hit = regex.search(blob) if regex is not None else (pat in blob)
   113	            if hit:
   114	                hits.append(f"{path}:{pat}")
   115	                if len(hits) > 20:
   116	                    return hits
   117	    return hits
   118	
   119	
   120	_HEREDOC_SENTINEL = re.compile(r"<<-?\s*['\"]?(\w+)")
   121	
   122	
   123	def _extract_commit_message(cmd: str) -> tuple[str | None, str]:
   124	    """Pull the ``-m`` argument out of a git-commit command.
   125	
   126	    Returns ``(message, parse_mode)`` where ``parse_mode`` is:
   127	        * "literal"   — we parsed a plain quoted string cleanly
   128	        * "heredoc"   — message is being supplied via a HEREDOC
   129	        * "file"      — ``-F <file>`` used; message is in a file
   130	        * "unknown"   — we don't know what the message is
   131	
   132	    Callers can treat "unknown" as "can't enforce, allow through" to
   133	    avoid breaking legitimate non-inline commit flows.
   134	    """
   135	    # -F <file> — message read from a file
   136	    if re.search(r"(?:^|\s)(?:-F|--file)\s+\S+", cmd):
   137	        return None, "file"
   138	
   139	    # HEREDOC substitution — e.g. git commit -m "$(cat <<'EOF' ... EOF )"
   140	    if _HEREDOC_SENTINEL.search(cmd):
   141	        return None, "heredoc"
   142	
   143	    # Plain quoted message. Handles escaped quotes inside the value by
   144	    # looking for the matching close quote that isn't preceded by a
   145	    # backslash. Double-quote and single-quote variants.
   146	    for quote in ("'", '"'):
   147	        pattern = rf"""-m\s+{quote}((?:\\.|(?!{quote}).)*){quote}"""
   148	        m = re.search(pattern, cmd, flags=re.DOTALL)
   149	        if m:
   150	            raw = m.group(1)
   151	            # Un-escape the quotes so downstream callers see the real message
   152	            raw = raw.replace(f"\\{quote}", quote)
   153	            return raw, "literal"
   154	
   155	    return None, "unknown"
   156	
   157	
   158	def _is_force_push_to_protected(cmd: str) -> bool:
   159	    if "git push" not in cmd:
   160	        return False
   161	    if "--force" not in cmd and "-f " not in cmd and not cmd.rstrip().endswith("-f"):
   162	        return False
   163	    # protected refs
   164	    for ref in ("main", "master", "production", "prod"):
   165	        if re.search(rf"\b{ref}\b", cmd):
   166	            return True
   167	    return False
   168	
   169	
   170	def evaluate(tool_name: str, tool_input: dict, cwd: str | None = None) -> tuple[str, str]:
   171	    """Pure evaluator — given a tool call, return (decision, reason).
   172	
   173	    decision is "allow" or "block". Split out for unit testing; the
   174	    main entry point wraps this in stdin/stdout plumbing.
   175	    """
   176	    if tool_name != "Bash":
   177	        return "allow", ""
   178	
   179	    cmd = str(tool_input.get("command", ""))
   180	    if not cmd:
   181	        return "allow", ""
   182	
   183	    # Force-push protection
   184	    if _is_force_push_to_protected(cmd):
   185	        if os.environ.get("NCDEV_ALLOW_FORCE_PUSH") != "1":
   186	            return "block", (
   187	                "Force-push to a protected branch. Set "
   188	                "NCDEV_ALLOW_FORCE_PUSH=1 in the environment to override, "
   189	                "or push to a feature branch instead."
   190	            )
   191	
   192	    # Only inspect git-commit commands for the remaining rules
   193	    if "git commit" not in cmd:
   194	        return "allow", ""
   195	
   196	    # 1. Conventional Commits message shape
   197	    msg, parse_mode = _extract_commit_message(cmd)
   198	    if msg is not None:
   199	        if not CONVENTIONAL_RE.search(msg):
   200	            return "block", (
   201	                "Commit message does not follow Conventional Commits "
   202	                "(feat|fix|test|chore|refactor|docs|perf|style|build|ci|revert). "
   203	                f"Got: {msg.splitlines()[0][:120]!r}"
   204	            )
   205	    elif parse_mode in ("heredoc", "file"):
   206	        # We can't introspect the message body without running git, so
   207	        # allow it. Worst case: a badly-formatted heredoc lands — but
   208	        # relying on heredoc for commits is deliberate, users typically
   209	        # know what they're doing. "unknown" falls through to allow as
   210	        # well, since blocking would break edge-case pipelines.
   211	        pass
   212	
   213	    # 2. Prohibited patterns in staged content
   214	    patterns = _load_prohibited()
   215	    hits = _check_staged_for_prohibited(cwd, patterns)
   216	    if hits:
   217	        preview = ", ".join(hits[:5])
   218	        return "block", (
   219	            f"Staged changes contain prohibited patterns: {preview}"
   220	            + (" (and more)" if len(hits) > 5 else "")
   221	            + ". Remove them before committing."
   222	        )
   223	
   224	    return "allow", ""
   225	
   226	
   227	def main() -> None:
   228	    try:
   229	        event = json.load(sys.stdin)
   230	    except json.JSONDecodeError:
   231	        _emit("allow")
   232	
   233	    tool = event.get("tool_name") or event.get("tool") or ""
   234	    inp = event.get("tool_input") or event.get("input") or {}
   235	    cwd = event.get("cwd")
   236	
   237	    decision, reason = evaluate(tool, inp, cwd)
   238	    _emit(decision, reason)
   239	
   240	
   241	if __name__ == "__main__":
   242	    main()

exec
/bin/zsh -lc "git show 4a5a0f7:src/ncdev/v3/engine.py | sed -n '208,320p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
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
            state.completed_features = len([r for r in completed if r.status == StepStatus.PASSED])
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
    except ImportError:
        return features
    try:
        done_ids = set(scan_completed_features(target_path, features))
    except Exception:  # noqa: BLE001
        return features

exec
/bin/zsh -lc 'pytest -q tests/test_ncdev_v3/test_dependency_gating.py tests/unit/test_ai_session.py tests/unit/test_claude_executor.py tests/unit/test_hooks.py tests/test_ncdev_v3/test_metrics.py' in /Users/nrupal/dev/yensi/dev/nc-dev-system
codex
The targeted regression suite is running now. While that finishes, I’m checking the hook parser and the remaining status/reporting code for places where `BLOCKED` still falls through as if it didn’t exist.
 succeeded in 14596ms:
........................................................................ [ 97%]
..                                                                       [100%]

exec
/bin/zsh -lc "nl -ba src/ncdev/v3/charter.py | sed -n '160,280p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
   160	        target_repo=str(target_repo) if target_repo else "(none — greenfield)",
   161	        output_dir=str(output_dir),
   162	        project_type_hint=project_type_hint,
   163	        contract_schema=_schema_excerpt(TargetProjectContract),
   164	        verification_schema=_schema_excerpt(VerificationContract),
   165	        feature_queue_schema=_feature_queue_schema_excerpt(),
   166	    )
   167	
   168	
   169	def generate_charter(
   170	    prd_path: Path,
   171	    output_dir: Path,
   172	    *,
   173	    target_repo: Path | None = None,
   174	    project_type_hint: str = "web",
   175	    model: str | None = None,
   176	    timeout: int = 900,
   177	    max_budget_usd: float | None = None,
   178	    log_path: Path | None = None,
   179	    config: NCDevV2Config | None = None,
   180	) -> tuple[CharterBundle | None, ClaudeSessionResult]:
   181	    """Run the charter Claude session and load the produced artifacts.
   182	
   183	    Returns ``(bundle, session_result)``. ``bundle`` is None if the
   184	    session failed, produced invalid JSON, or wrote a ``charter-error.json``
   185	    (enforced hard-fail for greenfield UI without design system).
   186	    """
   187	    output_dir.mkdir(parents=True, exist_ok=True)
   188	    prompt = build_charter_prompt(prd_path, target_repo, output_dir, project_type_hint)
   189	
   190	    session = run_ai_session(
   191	        prompt,
   192	        cwd=output_dir,
   193	        config=config,
   194	        tools=DEFAULT_PLAN_TOOLS,
   195	        model=model,
   196	        timeout=timeout,
   197	        include_codex_protocol=False,   # planning only — no Codex shell-out
   198	        max_budget_usd=max_budget_usd,
   199	        log_path=log_path,
   200	    )
   201	
   202	    # Hard-fail: greenfield UI without design system writes this file.
   203	    error_path = output_dir / "charter-error.json"
   204	    if error_path.exists():
   205	        return None, session
   206	
   207	    if not session.success:
   208	        return None, session
   209	
   210	    try:
   211	        bundle = load_charter(output_dir)
   212	    except (FileNotFoundError, json.JSONDecodeError, ValueError):
   213	        return None, session
   214	
   215	    return bundle, session
   216	
   217	
   218	def load_charter(output_dir: Path) -> CharterBundle:
   219	    """Load the three charter artifacts from disk. Raises on missing/invalid."""
   220	    contract_path = output_dir / "target-project-contract.json"
   221	    verification_path = output_dir / "verification-contract.json"
   222	    feature_queue_path = output_dir / "feature-queue.json"
   223	
   224	    for p in (contract_path, verification_path, feature_queue_path):
   225	        if not p.exists():
   226	            raise FileNotFoundError(f"Charter artifact missing: {p}")
   227	
   228	    contract = TargetProjectContract.model_validate_json(
   229	        contract_path.read_text(encoding="utf-8"),
   230	    )
   231	    verification = VerificationContract.model_validate_json(
   232	        verification_path.read_text(encoding="utf-8"),
   233	    )
   234	    feature_queue = FeatureQueueDoc.model_validate_json(
   235	        feature_queue_path.read_text(encoding="utf-8"),
   236	    )
   237	
   238	    return CharterBundle(
   239	        contract=contract,
   240	        verification=verification,
   241	        feature_queue=feature_queue,
   242	    )
   243	
   244	
   245	def write_charter(bundle: CharterBundle, output_dir: Path) -> None:
   246	    """Persist a charter bundle as three JSON files. Useful for tests."""
   247	    output_dir.mkdir(parents=True, exist_ok=True)
   248	    (output_dir / "target-project-contract.json").write_text(
   249	        bundle.contract.model_dump_json(indent=2), encoding="utf-8",
   250	    )
   251	    (output_dir / "verification-contract.json").write_text(
   252	        bundle.verification.model_dump_json(indent=2), encoding="utf-8",
   253	    )
   254	    (output_dir / "feature-queue.json").write_text(
   255	        bundle.feature_queue.model_dump_json(indent=2), encoding="utf-8",
   256	    )

exec
/bin/zsh -lc "rg -n \"run_ai_session\\(\" src/ncdev/v3 src/ncdev/dev.py" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
src/ncdev/dev.py:258:    session = run_ai_session(
src/ncdev/v3/charter.py:190:    session = run_ai_session(
src/ncdev/v3/design_phase.py:284:        session = run_ai_session(
src/ncdev/v3/design_phase.py:300:        session = run_ai_session(
src/ncdev/v3/design_phase.py:327:    session = run_ai_session(
src/ncdev/v3/claude_executor.py:214:    session = run_ai_session(

exec
/bin/zsh -lc "nl -ba src/ncdev/v3/design_phase.py | sed -n '240,380p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
   240	
   241	def run_design_phase(
   242	    contract: TargetProjectContract,
   243	    target_path: Path,
   244	    output_dir: Path,
   245	    *,
   246	    model: str | None = None,
   247	    timeout: int = 1200,
   248	    max_budget_usd: float | None = None,
   249	    log_path: Path | None = None,
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
   361	    doc = _load_design_doc(output_dir)
   362	    if doc is None:
   363	        return DesignPhaseResult(
   364	            hard_failed=True,
   365	            session=session,
   366	            error=(
   367	                "Design session reported success but no valid "
   368	                f"{output_dir}/design-system.json was produced."
   369	            ),
   370	        )
   371	    return DesignPhaseResult(design_doc=doc, session=session)
   372	
   373	
   374	def _load_design_doc(output_dir: Path) -> DesignSystemDoc | None:
   375	    path = output_dir / "design-system.json"
   376	    if not path.exists():
   377	        return None
   378	    try:
   379	        return DesignSystemDoc.model_validate_json(path.read_text(encoding="utf-8"))
   380	    except Exception:  # noqa: BLE001

exec
/bin/zsh -lc "nl -ba src/ncdev/dev.py | sed -n '160,320p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
   160	def _build_task_prompt(task: str, project_path: Path, project_id: str, mode: str) -> str:
   161	    """Compose the short prompt for a freeform dev task.
   162	
   163	    Deliberately terse — the Codex protocol is injected via
   164	    ``--append-system-prompt`` by :func:`run_claude_session`, and Claude
   165	    can read the repo itself with the Read tool. We do not pre-gather
   166	    file trees or README content here; Claude is better at deciding
   167	    what to look at.
   168	    """
   169	    return f"""# Task for this ncdev dev session
   170	
   171	Mode: {mode}
   172	Project: {project_path}
   173	Citex project ID: {project_id}
   174	Citex URL: {CITEX_API}
   175	
   176	## What the user wants
   177	
   178	{task}
   179	
   180	## Your workflow
   181	
   182	You are the engineer. Drive the full cycle yourself using the skill
   183	machinery available to you. Codex is your implementation peer — see
   184	the Codex protocol in your system prompt.
   185	
   186	1. Explore the project using Read/Glob/Grep. Query Citex (via HTTP
   187	   or any CLI it exposes) for prior context.
   188	2. If this is non-trivial, use the `writing-plans` skill.
   189	3. Use `test-driven-development` for any behavioural change.
   190	4. Delegate raw implementation and test writing to Codex via Bash:
   191	   `codex exec --full-auto --sandbox danger-full-access "<scoped task>"`.
   192	5. Use `verification-before-completion` — run the project's tests,
   193	   boot the app, check a health endpoint if one exists. No claiming
   194	   done without evidence.
   195	6. On failure, use `systematic-debugging` — root-cause first, don't
   196	   loop blindly.
   197	7. Commit your work using Conventional Commits. Leave the working
   198	   tree clean.
   199	
   200	## What success looks like
   201	
   202	- Tests exist and pass for any behavioural change.
   203	- Working tree is clean, all changes committed.
   204	- One-paragraph summary in your final response.
   205	
   206	Begin.
   207	"""
   208	
   209	
   210	# ── Main Entry Point ────────────────────────────────────────────────────
   211	
   212	
   213	def run_dev(
   214	    project_path: Path,
   215	    task: str,
   216	    mode: str = "auto",
   217	    *,
   218	    model: str | None = None,
   219	    timeout: int = 3600,
   220	    max_budget_usd: float | None = None,
   221	    config: NCDevV2Config | None = None,
   222	) -> dict[str, Any]:
   223	    """Run a single ncdev dev session.
   224	
   225	    This is thin glue. Claude does the actual work; NC Dev handles:
   226	    preflight, git repo setup, session orchestration, broken-tag
   227	    fallback on failure, Citex ingestion of the run summary.
   228	    """
   229	    start = time.time()
   230	    project_id = project_path.name
   231	    run_id = f"dev-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"
   232	
   233	    require_citex(CITEX_API)
   234	
   235	    console.print(Panel(
   236	        f"[bold cyan]NC Dev System — thin orchestrator[/bold cyan]\n"
   237	        f"Project: {project_path}\n"
   238	        f"Task:    {task}\n"
   239	        f"Mode:    {mode}\n"
   240	        f"Run:     {run_id}",
   241	        border_style="cyan",
   242	    ))
   243	
   244	    _ensure_git_repo(project_path, mode)
   245	
   246	    pre_head = _git_head(project_path)
   247	
   248	    # Load mode-aware config so the session dispatcher knows which CLI to run.
   249	    effective_config = config
   250	    if effective_config is None:
   251	        try:
   252	            effective_config = load_v2_config(project_path)
   253	        except Exception:  # noqa: BLE001
   254	            effective_config = NCDevV2Config()
   255	    console.print(f"\n[bold]Running session (mode={effective_config.mode})...[/bold]")
   256	    log_path = project_path / ".ncdev" / "runs" / run_id / "session.jsonl"
   257	    prompt = _build_task_prompt(task, project_path, project_id, mode)
   258	    session = run_ai_session(
   259	        prompt,
   260	        cwd=project_path,
   261	        config=effective_config,
   262	        tools=DEFAULT_BUILD_TOOLS,
   263	        model=model,
   264	        timeout=timeout,
   265	        permission_mode="acceptEdits",
   266	        max_budget_usd=max_budget_usd,
   267	        log_path=log_path,
   268	    )
   269	    console.print(f"  Session: {session.summary()}")
   270	
   271	    post_head = _git_head(project_path)
   272	    dirty = _git_working_tree_dirty(project_path)
   273	    made_commit = bool(post_head and post_head != pre_head)
   274	
   275	    status = "passed"
   276	    if not session.success or not made_commit:
   277	        status = "failed"
   278	    if dirty:
   279	        # Recoverability: commit leftovers with [BROKEN]
   280	        broken_sha = _commit_broken_leftovers(project_path, task)
   281	        if broken_sha:
   282	            console.print(f"  [yellow]Committed leftovers with [BROKEN] tag: {broken_sha[:8]}[/yellow]")
   283	            post_head = broken_sha
   284	        status = "failed"
   285	
   286	    duration = time.time() - start
   287	
   288	    # Ingest short run summary to Citex (best-effort; do not fail the run)
   289	    try:
   290	        citex_store(
   291	            project_id,
   292	            content=(
   293	                f"ncdev dev run {run_id}\n"
   294	                f"Task: {task}\n"
   295	                f"Status: {status}\n"
   296	                f"Commit: {post_head[:12] if post_head else ''}\n"
   297	                f"Session: {session.summary()}\n"
   298	                f"Final response:\n{(session.final_text or '')[:2000]}"
   299	            ),
   300	            metadata={
   301	                "run_id": run_id,
   302	                "task": task[:500],
   303	                "mode": mode,
   304	                "status": status,
   305	                "commit_sha": post_head,
   306	                "skills_invoked": session.skills_invoked,
   307	                "codex_invocations": len(session.codex_invocations),
   308	                "total_cost_usd": session.total_cost_usd,
   309	                "duration_seconds": duration,
   310	                "timestamp": datetime.now(timezone.utc).isoformat(),
   311	            },
   312	        )
   313	    except Exception as exc:  # noqa: BLE001
   314	        console.print(f"  [yellow]Citex ingestion of run summary failed: {exc}[/yellow]")
   315	
   316	    console.print(Panel(
   317	        f"[bold]Status:[/bold] {status}\n"
   318	        f"[bold]Commit:[/bold] {post_head[:12] if post_head else '(none)'}\n"
   319	        f"[bold]Skills:[/bold] {', '.join(session.skills_invoked) or '(none)'}\n"
   320	        f"[bold]Codex calls:[/bold] {len(session.codex_invocations)}\n"

codex
I found a concrete regression in the new tail buffer implementation: it preserves the tail only at chunk granularity, not byte granularity, so a single oversized chunk can be dropped entirely. I’m confirming that behavior directly rather than leaving it theoretical.
exec
/bin/zsh -lc "python - <<'PY'
from ncdev.ai_session import _TailBuffer
b = _TailBuffer(10)
b.append('x'*25)
print('truncated', b.truncated)
print('text_len', len(b.text()))
print('text', repr(b.text()))
PY" in /Users/nrupal/dev/yensi/dev/nc-dev-system
exec
/bin/zsh -lc "python - <<'PY'
from ncdev.v3.metrics import compute_run_metrics
from ncdev.v3.models import V3RunState, StepResult, StepStatus
state = V3RunState(run_id='r', started_at='2026-04-11T10:00:00+00:00', updated_at='2026-04-11T10:10:00+00:00', completed_steps=[StepResult(feature_id='f1', status=StepStatus.BLOCKED)])
m = compute_run_metrics(state)
print('failed_features', m.failed_features)
print('total_features', m.total_features)
print('statuses', [f.status for f in m.features])
PY" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 123ms:
failed_features 0
total_features 1
statuses ['blocked']

 succeeded in 270ms:
truncated True
text_len 0
text ''

exec
/bin/zsh -lc "nl -ba src/ncdev/ai_session.py | sed -n '340,420p'" in /Users/nrupal/dev/yensi/dev/nc-dev-system
 succeeded in 0ms:
   340	
   341	
   342	# ---------------------------------------------------------------------------
   343	# Helpers (shared)
   344	# ---------------------------------------------------------------------------
   345	
   346	
   347	class _TailBuffer:
   348	    """Accumulate text but keep only the tail of ``max_bytes``.
   349	
   350	    Recent output is more useful than the head when debugging a builder
   351	    that went off the rails. ``truncated`` flips True once we start
   352	    dropping bytes so callers can surface that to users / logs.
   353	    """
   354	
   355	    __slots__ = ("_chunks", "_size", "_max", "truncated")
   356	
   357	    def __init__(self, max_bytes: int) -> None:
   358	        self._chunks: list[str] = []
   359	        self._size = 0
   360	        self._max = max_bytes
   361	        self.truncated = False
   362	
   363	    def append(self, chunk: str) -> None:
   364	        if not chunk:
   365	            return
   366	        enc = len(chunk.encode("utf-8", errors="ignore"))
   367	        self._chunks.append(chunk)
   368	        self._size += enc
   369	        while self._size > self._max and self._chunks:
   370	            head = self._chunks.pop(0)
   371	            self._size -= len(head.encode("utf-8", errors="ignore"))
   372	            self.truncated = True
   373	
   374	    def text(self) -> str:
   375	        return "".join(self._chunks)
   376	
   377	
   378	def _kill_process_tree(proc: subprocess.Popen) -> None:
   379	    """Kill a process and its children. Mirror of claude_session's helper."""
   380	    if proc.poll() is not None:
   381	        return
   382	    try:
   383	        if _IS_POSIX:
   384	            try:
   385	                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
   386	            except (ProcessLookupError, PermissionError):
   387	                proc.terminate()
   388	            try:
   389	                proc.wait(timeout=3)
   390	            except subprocess.TimeoutExpired:
   391	                try:
   392	                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
   393	                except (ProcessLookupError, PermissionError):
   394	                    proc.kill()
   395	        else:
   396	            proc.terminate()
   397	            try:
   398	                proc.wait(timeout=3)
   399	            except subprocess.TimeoutExpired:
   400	                proc.kill()
   401	    except Exception:  # noqa: BLE001
   402	        pass

codex
## Architecture verdict
`4a5a0f7` closes the round-2 “didn’t land” items I called out: the `console` crash is gone, `_commit_broken()`’s return value is now wired, dependency blocking is no longer conflated with brownfield skips, `--strict-deps` no longer reports a false pass, `custom` mode now honors configured routing, and hook/verifier regex behavior now matches. I reran the targeted regression suite for the touched areas, and it passes. The branch is much closer, but there is still one real default-path blocker and a couple smaller regressions from the hardening itself.

## R2 fixes verified
- Fix A landed. [`claude_executor.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:30>) now defines `logger`, and the old undefined `console` calls in `_commit_broken()` are gone at [`claude_executor.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:598>).
- Fix B landed. The caller now branches on `_commit_broken()` and records a recoverability note when it fails at [`claude_executor.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:266>).
- Fix C landed. `StepStatus.BLOCKED` exists at [`models.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/models.py:42>), and `_unmet_dependencies()` now treats only `PASSED` and `SKIPPED` as satisfied at [`engine.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:289>).
- Fix D landed. Run-level status now treats both `FAILED` and `BLOCKED` as unsuccessful at [`engine.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:268>).
- Fix E landed for valid provider names. `custom` now routes through `_resolve_custom_providers()` at [`ai_session.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/ai_session.py:75>) and [`ai_session.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/ai_session.py:137>).
- Fix F landed. The hook now does regex search with literal fallback at [`pre_bash_guard.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/scripts/ncdev-hooks/pre_bash_guard.py:80>).
- Fix G broadly landed. `run_codex_session()` now uses `Popen`, drain threads, a watchdog, and bounded capture at [`ai_session.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/ai_session.py:193>).
- Fix H landed as implemented. A configured health URL is now a hard failure at [`claude_executor.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:401>).

## R2 fixes that still didn't land
None. The specific round-2 “didn’t land” items are actually fixed in code now.

## New issues introduced in R2
- The new hard health check still has broken timing semantics. [`claude_executor.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:406>) now fails the feature if the probe misses, but [`_probe_health()`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:534>) does only one immediate `GET` and clamps the timeout to `min(timeout, 10)`. It does not poll for up to `boot_timeout_seconds`. So a healthy app that comes up a few seconds later now fails deterministically. This is the remaining blocker on the default path.
- `_TailBuffer` is not actually a byte-tail buffer for oversized chunks. [`ai_session.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/ai_session.py:363>) appends whole chunks, then evicts whole chunks from the front. If one chunk exceeds the cap, the buffer becomes empty. I reproduced `_TailBuffer(10).append('x' * 25) -> ''`. In `codex_only`, that can erase the only useful output from a noisy failure.
- `BLOCKED` is still unhandled in run metrics. [`metrics.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/metrics.py:58>) and [`metrics.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/metrics.py:93>) count only `FAILED`, so a run with blocked features reports `failed_features == 0`. The engine summary is fixed; the metrics layer is now inconsistent with it.
- `custom` with an unknown provider name is an uncaught config crash, not a structured failure. [`ai_session.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/ai_session.py:140>) calls [`resolve_provider_name()`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/provider_dispatch.py:60>), which raises `ValueError`, and callers like [`charter.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/charter.py:190>) do not catch it.

## Still open from earlier rounds
- `_extract_event_signals()` is still schema-fragile. This commit did not change the Claude stream-shape assumptions.
- Commit-message enforcement is still intentionally bypassable for heredoc, `-F`, and unknown forms at [`pre_bash_guard.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/scripts/ncdev-hooks/pre_bash_guard.py:205>).
- Status semantics are still internally inconsistent: [`models.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/models.py:49>) says brownfield already-done work is `SKIPPED`, but [`state_scanner.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/state_scanner.py:60>) still emits `PASSED`. So `state.completed_features` is “correct” today only because the scanner lies in its favor.

## Ready to inherit?
No. The one blocker left on the mainline path is the health probe: it is now hard-failing features without actually honoring `boot_timeout_seconds` as a startup grace period. Fix that to poll/retry until the budget expires, and I’d be comfortable inheriting the default flow. After that, I’d fix the `_TailBuffer` oversized-chunk behavior, but I would not block inheritance on that alone unless `codex_only` is production-critical.

## Honest one-liner
Most of the round-2 hardening finally landed, but the new hard health check is still wrong enough to reject good builds, so it is not ready yet.
tokens used
131,665
## Architecture verdict
`4a5a0f7` closes the round-2 “didn’t land” items I called out: the `console` crash is gone, `_commit_broken()`’s return value is now wired, dependency blocking is no longer conflated with brownfield skips, `--strict-deps` no longer reports a false pass, `custom` mode now honors configured routing, and hook/verifier regex behavior now matches. I reran the targeted regression suite for the touched areas, and it passes. The branch is much closer, but there is still one real default-path blocker and a couple smaller regressions from the hardening itself.

## R2 fixes verified
- Fix A landed. [`claude_executor.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:30>) now defines `logger`, and the old undefined `console` calls in `_commit_broken()` are gone at [`claude_executor.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:598>).
- Fix B landed. The caller now branches on `_commit_broken()` and records a recoverability note when it fails at [`claude_executor.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:266>).
- Fix C landed. `StepStatus.BLOCKED` exists at [`models.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/models.py:42>), and `_unmet_dependencies()` now treats only `PASSED` and `SKIPPED` as satisfied at [`engine.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:289>).
- Fix D landed. Run-level status now treats both `FAILED` and `BLOCKED` as unsuccessful at [`engine.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/engine.py:268>).
- Fix E landed for valid provider names. `custom` now routes through `_resolve_custom_providers()` at [`ai_session.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/ai_session.py:75>) and [`ai_session.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/ai_session.py:137>).
- Fix F landed. The hook now does regex search with literal fallback at [`pre_bash_guard.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/scripts/ncdev-hooks/pre_bash_guard.py:80>).
- Fix G broadly landed. `run_codex_session()` now uses `Popen`, drain threads, a watchdog, and bounded capture at [`ai_session.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/ai_session.py:193>).
- Fix H landed as implemented. A configured health URL is now a hard failure at [`claude_executor.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:401>).

## R2 fixes that still didn't land
None. The specific round-2 “didn’t land” items are actually fixed in code now.

## New issues introduced in R2
- The new hard health check still has broken timing semantics. [`claude_executor.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:406>) now fails the feature if the probe misses, but [`_probe_health()`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/claude_executor.py:534>) does only one immediate `GET` and clamps the timeout to `min(timeout, 10)`. It does not poll for up to `boot_timeout_seconds`. So a healthy app that comes up a few seconds later now fails deterministically. This is the remaining blocker on the default path.
- `_TailBuffer` is not actually a byte-tail buffer for oversized chunks. [`ai_session.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/ai_session.py:363>) appends whole chunks, then evicts whole chunks from the front. If one chunk exceeds the cap, the buffer becomes empty. I reproduced `_TailBuffer(10).append('x' * 25) -> ''`. In `codex_only`, that can erase the only useful output from a noisy failure.
- `BLOCKED` is still unhandled in run metrics. [`metrics.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/metrics.py:58>) and [`metrics.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/metrics.py:93>) count only `FAILED`, so a run with blocked features reports `failed_features == 0`. The engine summary is fixed; the metrics layer is now inconsistent with it.
- `custom` with an unknown provider name is an uncaught config crash, not a structured failure. [`ai_session.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/ai_session.py:140>) calls [`resolve_provider_name()`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/provider_dispatch.py:60>), which raises `ValueError`, and callers like [`charter.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/charter.py:190>) do not catch it.

## Still open from earlier rounds
- `_extract_event_signals()` is still schema-fragile. This commit did not change the Claude stream-shape assumptions.
- Commit-message enforcement is still intentionally bypassable for heredoc, `-F`, and unknown forms at [`pre_bash_guard.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/scripts/ncdev-hooks/pre_bash_guard.py:205>).
- Status semantics are still internally inconsistent: [`models.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/models.py:49>) says brownfield already-done work is `SKIPPED`, but [`state_scanner.py`](</Users/nrupal/dev/yensi/dev/nc-dev-system/src/ncdev/v3/state_scanner.py:60>) still emits `PASSED`. So `state.completed_features` is “correct” today only because the scanner lies in its favor.

## Ready to inherit?
No. The one blocker left on the mainline path is the health probe: it is now hard-failing features without actually honoring `boot_timeout_seconds` as a startup grace period. Fix that to poll/retry until the budget expires, and I’d be comfortable inheriting the default flow. After that, I’d fix the `_TailBuffer` oversized-chunk behavior, but I would not block inheritance on that alone unless `codex_only` is production-critical.

## Honest one-liner
Most of the round-2 hardening finally landed, but the new hard health check is still wrong enough to reject good builds, so it is not ready yet.
