# AGENTS.md — NC Dev System

How to use NC Dev System from Codex CLI (or any AI agent).

---

## 1. Project Overview

NC Dev System is an autonomous development pipeline: **Requirements-In, Product-Out.** It takes PRDs, specs, and design documents and builds complete applications — frontend, backend, tests, Docker configs, CI/CD — with no human intervention required.

### Architecture

```
Discovery -> Feature Queue -> Sequential Build -> Quality Gate
```

1. **Discovery** — Parse requirements docs, extract features, design architecture, produce a feature queue.
2. **Feature Queue** — Ordered list of features with dependencies resolved. Each feature builds on verified working code from the previous step.
3. **Sequential Build** — Each feature is built, tested, and committed before the next starts. Failed features get repair attempts.
4. **Quality Gate** — Test Craftr runs exploratory tests against the running app, generates a fix manifest, and ncdev applies fixes in a loop until quality thresholds are met.

### CLI Commands

| Command | Purpose |
|---------|---------|
| `ncdev full` | Run the full sequential verified sprint pipeline (discovery through build) |
| `ncdev full --quality-gate` | Full pipeline + quality gate loop (build-test-fix) |
| `ncdev dev` | Autonomous dev mode — give it a project and a task description |
| `ncdev fix` | Fix production errors from a Sentinel failure report |
| `ncdev serve` | Start HTTP intake API for Sentinel reports (port 16650) |
| `ncdev report` | Generate video report for a completed project |
| `ncdev doctor` | Check all prerequisites are installed |
| `ncdev quickstart` | Print the recommended workflow |

---

## 2. How to Use from Codex CLI

### Greenfield Project (Build from Scratch)

```bash
# 1. Prepare your requirements docs (PRD, specs) in a directory
#    The --source flag accepts a single file or directory entry point.

# 2. Dry-run to preview the feature queue without building anything
ncdev full --source ./docs/README.md --dry-run

# 3. Run the full pipeline
ncdev full --source ./docs/README.md --base-url http://localhost:23000

# 4. With quality gate (Test Craftr must be running at localhost:16630)
ncdev full --source ./docs/README.md --base-url http://localhost:23000 --quality-gate
```

**What happens at each phase:**

1. **Discovery** (Opus-tier model) — Reads the source docs, extracts every feature, designs the architecture, and produces an ordered feature queue.
2. **Scaffold** — Creates the repo, generates the project skeleton (FastAPI backend, React/Vite frontend, Docker configs, Makefile).
3. **Sequential Build** — For each feature in the queue:
   - Generates a build prompt with full context of what exists so far.
   - Invokes the builder CLI (Codex or Claude) to implement the feature.
   - Runs tests. If tests fail, attempts up to `--max-repairs` repair cycles (default: 2).
   - Commits on success. Skips on repeated failure and moves to the next feature.
4. **Quality Gate** (if `--quality-gate` is set) — Triggers Test Craftr, waits for results, generates fix manifests, applies fixes, re-tests. Repeats up to `max_cycles` (default: 3) or until thresholds are met.

### Brownfield Project (Existing Codebase)

```bash
# Point --target-repo at the existing repository
ncdev full --source /path/to/updated-prd.md \
  --target-repo /path/to/existing-repo \
  --base-url http://localhost:23000 \
  --quality-gate
```

The discovery phase analyzes the existing codebase alongside the requirements to determine what needs building vs. what already exists.

### Autonomous Dev Mode (Single Task)

```bash
# Give it a project directory and a natural language task
ncdev dev --project /path/to/repo --task "Build a document Q&A feature for law firms"

# Specify the mode explicitly
ncdev dev --project /path/to/repo --task "Fix payment webhook timeout" --mode bugfix
ncdev dev --project /path/to/repo --task "Add PDF export feature" --mode enhance
```

Dev mode is for targeted work on an existing project — it analyzes the codebase, plans the work, builds it, and runs tests.

### Triggering from Codex CLI

```bash
# Codex can invoke ncdev as a subprocess
codex exec "Run ncdev full with quality gate against the project at ./my-project"

# Or use ncdev directly in the working directory
cd /path/to/workspace
ncdev full --source /path/to/prd --base-url http://localhost:PORT --quality-gate

# Fix mode — apply Sentinel failure reports
ncdev fix --report /path/to/sentinel-report.json --target /path/to/repo
ncdev fix --report-dir /path/to/reports/ --target /path/to/repo --batch --auto-deploy
```

### Key CLI Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--source` | (required) | Path to requirements doc or directory |
| `--target-repo` | (inferred from cwd) | Existing repo to build into |
| `--base-url` | `http://localhost:23000` | Where the app will be served |
| `--dry-run` | false | Preview feature queue without building |
| `--model` | `opus` | Claude model for fallback/repair (`opus`, `sonnet`, `haiku`) |
| `--timeout` | 600 | Builder timeout per feature in seconds |
| `--max-repairs` | 2 | Max repair attempts per feature |
| `--quality-gate` | false | Enable the build-test-fix quality gate loop |

---

## 3. AI Provider Configuration

All AI CLI calls are routed through a pluggable adapter at `src/ncdev/ai_provider.py`. No direct subprocess calls to `codex` or `claude` exist outside this module.

### Provider Hierarchy

| Priority | Provider | CLI Command | Notes |
|----------|----------|-------------|-------|
| Primary | Codex CLI | `codex exec --full-auto --skip-git-repo-check` | Default. Grants all tool permissions automatically. |
| Fallback | Claude CLI | `claude -p - --output-format text --allowedTools "..."` | Used when Codex CLI is unavailable. Supports tool allow-listing. |

### Configuration

Quality gate AI settings are in `src/ncdev/quality_gate/config.py`:

```python
ai_provider: str = "codex"   # Primary provider: "codex" or "claude"
ai_fallback: str = "claude"  # Fallback if primary is unavailable
ai_fix_timeout: int = 600    # Max seconds per fix group
```

### How Provider Selection Works

1. `get_provider_with_fallback(primary, fallback)` is called.
2. It checks if the primary CLI is installed and reachable (`--version` check).
3. If available, uses the primary. Otherwise, falls back.
4. The provider writes the prompt to a temp file, pipes it to the CLI, and captures stdout.

### Builder-Level Configuration

The builder that runs during the sequential build phase is configured separately via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `NC_BUILDER_CLI` | `claude` | Builder CLI: `claude` or `codex` |
| `NC_BUILDER_MODEL` | `claude-sonnet-4-6` | Model for the builder |
| `NC_MAX_BUILDER_ATTEMPTS` | `2` | Retries before fallback |
| `NC_BUILDER_TIMEOUT` | `600` | Per-builder timeout in seconds |

---

## 4. Quality Gate Integration

The quality gate is a closed-loop system: **build -> test -> fix -> re-test**.

### How It Works

1. **Trigger** — ncdev POSTs to Test Craftr (`POST /api/pipeline/runs`) with the target URL and PRD content.
2. **Wait** — Polls `GET /api/runs/{id}` until status is `completed`, `failed`, or `stopped`.
3. **Fetch Issues** — Retrieves all issues from `GET /api/runs/{id}/issues`.
4. **Score** — Test Craftr returns three quality scores: `core_flow`, `resilience`, `polish`.
5. **Generate Manifest** — Converts issues into a `FixManifest` with priority, category, reproduction steps, and affected file hints.
6. **Fix** — Groups issues by URL, invokes the AI provider with a combined prompt for each group. Snapshots the git state before each fix, reverts if the app fails to boot after the fix.
7. **Commit** — Each successful URL group fix is committed individually.
8. **Re-test** — Loop back to step 1. Stops when thresholds are met, max cycles exhausted, or regression detected.

### Quality Thresholds

| Score | Threshold | Meaning |
|-------|-----------|---------|
| `core_flow` | 100 | All primary user journeys work perfectly |
| `resilience` | >= 70 | Error handling, edge cases, recovery |
| `polish` | >= 80 | UI quality, responsiveness, accessibility |

The pipeline **passes** only when all three thresholds are met simultaneously.

### Fix Manifest Format

```json
{
  "run_id": "tc-run-abc123",
  "target_path": "/path/to/project",
  "scores": { "core_flow": 80, "resilience": 50, "polish": 60 },
  "issues": [
    {
      "id": "issue-001",
      "priority": "P0",
      "persona": "end-user",
      "category": "functionality",
      "title": "Login form does not submit",
      "flow": "/login -> click submit",
      "expected": "User is authenticated and redirected to dashboard",
      "actual": "Nothing happens, no network request sent",
      "root_cause_hint": "onClick handler missing on submit button",
      "reproduction": ["Navigate to /login", "Fill email and password", "Click Submit"],
      "evidence": { "screenshot": "...", "console_errors": ["..."] },
      "affected_files_hint": ["frontend/src/pages/LoginPage.tsx"]
    }
  ]
}
```

### Fix Safety Mechanisms

- **Git snapshot** before each fix attempt (via `git stash create`).
- **Boot check** after every fix — imports `app.main:app` to verify the backend still starts.
- **Automatic revert** if the boot check fails or the AI provider returns no result.
- **Regression detection** — if any score decreases between cycles, the loop stops immediately.
- **Timeout scaling** — P0/P1 issues get 300s, P2 gets 180s, P3 gets 120s. Grouped fixes get 2x time (capped at `ai_fix_timeout`).

### Citex RAG Enrichment

When Citex is running (localhost:20161), fix prompts are enriched with:
- Test Craftr findings from previous runs (category: `signals`).
- Relevant code context from the target project (category: `code`).

This gives the AI fixer additional context beyond what is in the manifest.

---

## 5. Roles/Personas for Codex

When Codex (or any AI agent) is driving ncdev, it should adopt these personas depending on the phase:

### Architect (Discovery/Planning Phase)

- Analyze the PRD, design the system architecture, define the feature queue.
- Resolve dependencies between features. Order the queue so foundations come first.
- Use a high-reasoning model (Opus-tier).
- Output: Feature queue JSON, architecture decisions, tech stack choices.

### Builder (Feature Execution Phase)

- Implement features sequentially. Each feature builds on verified working code.
- Write tests alongside implementation. Commit after each feature passes.
- Use a fast code generation model (Sonnet-tier).
- Output: Working code, passing tests, committed to the feature branch.

### Fixer (Quality Gate Fix Cycle)

- Read the fix manifest. Understand the root cause from the evidence and hints.
- Apply minimal, targeted fixes. Do not refactor unrelated code.
- Issues at the same URL are grouped — analyze them together for shared root causes.
- Verify the app boots after each fix. Revert if broken.
- Use a code generation model (Sonnet-tier).
- Output: Committed fixes, one commit per URL group.

### Reviewer (Verification Phase)

- Check if fixes actually resolve the issues reported by Test Craftr.
- Run tests, verify the app boots and serves correctly.
- Watch for regressions — any score decrease means the fix cycle should stop.
- Use a reasoning model (Opus-tier).
- Output: Pass/fail decision, regression flag.

---

## 6. Project Structure

```
nc-dev-system/
├── src/ncdev/
│   ├── cli.py                    # CLI entry point — all commands defined here
│   ├── ai_provider.py            # AI provider adapter (Codex + Claude CLI)
│   ├── dev.py                    # Autonomous dev mode (ncdev dev)
│   ├── intake_api.py             # HTTP intake API for Sentinel (ncdev serve)
│   ├── preflight.py              # Prerequisite checks (ncdev doctor)
│   ├── utils.py                  # Shared utilities
│   │
│   ├── discovery/                # Phase 1: Parse requirements, extract features
│   │   └── pipeline.py
│   │
│   ├── v3/                       # V3 engine: Sequential Verified Sprint Pipeline
│   │   ├── engine.py             # Main V3 entry point (run_v3_full)
│   │   ├── feature_queue.py      # Feature queue generation and ordering
│   │   ├── step_executor.py      # Per-feature build + test + commit
│   │   ├── models.py             # V3 state models
│   │   └── citex_client.py       # Citex RAG integration
│   │
│   ├── v2/                       # V2 engine (Sentinel fix mode, legacy)
│   │   ├── engine.py             # V2 fix pipeline
│   │   ├── config.py             # V2 build config
│   │   ├── execution.py          # Task execution
│   │   ├── routing.py            # Model routing
│   │   └── prepare.py            # Target project preparation
│   │
│   ├── quality_gate/             # Build-test-fix loop
│   │   ├── orchestrator.py       # Main loop: trigger TC -> wait -> fix -> repeat
│   │   ├── config.py             # Thresholds, provider settings
│   │   ├── models.py             # FixManifest, QualityScores, PipelineState
│   │   └── manifest.py           # Converts TC issues to FixManifest
│   │
│   ├── adapters/                 # AI provider registry
│   │   └── registry.py
│   │
│   └── artifacts/                # Build artifacts and state persistence
│       └── state.py
│
├── tests/                        # 1310+ tests
├── CLAUDE.md                     # Project instructions for Claude Code
└── AGENTS.md                     # This file
```

---

## 7. Environment Requirements

### Required

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.13+ | NC Dev System runtime |
| Node.js | Latest LTS | Frontend builds in generated projects |
| Git | Any recent | Version control, worktrees, fix snapshots |
| Codex CLI | Latest | Primary AI provider |
| Claude CLI | Latest | Fallback AI provider |
| pytest | Latest | Test runner |
| npm/npx | Latest | Frontend tooling |

### Optional

| Tool | Address | Purpose |
|------|---------|---------|
| Test Craftr | `localhost:16630` | Quality gate — exploratory testing |
| Redis | `localhost:16633` | Quality gate state (used by Test Craftr) |
| Citex | `localhost:20161` | RAG context enrichment for fix prompts |
| Docker | Local | Running generated projects |
| Ollama | `localhost:11434` | Local models for mock data and vision pre-screening |

### Verify Setup

```bash
ncdev doctor
```

This checks all required tools, optional services, and reports what is missing.

### Port Allocation

| Service | Port |
|---------|------|
| NC Dev Intake API | 16650 |
| Test Craftr | 16630 |
| Redis (quality gate) | 16633 |
| Citex | 20161 |
| Generated project (default) | 23000+ |
