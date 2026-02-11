# NC Dev System - Architecture

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           USER INTERACTION LAYER                            │
│                                                                             │
│   Remote Message ──→ Claude Code Web (claude.ai/code)                       │
│   CLI Command    ──→ Claude Code Terminal (claude --remote "Build X")       │
│   Slack/Discord  ──→ Claude Code Remote (webhook → task)                    │
│   Helyx Canvas   ──→ API trigger → Claude Code headless                    │
└─────────────────────────┬───────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                      ORCHESTRATION LAYER (Claude Code Opus)                 │
│                                                                             │
│   ┌─────────────────┐  ┌──────────────────┐  ┌──────────────────────────┐  │
│   │  Team Lead       │  │  Shared Task List │  │  Agent Mailbox           │  │
│   │  (Opus 4.6)      │  │  ~/.claude/tasks/ │  │  Inter-agent messaging   │  │
│   │                  │  │                    │  │                          │  │
│   │  Responsibilities│  │  Features queue    │  │  Status updates          │  │
│   │  - Parse PRD     │  │  Bug fixes queue   │  │  Context sharing         │  │
│   │  - Plan phases   │  │  Test failures     │  │  Escalation alerts       │  │
│   │  - Assign tasks  │  │  Verification queue│  │                          │  │
│   │  - Review merges │  │                    │  │                          │  │
│   │  - Report back   │  │                    │  │                          │  │
│   └─────────────────┘  └──────────────────┘  └──────────────────────────┘  │
└─────────────┬───────────────────┬───────────────────┬───────────────────────┘
              │                   │                   │
              ▼                   ▼                   ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────────────────────┐
│  CODEX BUILDERS  │ │  LOCAL AGENTS    │ │  INTEGRATION AGENTS              │
│  (OpenAI GPT5.3) │ │  (Ollama)        │ │  (MCP Servers)                   │
│                  │ │                  │ │                                  │
│  ┌────────────┐  │ │  ┌────────────┐  │ │  ┌────────────┐ ┌────────────┐  │
│  │ Builder 1  │  │ │  │ Mock Gen   │  │ │  │ Test       │ │ GitHub     │  │
│  │ Codex 5.3  │  │ │  │ Qwen 32B   │  │ │  │ Crafter    │ │ MCP        │  │
│  │ Worktree 1 │  │ │  │            │  │ │  │ MCP Server │ │            │  │
│  └────────────┘  │ │  └────────────┘  │ │  └────────────┘ └────────────┘  │
│  ┌────────────┐  │ │  ┌────────────┐  │ │  ┌────────────┐ ┌────────────┐  │
│  │ Builder 2  │  │ │  │ Test Data  │  │ │  │ Visual     │ │ Playwright │  │
│  │ Codex 5.3  │  │ │  │ Qwen 14B   │  │ │  │ Designer   │ │ MCP        │  │
│  │ Worktree 2 │  │ │  │            │  │ │  │ MCP Server │ │            │  │
│  └────────────┘  │ │  └────────────┘  │ │  └────────────┘ └────────────┘  │
│  ┌────────────┐  │ │  ┌────────────┐  │ │                                 │
│  │ Builder 3  │  │ │  │ Vision QA  │  │ │                                 │
│  │ Codex 5.3  │  │ │  │ Qwen2.5-VL │  │ │                                 │
│  │ Worktree 3 │  │ │  │ 7B         │  │ │                                 │
│  └────────────┘  │ │  └────────────┘  │ │                                 │
│  ┌────────────┐  │ │  ┌────────────┐  │ │                                 │
│  │ Reviewer   │  │ │  │ Fixture    │  │ │                                 │
│  │ Claude Opus│  │ │  │ Generator  │  │ │                                 │
│  │            │  │ │  │ Llama 8B   │  │ │                                 │
│  └────────────┘  │ │  └────────────┘  │ │                                 │
└──────────────────┘ └──────────────────┘ └──────────────────────────────────┘
              │                   │                   │
              ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          EXECUTION LAYER                                    │
│                                                                             │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌─────────────┐  │
│  │ Git       │ │ Docker    │ │ Playwright│ │ Shell     │ │ File System │  │
│  │ Worktrees │ │ Compose   │ │ Browser   │ │ Executor  │ │ Manager     │  │
│  │           │ │           │ │           │ │           │ │             │  │
│  │ 3 isolate │ │ MongoDB   │ │ Chrome    │ │ npm/pip   │ │ Artifacts   │  │
│  │ branches  │ │ Redis     │ │ Firefox   │ │ build     │ │ Screenshots │  │
│  │ per build │ │ App svcs  │ │ WebKit    │ │ test      │ │ Reports     │  │
│  └───────────┘ └───────────┘ └───────────┘ └───────────┘ └─────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          DATA LAYER                                         │
│                                                                             │
│  ┌───────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ Git Repository │  │ Build Logs   │  │ Test Results │  │ Screenshots  │  │
│  │ (GitHub)       │  │ (local fs)   │  │ (JSON/HTML)  │  │ (PNG/GIF)    │  │
│  └───────────────┘  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Architecture Decisions & Recommendations

### Decision 1: OpenAI Codex GPT 5.3 as Sub-Builders

**Recommendation: Use OpenAI Codex CLI (GPT 5.3) as the "fast" coding tier, managed by Claude Code Opus as orchestrator.**

Rationale:
- **Token economics**: User has Codex tokens/credits — using Codex for bulk coding saves Claude cloud tokens entirely for orchestration and review
- **Speed**: Codex GPT 5.3 is optimized for code generation tasks, fast execution
- **Full-auto mode**: `codex exec --full-auto` runs autonomously with workspace-write sandbox — ideal for subprocess invocation
- **JSONL streaming**: `codex exec --json` provides structured output Claude Code can parse programmatically
- **Proven integration**: claude-flow and claude-octopus both demonstrate Claude Code + Codex working together
- **Sandboxed**: Codex's workspace-write sandbox limits blast radius per worktree

Integration pattern:
```
Claude Code Opus (orchestrator)
  │
  ├── Spawns Codex via Bash tool:
  │   codex exec --full-auto --json --cd /path/to/worktree "implement feature X"
  │
  ├── Reads JSONL stream for progress monitoring
  │
  ├── Reviews Codex output (git diff) using Opus reasoning
  │
  └── Merges or requests fixes
```

Model assignment:
```
Claude Opus 4.6    → Orchestrator (Team Lead), Reviewer, Architecture, Delivery
Codex GPT 5.3      → Builders (x3), Feature implementation, Unit test writing
Claude Sonnet 4.5  → Tester (Playwright), Fallback builder if Codex fails
Claude Haiku 4.5   → Quick validation, lint checks, simple fixes
Ollama Local       → Test data, mock data, bulk generation, vision pre-screening
```

### Codex CLI Setup

```bash
# Install
npm i -g @openai/codex

# Authenticate with API key
printenv OPENAI_API_KEY | codex login --with-api-key

# Or with ChatGPT subscription
codex login

# Verify
codex login status

# Configuration (~/.codex/config.toml)
model = "gpt-5-codex"
sandbox_mode = "workspace-write"
approval_policy = "never"
```

### How Claude Code Invokes Codex

Claude Code's Team Lead agent uses the Bash tool to spawn Codex:

```bash
# Basic feature implementation
CODEX_API_KEY="${OPENAI_API_KEY}" codex exec --full-auto --json \
  --cd .worktrees/feature-auth \
  "Implement user authentication following the spec in .nc-dev/features/auth.json. \
   Write unit tests. Follow project conventions in CLAUDE.md." \
  -o .nc-dev/codex-results/feature-auth.txt

# With structured output
CODEX_API_KEY="${OPENAI_API_KEY}" codex exec --full-auto \
  --output-schema .nc-dev/schemas/build-result.json \
  --cd .worktrees/feature-dashboard \
  "Build the dashboard feature per spec" \
  -o .nc-dev/codex-results/feature-dashboard.json
```

### Codex Result Schema

```json
{
  "type": "object",
  "properties": {
    "status": { "enum": ["success", "partial", "failed"] },
    "files_created": { "type": "array", "items": { "type": "string" } },
    "files_modified": { "type": "array", "items": { "type": "string" } },
    "tests_written": { "type": "integer" },
    "tests_passing": { "type": "integer" },
    "issues": { "type": "array", "items": { "type": "string" } },
    "summary": { "type": "string" }
  },
  "required": ["status", "summary"]
}
```

### Fallback Strategy

```
Codex GPT 5.3 (primary builder)
  │
  ├── SUCCESS → Claude Opus reviews diff → merge
  │
  ├── PARTIAL → Claude Sonnet fixes remaining issues → retest
  │
  └── FAILED → Claude Sonnet takes over as builder (fallback)
              → If Sonnet also fails → escalate to user
```

### Decision 2: Test Crafter as MCP Server

**Recommendation: Expose Test Crafter as an MCP server that Claude Code calls directly.**

Rationale:
- MCP gives Claude Code native tool access to Test Crafter's capabilities
- Claude Code can trigger test runs, poll status, and process results within the same conversation
- No manual API calls or external orchestration needed
- Test Crafter already has a REST API (port 16630) — wrapping it in MCP is straightforward

Implementation:
```json
// .mcp.json
{
  "mcpServers": {
    "test-crafter": {
      "type": "http",
      "url": "http://localhost:16630/mcp"
    }
  }
}
```

MCP tools to expose:
- `test_crafter_run` — Submit PRD + target URL, start autonomous test run
- `test_crafter_status` — Check run progress
- `test_crafter_results` — Get issues found with screenshots
- `test_crafter_verify` — Run verification tests for specific fixes

### Decision 3: Visual Designer Generates Reference Mockups

**Recommendation: Yes — generate UI mockups from requirements first, then use as visual test references.**

This creates a closed loop:
```
Requirements → Visual Designer → Reference Mockups
                                       ↓
                                 Build Features
                                       ↓
                              Playwright Screenshots
                                       ↓
                           AI Vision Comparison
                           (built vs. reference)
                                       ↓
                              Pass / Fail + Feedback
```

The Visual Designer (port 12101) can also be wrapped as an MCP server:
- `visual_designer_generate` — Journey text → layout variations
- `visual_designer_screenshot` — Capture mockup as PNG
- `visual_designer_export` — Export React components as reference

### Decision 4: Build Fresh on Claude Code Native Capabilities

**Recommendation: Build fresh using Claude Code Teams + Skills + Agent SDK. Incorporate proven PATTERNS from existing tools, not the tools themselves.**

What to reuse from each tool:
- **From Auto-Coder**: Worktree isolation pattern, spec→plan→build pipeline structure, QA self-healing loop (up to 50 iterations)
- **From Forge**: Phase-based lifecycle (validate→research→architecture→build→test→harden), Definition of Done per task
- **From Claude Tools/AF**: Watchdog/investigation agent pattern, file locking protocol, JIRA integration pattern
- **From Test Crafter**: PRD-to-flow extraction, visual comparison engine, issue generation format

Why NOT wrap existing tools:
- Each tool has its own orchestration layer (Python scripts, LangGraph, etc.) that conflicts with Claude Code Teams
- Claude Code Teams already provides: shared task lists, inter-agent messaging, background execution, session management
- Building on native capabilities means updates to Claude Code automatically improve the system

### Decision 5: Default Tech Stack with Override

**Recommendation: Enforce the Yensi standard stack as default, allow PRD-level override.**

Default stack (from docs-only/technical.md):
```
Frontend: React 19, Vite, TypeScript strict, Tailwind CSS, Zustand
Backend:  FastAPI, Python 3.12+, Pydantic v2, Motor (async MongoDB)
Database: MongoDB (Motor), Redis (caching/queues)
Testing:  Playwright (E2E), Vitest (unit), pytest (backend)
Infra:    Docker Compose, sequential ports from 23000+
AI:       Claude CLI (dev) / Open Router (prod) via adapter pattern
```

Override mechanism:
- If the PRD specifies "use Next.js" or "use PostgreSQL", the system respects it
- The Planner agent detects stack preferences from requirements
- Scaffold templates exist for each supported stack variant

### Decision 6: New Project, Documented in docs-only

**Recommendation: New project at `/Users/nrupal/dev/yensi/dev/nc-dev-system/`, with planning docs in `/Users/nrupal/dev/yensi/dev/docs-only/planning/nc-dev-system/`.**

The project itself will be relatively lightweight — mostly Claude Code configuration:
```
nc-dev-system/
├── .claude/
│   ├── settings.json         # Claude Code settings
│   ├── teams/                # Team configurations
│   ├── skills/               # Custom skills (the pipeline stages)
│   ├── agents/               # Custom subagent definitions
│   └── commands/             # Slash commands for invocation
├── .mcp.json                 # MCP server connections
├── scripts/
│   ├── setup-ollama.sh       # Download and configure local models
│   ├── start-services.sh     # Start Test Crafter, Visual Designer, etc.
│   └── setup-project.sh      # One-time setup
├── templates/
│   ├── scaffold-react-fastapi/ # Default project scaffold
│   ├── playwright-config/      # E2E test configuration template
│   ├── mock-layer/             # MSW + factory template
│   └── docker-compose/         # Docker template
├── prompts/
│   ├── orchestrator.md         # Team Lead system prompt
│   ├── builder.md              # Builder agent prompt
│   ├── tester.md               # Test agent prompt
│   ├── mocker.md               # Mock generation prompt
│   └── reporter.md             # Report generation prompt
├── CLAUDE.md                   # Project-level Claude Code instructions
├── AGENTS.md                   # Agent topology documentation
└── README.md                   # Setup and usage guide
```

## Data Flow Architecture

```
Phase 1: UNDERSTAND (Opus)
  requirements.md
       │
       ├──→ Extract features (structured JSON)
       ├──→ Identify external APIs → plan mock layer
       ├──→ Identify UI screens → plan visual tests
       ├──→ Generate architecture (API contracts, DB schema)
       └──→ Create Git repo on GitHub (gh repo create)

Phase 2: SCAFFOLD (Claude Sonnet / Codex)
  architecture.json + contracts/
       │
       ├──→ Generate project from template
       ├──→ Set up Docker Compose (app + MongoDB + Redis)
       ├──→ Generate mock layer (MSW + Nock + factories)
       ├──→ Generate Playwright config + base tests
       ├──→ Generate reference mockups (Visual Designer)
       └──→ Commit: "Initial scaffold with mock layer"

Phase 3: BUILD (3x Codex GPT 5.3 in parallel worktrees)
  features.json (ordered by dependency)
       │
       Team Lead spawns 3 Codex CLI processes via Bash:
       ├──→ codex exec --full-auto --cd .worktrees/feature-a "build Feature A"
       ├──→ codex exec --full-auto --cd .worktrees/feature-b "build Feature B"
       └──→ codex exec --full-auto --cd .worktrees/feature-c "build Feature C"
       │
       Each Codex builder (GPT 5.3) autonomously:
       ├──→ Implements feature code
       ├──→ Writes unit tests (Vitest/pytest)
       ├──→ Writes Playwright E2E test
       ├──→ Commits with descriptive message
       └──→ Exits → Team Lead reviews diff + merges
       │
       Fallback: If Codex fails → Claude Sonnet takes over

Phase 4: VERIFY (per feature, after merge)
  merged feature on main
       │
       ├──→ Start Docker services
       ├──→ Run unit tests (vitest run, pytest)
       ├──→ Run Playwright E2E tests
       ├──→ Capture screenshots (all routes, desktop + mobile)
       ├──→ AI Vision analysis:
       │     ├── Local first (Qwen2.5-VL 7B) for pre-screening
       │     └── Cloud (Claude Vision) for failures/ambiguous cases
       ├──→ Test Crafter autonomous sweep (PRD + localhost URL)
       └──→ Results:
             ├── PASS → Continue to next feature
             └── FAIL → Generate issue → Route to Builder → Retest

Phase 5: HARDEN (Claude Sonnet + Local models)
  all features passing
       │
       ├──→ Error handling audit (Sonnet)
       ├──→ Loading states and edge cases (Sonnet)
       ├──→ Responsive testing - mobile/tablet (Playwright)
       ├──→ Accessibility check (Test Crafter WCAG module)
       ├──→ Performance audit (Lighthouse via Playwright)
       ├──→ Generate additional mock scenarios (Local Ollama)
       └──→ Final visual regression baseline

Phase 6: DELIVER (Opus)
  production-ready codebase
       │
       ├──→ Generate usage documentation with annotated screenshots
       ├──→ Generate API documentation
       ├──→ Create build report (features, test results, known limitations)
       ├──→ Push to GitHub with comprehensive README
       ├──→ Send delivery notification with:
       │     ├── Repository URL
       │     ├── Screenshot gallery
       │     ├── Usage guide
       │     ├── Test results summary
       │     └── Mock API documentation
       └──→ Mark task complete in Helyx
```

## Port Allocation

NC Dev System services:
```
24000  NC Dev System API (if needed for external triggers)
24001  Playwright browser pool
24002  Ollama API (default 11434, but can proxy)

Existing services used:
12100-12104  Visual Designer
16630-16633  Test Crafter
```

Generated project ports (per docs-only/technical.md):
```
23000+  Frontend
23001+  Backend
23002+  MongoDB
23003+  Redis
```
