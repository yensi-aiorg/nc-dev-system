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
