# Grounded Integration Gate — Design Spec

**Date:** 2026-05-29
**Status:** Design — approved approach (full grounded gate), proceeding to plan
**Repo:** `nc-dev-system`
**Builds on:** `2026-05-29-grounded-agentic-verifier-design.md` (reuses its `grounded_verify` machinery)

---

## 1. Why

The grounded per-feature verifier shipped and measured 3/3 first-pass — but the end-to-end smoke build still ended `integration_failed` on the **separate** end-of-run integration gate: `required file missing: tests/test_echo.py`. The tests existed (at `backend/tests/...`); the gate's **Clause 2 exact-path `required_files` `.exists()`** check is the same brittle-deterministic-judgment class the per-feature verifier already eliminated. This slice applies the identical pattern to the integration gate.

## 2. Principle (unchanged)

> Agents own decisions; deterministic tools own observation; an agent may never claim an outcome it didn't get from a tool.

Keep the integration gate's **executable** checks (they are real product-level ground truth); replace its **brittle judgment** clauses with the grounded judge.

## 3. Clause classification (from the current `integration_gate.py`)

| Clause | Nature | Disposition |
|---|---|---|
| 0 — app `start_command` + health wait | executable | **Hard floor + evidence** (can't judge a product that won't boot) |
| 1 — asset-manifest aggregate coverage | brittle judgment | → evidence (advisory), judge decides |
| **2 — `required_files` exact-path `.exists()`** | **brittle judgment** | → **replaced by judge** (intent, not path) |
| 3 — `required_routes` HTTP probes | executable | evidence (per-route 2xx/3xx fact) |
| 4/5/6 — backend/frontend/e2e test suites | executable | evidence (exit + tail) |
| 7 — lint | executable | evidence |
| 8 — build | executable | evidence |
| teardown — `stop_command` | side-effect | run as today (non-failing) |

## 4. Architecture — `grounded_integration_gate(...)`

New function (in `src/ncdev/pipeline/grounded_verify/integration.py`) that **returns the existing `IntegrationResult`** so the engine call site is unchanged.

1. **Hard floor:** if `start_command` is set, run it + wait for health; if the app does not come up → `IntegrationResult(passed=False, failures=["app did not start: <tail>"])` without calling the judge (can't probe a dead product). If no `start_command`, skip the floor.
2. **Evidence gathering (executes, no verdict):** probe every built feature's `required_routes` (record per-route reachability), run backend/frontend/e2e/lint/build commands (exit + tail), run asset-manifest aggregate (advisory), and `git`-list the repo's actual files. Assemble a product-level `EvidenceBundle` (reuse the model). Run teardown (`stop_command`) if we started the app.
3. **Product judge (Opus, read-only tools):** a product-level prompt — "does the whole product satisfy the PRD/charter intent, given this evidence and the repo? Judge INTENT, not exact file paths: a required file satisfied at a reasonable alternate path counts; a route that returns 2xx satisfies its contract regardless of layout. Executable failures (a test suite, build, lint, or required route that genuinely failed) are decisive toward FAIL unless you can evidence them as harness/env noise. Dependency-only findings never count." Returns the same `Verdict` model.
4. **Map `Verdict` → `IntegrationResult`:** `passed = verdict == "PASS"`; `failures = verdict.reasons` when FAIL; populate the executable observability fields (`backend_tests_ok`, `routes_failed`, `build_ok`, …) from the gathered evidence so the run report stays informative.

## 5. Reuse / refactor

- Reuse `EvidenceBundle`, `EvidenceItem`, `Verdict`, `parse_verdict` from `grounded_verify`.
- Extract the session+parse+retry+fail-safe core of `judge()` into a shared helper `_run_judge(prompt, *, target_path, session_runner) -> Verdict` in `judge.py`; the feature `judge()` and the new integration gate both call it with their own prompt builders (`build_prompt` / `build_integration_prompt`). This keeps the read-only-tools + fenced-JSON + one-retry + conservative-FAIL behavior identical and in one place.
- Reuse the executable helpers already in `integration_gate.py` (`_run_shell`, `_probe`, `_wait_for_health`, `_resolve_url`, `_derive_base_url`, `_tail`) — import them rather than reimplement.

## 6. Integration

`engine.py:569` calls `run_integration_gate(...)` and reads `.passed`/`.failures`. Swap that single call to `grounded_integration_gate(...)` (same return type, same kwargs `probe_health`, `run_test_commands`). Delete the brittle clauses (1 manifest-as-verdict, 2 required_files) from the old function; keep the old `run_integration_gate` only if still referenced, else remove. The new function lives in the `grounded_verify` package; the executable helpers may stay in `integration_gate.py` and be imported, or move alongside — implementer's call, but no duplication.

## 7. Testing

- **Deterministic unit tests:** hard floor (app-won't-start → FAIL without judge); evidence gathering populates route/test/build facts; `IntegrationResult` field mapping from a stubbed `Verdict`; the invariant that the judge is not called when the hard floor fails. Stub `session_runner`.
- **Replay/scenario (llm-marked, run explicitly):** the exact smoke-build failure — `required_files` lists `tests/test_echo.py` but the file exists at `backend/tests/test_echo.py` and routes/tests pass → assert the grounded gate returns `passed=True` (intent met at an alternate path), where the old gate returned False.
- Full suite stays green (`-m "not llm"`).

## 8. Success criteria

1. The recorded smoke-build scenario (`required file missing: tests/test_echo.py` while the product actually works) now PASSES the integration gate.
2. A genuinely broken product (a real failing test suite or a route that 500s) still FAILS.
3. Engine integration unchanged (same `IntegrationResult` contract); full suite green.
4. The exact-path `required_files` + manifest-as-verdict clauses are gone; executable checks survive as evidence.

### Measured results (2026-05-29)

**Built, reviewed, merged (`f65cd94`), pushed.** Reused the verifier machinery; extracted `_run_judge` shared core. Full suite green (900+), 32 deterministic gate tests + 1 live scenario.

- **Live scenario (real judge):** a *complete* echo service whose test file is at `backend/tests/test_echo.py` while the contract lists `tests/test_echo.py` → **PASS** (intent satisfied at an alternate path) — the exact case the old gate false-failed. A *thin/absent* product → correctly **FAIL** ("feature is genuinely absent, not relocated", using the new `git ls-files` evidence).
- **End-to-end smoke build:** 3/3 features passed; the old `required file missing: tests/test_echo.py` false-fail is **gone**. The gate now ends red only on a *genuine* "app did not start" (the hard floor correctly caught a real port collision — port 23301 held by another live project's container), which is correct conservative behavior, not a false-fail. A fully-green run only needs a free port.
- Code review (CHANGES-REQUESTED → fixed): the integration `EvidenceBundle` now carries the repo file inventory (`git ls-files`) and route status detail, so the judge can ground "alternate path" and "404 vs unreachable" rulings.

## 9. Out of scope

Planner/builder/repair agents (future slices). This slice is the integration gate only.
