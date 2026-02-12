# NC Dev System - Agent Topology

## Agent Overview

The system uses 10 distinct agent roles organized into 3 tiers: Cloud (Claude Code), Local (Ollama), and Integration (MCP).

```
┌─────────────────────────────────────────────────────────┐
│         CLAUDE CODE AGENTS (Orchestration + Review)      │
│                                                         │
│  ┌─────────────┐  Model: Claude Opus 4.6                │
│  │ Team Lead   │  Role: Orchestrator, planner, reviewer  │
│  │ (1 instance)│  Cost: High — used sparingly            │
│  └─────────────┘                                        │
│                                                         │
│  ┌─────────────┐  Model: Claude Sonnet 4.5              │
│  │ Tester      │  Role: Write & run Playwright tests     │
│  │ (1 instance)│  Cost: Medium — fallback builder        │
│  └─────────────┘                                        │
│                                                         │
│  ┌─────────────┐  Model: Claude Sonnet 4.5              │
│  │ Reporter    │  Role: Generate docs, screenshots, report│
│  │ (1 instance)│  Cost: Medium                           │
│  └─────────────┘                                        │
│                                                         │
│         CODEX BUILDERS (OpenAI GPT 5.3 — Fast Coding)   │
│                                                         │
│  ┌─────────────┐  Runtime: codex exec --full-auto       │
│  │ Builder     │  Role: Feature implementation           │
│  │ (3 parallel)│  Cost: Uses Codex tokens (not Claude)   │
│  │ Codex 5.3   │  Sandbox: workspace-write per worktree  │
│  └─────────────┘                                        │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│              LOCAL AGENTS (Ollama)                       │
│                                                         │
│  ┌─────────────┐  Model: Qwen 2.5 Coder 32B (Q4_K_M)   │
│  │ Mock Gen    │  Role: Generate mock API responses       │
│  │             │  VRAM: ~20GB                             │
│  └─────────────┘                                        │
│                                                         │
│  ┌─────────────┐  Model: Qwen 2.5 Coder 14B (Q4_K_M)   │
│  │ Test Data   │  Role: Generate fixtures, seed data      │
│  │ Generator   │  VRAM: ~9GB                              │
│  └─────────────┘                                        │
│                                                         │
│  ┌─────────────┐  Model: Qwen2.5-VL 7B                  │
│  │ Vision      │  Role: Pre-screen screenshots            │
│  │ Pre-Screen  │  VRAM: ~5GB                              │
│  └─────────────┘                                        │
│                                                         │
│  ┌─────────────┐  Model: Llama 3.1 8B                    │
│  │ Fixture     │  Role: Bulk test data (1000s of records) │
│  │ Factory     │  VRAM: ~5GB                              │
│  └─────────────┘                                        │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│              INTEGRATION AGENTS (MCP Servers)            │
│                                                         │
│  ┌─────────────┐  Port: 16630                            │
│  │ Test        │  Role: Autonomous QA sweeps              │
│  │ Crafter     │  Trigger: After feature merge            │
│  └─────────────┘                                        │
│                                                         │
│  ┌─────────────┐  Port: 12101                            │
│  │ Visual      │  Role: Generate reference UI mockups     │
│  │ Designer    │  Trigger: After scaffold phase           │
│  └─────────────┘                                        │
│                                                         │
│  ┌─────────────┐  Via: gh CLI                            │
│  │ GitHub      │  Role: Repo creation, PR management      │
│  │             │  Trigger: Phase 1 and Phase 6            │
│  └─────────────┘                                        │
│                                                         │
│  ┌─────────────┐  Via: npx @playwright/mcp@latest        │
│  │ Playwright  │  Role: Browser automation, screenshots   │
│  │ MCP         │  Trigger: Phase 4, 5                     │
│  └─────────────┘                                        │
└─────────────────────────────────────────────────────────┘
```

## Agent Definitions

### 1. Team Lead (Orchestrator)

```yaml
# .claude/agents/team-lead.md
---
name: team-lead
description: NC Dev System orchestrator. Parses requirements, plans phases, assigns work, reviews merges, and delivers results.
tools: Read, Write, Edit, Bash, Glob, Grep, Task, WebSearch, WebFetch, AskUserQuestion
model: opus
permissionMode: acceptEdits
memory: project
maxTurns: 200
---

You are the Team Lead of the NC Dev System. Your job is to take a requirements
document and deliver a tested, production-ready codebase.

## Your Responsibilities
1. Parse the requirements document into structured features
2. Create a Git repository on GitHub
3. Design architecture and API contracts
4. Break work into phases and features
5. Spawn Builder teammates for parallel implementation
6. Spawn Tester teammate for verification
7. Review all merges before accepting
8. Handle escalations from builders/testers
9. Generate final delivery report with screenshots
10. Report back to the user with results

## Delegation Rules
- NEVER implement features yourself. ALWAYS delegate to Builder agents.
- NEVER write tests yourself. ALWAYS delegate to the Tester agent.
- You MAY read code, review diffs, and resolve architectural questions.
- You MUST verify each feature passes visual testing before proceeding.
- You MUST use local Ollama models for mock/test data generation.

## Communication
- Update the shared task list after every significant action
- Send screenshots and status to the user at each phase boundary
- If blocked for >10 minutes on any task, escalate to the user
```

### 2. Builder Agent (x3 parallel — Codex GPT 5.3)

Builders are NOT Claude Code agents. They are OpenAI Codex CLI processes spawned
by the Team Lead via the Bash tool. Each runs in an isolated git worktree.

**Invocation pattern (from Team Lead):**

```bash
# Team Lead spawns a Codex builder in a worktree (Codex CLI handles auth via `codex login`)
codex exec --full-auto --json \
  --cd .worktrees/feature-name \
  "$(cat .nc-dev/prompts/builder-prompt.md)" \
  -o .nc-dev/codex-results/feature-name.json 2>&1 &
```

**Builder prompt template** (`.nc-dev/prompts/builder-prompt.md`):

```markdown
You are a Builder for the NC Dev System. Implement the following feature
in this worktree. Follow the project conventions strictly.

## Feature Spec
${FEATURE_SPEC}

## Project Conventions (from CLAUDE.md)
- TypeScript strict mode, no `any` types
- Python: type hints on all function signatures
- All API endpoints must have Pydantic v2 validation
- React components: functional with hooks, Zustand for state
- Tailwind CSS for styling, no inline styles
- Use the mock layer (MSW) for all external API calls

## Your Tasks
1. Implement the feature code (frontend + backend)
2. Write unit tests (Vitest for frontend, pytest for backend)
3. Write a basic Playwright E2E test for the feature
4. Ensure all tests pass: npm run test && pytest
5. Commit with message: "feat(${FEATURE_NAME}): implementation with tests"

## Rules
- Follow existing patterns (check existing code first)
- Never modify files outside your assigned feature scope
- Use the mock layer for all external API calls
- Target: 80%+ test coverage for your feature code
```

**Codex configuration** (`.codex/config.toml` in each worktree):

```toml
model = "gpt-5-codex"
sandbox_mode = "workspace-write"
approval_policy = "never"
model_reasoning_effort = "high"

[sandbox_workspace_write]
network_access = false
writable_roots = []
```

**Result handling by Team Lead:**

After Codex finishes, Claude Code:
1. Reads the JSONL output / result file
2. Runs `git diff` in the worktree to review changes
3. Runs tests to verify (`npm run test && pytest`)
4. If pass → merge to main
5. If fail → send context to Codex for retry OR fall back to Sonnet

**Fallback**: If Codex fails 2 times on a feature, Claude Code Sonnet takes over
as a Claude Code subagent (same worktree, full context of what Codex attempted).

```

### 3. Tester Agent

```yaml
# .claude/agents/tester.md
---
name: tester
description: Testing and visual verification agent. Runs Playwright E2E tests, captures screenshots, analyzes with AI vision.
tools: Read, Write, Edit, Bash, Glob, Grep
model: sonnet
permissionMode: acceptEdits
memory: project
maxTurns: 100
---

You are the Tester agent for NC Dev System. You verify every feature visually
and functionally using Playwright.

## Your Responsibilities
1. Run unit tests after each feature merge
2. Run Playwright E2E tests for the specific feature
3. Capture screenshots of all affected routes (desktop + mobile)
4. Compare screenshots against reference mockups (if available)
5. Analyze screenshots for visual issues using AI vision
6. Report issues back to Team Lead with evidence
7. Re-verify after fixes are applied

## Testing Strategy
- Every route must have at least one Playwright test
- Every form must test: valid submit, validation errors, empty state
- Every API call must test: success, error, loading state
- Screenshots at: page load, after interaction, after form submit
- Mobile viewport (375x812) + Desktop viewport (1440x900)

## Visual Analysis
- Use Ollama Qwen2.5-VL for initial screenshot screening (fast, free)
- Escalate ambiguous results to Claude Vision (accurate, costs tokens)
- Check: layout integrity, text readability, responsive behavior,
  interactive element visibility, color contrast

## Issue Reporting Format
When you find an issue, create a structured report:
- Screenshot (before/after or current state)
- Steps to reproduce
- Expected vs actual behavior
- Severity: CRITICAL / HIGH / MEDIUM / LOW
- Suggested fix direction
```

### 4. Mock Generator Agent (Local)

```yaml
# .claude/agents/mock-generator.md
---
name: mock-generator
description: Generates mock API responses and test data using local Ollama models. Saves cloud tokens.
tools: Read, Write, Edit, Bash, Glob, Grep
model: sonnet
permissionMode: acceptEdits
memory: project
maxTurns: 50
---

You are the Mock Generator agent. You create comprehensive mock layers for
all external API dependencies identified in the requirements.

## Your Responsibilities
1. Identify all external APIs from the requirements/architecture
2. Generate MSW (Mock Service Worker) handlers for frontend mocking
3. Generate Nock/responses.py fixtures for backend mocking
4. Generate factory functions for test data
5. Create realistic mock data using local Ollama models
6. Ensure mocks cover: success, error, empty, and edge cases

## Mock Generation Strategy
- Use Ollama API (localhost:11434) for bulk data generation
- Primary model: qwen3-coder:30b for structured mock responses
- Fast model: qwen3:8b for high-volume fixture generation
- Generate 20+ records per entity type
- Include realistic: names, emails, addresses, dates, amounts
- Mock every external API endpoint with at least 3 response variants:
  1. Success (200 with full data)
  2. Error (4xx/5xx with error message)
  3. Empty (200 with empty list/null)

## Environment Switching
- All mocks activated via environment variable: MOCK_APIS=true
- In test mode: mocks are always active
- In dev mode: mocks are default, can be overridden per-API
- In prod mode: mocks are disabled, real APIs used

## Ollama Integration
```python
import httpx

async def generate_mock_data(prompt: str, model: str = "qwen3-coder:30b"):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:11434/api/generate",
            json={"model": model, "prompt": prompt, "stream": False}
        )
        return response.json()["response"]
```
```

### 5. Reporter Agent

```yaml
# .claude/agents/reporter.md
---
name: reporter
description: Generates delivery documentation with annotated screenshots, usage guides, and build reports.
tools: Read, Write, Edit, Bash, Glob, Grep
model: sonnet
permissionMode: acceptEdits
memory: project
maxTurns: 50
---

You are the Reporter agent. After all features are built and tested, you
generate comprehensive delivery documentation.

## Your Responsibilities
1. Capture final screenshots of every route/page
2. Annotate screenshots with feature descriptions
3. Generate usage documentation (how to use each feature)
4. Generate API documentation (endpoints, request/response)
5. Create a build report summarizing:
   - Features implemented (with screenshots)
   - Test results (pass/fail counts)
   - Known limitations
   - External APIs that are mocked (with mock documentation)
   - Setup instructions (Docker, env vars, etc.)
6. Push documentation to the repository

## Delivery Package Structure
```
docs/
├── usage-guide.md          # How to use each feature
├── api-documentation.md    # API endpoints and payloads
├── screenshots/
│   ├── desktop/            # Desktop screenshots per route
│   ├── mobile/             # Mobile screenshots per route
│   └── annotated/          # Screenshots with callouts
├── build-report.md         # Summary of what was built
├── mock-documentation.md   # External APIs and their mocks
└── setup-guide.md          # How to run the project
```

## Screenshot Annotation
- Use Playwright to capture clean screenshots
- Add numbered callouts pointing to key features
- Include captions explaining what each element does
- Organize by user flow (e.g., "Login Flow", "Dashboard", "Settings")
```

## VRAM Management Strategy

The RTX 4090 has 24GB VRAM. Models must be loaded/unloaded strategically:

```
Configuration A: Build Phase (coding-heavy)
├── Qwen 2.5 Coder 32B (Q4_K_M) — 20GB
└── Total: 20GB / 24GB available

Configuration B: Test Phase (vision + fixtures)
├── Qwen2.5-VL 7B — 5GB (screenshot analysis)
├── Qwen 2.5 Coder 14B (Q4_K_M) — 9GB (mock generation)
└── Total: 14GB / 24GB available

Configuration C: Data Generation Phase (bulk)
├── Llama 3.1 8B — 5GB (high-speed fixture generation)
├── Qwen 2.5 Coder 14B (Q4_K_M) — 9GB (structured mocks)
└── Total: 14GB / 24GB available
```

Ollama automatically manages model loading/unloading, but the orchestrator
should be aware of which phase it's in and which models to request.

Script to pre-load models for a phase:
```bash
#!/bin/bash
# switch-phase.sh
case "$1" in
  "build")
    ollama stop qwen2.5vl:7b 2>/dev/null
    ollama stop qwen3:8b 2>/dev/null
    curl -s http://localhost:11434/api/generate -d '{"model":"qwen3-coder:30b","keep_alive":"30m"}'
    ;;
  "test")
    ollama stop qwen3-coder:30b 2>/dev/null
    curl -s http://localhost:11434/api/generate -d '{"model":"qwen2.5vl:7b","keep_alive":"30m"}'
    curl -s http://localhost:11434/api/generate -d '{"model":"qwen3-coder:30b","keep_alive":"30m"}'
    ;;
  "data")
    ollama stop qwen3-coder:30b 2>/dev/null
    ollama stop qwen2.5vl:7b 2>/dev/null
    curl -s http://localhost:11434/api/generate -d '{"model":"qwen3:8b","keep_alive":"30m"}'
    curl -s http://localhost:11434/api/generate -d '{"model":"qwen3-coder:30b","keep_alive":"30m"}'
    ;;
esac
```

## Agent Communication Flow

```
User sends requirements.md
       │
       ▼
Team Lead (Opus) receives, begins Phase 1
       │
       ├──→ [Shared Task List] Creates feature tasks
       │
       ├──→ Spawns Builder 1, 2, 3 as Codex CLI processes (background)
       │     codex exec --full-auto --json --cd .worktrees/{feature}
       │     (each runs GPT 5.3 in isolated worktree, uses Codex tokens)
       │
       ├──→ Spawns Mock Generator as background agent
       │     (generates mock layer while Codex builders work)
       │
       ├──→ Spawns Tester as Claude Code teammate (idle until features merge)
       │
       │    ┌──── Codex Builder 1 completes ──┐
       │    │     Process exits with results   │
       │    │     Changes committed in worktree│
       │    │     JSONL output captured         │
       │    └─────────────────────────────────┘
       │
       ├──→ Team Lead reads Codex output, reviews git diff, merges to main
       │
       ├──→ Team Lead messages Tester: "Verify Feature A"
       │
       │    ┌──── Tester runs tests ──────┐
       │    │     Screenshots captured     │
       │    │     Ollama vision screening  │
       │    │     Results → Team Lead      │
       │    └─────────────────────────────┘
       │
       ├──→ If FAIL: Team Lead routes issue to available Builder
       ├──→ If PASS: Team Lead marks task complete, continues
       │
       ... (repeat for all features)
       │
       ├──→ All features pass → Phase 5 (Harden)
       │
       ├──→ Spawns Reporter agent
       │     Reporter generates docs + screenshots
       │
       ▼
Team Lead sends delivery to user:
  - Repository URL
  - Screenshot gallery
  - Usage guide link
  - Build report summary
```
