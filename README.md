# NC Dev System

A target-repo-first autonomous development controller for website SaaS projects.

## What It Does

```
INPUT: requirements.md
  │
  ├── 1. Parses requirements → structured features, architecture, API contracts
  ├── 2. Creates Git repository (GitHub)
  ├── 3. Scaffolds project (React 19 + FastAPI + MongoDB + Docker)
  ├── 4. Generates comprehensive mock layer for all external APIs
  ├── 5. Builds features in parallel (3x Codex GPT 5.3 in isolated worktrees)
  ├── 6. Tests each feature (Playwright E2E + visual AI analysis)
  ├── 7. Runs Test Crafter for autonomous QA sweep
  ├── 8. Iterates on failures (fix → retest loop)
  ├── 9. Hardens (error handling, responsive, accessibility, performance)
  ├── 10. Generates usage documentation with screenshots
  │
OUTPUT:
  ├── Git repository with full source code
  ├── Docker deployment configs
  ├── Comprehensive test suite (unit + E2E + visual)
  ├── Mock system for all external APIs
  ├── Screenshots (desktop + mobile) for every route
  ├── Usage documentation with annotated screenshots
  └── Build report (features, test results, known limitations)
```

## AI Architecture

- **Claude Code Opus 4.6** — Orchestrator (Team Lead), reviewer, architecture
- **OpenAI Codex GPT 5.3** — 3x parallel builders (uses Codex tokens, saves Claude tokens)
- **Claude Code Sonnet 4.5** — Tester, fallback builder
- **Ollama Local Models** — Mock data, test fixtures, vision pre-screening (free)

## Quick Start

```bash
# One-time setup
./scripts/setup.sh          # Check prerequisites
./scripts/setup-ollama.sh   # Download local AI models

# Python runtime setup (Phase 1 implementation)
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Discover phases against an existing target repo
PYTHONPATH=src python -m ncdev.cli discover-v2 \
  --source /path/to/requirements-or-doc-folder \
  --target-repo /path/to/target-repo \
  --dry-run

# Prepare the target repo
PYTHONPATH=src python -m ncdev.cli prepare-v2 \
  --source /path/to/requirements-or-doc-folder \
  --target-repo /path/to/target-repo

# Run the full loop
PYTHONPATH=src python -m ncdev.cli full-v2 \
  --source /path/to/requirements-or-doc-folder \
  --target-repo /path/to/target-repo \
  --base-url http://localhost:23000
```

The active operating model is documented in:

- [`docs/planning/12-website-saas-operating-spec.md`](./docs/planning/12-website-saas-operating-spec.md)
- [`docs/planning/13-operator-quickstart.md`](./docs/planning/13-operator-quickstart.md)

## Runtime CLI

```bash
# Discovery against docs plus an existing target repo
ncdev discover-v2 --source /path/to/docs --target-repo /path/to/repo --dry-run

# Prepare the target repo for execution
ncdev prepare-v2 --source /path/to/docs --target-repo /path/to/repo

# Execute queued jobs for a prepared run
ncdev execute-v2 --run-id <run-id>

# Verify the prepared target app
ncdev verify-v2 --run-id <run-id> --base-url http://localhost:23000

# Full loop: prepare -> execute -> verify -> repair -> deliver
ncdev full-v2 --source /path/to/docs --target-repo /path/to/repo --base-url http://localhost:23000

# Inspect run status
ncdev status-v2 --run-id <run-id>
```

## Implemented Runtime Scope

- Target-repo-first V2 flow for website SaaS projects
- Claude-led discovery and phase planning artifacts
- Codex-backed implementation in isolated worktrees
- Verification contracts and evidence expectations persisted per run
- Playwright screenshot/report recognition inside the target repo
- Delivery summary and release-gate reporting
- Optional generated scaffold when no `--target-repo` is supplied

## Prerequisites

- Claude Code CLI (`npm i -g @anthropic-ai/claude-code`)
- OpenAI Codex CLI (`npm i -g @openai/codex`)
- Ollama with RTX 4090 (24GB VRAM)
- Docker + Docker Compose
- Node.js 20+ / Python 3.12+
- GitHub CLI (`gh`)

## Project Structure

```
nc-dev-system/
├── .claude/
│   ├── settings.json       # Claude Code settings + permissions
│   ├── agents/             # Agent definitions (team-lead, tester, etc.)
│   ├── skills/             # Pipeline stage skills
│   ├── commands/           # User slash commands (/build, /status, /deliver)
│   └── teams/              # Team configurations
├── .mcp.json               # MCP server connections
├── scripts/                # Setup and utility scripts
├── prompts/                # Agent prompt templates
├── docs/planning/          # Architecture and planning docs
├── CLAUDE.md               # Project instructions for all agents
├── AGENTS.md               # Agent topology documentation
└── README.md
```

## Planning Documentation

See `docs/planning/` for comprehensive architecture and implementation docs.
