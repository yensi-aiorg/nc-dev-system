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
