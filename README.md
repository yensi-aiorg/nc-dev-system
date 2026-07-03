> ⚠️ **RETIRED as the factory fix engine (2026-07-03).** Superseded by **nc-dev-v3** (`github.com/yensi-solutions/nc-dev-v3`) — persistent HTTP intake on :16651 (launchd `solutions.yensi.ncdev3-intake`), Sentinel-wire-compatible. This repo is kept for history only; do not add new integrations against `ncdev serve` (:16650).

# NC Dev System

**Thin orchestrator. Claude drives, Codex implements.**

NC Dev takes a PRD and produces a verified, committed, working codebase —
sequentially, one feature at a time, with each feature gated by tests
that actually run.

The orchestrator itself is small. The intelligence lives in the agents
it spawns: Claude sessions for planning / review / debugging, Codex
sessions for raw implementation. NC Dev is what wires them together,
guards the commits, persists evidence, and keeps the loop honest.

> Current state: **932 tests passing on `main`**.

---

## The two main commands

```bash
# Autonomous closed-loop factory — the default for end-to-end product builds
ncdev factory --source prd.md

# Single open-loop build pass — debug / one-shot mode
ncdev full --source prd.md
```

`factory` runs `build → judge → repeat` until the product is complete,
unrecoverable, or the cycle / spend budget runs out. `full` is one pass
of the same pipeline without the Steward judging at the end — useful
for inspecting a single sprint in isolation.

For a single freeform engineering task against an existing repo:

```bash
ncdev dev --project /path/to/repo --task "Add a /healthz endpoint with tests"
```

For the full CLI surface, run `ncdev quickstart` or `ncdev --help`.

---

## How a PRD flows end to end

```
ncdev factory --source prd.md
    │
    ├─ Preflight (git, claude, codex, Citex, optionally Stitch MCP)
    │
    ├─ Phase 2: Charter (one Claude session, writing-plans skill)
    │     Three artifacts only — no more 9-doc discovery:
    │       target-project-contract.json   # stack, language, DB, auth, ports
    │       verification-contract.json     # what "done" means
    │       feature-queue.json             # ordered FeatureStep list
    │
    ├─ Phase 3: Design system (one Claude session)
    │     ├─ Greenfield UI + Stitch MCP + NCDEV_USE_STITCH=1 → Stitch tokens + screens
    │     ├─ Brownfield + docs/design-system/ exists → Claude summarises
    │     └─ No usable design system / Stitch unavailable → deterministic seed tokens
    │
    ├─ Recovery branch checkpoint
    │     NC Dev creates/switches to ncdev/<project>-<run_id> in the
    │     target repo and commits compact recovery metadata under
    │     .ncdev/recovery/<run_id>/ before feature work starts.
    │     Later checkpoints copy state + result metadata there without
    │     committing the noisy .nc-dev/runs logs.
    │
    ├─ Phase 4: Brownfield Citex ingestion (when applicable)
    │     Existing code chunked + synthesised into Citex RAG so feature
    │     N+1 sees what feature N built.
    │
    ├─ Phase 5: Sequential per-feature execution
    │     For each feature, one Claude session that:
    │       - Uses writing-plans, test-driven-development,
    │         verification-before-completion, systematic-debugging
    │         skills internally
    │       - Delegates raw impl + test writing to Codex via Bash:
    │           codex exec --full-auto --sandbox danger-full-access "<task>"
    │       - Emits .ncdev/assets-needed/<feature_id>.json for any
    │         images / GIFs / SVGs the feature references
    │       - Commits with Conventional Commits when verification passes
    │     NC Dev streams session events, verifies post-hoc, and tags
    │     [BROKEN] on the commit if verification fails (recoverable on
    │     the next factory cycle).
    │
    ├─ Phase 6: Product Steward (factory mode only)
    │     One Claude session reads the PRD, feature queue, completed
    │     results, and current repo state and emits a Disposition:
    │       continue | repair_current_slice | insert_features |
    │       rewrite_acceptance | rerun_charter | stop_as_unrecoverable
    │     The Steward holds whole-product UX coherence in its head —
    │     the role that was missing from open-loop builds.
    │
    └─ Loop or summary
       Factory: repeat from Phase 5 until Steward says continue at
                end-of-queue, or stop_as_unrecoverable, or cycle /
                spend budget is exhausted.
       Full:    write summary + metrics, exit.
```

---

## Mode switch — the budget lever

`.nc-dev/config.yaml` has a single `mode:` field that flips who does
what. Flip one line, no code change.

| `mode:`                       | planning | review  | implementation | tests   |
|-------------------------------|----------|---------|----------------|---------|
| `claude_plan_codex_build`     | Claude   | Claude  | Codex          | Codex   | (default)
| `codex_only`                  | Codex    | Codex   | Codex          | Codex   | (lean days)
| `claude_only`                 | Claude   | Claude  | Claude         | Claude  |
| `openrouter`                  | OR API   | OR API  | OR API         | OR API  | (needs OPENROUTER_API_KEY)
| `custom`                      | hand-tuned routing                          |

## House defaults — the stack lever

A second config block governs what the charter LLM falls back to when
the PRD is silent on a stack choice. The PRD always wins when it names
a specific library or service.

| Slot | Default | Notes |
|------|---------|-------|
| `auth.fallback` | `keycloak_standalone` | Set to `keystone` only via PRD ask. |
| `auth.ui_owner` | `application` | **Invariant.** App owns login/signup/MFA UI; Keycloak's hosted page is never shown. |
| `frontend.state_fallback` | `zustand` | PRD-named libraries (e.g. `redux_toolkit`) win. |
| `frontend.data_fetching_fallback` | `axios_with_interceptors` | PRD-named libraries (e.g. `tanstack_query`, `swr`) win. |
| `port_base` | `23300` | Generated projects allocate 6 sequential ports from here. |

Social authentication is **off by default** — opt-in via PRD only.
When the PRD asks for it, Keystone exposes Google via its BFF flow
(`/api/auth/google/start` → `/api/auth/google/callback`); standalone
Keycloak wires Google as an identity provider in the realm.

See [`CLAUDE.md`](./CLAUDE.md#house-defaults-nc-devconfigyaml--house_defaults)
for the full rule set.

---

## Quick start

```bash
# One-time
git clone <repo>
cd nc-dev-system
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Verify prerequisites
ncdev doctor

# Run the factory against a PRD
ncdev factory --source path/to/prd.md

# Single-pass build against an existing repo
ncdev full --source path/to/prd.md --target-repo /path/to/repo

# Single freeform task
ncdev dev --project /path/to/repo --task "Add structured logging"

# Inspect the last factory run
ncdev factory-status

# HTTP intake for Sentinel reports (auto-fix loop)
ncdev serve   # binds 16650 by default
```

## Full CLI

| Command | Purpose |
|---------|---------|
| `ncdev quickstart`       | Print the recommended workflow |
| `ncdev doctor`           | Check prerequisites |
| `ncdev spec`             | Generate a behavior contract without building |
| `ncdev factory`          | Closed-loop autonomous build (default for products) |
| `ncdev factory-status`   | Inspect the latest factory run summary |
| `ncdev full`             | One open-loop sprint pass |
| `ncdev dev`              | Single freeform engineering task |
| `ncdev fix`              | Fix a production error from a Sentinel report |
| `ncdev serve`            | HTTP intake for Sentinel + manual QA reports |
| `ncdev qa-import`        | Import a manual QA report as durable intake |
| `ncdev qa-monitor`       | List imported manual QA reports |
| `ncdev qa-update`        | Update a manual QA intake status |
| `ncdev skill-candidates` | List recurring ledger patterns + pending skills |
| `ncdev skill-author`     | Author a new skill for a recurring pattern |
| `ncdev skill-promote`    | Promote an authored skill into `~/.claude/skills` |
| `ncdev skill-review`     | Lightweight Steward review of a pending skill |

Run any subcommand with `--help` for its full flag set.

---

## Prerequisites

- **Claude Code CLI** — `npm i -g @anthropic-ai/claude-code`
- **OpenAI Codex CLI** — `npm i -g @openai/codex`
- **Python 3.12+** (3.13 supported)
- **Docker + Docker Compose** (for generated projects' local infra)
- **Node.js 20+** (for generated projects' frontends)
- **GitHub CLI** (`gh`) — for repo / PR operations
- *Optional:* Stitch MCP for greenfield UI design generation (`NCDEV_USE_STITCH=1`)
- *Optional:* Ollama (any recent GPU) for mock generation and local
  vision pre-screening

## Repository layout

```
nc-dev-system/
├── src/ncdev/
│   ├── cli.py                      # Subcommand entry points
│   ├── claude_session.py           # Primitive — spawn Claude with hooks + cost ceiling
│   ├── ai_provider.py              # CLI/API adapters (Codex, Claude, OpenRouter)
│   ├── provider_dispatch.py        # Maps routing keys → providers (honours mode)
│   ├── factory.py                  # Closed-loop factory orchestration
│   ├── dev.py                      # Single-task `ncdev dev` orchestrator
│   ├── intake_api.py               # HTTP intake (`ncdev serve`)
│   ├── run_caps.py                 # Wall-time + spend caps
│   ├── spend_ledger.py             # Per-run cost accounting
│   ├── core/
│   │   └── config.py               # NCDevConfig, MODE_PRESETS, HouseDefaultsConfig
│   ├── contracts/                  # Behavior contract schema + writer
│   └── pipeline/
│       ├── charter.py              # Phase 2 — generates the 3 charter artifacts
│       ├── design_phase.py         # Phase 3 — Stitch / existing / deterministic seed
│       ├── context_ingestion.py    # Phase 4 — brownfield → Citex RAG
│       ├── claude_executor.py      # Phase 5 — per-feature Claude session
│       ├── product_steward.py      # Phase 6 — closed-loop judge
│       ├── engine.py               # Top-level orchestrator + recovery checkpoints
│       ├── state_scanner.py        # Skip features already implemented
│       ├── asset_manifest.py       # Per-feature image/GIF/SVG manifest
│       ├── integration_gate.py     # Cross-feature verification gate
│       └── gauntlet/               # Verification gauntlet layers L0–L4
├── prompts/
│   ├── protocols/codex-via-bash.md # Protocol Claude reads at session init
│   ├── orchestrator.md             # Per-feature executor system prompt
│   └── …
├── scripts/
│   ├── ncdev-hooks/                # PreToolUse hook (Conventional Commits, prohibited patterns, force-push guard)
│   ├── setup.sh
│   ├── setup-ollama.sh
│   └── switch-phase.sh
├── tests/                          # 932 tests
├── docs/planning/                  # Architecture + planning docs
├── CLAUDE.md                       # Authoritative project instructions
└── README.md                       # You are here
```

---

## What NC Dev explicitly does NOT do anymore

- ❌ Hand Claude / Codex a mega-prompt full of `FRONTEND_METHODOLOGY` /
  `GUARDRAILS` / "execution order: backend first" prose. Claude decides.
- ❌ Run a Python build / verify / repair loop. Claude's
  `verification-before-completion` + `systematic-debugging` skills do
  it in-session.
- ❌ Generate 9 discovery artifacts. Three only: contract, verification,
  feature queue.
- ❌ Use separate per-task provider routing (source_ingest, market_research,
  feature_extraction, etc.) for the main flow. One Claude session per
  feature, full stop.
- ❌ Call `claude -p "<prompt>" --output-format text`. Everything is
  `--output-format stream-json` for event-level observability.

## What NC Dev still owns

- ✅ Cross-feature coherence via sequential verified commits
  (rollback unit = one feature)
- ✅ Citex RAG grounding so feature N+1 sees what feature N built
- ✅ Brownfield state scanner (skip features already implemented)
- ✅ The charter — the user's control plane for hard architectural
  constraints
- ✅ Verification contract enforcement (required files, asset manifest,
  prohibited patterns)
- ✅ `[BROKEN]` tag for recoverability across factory cycles
- ✅ Mode switch + house defaults for budget / stack control
- ✅ Spend ledger + wall-time caps so unattended runs cannot bankrupt you
- ✅ Hooks: Conventional Commits, prohibited-pattern guard, force-push
  guard (project-overridable via `NCDEV_HOOKS_CONFIG`)
- ✅ Asset manifest so generated code that references unlisted images
  fails verification
- ✅ Git / GitHub repo setup for greenfield runs

---

## Generated-project ports

When NC Dev scaffolds a new project, services are allocated from
`house_defaults.port_base` (23300 by default) upward:

| Service | Port |
|---------|------|
| Frontend | 23300 |
| Backend  | 23301 |
| MongoDB  | 23302 |
| Redis    | 23303 |
| Keycloak (only when `auth_provider = keycloak_standalone`) | 23304 |
| Keycloak Postgres (only when `auth_provider = keycloak_standalone`) | 23305 |

When `auth_provider = keystone`, Keycloak / kc-postgres are skipped —
Keystone provides its own auth stack via `keystone-sdk` and either the
shared YENSI Keystone infra or `standalone_mode: true` for local dev.

---

## Related YENSI projects

- **keystone** — Shared auth / logging / monitoring platform. When a
  PRD asks for Keystone, NC Dev wires the generated project against
  `keystone-sdk` + `@keystone/react` instead of standing up its own
  Keycloak.
- **sentinel** — Production monitoring + auto-fix dispatch. Reports
  flow into `ncdev serve` and become `ncdev fix` runs.
- **citex** — RAG engine (vector + graph + ingestion). Powers
  cross-feature grounding.
- **ignition**, **helyx**, **vigil**, **citebot**, **yensi-booking** —
  Other projects in the YENSI org.

---

## Documentation

- [`CLAUDE.md`](./CLAUDE.md) — Authoritative project instructions (read
  this if you're going to extend NC Dev itself)
- [`prompts/protocols/codex-via-bash.md`](./prompts/protocols/codex-via-bash.md)
  — The Codex protocol every per-feature Claude session reads at init
- [`docs/planning/`](./docs/planning/) — Architecture + design history
