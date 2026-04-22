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
