# NC Dev System

An autonomous development agent that takes a requirements document and delivers a tested, production-ready codebase.

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

# Interactive build
claude
> /build /path/to/requirements.md

# Remote build (CLI)
claude --remote "Build from requirements.md using NC Dev System"

# Check status
claude
> /status
```

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
