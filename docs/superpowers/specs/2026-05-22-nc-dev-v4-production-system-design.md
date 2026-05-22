# NC Dev System v4 — Production-Grade Autonomous Build System

**Date:** 2026-05-22
**Branch:** `nc-dev/v4-production-hardening`
**Baseline:** 805 tests passing, 0 failing
**Author:** Claude (Opus 4.7), acting as system owner under full delegation

---

## 1. Thesis

NC Dev's architecture is correct and matches what every serious 2026 autonomous-coding
system (Devin, Factory, OpenHands, Kiro) converged on: a thin orchestrator, one coherent
session per feature, sequential verified commits, a charter as the control plane, RAG
grounding, and an honest-failure tag. **We do not rewrite it.**

The gap is the *unsolved 80%* of the field: generation is nearly solved; **proof of
correctness is not**. NC Dev today treats "tests pass" as "done." The industry's hard-won
lesson — Replit's confession being the bluntest — is that **agents game green tests by
stubbing, mocking, and bypassing the very integrations they were told to build.**

v4's organizing principle: **the verification is the product.** The system's real job is
to *manufacture the proof of correctness that the PRD does not hand it.*

## 2. Known defects fixed by v4 (the foundation)

From a full codebase audit. Each is fixed under TDD in Phase 1.

| # | Defect | File | Impact | Status |
|---|--------|------|--------|--------|
| 1 | Phase 4 ingestion reads dead artifact names (`design-brief.json`, `build-plan.json`) | `pipeline/context_ingestion.py:37-51` | **Cross-feature RAG grounding is silently dead** — feature N+1 never sees feature N | ✅ fixed |
| 2 | Two parallel AI-invocation stacks (`ai_session.py` vs `ai_provider.py`) | both | Divergent subprocess shapes, timeouts, result schemas | → Phase 2 (the legacy quality gate that `ai_provider` serves is removed when the Gauntlet replaces it; unifying now means unifying against deleted code) |
| 3 | `openrouter` mode validates as legal but raises `NotImplementedError` mid-run | `ai_session.py:161` | Uncaught crash on a config the schema accepts | ✅ fixed |
| 4 | `lru_cache(maxsize=1)` on gate config is process-global, cwd-bound | `core/capability_policy.py:76` | Wrong thresholds in `ncdev serve`; leaks across tests | ✅ fixed |
| 5 | Nested `asyncio.run()` in factory | `factory.py:191,220` | Latent `RuntimeError` if ever inside an event loop | ✅ fixed |
| 6 | Git-identity failure produces silent `[BROKEN]`, dirty tree poisons next cycle | `claude_executor.py:905-937` | False "Claude made changes" on next cycle | ✅ fixed |
| 7 | Capability router wired to 1 of 8 capabilities | `core/capability_router.py` | Capability-matrix routing is aspirational, not live | → Phase 4 (router wiring is Phase 4's job; the gauntlet's oracle layer is its real consumer) |
| 8 | `design_seed.py` output never schema-validated, no tests | `pipeline/design_seed.py` | Malformed design tokens propagate silently | ✅ fixed |
| 9 | Dead `FactoryStopReason.NOT_YET_IMPLEMENTED` enum | `factory.py:60` | Confusing dead sentinel | ✅ fixed |
| 10 | Charter passes semantic garbage (null feature IDs, null acceptance) | `pipeline/charter.py:413-466` | Bad data drives the whole run | ✅ fixed |

Also: dead code (`artifacts/state.py` v2 schemas, unused `RoutingConfig` task keys,
duplicated `_kill_process_tree`), and zero test coverage on real `claude`/`codex`
stream-json parsing.

## 3. The six pillars

### Pillar A — Fix the foundation
Resolve all 10 defects above + delete dead code. TDD each. The Phase 4 grounding bug is
the highest priority single fix in the whole program.

### Pillar B — The Verification Gauntlet *(the core new subsystem)*
Replace "tests pass = done" with a layered, mandatory ladder, run per feature and
aggregated per product. Each layer is independent, has one job, and emits a structured
`GauntletLayerResult`.

| Layer | Checks | Blocks commit on |
|-------|--------|------------------|
| L0 Typecheck/compile | tsc / mypy / build | any error |
| L1 Lint & static | eslint / ruff / project linters | error-level only |
| L2 Unit tests | project unit suite | any failure |
| L3 Integration tests | cross-module suite | any failure |
| L4 E2E | Playwright against running app | any failure |
| L5 **Visual verification** | screenshots + AI-vision review vs acceptance criteria | broken layout / error banners — **mandatory for any UI feature** |
| L6 **Security** | multi-tool SAST + dependency-existence/provenance scan | confirmed vuln; non-existent or unsigned dependency (slopsquatting) |
| L7 **Anti-bypass** | scan diff + run for stubbed/mocked/bypassed integrations the feature was told to build real | integration replaced by stub/mock/`pass` |
| L8 **Oracle review** | a *different top-tier model* than the builder scores the diff against each explicit acceptance criterion | any criterion scored "not met" |

Design rules:
- Layers are data-driven from the project's `verification-contract.json` (which layers
  apply, thresholds). A backend-only feature skips L5.
- L8 is anchored to **explicit acceptance criteria**, never "is this good?" — the
  research shows un-anchored LLM-judges rubber-stamp.
- L8 uses a **decorrelated** model: Claude-built → GPT-5.5 reviews; Codex-built → Opus
  reviews. This is about catching blind spots, not cost.
- The gauntlet is its own module (`pipeline/gauntlet/`), independently testable, with a
  thin façade `run_gauntlet(feature, contract, repo) -> GauntletReport`.

### Pillar C — Spec integrity
- Charter phase emits an explicit `assumptions[]` list — ambiguities it resolved by
  choice — instead of silently guessing. Surfaced in the run report.
- Charter / verification-contract / feature-queue are **re-read verbatim every session,
  never compacted.** Cognition proved model-generated summaries drop load-bearing facts.
- Add full semantic validation to `validate_charter_completeness()`: non-empty feature
  IDs, non-null acceptance bags, valid route patterns, sane priorities.

### Pillar D — Model policy (revised after owner review)
- **Every code-touching or judgment step uses the top tier:** Opus 4.7 (Claude side),
  GPT-5.5 / GPT-5.x-Codex (OpenAI side). No routing-down on work that matters — a
  weaker model fails expensively and late, in rework loops that cost more than the
  token delta.
- A smaller model (Haiku 4.5) is permitted **only** for genuinely mechanical, non-code
  classification, and only as an opt-in knob defaulting to top-tier. It buys latency,
  not correctness.
- Cost is controlled by **short feature scopes, prompt caching of stable prefixes, and
  lean context** — never by downgrading the model.
- Wire `capability_router.resolve_capability()` for all 8 capabilities so routing is
  real, not aspirational. Update the model matrix to May-2026 IDs.
- The `mode:` switch remains as an owner-controlled budget lever; shipped default is
  top-tier everywhere.

### Pillar E — Cost & context governance
- Hard per-feature cost ceiling, enforced (already partially present).
- Per-session compaction step for long feature builds — but compaction *never* touches
  the charter triad (see Pillar C).
- Context-as-cost-center discipline: retrieve via Citex, don't re-stuff the repo.

### Pillar F — Observability / eval-driven development
- The capability ledger becomes a living eval suite — every gauntlet layer result is
  recorded; regressions are visible across runs.
- Structured per-run report: features built, gauntlet results per layer, assumptions,
  cost, `[BROKEN]` items.

## 3a. Progress log

- **Phase 0** ✅ — research, design doc, baseline (805 tests).
- **Phase 1** ✅ — 8/10 defects fixed; #2 reclassified, #7 → Phase 4.
- **Phase 2** ✅ — Verification Gauntlet L0-L8 built, tested, and wired
  into the feature executor (executor layer subset; full ladder
  reserved for the integration gate). Defect #2 reclassified:
  `ai_session` (agentic build sessions) and `ai_provider` (plain
  completions) serve genuinely different needs — `run_codex_session`
  even rewrites prompts with build instructions, so routing a
  summarisation through it would be incorrect. The only real residue
  is the opt-in `--legacy-quality-gate` CLI path; removing it is
  non-blocking cleanup, not a correctness fix.
- **Phase 3** ✅ — charter `assumptions` surface: the charter records
  every PRD ambiguity it resolved by judgment, surfaced in a panel
  right after charter generation so a wrong call is caught before the
  build compounds it. The no-compaction guarantee (Pillar C) is
  satisfied by architecture, not code: NC Dev spawns a fresh session
  per feature with the charter re-included verbatim in each prompt, so
  the charter is never subject to long-horizon multi-feature
  compaction — the failure mode Cognition documented.

- **Phase 4** ✅ — availability-aware failover. `run_ai_session` now
  checks the orchestrator CLI is on PATH; if not, and the other CLI
  is, it fails over (Claude↔Codex) rather than failing the feature —
  directly serving the standing instruction that work continues on
  Codex during a Claude outage. Honest no-ops found and recorded: the
  model matrix already uses aliases that auto-track frontier versions
  (guarded by `test_no_model_literals`), so there is nothing to bump;
  prompt caching is handled inside the `claude` CLI, not by NC Dev.
  Defect #7: with top-tier-everywhere the capability matrix's
  per-capability cost-routing is moot, and its one real value
  (failover) is now delivered directly in `run_ai_session`; the
  matrix is retained for future config-driven multi-provider setups.

- **Phase 5** ✅ — structured run report. `pipeline/run_report.py`
  consolidates the scattered run evidence (per-step results, per-step
  `gauntlet.json`, charter assumptions, integration result) into one
  `report.json` + `report.md` written at end of run: per-feature table
  with gauntlet verdicts, charter assumptions, gauntlet blocking
  breakdown, and a "needs attention" list. The per-feature cost
  ceiling (`max_budget_usd`) and per-session compaction were found
  already handled — the ceiling is wired through `run_ai_session`, and
  compaction is the `claude` CLI's job within NC Dev's short
  per-feature sessions. The capability ledger continues to record
  cycles; the run report is the per-run companion.

## 4. Phased roadmap

Each phase: TDD, verified commits, own branch, merged only when the gauntlet (once it
exists) or the existing 805+ suite is green.

0. **Baseline** — branch, this design doc, real test numbers. *(done)*
1. **Foundation fixes** — the 10 defects + dead-code removal.
2. **The Verification Gauntlet** — `pipeline/gauntlet/`, L0–L8, wired into the executor
   and integration gate.
3. **Spec integrity** — charter assumptions, no-compaction guarantee, semantic validation.
4. **Model policy** — capability router wired for all 8, May-2026 model matrix, caching.
5. **Cost & context governance + observability** — compaction, ledger-as-eval, run report.
6. **End-to-end proof** — a real factory run on a representative PRD; the system proves
   itself.

## 5. Out of scope (YAGNI)
- No rewrite. No new orchestration framework.
- No multi-agent fan-out of *feature builds* — coherence is the thing that would be lost;
  the field agrees sequential verified commits is correct.
- No self-hosted/open-weight mode in v4 (noted as a future option).

## 6. Success criteria
- All 10 defects fixed; cross-feature grounding demonstrably live.
- Gauntlet L0–L8 implemented, tested, and blocking commits on real failures.
- A factory run on a real PRD produces code that passes the full gauntlet, with a
  structured report — and the anti-bypass layer demonstrably catches a planted stub.
- Test suite grows from 805 with no regressions.
