# Sentinel Fix → Production Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) tracking. Each slice is one Codex handoff + verify + commit + push.

**Goal:** Eliminate every stub in NC Dev's production-fix path so a wrapper can POST a `SentinelFailureReport` and get a verified fix auto-merged to staging — no stubs, no dead ends.

**Architecture:** A production failure report is just another *issue*. `run_sentinel_fix` becomes a thin adapter onto the existing factory loop (`run_factory_from_issues`), wrapped with production-specific concerns the factory lacks: reproduce-first, safety rails, PR/auto-merge-to-staging, post-deploy verification, callback.

**Decisions locked (user, 2026-05-18):**
- Deploy autonomy: **auto-merge to staging** — verified fix → PR → auto-merge to staging branch → staging deploy. Human promotes staging→prod.
- Repro environment: **local checkout** — clone repo at the failing SHA, reproduce against the working tree.
- Target scope: **any registered repo** — `sentinel.services` config is the registry; unknown service name → rejected.

**Tech stack:** Python 3.11+, pydantic, pytest, FastAPI (intake), `gh` CLI (PRs). Reuses `run_factory`, `sentinel_safety.py`, `sentinel_prompts.py`, `sentinel_callback.py`.

---

## Stub inventory being eliminated

| Stub | Becomes real in |
|---|---|
| `core/engine.py` `run_sentinel_fix` (loads report, marks PASSED) | S18 |
| `intake_api.py` accept-and-queue (no executor) | S19, S20 |
| `sentinel_safety.py` primitives unwired | S17 |
| `sentinel_prompts.py` / `sentinel_callback.py` unwired | S16, S18 |
| `src/ncdev/adapters/` dead code | S24 (deleted) |

---

## Schema reference (existing, do not change)

`SentinelFailureReport`: `report_id, service: ServiceInfo, source, severity, error: ErrorDetail, frequency, context, triage: TriageInfo|None, detected_at`.
`ServiceInfo`: `name, version, git_sha, git_repo, environment, default_branch`.
`ErrorDetail`: `error_type, error_code, message, stack_trace, file, line, function, component`.
`SentinelFixResult`: `report_id, run_id, outcome: FixOutcome, outcome_detail, pr_url, fix_branch, commit_sha, files_changed, reproduction_test, agent_reasoning, fix_description, attempts_used, max_attempts, duration_seconds, started_at, completed_at`.
`FixOutcome`: `FIXED | CANNOT_REPRODUCE | FIX_FAILED | VALIDATION_FAILED | CHECKOUT_FAILED | BLOCKED`.

---

## Slice sequence (sequential S14→S23; S24 anytime)

### S14 — Extend SentinelServiceConfig + service registry
**Files:** `src/ncdev/core/config.py`, `tests/unit/test_core_config.py`
- Add to `SentinelServiceConfig`: `staging_branch: str = "staging"`, `deploy_command: str = ""`, `staging_url: str = ""`, `protected_files: list[str] = []`, `repo_clone_url: str = ""`.
- New `resolve_service(report, config) -> SentinelServiceConfig` — looks up `report.service.name` in `config.sentinel.services`; raises `UnknownServiceError` if absent.
- New `validate_service_for_deploy(svc) -> list[str]` — returns missing-field violations (`deploy_command`/`staging_url` empty) so S21/S23 fail loud, not silent.
- **Acceptance:** registered service resolves; unknown raises; deploy-validation lists missing fields.

### S15 — sentinel_charter: report → synthetic charter
**Files:** `src/ncdev/sentinel_charter.py` (new), `tests/unit/test_sentinel_charter.py`
- `synthesize_charter_from_report(report, service_cfg) -> CharterBundle` — one `FeatureStep` (`fix-<report_id-slug>`), brownfield contract from `service_cfg.repo_path`, verification contract from `service_cfg.test_commands`. Feature description embeds the error detail. `must_mention_feature_id=False`.
- **Acceptance:** report → bundle with exactly one feature; contract is brownfield; required_test slot reserved for the reproduction test.

### S16 — Reproduction-first gate
**Files:** `src/ncdev/sentinel_reproduce.py` (new), `tests/unit/test_sentinel_reproduce.py`
- `reproduce_failure(report, repo_dir, *, config) -> ReproductionResult` — runs a Claude session with `build_reproduction_prompt` to author a failing test that captures the production error; runs it; confirms it fails *for the reported reason*.
- `ReproductionResult`: `reproduced: bool, test_path: str, test_output: str, reason: str`.
- If not reproduced → caller halts with `FixOutcome.CANNOT_REPRODUCE`.
- **Acceptance:** mocked session that writes a failing test → `reproduced=True`; session that writes a passing/absent test → `reproduced=False`.

### S17 — SentinelSafetyGate
**Files:** `src/ncdev/core/sentinel_safety.py` (extend), `tests/unit/test_sentinel_safety.py`
- New `SentinelSafetyGate` composing the four existing primitives. Methods: `preflight(report) -> (ok, reason)` (circuit breaker tripped? cooling down? duplicate active?); `check_scope(files, lines, paths, protected_files) -> (ok, reason)`; `record_success(service)` / `record_failure(service)`.
- ScopeGuard's `_PROTECTED_PATTERNS` is augmented per-call with `service_cfg.protected_files`.
- **Acceptance:** tripped breaker blocks preflight; over-scope blocked; protected file blocked; dedup blocks a second concurrent run for the same key.

### S18 — run_sentinel_fix real orchestration
**Files:** `src/ncdev/core/engine.py`, `tests/unit/test_sentinel_fix.py` (new/extend)
- Replace the stub body. Flow: `resolve_service → safety preflight → git clone <repo_clone_url> @git_sha → reproduce_failure (S16) → synthesize_charter (S15) with the repro test as required_test → run_factory (existing) on the clone → verify (repro test passes + suite green + scope ok) → build SentinelFixResult → send_fix_result callback`.
- Each failure branch sets the right `FixOutcome` (CHECKOUT_FAILED, CANNOT_REPRODUCE, FIX_FAILED, VALIDATION_FAILED, BLOCKED).
- `dry_run` still short-circuits cleanly (preserve existing behaviour).
- **Acceptance:** mocked clone+reproduce+factory all-pass → outcome FIXED, callback sent; reproduce-fail → CANNOT_REPRODUCE, no factory run; safety-block → BLOCKED.

### S19 — HTTP intake background executor
**Files:** `src/ncdev/intake_api.py`, `tests/test_intake_api.py` (extend)
- A worker (thread pool, size = `max_concurrent_runs`) drains `queued` runs and calls `run_sentinel_fix`. Status moves `queued→running→complete/failed`. Result stored on the registry entry.
- `POST /api/v1/reports` still returns 202 immediately; the run executes in the background.
- **Acceptance:** POST a report → poll `/runs/{id}` → observe `running` then `complete`; `max_concurrent_runs` respected.

### S20 — Intake status/result endpoints reflect reality
**Files:** `src/ncdev/intake_api.py`, `tests/test_intake_api.py`
- `GET /runs/{id}` returns live status; `GET /runs/{id}/result` returns the actual `SentinelFixResult` once `complete`.
- **Acceptance:** result endpoint returns the FixResult JSON after a completed run; 404 → 409-style "not complete" while running.

### S21 — PR + auto-merge to staging
**Files:** `src/ncdev/core/sentinel_deploy.py` (new), `tests/unit/test_sentinel_deploy.py`
- `open_and_merge_to_staging(repo_dir, svc, report, fix_branch) -> DeployResult` — push branch, `gh pr create` (label from `svc.pr_labels`), then `gh pr merge --merge` into `svc.staging_branch`, then run `svc.deploy_command`.
- Honors `validate_service_for_deploy` (S14) — missing `deploy_command` → loud failure, no silent skip.
- **Acceptance:** mocked `gh`/subprocess → PR opened, merged to staging, deploy_command invoked; missing config → explicit error.

### S22 — Rollback on failed staging verification
**Files:** `src/ncdev/core/sentinel_deploy.py` (extend), `tests/unit/test_sentinel_deploy.py`
- Record `pre_fix_staging_sha` before the merge. `revert_staging_merge(repo_dir, svc, pre_fix_staging_sha)` — `git revert`/reset the staging merge and redeploy.
- **Acceptance:** revert restores the recorded SHA and re-runs deploy_command.

### S23 — Post-deploy live verification loop
**Files:** `src/ncdev/core/sentinel_deploy.py` (extend) + wired in `core/engine.py`, `tests/unit/test_sentinel_deploy.py`
- `verify_on_staging(repo_dir, svc, repro_test) -> bool` — re-run the reproduction test against `svc.staging_url`.
- Pass → `SentinelFixResult.outcome = FIXED`, callback. Fail → `revert_staging_merge` (S22) + `outcome = VALIDATION_FAILED`, callback.
- **Acceptance:** staging verify pass → FIXED; fail → revert called + VALIDATION_FAILED.

### S24 — Delete dead adapters/
**Files:** remove `src/ncdev/adapters/`
- Confirm nothing imports it (grep), delete the directory, remove any references in `capability_router`/`registry` docstrings.
- **Acceptance:** `pytest tests -q` green after deletion; no import errors.

---

## Verification per slice

Every slice: `pytest tests/unit/<slice-test>.py -v` green → `pytest tests -q` no regressions → `ruff check src tests` clean → one Conventional Commit → `git push origin main`.

## Self-review

- **Every stub mapped to a slice:** ✅ (table above).
- **No new stubs introduced:** each slice's failure branches set explicit `FixOutcome` values, no silent PASSED.
- **Production safety:** reproduce-first (S16) + safety gate (S17) + human gate before prod (staging stop) + rollback (S22).
- **Config gaps fail loud:** S14's `validate_service_for_deploy` + S21 honoring it — missing `deploy_command`/`staging_url` raises, never no-ops.
