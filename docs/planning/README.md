# NC Dev System — Planning Documentation

An autonomous development agent that takes a requirements document and delivers a tested, production-ready codebase. Triggered remotely via Telegram (OpenClaw), Claude Code Web, or CLI.

## Document Index

| Document | Description |
|----------|-------------|
| [00-overview.md](./00-overview.md) | Vision, mission, core principles, what the system does |
| [01-architecture.md](./01-architecture.md) | System architecture, all 6 architecture decisions with recommendations |
| [02-agent-topology.md](./02-agent-topology.md) | All 10 agent roles, their prompts, VRAM management strategy |
| [03-local-models.md](./03-local-models.md) | Ollama model selection (RTX 4090), setup script, token optimization |
| [04-claude-code-setup.md](./04-claude-code-setup.md) | Claude Code Teams, Skills, Commands, MCP, remote interaction config |
| [05-testing-pipeline.md](./05-testing-pipeline.md) | 4-level testing (unit, E2E, visual AI, Test Crafter), Playwright config |
| [06-mocking-system.md](./06-mocking-system.md) | MSW, pytest fixtures, Ollama data gen, factory pattern, env switching |
| [07-remote-interaction.md](./07-remote-interaction.md) | Remote triggering, delivery package, screenshots, usage docs, Helyx sync |
| [08-integration-map.md](./08-integration-map.md) | How all existing tools connect, MCP adapters needed, dependency graph |
| [09-implementation-phases.md](./09-implementation-phases.md) | 5-phase build plan (Foundation → Build Engine → Testing → Integration → Remote) |
| [10-openclaw-telegram-integration.md](./10-openclaw-telegram-integration.md) | Telegram bot via OpenClaw, conversation flow, plugin architecture |

## Architecture Summary

```
User (Telegram/Web/CLI)
  → OpenClaw Gateway (Telegram bot)
    → Claude Code Opus (Team Lead / Orchestrator)
      → Codex GPT 5.3 x3 (Parallel Builders — uses Codex tokens, not Claude)
      → Claude Code Sonnet (Tester — Playwright + AI Vision + fallback builder)
      → Ollama Local Models (Mock data, test fixtures, vision pre-screening)
      → Test Crafter MCP (Autonomous QA sweep)
      → Visual Designer MCP (Reference mockups)
      → Playwright MCP (Browser automation)
      → GitHub CLI (Repository management)
    → Delivery: Repo + Screenshots + Docs + Test Results
  → OpenClaw Gateway
→ User receives results on Telegram

Token optimization: Codex tokens for building, Ollama for data/vision, Claude only for orchestration
```

## Key Decisions

1. **Codex GPT 5.3** as fast builders — uses existing Codex tokens, saves Claude cloud tokens
2. **Claude Code Opus** as orchestrator/reviewer — reasoning-heavy tasks only
3. **Claude Code Sonnet** as tester + fallback builder — when Codex needs backup
4. **Test Crafter as MCP server** — Claude Code calls it natively
5. **Visual Designer generates references** — closed design→build→compare loop
6. **Build fresh on Claude Code native** — Teams, Skills, Agent SDK (not custom orchestrator)
7. **Default stack with override** — React 19 + FastAPI + MongoDB unless PRD specifies otherwise
8. **OpenClaw Telegram bot** — remote interaction via existing messaging gateway
9. **Ollama for bulk work** — Qwen 2.5 Coder 32B (mocks), Qwen2.5-VL 7B (vision), Llama 3.1 8B (fixtures)

## Quick Start (After Implementation)

```bash
# Setup
cd nc-dev-system
./scripts/setup.sh
./scripts/setup-ollama.sh

# Interactive build
claude
> /build /path/to/requirements.md

# Remote build (CLI)
claude --remote "Build from requirements.md using NC Dev System"

# Remote build (Telegram)
# Message @nc_dev_agent_bot: "Build a task management app with these features..."
```
