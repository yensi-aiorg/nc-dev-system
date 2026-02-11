# NC Dev System - Overview

## Vision

NC Dev System is a fully autonomous, end-to-end software development agent that takes a requirements document as input and delivers a tested, near-production-ready codebase as output. It operates remotely, creating Git repositories, building features, testing visually with Playwright, generating mocks for all external dependencies, and reporting back with screenshots and usage documentation.

## Mission

Unify the disparate tools in the Yensi ecosystem (Test Crafter, Auto-Coder, Forge, Visual Designer, PRD Agent, Claude Tools Framework) into a single coherent development system powered by Claude Code's native multi-agent architecture (Teams, Skills, Agent SDK), using local Ollama models to optimize cloud token usage.

## Core Principles

1. **Requirements-In, Product-Out** - The only input is a requirements document. Everything else is generated.
2. **Visual Verification** - Every feature is visually tested with Playwright screenshots analyzed by AI vision.
3. **Mock Everything** - All third-party APIs are mocked and tested. The system runs without real API keys.
4. **Remote-First** - Interact via Telegram (OpenClaw), receive results asynchronously. No babysitting required.
5. **Three-Tier AI** - Claude Code Opus orchestrates, Codex GPT 5.3 builds (uses Codex tokens), Ollama handles bulk data/vision.
6. **Token Optimization** - Codex tokens for building, Ollama for data generation, Claude reserved for orchestration and review.
7. **Evidence-Based Delivery** - Screenshots, test reports, and usage docs accompany every delivery.

## What This System Does

```
INPUT: requirements.md (from user, remote message, or PRD Agent output)
  |
  v
[NC Dev System]
  |
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
  |
  v
OUTPUT:
  ├── Git repository with full source code
  ├── Docker deployment configs
  ├── Comprehensive test suite (unit + E2E + visual)
  ├── Mock system for all external APIs
  ├── Visual regression baselines
  ├── Usage documentation with annotated screenshots
  └── Build report (what was built, test results, known limitations)
```

## How It Differs From Existing Tools

| Existing Tool | What It Does | What NC Dev System Adds |
|---------------|-------------|------------------------|
| **Auto-Coder** | Spec → code generation with worktree isolation | Visual testing, mocking, remote interaction, end-to-end pipeline |
| **Forge** | 16-agent lifecycle from validation to deployment | Claude Code native orchestration (not custom LangGraph), local model integration |
| **Claude Tools/AF** | Multi-agent orchestrator with JIRA sync | Claude Code Teams/Skills instead of custom Python orchestrator |
| **Test Crafter** | Autonomous testing from PRD + URL | Integrated as a verification stage, not standalone |
| **Visual Designer** | Journey → UI mockups | Mockups become visual test references |
| **PRD Agent** | Conversation → PRD document | PRD output feeds directly into NC Dev System as input |

## System Name

**NC Dev System** - "NC" standing for the developer namespace (nc-minions). The system itself is invoked as a Claude Code skill or remote task.

## Key Metrics

- **Input**: 1 requirements document
- **Output**: Production-ready repository with tests
- **Build Time Target**: 2-8 hours depending on complexity (autonomous, no human intervention)
- **Test Coverage Target**: 80%+ (unit + E2E)
- **Visual Verification**: Every route/page screenshotted and AI-verified
- **Mock Coverage**: 100% of external API dependencies mocked
- **Claude Token Savings**: 70-80% — Codex handles building (Codex tokens), Ollama handles data/vision (free)
