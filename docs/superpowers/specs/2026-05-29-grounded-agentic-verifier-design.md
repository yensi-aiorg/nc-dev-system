# Grounded Agentic Verifier — Design Spec

**Date:** 2026-05-29
**Status:** Design — awaiting user review before implementation plan
**Repo:** `nc-dev-system`
**Related:** `docs-only/planning/2026-05-29-nc-dev-teardown/00-TEARDOWN-AND-VERDICT.md`

---

## 1. Why

Measured over the May 27–28 runs (target `aigizmo-ledger`), NC Dev's verify stage produced **2 passes / 43 runs (~5%)** at **$18–25 per failed run**, with `first_pass_success_rate = 0.0` across the capability ledger. Root-cause investigation (systematic, evidence-based) found the failures were **not** model or code-quality failures — they were **rigid, mis-scoped verification checks false-failing correct work**:

- **L6-security scanned `backend/.venv`** — flagged weak-hash "High" findings inside *pymongo / websockets* (245,218 lines of vendored deps scanned). The feature's own code was clean.
- **Test-command CWD bug** — `required test … failed: /usr/bin/cd: line 4: cd: backend: No such file or directory`. The tests never ran; the shell `cd` path was wrong. Pure false-fail.
- **`required_files` exact-path matching** — "required file missing: backend/app/api/conflicts.py" fails when the implementer placed the file at a reasonable but different path.
- **Real failures mixed in** — `KeyError: 'items'`, `assert status_code == 201` — some features genuinely incomplete.

Across 25 recorded gauntlet runs: **L6-security failed 14×, L8-oracle (the existing AI judge) failed 17×, and a mechanical layer blocked the feature even though the AI oracle had PASSED it 6 times.** The mechanical gates were vetoing correct work.

**Decision (user, 2026-05-29):** make verification AI-judge-primary with deterministic checks as *grounding evidence*, not hard vetoes — "each step is an agent that thinks, grounded in real tool output." Built as a thin agentic layer over the native CLIs, retiring brittle Python. This spec covers the **first slice: the verifier.** Planner/builder/repair/integration agents are out of scope for this spec.

## 2. Principle

> **Agents own every decision. Deterministic tools own every observation. An agent may never claim an outcome it did not get from a tool.**

The brittleness came from hardcoded *judgment* (exact paths, dep-polluted scans, shell-fragile test invocation). The fix removes hardcoded judgment while *keeping* deterministic *execution* as the agent's grounding. Tests still run for real; the agent decides whether a result matters.

## 3. Scope

**In scope:** a standalone `grounded_verify(...)` module that fully replaces `run_gauntlet` (EXECUTOR_LAYERS) and `_post_session_verification` in `pipeline/claude_executor.py`.

**Out of scope (later specs):** agentifying the planner/charter, builder, repair, and integration stages; the broader "thin orchestrator" replacement of nc-dev. This module is built import-only and orchestrator-agnostic so those later steps can reuse it.

## 4. Architecture — three phases per verify call

### Phase 1 — Hard floor (Python, pre-LLM, zero token cost)
The only non-negotiable, agent-cannot-override gates. Evaluated before the agent is invoked:
- **No work produced** — `post_commit == pre_commit` and working tree clean → `FAIL("no work produced")`.
- **Won't compile / import** — the declared build/typecheck command (or language default: `python -c "import"` smoke / `tsc --noEmit` / build) exits non-zero → `FAIL("does not compile")`.

Rationale: judgment over an empty or non-loadable tree is meaningless. Everything else is judged. Note deliberately: **tests passing is NOT a hard floor** — the `cd:backend` false-fail proves test-command failures must be judged (real bug vs. harness/env noise), not auto-failed.

### Phase 2 — Evidence gathering (Python harness, executes, emits facts, NO verdict)
Runs and captures — makes no pass/fail decision:
- declared backend/frontend test commands → `{exit_code, output_tail}` (scoped to feature tests where the contract specifies them)
- health probe (only if `feature.acceptance.verify_app_boots`)
- lint / static checks (advisory)
- **security scan scoped to the diff only** — bandit/semgrep run against changed files, never `.venv` / `node_modules` / build artifacts
- declared screenshots (if any) captured to disk as evidence; visual review folds into the agent's judgment (Opus is multimodal) rather than a separate L5 pass/fail layer
- the diff text and the list of changed files

Output: `EvidenceBundle = [EvidenceItem{name, command, exit_code, output_tail, scope}]`. This **guarantees** the basics were actually executed; the agent cannot skip them.

### Phase 3 — Agent judgment (Opus 4.8, tools-in-loop)
Input: feature **intent** (description + acceptance as intent, not exact paths) + the `EvidenceBundle` + prior-cycle context (previous verdict + repair guidance, for the repair loop).
Tools: `bash` (run a specific test, inspect), `read`, `grep` — to dynamically investigate beyond the pre-gathered evidence.
Output (StructuredOutput schema):
```
{ verdict: "PASS" | "FAIL",
  confidence: 0.0–1.0,
  reasons: [str],
  repair_guidance: [str],     # populated on FAIL — feeds next repair cycle
  evidence_consulted: [str] } # which evidence items / commands it relied on
```

**Prompt rules (encode today's lessons):**
1. A genuinely failing test is **decisive toward FAIL** unless you can justify, *with evidence*, that it is harness/environmental noise (e.g. a shell `cd` error, an unstarted service, a pre-existing unrelated failure).
2. Judge **intent satisfaction**, not exact file paths/names. A file at a reasonable alternate path satisfies a required-file intent.
3. Findings inside dependencies (`.venv`, `node_modules`) are **never** the feature's fault.
4. You must ground every reason in an evidence item or a tool call you made. Do not assert an outcome you did not observe.

## 5. Output contract & integration

`grounded_verify(...)` returns a `VerificationResult` shaped to what `claude_executor` already consumes (verdict → `StepStatus`, `reasons` → `failure_reasons`, `repair_guidance` → next repair cycle), so the repair loop, the `fpsr` capability ledger, and status wiring are **unchanged**.

Integration: replace the `_post_session_verification(...)` call (~`claude_executor.py:531`) and the gauntlet block (~`:587–620`) with a single `grounded_verify(...)` call. Artifacts written to the step dir: `evidence-bundle.json`, `verdict.json` (replacing `gauntlet.json`).

## 6. Retire / keep

**Delete (the verdict logic):**
- `pipeline/gauntlet/` layer framework — `layers_static` (L0/L1/L6/L7), `layers_visual` (L5), `layers_oracle` (L8) runners and the gauntlet driver (~640 LOC).
- The 8-clause `_post_session_verification` acceptance logic in `claude_executor.py` (exact-path `required_files`, `must_mention_feature_id`, etc., ~200 LOC).

**Keep (the execution), refactored into the evidence-gatherer's tools:**
- run-shell-and-capture, **diff-scoped** bandit/SAST, health probe, diff/changed-files helpers.

Net: ~840 LOC of brittle judgment removed; deterministic execution preserved. Module has no nc-dev orchestration coupling.

## 7. Testing

**Replay harness (primary validation)** — fixtures built from real recorded runs in `.nc-dev/runs/`:
- f05 `.venv`-bandit evidence → assert verdict is **PASS** (dependency finding, not feature fault).
- f08 `cd: backend: No such file` test evidence → assert **not** false-failed on the shell error (judged as harness noise).
- Real `KeyError: 'items'` / `status_code != 201` evidence → assert **FAIL** (genuine).

**Deterministic unit tests (no LLM):**
- Hard floor: no commit → FAIL; won't compile → FAIL; agent **not** invoked when floor fails (invariant).
- Evidence-gatherer: bandit excludes `.venv`/`node_modules`; test command runs in the correct cwd; EvidenceBundle always contains the guaranteed items.

**Cost measurement:** record verify-stage cost per feature; compare repair-cycle count and total run cost against the $18–25 / 5%-pass baseline on a follow-up real run.

## 8. Success criteria

1. On the recorded false-fail fixtures (f05, f08), the verifier no longer fails correct work.
2. On the recorded genuine-failure fixtures, it still fails them.
3. A fresh real build shows materially higher first-pass rate and lower per-feature repair-cycle count than the baseline.
4. ~840 LOC of gauntlet + clause logic removed; the module is import-only and orchestrator-agnostic.

### Measured results (2026-05-29)

**Real-judge replay (3 recorded evidence patterns):** all correct — dep-noise (f05) → PASS, genuine `KeyError` (assertions ran) → FAIL, harness-noise `cd` error + real work on disk (f08) → PASS.

**End-to-end smoke build** (`echo-service`, run `run-20260529T093515Z-3fa56422`):
- **3/3 features PASSED first-pass** (f01-scaffold, f02-echo-endpoint, f03-containerization-docs), zero repair cycles — vs the baseline of **2/43 (~5%), fpsr=0.0**.
- Each verdict was genuinely grounded (0.97 confidence, citing real code lines).
- The build-advisory mechanism worked: at f01 `docker compose build` exited 1 (no compose file yet) and the verifier correctly treated it as **non-blocking advisory** and PASSED on intent; at f03 it cited `docker compose build exited 0` as positive evidence.
- A pre-fix run halted at f01 because the hard floor used `build_command` (`docker compose build`) as a compile gate — fixed: the hard floor now byte-compiles changed Python files, and `build_command` is advisory evidence (commit `78c995b`).

**Known follow-up:** the run ended `integration_failed` on the *separate* end-of-run integration gate (`required file missing: tests/test_echo.py` — exact-path matching). That gate is the same brittle-deterministic class this verifier replaced per-feature, and is the natural next slice to make agentic.

## 9. Resolved design decisions

These were open questions; resolved 2026-05-29.

- **Structured verdict output** — fenced-JSON + validate + one retry. The verifier prompt must end with a single ` ```json ` block matching a pydantic `Verdict` model; parse it from the existing stream-json result event (`claude_session.py`), validate against the model, and on failure retry **once** with the validation error fed back. `claude` exposes no `--output-schema` flag, so we do not depend on one; Opus 4.8 reliably emits one clean JSON block. The pydantic `Verdict` model is the single source of truth for the contract in §4 Phase 3.
- **Security scan scope** — bandit on **Python diffs only** for v1. Frontend/TS diffs are judged by the agent from the diff text (plus eslint security rules if the target project already defines them). No standalone JS/TS SAST (semgrep) until evidence shows a real JS vulnerability escaping. Keeps the deterministic surface minimal.
- **Visual review** — folded into the agent via the `Read` tool (Claude Code is multimodal; `Read` renders PNGs). The evidence-gatherer captures declared screenshots to disk; the agent reads them inline when the feature is UI-bearing and treats visual defects as a signal into the verdict, not a separate hard gate. A dedicated vision call is a **fallback only**, used if the replay tests show headless image-reading is unreliable.
- **Low-confidence PASS** — no branching in v1. `confidence` is recorded in the verdict (for observability and the capability ledger) but a PASS is a PASS. A re-check path is added later only if data shows low-confidence passes correlate with escaped defects.
