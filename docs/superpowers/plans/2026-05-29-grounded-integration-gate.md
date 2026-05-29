# Grounded Integration Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Replace the end-of-run integration gate's brittle judgment (exact-path `required_files`, manifest-as-verdict) with a grounded product judge, keeping its executable checks (boot/routes/tests/lint/build) as evidence. Returns the existing `IntegrationResult` so the engine is unchanged.

**Architecture:** New `grounded_integration_gate()` in `src/ncdev/pipeline/grounded_verify/integration.py`. Reuses `EvidenceBundle`/`EvidenceItem`/`Verdict`/`parse_verdict` and a shared judge core extracted from `judge.py`. Executable helpers imported from the existing `integration_gate.py`.

**Tech Stack:** Python 3.13, pydantic v2, pytest. Mirrors the `grounded_verify` per-feature module already in the repo — implementers should read that module for the exact patterns (read-only `VERIFIER_TOOLS`, fenced-JSON+retry+fail-safe, monkeypatchable bare-name imports, injected `session_runner`).

**Spec:** `docs/superpowers/specs/2026-05-29-grounded-integration-gate-design.md`

---

## Task 1: Extract shared judge core

**Files:** Modify `src/ncdev/pipeline/grounded_verify/judge.py`; Test `tests/test_grounded_verify/test_judge.py`

Refactor so the session+parse+retry+fail-safe loop is reusable by both the feature judge and the integration judge.

- [ ] **Step 1: Write the failing test** — add to `test_judge.py`:
```python
def test_run_judge_core_parses_and_fails_safe(tmp_path):
    from ncdev.pipeline.grounded_verify.judge import _run_judge
    ok_runner = lambda *a, **k: FakeSession('```json\n{"verdict":"PASS"}\n```')
    assert _run_judge("any prompt", target_path=tmp_path, session_runner=ok_runner).verdict == "PASS"
    bad_runner = lambda *a, **k: FakeSession("no json")
    v = _run_judge("p", target_path=tmp_path, session_runner=bad_runner)
    assert v.verdict == "FAIL" and v.confidence == 0.0
```
- [ ] **Step 2: Run, expect FAIL** (`_run_judge` undefined): `python -m pytest tests/test_grounded_verify/test_judge.py::test_run_judge_core_parses_and_fails_safe -v`
- [ ] **Step 3: Implement** — extract the body of `judge()` (the `for attempt in range(2)` loop incl. `VERIFIER_TOOLS`/`permission_mode="default"`/retry-nudge/conservative FAIL) into:
```python
def _run_judge(prompt: str, *, target_path, session_runner=run_claude_session, timeout: int = 900) -> Verdict:
    for attempt in range(2):
        result = session_runner(prompt, cwd=target_path, tools=VERIFIER_TOOLS,
                                model="opus", timeout=timeout, permission_mode="default")
        verdict = parse_verdict(getattr(result, "final_text", "") or "")
        if verdict is not None:
            return verdict
        prompt = prompt + "\n\nYour previous response had no valid JSON verdict block. Respond with EXACTLY ONE fenced ```json block matching the schema."
    return Verdict(verdict="FAIL", confidence=0.0,
                   reasons=["verifier could not parse a valid verdict after retry"],
                   repair_guidance=["re-run verification"])
```
Then make `judge(...)` call `return _run_judge(build_prompt(...), target_path=target_path, session_runner=session_runner, timeout=timeout)`. Keep `judge`'s public signature identical.
- [ ] **Step 4: Run** the whole judge test file: `python -m pytest tests/test_grounded_verify/test_judge.py -v` — all pass (existing 11 + new 1).
- [ ] **Step 5: Commit** — `refactor(grounded-verify): extract reusable _run_judge core`

## Task 2: Product-level prompt builder

**Files:** Create `src/ncdev/pipeline/grounded_verify/integration.py`; Test `tests/test_grounded_verify/test_integration_gate.py`

- [ ] **Step 1: Failing test** — assert `build_integration_prompt(intent, evidence, completed_feature_ids)` includes: the product intent, an explicit "judge INTENT not exact file paths" instruction, the evidence items (e.g. a route probe + a build line), and the fenced-JSON schema reminder.
```python
def test_integration_prompt_has_intent_evidence_and_rules():
    from ncdev.pipeline.grounded_verify.integration import build_integration_prompt
    from ncdev.pipeline.grounded_verify.models import EvidenceBundle, EvidenceItem
    ev = EvidenceBundle(items=[EvidenceItem(name="route:/health", exit_code=0, scope="route"),
                               EvidenceItem(name="build", command="docker compose build", exit_code=0, scope="build")],
                        changed_files=[])
    p = build_integration_prompt("Echo service: /health + /api/v1/echo", ev, ["f01","f02"])
    assert "intent" in p.lower() and ("not exact" in p.lower() or "alternate path" in p.lower())
    assert "route:/health" in p and "```json" in p
```
- [ ] **Step 2: Run, expect FAIL** (module/function missing).
- [ ] **Step 3: Implement** `build_integration_prompt(product_intent: str, evidence: EvidenceBundle, completed_feature_ids: list[str], *, prior_context: str = "") -> str`. Product-level rules: judge whole-product intent satisfaction not exact paths; a required file satisfied at a reasonable alternate path counts; a route returning 2xx satisfies its contract regardless of layout; an executable failure (test suite / build / lint / required route that genuinely failed) is decisive toward FAIL unless evidenced as harness/env noise; dependency-only findings never count; ground every reason in evidence or a tool call. End with the same fenced-JSON `Verdict` schema block as `judge.py`'s `_RULES`.
- [ ] **Step 4: Run** the new test — pass.
- [ ] **Step 5: Commit** — `feat(grounded-verify): product-level integration prompt`

## Task 3: grounded_integration_gate (floor + evidence + judge + mapping)

**Files:** Modify `src/ncdev/pipeline/grounded_verify/integration.py`; Test `tests/test_grounded_verify/test_integration_gate.py`

Reuse executable helpers by importing from `ncdev.pipeline.integration_gate` (`_run_shell`, `_probe`, `_wait_for_health`, `_resolve_url`, `_derive_base_url`, `_tail`) and the `IntegrationResult` dataclass.

- [ ] **Step 1: Failing tests** (stub `session_runner`; monkeypatch the executable helpers so no real shell/HTTP runs):
  - `test_hard_floor_app_wont_start_fails_without_judge`: `start_command` set, monkeypatch `_run_shell` to return `(False, "boom")`; assert `IntegrationResult.passed is False`, a failure mentioning "did not start", and the judge stub was NOT called.
  - `test_pass_verdict_maps_to_result`: monkeypatch helpers to succeed; stub judge core to a PASS `Verdict`; assert `result.passed is True`, `result.failures == []`.
  - `test_fail_verdict_surfaces_reasons`: stub judge to FAIL with reasons; assert `result.passed is False` and reasons in `result.failures`.
- [ ] **Step 2: Run, expect FAIL** (`grounded_integration_gate` undefined).
- [ ] **Step 3: Implement** `grounded_integration_gate(bundle, target_path, completed, *, probe_health=True, run_test_commands=True, session_runner=run_claude_session) -> IntegrationResult`:
  1. **Hard floor:** if `bundle.verification.start_command and run_test_commands`: run it; if not ok → return `IntegrationResult(passed=False, failures=[f"app did not start: {_tail(out)}"], app_started=False)`. Else `_wait_for_health(...)`, set `app_started=True`, `started_here=True`.
  2. **Evidence:** build `EvidenceItem`s for: each built feature's `required_routes` (`name=f"route:{route}"`, `exit_code=0 if _probe else 1`, `scope="route"`); backend/frontend/e2e/lint/build commands (`_run_shell`, `scope="test"/"lint"/"build"`); asset-manifest aggregate (advisory). Populate the `IntegrationResult` observability fields (`routes_probed`, `routes_failed`, `backend_tests_ok`, `build_ok`, …) from these as you go. `git`-list files into `changed_files` or a repo-files evidence item. Teardown via `stop_command` if `started_here` (non-failing).
  3. **Judge:** `verdict = _run_judge(build_integration_prompt(product_intent, evidence, built_ids), target_path=target_path, session_runner=session_runner)` where `product_intent` = `bundle` overview/charter summary (use `bundle.contract`/PRD text available on the bundle; fall back to joining feature titles).
  4. **Map:** `result.passed = verdict.verdict == "PASS"`; if not, `result.failures = list(verdict.reasons)`. Keep the populated observability fields. `result.duration_seconds` set. Return.
- [ ] **Step 4: Run** test file — all pass.
- [ ] **Step 5: Commit** — `feat(grounded-verify): grounded_integration_gate (floor + evidence + product judge)`

## Task 4: Scenario regression (the recorded smoke-build failure)

**Files:** Test `tests/test_grounded_verify/test_integration_gate.py` (add an llm-marked test)

- [ ] **Step 1: Add** `@pytest.mark.llm` test reproducing the smoke failure: build a `target_path` where `required_files` lists `tests/test_echo.py` but the file exists at `backend/tests/test_echo.py`, the echo/health routes (stub the probes to 2xx) and test suite (stub to pass) succeed. Call the real `grounded_integration_gate` (real `session_runner`). Assert `result.passed is True` (intent met at an alternate path) — the case the old gate failed. Keep helpers real or lightly stubbed so only the judge is exercised live.
- [ ] **Step 2: Run deterministic** subset green: `python -m pytest tests/test_grounded_verify/ -q -m "not llm"`.
- [ ] **Step 3: (manual)** run `-m llm` once to confirm the ruling; if wrong, tune the product prompt rules and re-run.
- [ ] **Step 4: Commit** — `test(grounded-verify): integration-gate scenario for required_files-at-alternate-path`

## Task 5: Wire into the engine; retire brittle clauses

**Files:** Modify `src/ncdev/pipeline/engine.py` (~:569); Modify/trim `src/ncdev/pipeline/integration_gate.py`; full suite

- [ ] **Step 1:** In `engine.py`, change the import + call at ~:569 from `run_integration_gate(...)` to `grounded_integration_gate(...)` (same kwargs `probe_health`, `run_test_commands`; same `IntegrationResult` consumed at `.passed`/`.failures`). Add `session_runner` default.
- [ ] **Step 2:** In `integration_gate.py`, delete Clause 1 (manifest-as-verdict) and Clause 2 (`required_files` exact-path) from the old `run_integration_gate`. If `run_integration_gate` is no longer referenced anywhere (`grep -rn run_integration_gate src/ncdev tests`), remove it but KEEP the executable helpers (`_run_shell`, `_probe`, `_wait_for_health`, `_resolve_url`, `_derive_base_url`, `_tail`) and the `IntegrationResult` dataclass (now imported by the new module). Fix imports accordingly.
- [ ] **Step 3:** Update/trim any test that asserted the old `required_files`/manifest gate behavior (those test deleted behavior); keep tests of the executable helpers and the engine wiring. Run `python -m pytest -q -m "not llm"` — green. Report counts; if a non-gate test fails for a real reason, STOP and report.
- [ ] **Step 4: Commit** — `feat(grounded-verify): wire grounded integration gate into engine; retire exact-path clauses`

## Self-Review
- Spec coverage: §4.1 floor → T3; §4.2 evidence → T3; §4.3 judge → T2+T3 (+ shared core T1); §4.4 mapping → T3; §5 refactor/reuse → T1; §6 integration → T5; §7 testing → T3/T4/T5; §8 criteria → T4 (alt-path PASS), T3 (broken→FAIL), T5 (engine + suite). Covered.
- Types: `_run_judge`/`build_integration_prompt`/`grounded_integration_gate` signatures consistent across tasks; returns `IntegrationResult` (engine's existing consumer) and `Verdict` (reused). No new undefined types.
- No placeholders: code shown for the load-bearing steps; T3 evidence assembly described field-by-field against the real `IntegrationResult` dataclass.
