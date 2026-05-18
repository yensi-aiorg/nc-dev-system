# Dynamic Capability Adoption & Self-Improvement

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:writing-plans to turn this spec into an implementation plan, then superpowers:subagent-driven-development or superpowers:executing-plans to implement it.

**Goal:** Make NC Dev System a *dynamically improving* system instead of a fixed path. New Claude/Codex models, skills, slash commands (e.g. `/goal`, design skills), and CLI features should flow into builds with **zero code edits**, and the system should get measurably better at choosing and creating capabilities the more it runs.

**Architecture:** Two phases. **Phase 1 — Capability Adoption Layer** gives the existing `capability_router.py` *eyes*: a probe discovers what the installed toolchain can actually do, and a policy resolves `auto`/`latest` sentinels into concrete model / skill / flag choices at session start. **Phase 2 — Self-Learning Loop** gives the router *memory*: a cross-project ledger records what worked, feeds objective metrics and Steward narrative back into capability selection, and authors new skills from recurring patterns.

**Tech Stack:** Python 3.13+, Claude CLI, Codex CLI, Pydantic v2. Builds on existing `core/capability_router.py`, `core/availability.py`, `provider_dispatch.py`, and the Product Steward.

---

## 1. Current Problem

The system shells out to the `claude` and `codex` CLI binaries on `PATH`, so **runtime engine improvements land for free** when the CLIs are upgraded. But every point where a *capability* is named is **hardcoded or statically configured**:

| Where | What's frozen |
|-------|---------------|
| `claude_session.py` | `model: str = "claude-opus-4-6"` default literal |
| `ai_provider.py` | `model or "claude-opus-4-6"` fallback literal |
| `.nc-dev/config.yaml` | `preferred_models` pinned to explicit version strings |
| `ai_provider.py` `CodexCLIProvider.build_argv()` | Emits only `--model --sandbox --full-auto`; advanced flags dropped |
| `claude_session.py` `DEFAULT_TOOLS` | Frozen tool allowlist constant |
| Skill usage | No curation/selection step — relies on whatever is globally installed |

Consequences:
- A new model (Opus 4.7, etc.) requires a code/config edit before it is used.
- `.nc-dev/config.yaml` sets `reasoning_effort: high` for Codex, but `build_argv()` never passes it — **the field is dead code**.
- New slash commands and skills like `/goal` or design skills are never used: the pipeline neither knows they exist nor steers sessions toward them.
- `core/capability_router.py` already routes `capability → (provider, model)` — its docstring promises *"riding the model curve becomes 'edit one config file'"* — but it resolves model strings out of static config. It has **no eyes**: it cannot see what the toolchain actually offers, and the hardcoded defaults in `claude_session.py` / `ai_provider.py` **bypass it entirely**.

The system is **engine-dynamic** (CLI upgrades land) but **capability-static** (every model, tool, skill, and flag is wired by hand).

## 2. New Architecture

```
SESSION START
    │
    ├─ capability_probe.py  ── probes installed toolchain ──┐
    │     claude: version, models, skills/plugins, flags    │
    │     codex:  version, models, flags/profiles           │
    │                                                       ▼
    │                                          CapabilitySnapshot
    │                                          → .nc-dev/capabilities.json
    │                                                       │
    ├─ capability_policy.py ── resolves auto/latest ─────────┤
    │     snapshot + task key + policy (newest stable)       │
    │     + ledger metrics gate (Phase 2)                    │
    │     explicit config pins always win                    │
    │                                                       ▼
    ├─ capability_router.py (EXISTING) ── resolve_capability("implementation")
    │                                          → Resolved(provider, model, flags, skills)
    │                                                       │
    ├─ claude_session.py / ai_provider.py ── consume Resolved (no literals)
    │                                                       │
    └─ skill selection ── inject + steer per project type ──┘
          (charter/design phase: pick design skills, /goal, etc.;
           name them in append_system_prompt so sessions use them)

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

The *eyes*. Runs once per session/run, results cached in-process and to disk.

- `probe_claude()` → `ClaudeCapabilities`: CLI version; available models; installed skills and plugins (scan `~/.claude/skills`, `~/.claude/plugins`, and the project's `.claude/skills`); supported flags (parse `claude --help`).
- `probe_codex()` → `CodexCapabilities`: CLI version; available models; supported flags and profiles (parse `codex --help`).
- Where a CLI exposes no machine-readable model list, fall back to a known-models table keyed by CLI version, kept in this module (the *one* place a version string lives).
- Output: a `CapabilitySnapshot` Pydantic model, persisted to `.nc-dev/capabilities.json` with a UTC timestamp.

This extends, not replaces, `core/availability.py` — availability answers *"is the binary there?"*; the probe answers *"what can it do?"*.

### 3.2 `capability_policy.py` (new — `src/ncdev/core/`)

Turns `auto` into a concrete choice. Given `(CapabilitySnapshot, task_key, policy)`, resolves the model, skill set, and flag set.

- Default policy: **newest stable**. The latest model the snapshot reports, the recommended flag set.
- `auto` / `latest-opus` sentinels in `config.yaml` are resolved here.
- **Explicit version pins in `config.yaml` always win** — the escape hatch for reproducibility and incident response.
- In Phase 2, this module also consults the ledger metrics gate (§4.2).

`capability_router.py` calls `capability_policy.resolve()` instead of reading static model strings. `Resolved` is extended to carry the resolved skill set and flag set alongside `provider` and `model`.

### 3.3 De-hardcoding

| File | Change |
|------|--------|
| `claude_session.py` | Remove the `claude-opus-4-6` default literal; `model` is resolved via `capability_router` |
| `ai_provider.py` | Remove the `model or "claude-opus-4-6"` fallback; resolve via router |
| `.nc-dev/config.yaml` | `preferred_models` accepts `auto` / `latest-opus` sentinels |
| `ai_provider.py` `CodexCLIProvider.build_argv()` | Pass through advanced flags (`reasoning_effort`, profiles) from the resolved capability set — **revives the currently dead `reasoning_effort` config field** |

### 3.4 Skill selection + injection

A step in the charter or design phase that:

1. Picks the relevant skills for the project type from the probed inventory — e.g. a greenfield UI build gets design skills, `/goal`, `frontend-design`; a backend build gets a different set.
2. **Steers sessions toward them** by naming the selected skills (and what they are for) in each per-feature Claude session's `append_system_prompt`.

This directly closes the `/goal` gap: today a session will not invoke `/goal` because nothing tells it the command exists or applies. Phase 1 *consumes* skills only — no authoring (that is Phase 2, §4.3).

---

## 4. Phase 2 — Self-Learning Loop

**Outcome:** the system gets measurably better at choosing and creating capabilities the more it runs.

### 4.1 Capability ledger (`capability_ledger.py` — new)

Persisted at `~/.ncdev/capability-ledger.jsonl` so learning spans projects, not a single repo. After each factory run, two writers append entries:

- **Metrics writer** — objective stats per `(model, skill set, flag set)`: test pass rate, cycles-to-done, cost, `[BROKEN]` rate.
- **Steward narrative writer** — the Product Steward's retrospective emits *structured* lessons: which skills/models helped or hurt which feature classes, and recurring hand-fix patterns (skill candidates).

### 4.2 Feedback into the Phase 1 policy

The ledger changes how `capability_policy.py` resolves `auto`:

- **Metrics gate** — a capability with a bad track record is demoted even if it is newer. This is what makes auto-adopt safe over time (see §5).
- **Narrative bias** — Steward lessons tune skill selection per project type.

### 4.3 Skill authoring

When the ledger shows a recurring pattern (the Steward flags it ≥ N times across runs), a dedicated Claude session uses the `superpowers:writing-skills` skill to author a new skill, validate it, and add it to the library.

Unlike capability *consumption* (auto-adopt), *creating* a skill is a heavier commitment, so it stays **gated**: human review, or a Steward A/B evaluation on one slice, before the new skill is promoted into the selectable inventory.

---

## 5. Guardrails — making "auto-adopt" honest

Adoption policy is **probe + auto-adopt**: the newest capability the probe reports is used immediately. That is correct for velocity but has a real failure mode — a brand-new model or skill could silently degrade or destabilise builds. Given this project's own history (`URGENT-MEMORY-SAFETY-GUARDRAIL.md`), an untested capability running unsupervised is a risk class to respect. The design bakes in:

- **Snapshot + diff log** — every run records exactly which capabilities it used (`.nc-dev/capabilities.json` snapshots are retained). A quality drop becomes bisectable to *"the run where Opus 4.8 first landed."*
- **Phase 2 metrics gate closes the loop** — Phase 1 alone adopts blind; once the ledger exists, a new capability is used, measured, and auto-demoted if metrics tank. The blind window is an *accepted, time-boxed Phase-1 risk*, explicitly closed by Phase 2.
- **Pin escape hatch always wins** — an explicit version in `config.yaml` overrides `auto`, for reproducibility and incident response.

## 6. Non-Goals (YAGNI)

- **No release-watching daemon.** Nothing polls Anthropic/OpenAI release feeds. The installed CLI is the only source of truth.
- **No CLI self-upgrade.** The system does not upgrade the `claude`/`codex` binaries — that is the user's package manager.
- **OpenRouter path untouched.** The `OpenRouterProvider` API path keeps its current `OPENROUTER_MODEL` env-var behaviour.
- **No per-feature provider re-routing.** One Claude session per feature stays the rule; capability resolution happens at session start, not mid-build.

## 7. Build Sequence

**Phase 1 (foundation — build first):**
1. `capability_probe.py` + `CapabilitySnapshot` model + `.nc-dev/capabilities.json` persistence
2. `capability_policy.py` — `auto`/`latest` resolution, newest-stable policy, pin override
3. Extend `Resolved` and wire `capability_router.py` to call the policy
4. De-hardcode `claude_session.py` and `ai_provider.py`; add `auto` sentinels to `config.yaml`
5. Codex advanced-flag pass-through in `build_argv()`
6. Skill selection + injection step in the charter/design phase

**Phase 2 (built on Phase 1):**
7. `capability_ledger.py` + `~/.ncdev/capability-ledger.jsonl` store
8. Metrics writer + Steward narrative writer wired into the factory run end
9. Metrics gate + narrative bias feeding back into `capability_policy.py`
10. Gated skill authoring from recurring patterns

## 8. Success Criteria

- A new model appearing in the installed CLI is used on the next run with **no code or config edit**.
- `reasoning_effort` (and other Codex advanced flags) set in `config.yaml` actually reach `codex exec`.
- A greenfield UI build verifiably invokes design skills and `/goal` (visible in `skills_invoked`).
- `.nc-dev/capabilities.json` is written every run and accurately reflects the installed toolchain.
- After Phase 2: a capability with a poor track record in the ledger is demoted on the following run without human intervention.
- No hardcoded model literals remain in `claude_session.py` or `ai_provider.py`.
