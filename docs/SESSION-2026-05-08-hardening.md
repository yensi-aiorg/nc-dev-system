# NC Dev hardening session — 2026-05-08

Time-boxed live PRD-driven hardening run. Probe target: salon-
management PRD at `docs-only/planning/project-06-yensi-service-platform/`.

## Approach

Treated the salon PRD as a probe rather than a deliverable: launch
NC Dev against the PRD, observe the first failure mode, fix the
underlying NC Dev gap, rerun. Repeat. The salon project repo is
incidental output; the hardening commits are the real ship.

## NC Dev gaps closed (19 commits)

### Charter / planning phase (1)
- Charter retry on validator-rejected output, with the rejection
  reasons fed back into the retry prompt and failed attempts archived
  under `.attempt-N/` (`6bf721e`).

### Design phase (8)
- Hard-fail removed for greenfield-UI-without-Stitch (`6bf721e`).
- Deterministic archetype-driven seed replaces unreliable Claude
  fallback for the no-Stitch path (`ac5bf3a`).
- Stitch path is opt-in via `NCDEV_USE_STITCH=1`; auto-falls-back to
  seed when the spawned session can't actually invoke Stitch
  (`7f19976`).
- DesignSystemDoc.colors/typography/spacing accept `Any` — the
  brownfield summariser sometimes emits nested dicts (`eb261fc`).
- Validation errors persisted to disk for postmortem instead of
  silently swallowed (`836311f`).
- Design phase recognises its own seeded files via the
  `owned_by_feature` marker and skips the unreliable summariser
  (`7312ed0`).
- Seeded files include the bootstrap feature_id so the state-scanner's
  must_mention check passes for shared infra (`8548286`).

### Per-feature verification (5)
- Health probe is opt-in per feature via
  `FeatureAcceptance.verify_app_boots` (default False) — was failing
  every feature whose contract had backend_health_url because Claude
  sessions don't keep daemons up between sessions (`0ec42d4`).
- Charter prompt teaches Claude when to set verify_app_boots
  (scaffold yes, others no) (`3eb05f9`).
- Mode-aware feature prompt + structured-acceptance surfaced inline so
  Claude can see exactly what the verifier will check (`e77407e`).
- Per-feature verifier no longer enforces global required_screenshots
  on every feature — that list spans the whole product (`ec4f9d0`).
- Step 7 of build prompt: explicit "tag every required_file with
  feature_id BEFORE running tests" guidance with format examples
  (`de42059`).

### Test runner (3)
- Single-test runner cd's to the right project root (frontend/ for
  vitest, backend/ for pytest) — was reporting "no test files found"
  for valid frontend tests (`62dc56c`).
- target_path threaded through `_runner_for_test` so the walk-up
  reaches package.json instead of stopping inside src/ (`d3f45ec`).
- Playwright tests (e2e/ dir or playwright.config) routed to
  `npx playwright test` instead of vitest (`de42059`).

### Integration gate (1)
- App lifecycle: `start_command` runs before route probing,
  `stop_command` tears down after — was assuming a daemon would
  already be running, which Claude sessions don't (`833a0b1`).

### UX (1)
- Engine status line includes per-feature duration + file count
  (`e212097`).

### Tests added (covering all of the above)
- `test_state_scanner` for runner resolver + Playwright detection
  (`b79331e`, `de9545f`).
- `test_integration_gate` for lifecycle clauses (`631bfb8`).

## Live run signal

Run 10 (representative): state-scanner correctly skipped
f01-scaffold (recognised brownfield baseline), Phase 5 attempted
f02-auth-tenancy and got 21 files committed across 6.7 minutes,
verifier surfaced THREE specific failure clauses (asset manifest
not written, sqlalchemy missing in test env, one required test file
missing) and halted. f03-f10 BLOCKED on f02 — correct cascade
behaviour.

Failures attributed to Claude session execution, not NC Dev's
gates. Each failure had an actionable diagnostic.

## What did NOT ship

- Salon platform itself — only f01-scaffold was verified PASSED via
  NC Dev.
- Integration gate not exercised live (every run used
  `--skip-integration-gate` while the app lifecycle was being
  hardened).

## State at end of session

- NC Dev: 555 tests pass, 85% coverage, ruff + mypy clean
- Salon repo: pushed to https://github.com/yensi-aiorg/yensi-service-platform
- 19 commits ahead of where this session started
