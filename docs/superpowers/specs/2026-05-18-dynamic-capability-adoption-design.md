# Dynamic Capability Adoption & Self-Improvement

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:writing-plans to turn this spec into an implementation plan, then superpowers:subagent-driven-development or superpowers:executing-plans to implement it.

**Goal:** Make NC Dev System a *dynamically improving* system instead of a fixed path. New Claude/Codex models, skills, slash commands (e.g. `/goal`, design skills), and CLI features should flow into builds with **zero code edits**, and the system should get measurably better at choosing and creating capabilities the more it runs.

**Architecture:** Two phases. **Phase 1 — Capability Adoption Layer** gives the existing `capability_router.py` *eyes*: a probe inspects what the installed toolchain exposes, and a policy resolves `auto` sentinels into concrete model / skill / flag choices at session start. **Phase 2 — Self-Learning Loop** gives the router *memory*: a cross-project ledger records what worked, feeds objective metrics and Steward narrative back into capability selection, and authors new skills from recurring patterns.

**Tech Stack:** Python 3.13+, Claude CLI, Codex CLI, Pydantic v2. Builds on existing `core/capability_router.py`, `core/availability.py`, `core/models.py` capability artifacts, `provider_dispatch.py`, and the Product Steward.

*This spec was peer-reviewed against the codebase by Codex (2026-05-19) and revised: model-discovery claims corrected to alias-based resolution, the existing `CapabilitySnapshotDoc` schema reused rather than reinvented, and several accuracy fixes applied (see §1, §3.1, §3.4).*

---

## 1. Current Problem

The system shells out to the `claude` and `codex` CLI binaries on `PATH`, so **runtime engine improvements land for free** when the CLIs are upgraded. But every point where a *capability* is named is **hardcoded or statically configured**:

| Where | What's frozen |
|-------|---------------|
| `claude_session.py:122` | `model: str = "claude-opus-4-6"` default literal |
| `ai_provider.py:330` | `ClaudeCLIProvider.build_argv()` — `model or "claude-opus-4-6"` fallback literal |
| `ai_session.py:182` | `effective_model = model or "claude-opus-4-6"` literal |
| `cli.py:316,384` | `full` / `factory` `--model` default `"claude-opus-4-6"` |
| `core/config.py:98` | `DEFAULT_CAPABILITY_CHAINS` — `CapabilityChoice` model literals (`gpt-5.5`, `opus`, `anthropic/claude-opus-4-6`) |
| `core/config.py:~246` | `NCDevConfig.providers` default `preferred_models` (`gpt-5.5`, `opus`, `anthropic/claude-opus-4-6`) |
| `ai_provider.py:289` / `ai_session.py:240` | Codex argv emits only `--model --sandbox --full-auto`; advanced options (reasoning, profiles) dropped |
| `claude_session.py` `DEFAULT_TOOLS` | Frozen tool allowlist constant |
| Skill steering | A **static, hardcoded** skill list in `claude_executor.py:184` — not derived from what's installed; no per-project selection |

Consequences:
- A new model (Opus 4.7, etc.) requires a code/config edit before it is used.
- `.nc-dev/config.yaml` sets `reasoning_effort: high` for Codex, but the Codex argv builders never pass it — **the field is dead code**.
- Skill steering exists but is *frozen*: `claude_executor.py` names `writing-plans`, `test-driven-development`, `verification-before-completion`, `systematic-debugging` in every feature prompt. That list is hand-written and never includes newer capabilities like `/goal` or design skills. The missing layer is **dynamic inventory + per-project selection**, not steering itself.
- `core/capability_router.py` routes `capability → (provider, model)` — its docstring promises *"riding the model curve becomes 'edit one config file'"* — but it resolves model strings out of static config. It has **no eyes**: it cannot see what the toolchain exposes. And while one entry point (`product_steward.py:367`) does call `resolve_capability(...)`, **most session entry points** (`claude_session.py`, `ai_session.py`, `claude_executor.py`, the `cli.py` `--model` defaults) bypass the router and use hardcoded literals.

The system is **engine-dynamic** (CLI upgrades land) but **capability-static** (every model, tool, skill, and flag is wired by hand).

## 2. New Architecture

```
SESSION START
    │
    ├─ capability_probe.py  ── inspects installed toolchain ──┐
    │     claude: version, supported flags, installed         │
    │            skills/plugins, accepted model aliases       │
    │     codex:  version, supported flags, profiles,         │
    │            config keys (e.g. model_reasoning_effort)    │
    │                                                         ▼
    │                                  CapabilitySnapshotDoc (EXISTING schema,
    │                                  core/models.py) → .nc-dev/capabilities.json
    │                                  (atomic / lock-protected write)
    │                                                         │
    ├─ capability_policy.py ── resolves `auto` ────────────────┤
    │     snapshot + capability key + policy                   │
    │     alias-first (opus/sonnet/configured codex model),    │
    │     version-keyed table as pinning fallback              │
    │     + ledger metrics gate (Phase 2)                      │
    │     explicit config pins always win                      │
    │                                                          ▼
    ├─ capability_router.py (EXISTING) ── resolve_capability("implementation")
    │                                          → Resolved(provider, model, chain_position)
    │                                                          │
    ├─ session_options.py ── adapter: Resolved + snapshot ──────┤
    │     → SessionOptions(model, tools, extra_args,            │
    │                      append_system_prompt_additions)      │
    │                                                          ▼
    ├─ claude_session.py / ai_provider.py / ai_session.py ── consume SessionOptions
    │                                                          │
    └─ skill selection ── select from probed inventory, steer ─┘
          (every charter path — greenfield/brownfield/bugfix;
           replaces the hardcoded skill list in claude_executor.py)

AFTER EACH FACTORY RUN  (Phase 2)
    │
    ├─ metrics writer   ── per (model, skill set, flags): pass rate,
    │                       cycles-to-done, cost, [BROKEN] rate
    ├─ Steward narrative ── structured lessons: what helped / hurt,
    │                       recurring hand-fix patterns → skill candidates
    │                                       │
    │                                       ▼
    │                       ~/.ncdev/capability-ledger.jsonl  (cross-project)
    │                                       │
    ├─ feeds back ──────────────────────────┤
    │     metrics GATE   → demote bad-track-record capabilities
    │     narrative BIAS → tune skill selection per project type
    │
    └─ skill authoring  ── pattern flagged ≥ N times → Claude session uses
                            superpowers:writing-skills to author + validate
                            a new skill (GATED: human review or Steward A/B)
```

---

## 3. Phase 1 — Capability Adoption Layer

**Outcome:** new models, skills, and CLI features flow into builds with zero code edits.

### 3.1 `capability_probe.py` (new — `src/ncdev/core/`)

The *eyes*. Runs once per run, results cached in-process and to disk.

- `probe_claude()`: CLI version; supported flags (parse `claude --help`); installed skills and plugins (scan `~/.claude/skills`, `~/.claude/plugins`, and the project's `.claude/skills`); the set of model **aliases** the CLI accepts (`opus`, `sonnet`, …).
- `probe_codex()`: CLI version; supported flags and profiles (parse `codex --help` and `~/.codex/config.toml`); recognised config keys (notably `model_reasoning_effort`).
- **Model discovery is alias-first, not enumeration.** Neither CLI exposes a machine-readable list of every available model — `--help` reveals *flags*, not a model inventory, and any enumeration would drift from per-account entitlements. So the probe records the **accepted aliases** (which `DEFAULT_CAPABILITY_CHAINS` already uses — e.g. `model="opus"`). A small **version-keyed known-models table**, kept in this module, is the *fallback* for pinning a specific model generation when an alias is too coarse.
- **Reuse the existing schema.** `core/models.py` already defines `CapabilityDescriptor`, `ProviderCapabilitySnapshot`, and `CapabilitySnapshotDoc` (`schema_id: capability-snapshot.1`). The probe **populates these existing models** — it does not introduce a parallel snapshot type. Extend `CapabilityDescriptor` only if a probed attribute has no field yet.
- Output: a `CapabilitySnapshotDoc`, persisted to `.nc-dev/capabilities.json` with a UTC timestamp. **The write is atomic and lock-protected** (temp-file + rename, advisory lock) — Sentinel intake runs concurrent fixes, so multiple sessions may probe and write at once.
- **Failure policy:** if a probe step fails (CLI missing, `--help` parse error, filesystem scan error, offline/auth failure), the probe degrades gracefully — it records the failure in the snapshot's `notes`, falls back to the last good `.nc-dev/capabilities.json` if present, and finally to config pins. A failed probe never aborts a run.

This extends, not replaces, `core/availability.py` — availability answers *"is the binary there?"*; the probe answers *"what does it expose?"*.

### 3.2 `capability_policy.py` (new — `src/ncdev/core/`)

Turns `auto` into a concrete choice. Given `(CapabilitySnapshotDoc, capability_key, policy)`, resolves the model, skill set, and flag set.

- **Resolution order:** explicit version pin in config → resolved alias from the snapshot → version-keyed table → hard-coded last-resort default.
- Default policy: **newest available alias** for the provider (e.g. `opus` for planning/review, the configured Codex model for implementation).
- `auto` sentinels in `config.yaml` and `DEFAULT_CAPABILITY_CHAINS` are resolved here.
- **Explicit version pins always win** — the escape hatch for reproducibility and incident response. An explicit `--model X` on the CLI is treated as a hard pin, never as `auto`.
- In Phase 2, this module also consults the ledger metrics gate (§4.2).

### 3.3 `session_options.py` adapter (new — `src/ncdev/core/`)

`capability_router.Resolved` today carries only `capability, provider, model, chain_position`. Rather than expand `Resolved` and ripple a contract change through every caller, a thin adapter converts `Resolved` + the snapshot into a single `SessionOptions` struct:

```
SessionOptions(model, tools, extra_args, append_system_prompt_additions)
```

Session entry points (`run_claude_session`, `run_ai_session`, `run_codex_session`, provider `build_argv`) consume `SessionOptions`. `Resolved` stays minimal; the blast radius of the change is one adapter, not the whole call graph.

### 3.4 De-hardcoding

| File | Change |
|------|--------|
| `claude_session.py:122` | Remove the `claude-opus-4-6` default literal; `model` comes from `SessionOptions` |
| `ai_provider.py:330` | Remove the `ClaudeCLIProvider.build_argv()` fallback literal |
| `ai_session.py:182` | Remove the `model or "claude-opus-4-6"` literal |
| `cli.py:316,384` | `full` / `factory` `--model` default becomes `auto`. The `fix` command has **no `--model` flag of its own** — it passes `model=None` through `core/engine.py` (Sentinel reproduce / factory fix), so de-hardcoding the resolution path automatically covers bug fixing |
| `core/config.py:98` | `DEFAULT_CAPABILITY_CHAINS` — replace `CapabilityChoice` model literals with `auto` / alias sentinels |
| `core/config.py:~246` | `NCDevConfig.providers` default `preferred_models` — replace literals with `auto` / aliases |
| `.nc-dev/config.yaml` | `preferred_models` accepts `auto` and alias sentinels |
| `ai_provider.py:289` (`CodexCLIProvider.build_argv()`) **and** `ai_session.py:240` (`run_codex_session()`) | Pass through advanced Codex options from the resolved capability set. Note: current Codex CLI takes reasoning via config (`-c model_reasoning_effort="high"`), **not** a `--reasoning-effort` flag — the NC Dev `reasoning_effort` field must be **translated**, not passed verbatim. This revives the currently dead `reasoning_effort` config field. |

`MODE_PRESETS` (`core/config.py:48`) needs **no change** — it maps task keys to *provider names only* and contains no model literals.

### 3.5 Skill selection + injection

A step that runs wherever a charter is produced — the greenfield/brownfield charter phase, the design phase, **and the synthesized bugfix charter** (`sentinel_charter.py` / `issue_charter.py`). It **replaces the hardcoded skill list** in `claude_executor.py:184` with a dynamic, inventory-driven selection:

1. Reads the probed skill inventory (§3.1) and picks the relevant skills for the work type:
   - Greenfield UI build → design skills, `/goal`, `frontend-design`
   - Backend build → a different set
   - **Bug fixing** → `systematic-debugging` and reproduction-oriented skills, biased by the failure report
2. **Steers sessions toward them** by naming the selected skills (and what they are for) in each session's `append_system_prompt_additions`.
3. Records the selected skill set in the run artifacts for audit.

The Sentinel bugfix path has **no design phase**, so skill selection must hook the bugfix charter directly — otherwise a fix session, which most needs `systematic-debugging`, would get no dynamic skill steering at all.

This closes the `/goal` gap: the hardcoded list never names `/goal`, and nothing today derives the steered set from what is actually installed. **Security note:** auto-injecting globally installed skills/plugins can activate untrusted or stale instructions — selection draws only from a vetted allowlist of skill *sources*, not every file found on disk. Phase 1 *consumes* skills only — no authoring (that is Phase 2, §4.3).

---

## 4. Phase 2 — Self-Learning Loop

**Outcome:** the system gets measurably better at choosing and creating capabilities the more it runs.

### 4.1 Capability ledger (`capability_ledger.py` — new)

Persisted at `~/.ncdev/capability-ledger.jsonl` so learning spans projects, not a single repo. After each factory run, two writers append entries:

- **Metrics writer** — objective stats per `(model, skill set, flag set)`: test pass rate, cycles-to-done, cost, `[BROKEN]` rate. This requires extending `StepResult` metadata to record the *resolved capability set* per session — today it records skills/cost but not enough structured resolution data to attribute outcomes cleanly.
- **Steward narrative writer** — the Product Steward's retrospective emits *structured* lessons: which skills/models helped or hurt which feature classes, and recurring hand-fix patterns (skill candidates).

### 4.2 Feedback into the Phase 1 policy

The ledger changes how `capability_policy.py` resolves `auto`:

- **Metrics gate** — a capability with a bad track record is demoted even if it is newer. This is what closes the Phase-1 blind window (see §5).
- **Narrative bias** — Steward lessons tune skill selection per project type.

### 4.3 Skill authoring

When the ledger shows a recurring pattern (the Steward flags it ≥ N times across runs, `N` configurable), a dedicated Claude session uses the `superpowers:writing-skills` skill to author a new skill, validate it, and add it to the library.

Unlike capability *consumption* (auto-adopt), *creating* a skill is a heavier commitment, so it stays **gated**: human review, or a Steward A/B evaluation on one slice, before the new skill is promoted into the selectable inventory.

---

## 5. Guardrails — making "auto-adopt" honest

Adoption policy is **probe + auto-adopt**: the newest capability the policy resolves is used immediately. This was a deliberate choice (held after the Codex review explicitly flagged the risk and recommended a canary). It is correct for velocity but has a real failure mode — a brand-new model or skill could silently degrade or destabilise builds. Given this project's own history (`URGENT-MEMORY-SAFETY-GUARDRAIL.md`), an untested capability running unsupervised is a risk class to respect. The design bakes in:

- **Snapshot + diff log** — every run records exactly which capabilities it used (`.nc-dev/capabilities.json` snapshots retained). A quality drop becomes bisectable to *"the run where Opus 4.8 first landed."*
- **Phase 2 metrics gate closes the loop** — Phase 1 alone adopts blind; once the ledger exists, a new capability is used, measured, and auto-demoted if metrics tank. The blind window is an *accepted, time-boxed Phase-1 risk*, explicitly closed by Phase 2.
- **Pin escape hatch always wins** — an explicit model in `config.yaml` or on the CLI overrides `auto`, for reproducibility and incident response.
- **Model-validation fallback** — when a resolved model is rejected by the CLI at session start (entitlement / rollout gap), the policy falls back down the resolution order (§3.2) rather than failing the run.

## 6. Non-Goals (YAGNI)

- **No release-watching daemon.** Nothing polls Anthropic/OpenAI release feeds. The installed CLI is the only source of truth.
- **No CLI self-upgrade.** The system does not upgrade the `claude`/`codex` binaries — that is the user's package manager.
- **No model enumeration.** The probe does not attempt to list every model an account can reach — it records accepted aliases plus a version-keyed pinning table (§3.1).
- **OpenRouter path untouched.** The `OpenRouterProvider` API path keeps its current `OPENROUTER_MODEL` env-var behaviour and its default model literal. OpenRouter is explicitly **out of scope** for the "no hardcoded literals" criterion (§8) — bringing it into policy resolution is deferred.
- **No per-feature provider re-routing.** One Claude session per feature stays the rule; capability resolution happens at session start, not mid-build.

## 7. Build Sequence

**Phase 1 (foundation — build first):**
1. `capability_probe.py` — populate the existing `CapabilitySnapshotDoc`; atomic/lock-protected `.nc-dev/capabilities.json` write; failure policy
2. `capability_policy.py` — `auto` resolution (pin → alias → version table → default), alias-first model selection
3. `session_options.py` — `SessionOptions` adapter over `Resolved` + snapshot
4. Wire `capability_router.py` / `provider_dispatch.py` to the policy; route session entry points through `SessionOptions`
5. De-hardcode `claude_session.py`, `ai_provider.py`, `ai_session.py`, `cli.py`, `DEFAULT_CAPABILITY_CHAINS`, `NCDevConfig.providers`; add `auto` sentinels to `config.yaml`
6. Codex advanced-option pass-through in `CodexCLIProvider.build_argv()` **and** `run_codex_session()`, with `reasoning_effort` → `model_reasoning_effort` translation
7. Skill selection + injection step replacing the hardcoded list in `claude_executor.py`, hooked into every charter path
8. Unit tests: policy resolution, pin precedence, malformed/missing snapshot, unavailable provider, CLI argv generation, concurrent probe writes

**Phase 2 (built on Phase 1):**
9. Extend `StepResult` metadata to carry the resolved capability set
10. `capability_ledger.py` + `~/.ncdev/capability-ledger.jsonl` store; metrics writer + Steward narrative writer wired into the factory run end
11. Metrics gate + narrative bias feeding back into `capability_policy.py`
12. Gated skill authoring from recurring patterns

## 8. Success Criteria

- A new model alias appearing in the installed CLI is used on the next run with **no code or config edit**.
- `reasoning_effort` set in `config.yaml` is translated and actually reaches `codex exec` (verifiable in the Codex argv / config).
- A greenfield UI build verifiably invokes design skills and `/goal` (visible in `skills_invoked`).
- A Sentinel bugfix run verifiably invokes `systematic-debugging` (visible in `skills_invoked`).
- `.nc-dev/capabilities.json` is written every run (atomically), conforms to `capability-snapshot.1`, and reflects the installed toolchain.
- Concurrent Sentinel fixes do not corrupt `.nc-dev/capabilities.json`.
- After Phase 2: a capability with a poor track record in the ledger is demoted on the following run without human intervention.
- No hardcoded model literals remain in the CLI-provider path — `claude_session.py`, `ai_provider.py` (Claude path), `ai_session.py`, `cli.py` defaults, `DEFAULT_CAPABILITY_CHAINS`, `NCDevConfig.providers`. (The OpenRouter API path is out of scope — see §6.)

## 9. Impact on Existing Flows

This work is a layer *underneath* the existing flows. It changes *which* model / skill / flag a session receives — never *what* a flow does. No flow is removed, rewired, or degraded.

| Flow | Entry point | What changes | What does NOT change |
|------|-------------|--------------|----------------------|
| **Greenfield** | `ncdev full` / `factory` | Sessions get auto-resolved models + dynamic per-project skill steering | Charter → design → sequential feature execution, `[BROKEN]` tagging |
| **Brownfield** | `ncdev full` / `factory` | Same as greenfield | `state_scanner` skip logic, Citex ingestion/grounding |
| **Bug fixing** | `ncdev fix` / Sentinel intake | Same auto-resolution; bugfix charter gains dynamic `systematic-debugging` skill steering | Sentinel reproduce → fix → verify → deploy → rollback chain, intake API, callback |

All three flows spawn Claude through the single `run_claude_session` primitive (`sentinel_reproduce.py` is a confirmed caller alongside `charter.py` and `claude_executor.py`) and Codex through `ai_provider` / `ai_session` — so capability adoption reaches every flow uniformly with no per-flow code.

**Bug fixing is preserved and improved:** the Sentinel path picks up newest models for free, advanced Codex options actually reach `codex exec`, and fix sessions are dynamically steered toward debugging skills (§3.5). The capability of the system to fix bugs is a hard requirement and is unaffected by this design.
