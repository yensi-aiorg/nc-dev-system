# nc-dev-system

**Thin orchestrator — Claude drives, Codex implements**

**Deployed:** Local (ncdev CLI)
**Ports:** intake_api: 16650
**Tests:** 372 passing on `claude-orchestrator-migration` branch
**Commands:**
  - `ncdev full --source prd.md` — PRD-scale sequential sprint engine
  - `ncdev dev --project X --task Y` — single-task freeform engineering
  - `ncdev serve` — HTTP intake for Sentinel reports
  - `ncdev doctor` — preflight
**Strategy:** Claude is the orchestrator for each session; it invokes skills (`test-driven-development`, `verification-before-completion`, `systematic-debugging`) and delegates raw implementation + test writing to Codex via Bash (`codex exec --full-auto ...`). NC Dev itself is thin — it spawns sessions, streams events, commits verified work, tags `[BROKEN]` on failure for recoverability.

## Related YENSI Projects
- **sentinel**: Production monitoring & auto-fix dispatch
- **citebot**: SiteBot — AI document Q&A with visual citations
- **yensi-booking**: Virtual appointment scheduling SaaS
- **vigil**: AI ops engine — daily digest, WhatsApp bridge, CEO mode
- **keystone**: Shared infrastructure — auth, logging, monitoring
- **citex**: RAG engine — vector search + graph nodes + document ingestion
- **ignition**: Autonomous co-founder pipeline
- **helyx**: Command center — project management, canvas

---

## Architecture — how a PRD flows end to end

```
ncdev full --source prd.md
    │
    ├─ Preflight (git, claude, codex, Citex, optionally Stitch MCP)
    │
    ├─ Phase 2: Charter (one Claude session, writing-plans skill)
    │     → target-project-contract.json   # hard architectural constraints
    │     → verification-contract.json     # what "done" means
    │     → feature-queue.json             # ordered features
    │
    ├─ Phase 3: Design system (one Claude session)
    │     ├─ Greenfield UI + Stitch MCP available    → Stitch generates tokens + screens
    │     ├─ Brownfield + docs/design-system/ exists → Claude summarises into artifact
    │     ├─ Brownfield + no designs + no Stitch     → Claude's frontend-design skill
    │     └─ Greenfield UI + neither                 → HARD FAIL (intentional)
    │
    ├─ Phase 4: Brownfield Citex ingestion (when applicable)
    │     → existing code chunked + synthesised → Citex RAG
    │
    ├─ Phase 5: Sequential feature execution
    │     for each feature:
    │         one Claude session with:
    │           Tools:    Read, Write, Edit, Glob, Grep, Bash, Skill, Task
    │           Protocol: prompts/protocols/codex-via-bash.md (in system prompt)
    │           Hooks:    scripts/ncdev-hooks/settings.json (guard commits)
    │         Claude internally uses:
    │           writing-plans, test-driven-development,
    │           verification-before-completion, systematic-debugging
    │         Claude delegates to Codex for raw impl + test writing:
    │           codex exec --full-auto --sandbox danger-full-access "<scoped task>"
    │         Claude emits .ncdev/assets-needed/<feature_id>.json as it builds
    │         Claude commits with Conventional Commits when verification passes
    │     ncdev:
    │         streams events, reads final response, verifies post-hoc,
    │         tags [BROKEN] commit on failure
    │
    └─ Phase 6: Summary + metrics
```

## Mode switch — the budget lever

`.nc-dev/config.yaml` has a single `mode:` field that flips who does what. Flip one line, no code change:

| mode                        | planning | review  | implementation | tests   |
|-----------------------------|----------|---------|----------------|---------|
| `claude_plan_codex_build`   | Claude   | Claude  | Codex          | Codex   | (default)
| `codex_only`                | Codex    | Codex   | Codex          | Codex   | (lean days)
| `claude_only`               | Claude   | Claude  | Claude         | Claude  |
| `openrouter`                | OR API   | OR API  | OR API         | OR API  | (needs OPENROUTER_API_KEY)
| `custom`                    | hand-tuned routing   | — use when you want per-task overrides |

## Key modules

| Module                              | Role |
|-------------------------------------|------|
| `src/ncdev/claude_session.py`       | The primitive — `run_claude_session()` spawns Claude with stream-json + hooks + cost ceiling |
| `src/ncdev/ai_provider.py`          | CLI/API adapters: `CodexCLIProvider`, `ClaudeCLIProvider`, `OpenRouterProvider` |
| `src/ncdev/provider_dispatch.py`    | Maps routing task keys → providers, honouring `mode` |
| `src/ncdev/core/config.py`          | `NCDevConfig`, `MODE_PRESETS`, `RoutingConfig` |
| `src/ncdev/pipeline/charter.py`     | Phase B — generates the 3 charter artifacts |
| `src/ncdev/pipeline/design_phase.py`| Phase C — Stitch / existing / claude_generated / hard-fail |
| `src/ncdev/pipeline/asset_manifest.py` | Phase D — schema, scan, verify |
| `src/ncdev/pipeline/claude_executor.py` | Phase E — per-feature Claude session |
| `src/ncdev/pipeline/engine.py`      | Phase 1–6 — top-level orchestrator |
| `src/ncdev/dev.py`                  | `ncdev dev` — thin single-task orchestrator |
| `prompts/protocols/codex-via-bash.md` | Protocol Claude reads at session init |
| `scripts/ncdev-hooks/`              | PreToolUse hook — Conventional Commits, prohibited patterns, force-push guard |

## What NC Dev explicitly does NOT do anymore

- ❌ Hand Claude/Codex a mega-prompt full of `FRONTEND_METHODOLOGY` /
  `GUARDRAILS` / "execution order: backend first" prose. Claude decides.
- ❌ Run a Python build/verify/repair loop. Claude's
  `verification-before-completion` + `systematic-debugging` skills do
  it in-session.
- ❌ Generate 9 discovery artifacts. Three only: contract, verification,
  feature queue.
- ❌ Use separate per-task provider routing (source_ingest,
  market_research, feature_extraction, etc.) for the main flow. One
  Claude session per feature, full stop.
- ❌ Call `claude -p "<prompt>" --output-format text`. Everything is
  `--output-format stream-json` for event-level observability.

## What NC Dev still owns

- ✅ Cross-feature coherence via sequential verified commits (rollback
  unit = one feature)
- ✅ Citex RAG grounding so feature N+1 sees what feature N built
- ✅ Brownfield state scanner (skip features already implemented)
- ✅ The charter (hard architectural constraints) — the user's
  control plane
- ✅ Verification contract enforcement (required files, asset manifest,
  prohibited patterns)
- ✅ `[BROKEN]` tag for recoverability
- ✅ Mode switch for budget control
- ✅ Git / GitHub repo setup

---

## The Codex protocol (TL;DR)

Claude invokes Codex with:

```bash
codex exec --full-auto --sandbox danger-full-access "<prompt>"
```

Every Codex prompt follows a 5-section shape (Task / Context /
Requirements / Files / Verification) — see
`prompts/protocols/codex-via-bash.md` for the full spec and rationale.

Codex is used for: implementation, test writing, mechanical refactors,
boilerplate. Not for: planning, review, debugging, judgment calls.

## Hooks (guardrails)

`scripts/ncdev-hooks/settings.json` is wired in automatically via
`--settings` when a Claude session spawns. Current guards:

1. **Conventional Commits** — `git commit -m "..."` must start with
   `feat|fix|test|chore|refactor|docs|perf|style|build|ci|revert`.
2. **Prohibited patterns** — `TODO`, `FIXME`, `console.log(`, "Not yet
   implemented" in staged diff blocks the commit.
3. **Force-push protection** — `git push --force origin main` requires
   `NCDEV_ALLOW_FORCE_PUSH=1`.

Project-level overrides via `NCDEV_HOOKS_CONFIG=/path/to/hooks.json`
with `{"prohibited_patterns": [...]}`.

## Asset manifest

Every Claude feature-build session MUST emit
`.ncdev/assets-needed/<feature_id>.json` listing images/GIFs/SVGs/videos
the feature references but cannot generate itself. Downstream system
(Nano Banana 2 / human) populates them. The manifest is verified
against code references — committing code that references an unlisted
asset fails the feature.

Schema: `{id, name, type, description, generation_prompt,
suggested_dimensions, referenced_in[], target_path, status}`

Aggregate all features into `.ncdev/assets-needed/_all.json` for batch
processing.

## Ports (for generated projects)

| Service | Port |
|---------|------|
| Frontend | 23000 |
| Backend | 23001 |
| MongoDB | 23002 |
| Redis | 23003 |
| KeyCloak | 23004 |
| KeyCloak Postgres | 23005 |

## Git Conventions

- Repository: created under `yensi-solutions` org on first greenfield run
- Branch strategy: main + feature branches (`nc-dev/feature-name`)
- Commit format: enforced by the PreToolUse hook (Conventional Commits)
- Small, incremental commits, one per feature when possible
- `[BROKEN]` tag reserved for recoverability leftovers only

_Context synced: 2026-04-22_
