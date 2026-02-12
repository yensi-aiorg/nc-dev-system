# NC Dev System - Claude Code Configuration

## Prerequisites

```bash
# Claude Code CLI (latest) — orchestrator
npm install -g @anthropic-ai/claude-code

# Codex CLI (OpenAI) — fast builder tier (GPT 5.3)
npm install -g @openai/codex

# Claude Agent SDK (for programmatic orchestration)
pip install claude-agent-sdk

# Codex SDK (for programmatic builder control)
npm install @openai/codex-sdk

# Authenticate both (CLIs handle their own auth — no API keys needed)
claude                          # OAuth flow for Claude Code
codex login                     # OAuth flow for Codex

# Verify both
claude --version
codex login status

# Enable Agent Teams (experimental)
# Add to ~/.claude/settings.json:
# { "env": { "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1" } }
```

## Codex Configuration

```toml
# ~/.codex/config.toml (user-level defaults for all builder invocations)
model = "gpt-5-codex"
model_reasoning_effort = "high"
sandbox_mode = "workspace-write"
approval_policy = "never"

[sandbox_workspace_write]
network_access = false

[features]
shell_tool = true
```

## Project Structure

```
nc-dev-system/
├── .claude/
│   ├── settings.json           # Project-level settings
│   ├── agents/                 # Custom subagent definitions
│   │   ├── team-lead.md        # Orchestrator (Opus)
│   │   ├── builder.md          # Feature builder (Sonnet x3)
│   │   ├── tester.md           # Test & verify (Sonnet)
│   │   ├── mock-generator.md   # Mock/fixture gen (Sonnet + Ollama)
│   │   └── reporter.md         # Docs & screenshots (Sonnet)
│   ├── skills/                 # Custom skills (pipeline stages)
│   │   ├── parse-requirements/
│   │   │   └── SKILL.md
│   │   ├── scaffold-project/
│   │   │   └── SKILL.md
│   │   ├── generate-mocks/
│   │   │   └── SKILL.md
│   │   ├── build-feature/
│   │   │   └── SKILL.md
│   │   ├── visual-verify/
│   │   │   └── SKILL.md
│   │   ├── run-tests/
│   │   │   └── SKILL.md
│   │   ├── harden/
│   │   │   └── SKILL.md
│   │   └── deliver/
│   │       └── SKILL.md
│   ├── commands/               # User-invocable slash commands
│   │   ├── build.md            # /build <requirements-path>
│   │   ├── status.md           # /status — check build progress
│   │   └── deliver.md          # /deliver — generate final report
│   └── teams/                  # Team configurations (auto-managed)
├── .mcp.json                   # MCP server connections
├── CLAUDE.md                   # Project instructions for all agents
└── AGENTS.md                   # Agent topology documentation
```

## settings.json

```json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  },
  "permissions": {
    "allow": [
      "Bash(git *)",
      "Bash(gh *)",
      "Bash(docker *)",
      "Bash(docker compose *)",
      "Bash(npm *)",
      "Bash(npx *)",
      "Bash(pip *)",
      "Bash(python *)",
      "Bash(pytest *)",
      "Bash(curl http://localhost:*)",
      "Bash(ollama *)",
      "Bash(mkdir *)",
      "Bash(cp *)",
      "Bash(ls *)",
      "Bash(cat *)",
      "Bash(playwright *)",
      "Bash(npx playwright *)",
      "Read",
      "Write",
      "Edit",
      "Glob",
      "Grep",
      "WebSearch",
      "WebFetch"
    ],
    "deny": [
      "Bash(rm -rf /)",
      "Bash(sudo *)"
    ]
  }
}
```

## .mcp.json

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@playwright/mcp@latest"],
      "env": {}
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@anthropic-ai/mcp-server-github"],
      "env": {}
    },
    "test-crafter": {
      "type": "http",
      "url": "http://localhost:16630/mcp",
      "headers": {}
    },
    "visual-designer": {
      "type": "http",
      "url": "http://localhost:12101/mcp",
      "headers": {}
    }
  }
}
```

## CLAUDE.md (Project Instructions)

```markdown
# NC Dev System

You are part of the NC Dev System — an autonomous development agent that takes
requirements and delivers tested, production-ready codebases.

## Technology Stack (Default)

- Frontend: React 19, Vite, TypeScript strict, Tailwind CSS, Zustand
- Backend: FastAPI, Python 3.12+, Pydantic v2, Motor (async MongoDB)
- Database: MongoDB (Motor driver), Redis (caching/queues)
- Testing: Playwright (E2E), Vitest (frontend unit), pytest (backend unit)
- Infrastructure: Docker Compose
- Ports: Sequential from 23000+ (never use 3000, 5000, 8000, 27017)

## AI Integration (Adapter Pattern - Mandatory)

All AI features must use the adapter pattern:
- Development: Claude CLI via subprocess
- Production: Open Router API
- Local: Ollama API (localhost:11434)

## Local Model Usage

For mock data and test fixtures, use Ollama (localhost:11434):
- Mock API responses: qwen2.5-coder:32b or qwen2.5-coder:14b
- Bulk test data: llama3.1:8b
- Screenshot analysis: qwen2.5vl:7b (pre-screen before Claude Vision)

Always try local models first, fall back to cloud only when local fails.

## Git Conventions

- Repository: Created on GitHub under the user's account
- Branch strategy: main + feature branches (nc-dev/feature-name)
- Commit format: "feat: description" / "fix: description" / "test: description"
- Worktrees: Each builder uses isolated worktree in .worktrees/

## File Organization

Generated projects follow this structure:
```
project-name/
├── frontend/           # React 19 app
│   ├── src/
│   │   ├── components/ # Shared UI components
│   │   ├── features/   # Feature-based modules
│   │   ├── pages/      # Route pages
│   │   ├── stores/     # Zustand stores
│   │   ├── services/   # API clients
│   │   ├── mocks/      # MSW mock handlers
│   │   └── tests/      # Test files alongside source
│   ├── e2e/            # Playwright E2E tests
│   └── package.json
├── backend/            # FastAPI app
│   ├── app/
│   │   ├── routers/    # API route handlers
│   │   ├── services/   # Business logic
│   │   ├── models/     # Pydantic models
│   │   ├── db/         # Database layer
│   │   └── mocks/      # API mock fixtures
│   ├── tests/          # pytest tests
│   └── requirements.txt
├── docker-compose.yml
├── .env.example
└── docs/               # Generated documentation
```

## Testing Requirements

- Every feature must have unit tests (80%+ coverage target)
- Every route must have a Playwright E2E test
- Every route must be screenshotted (desktop + mobile)
- All external APIs must be mocked
- Visual verification must pass before feature is considered done
```

## Skills Definitions

### /parse-requirements

```yaml
# .claude/skills/parse-requirements/SKILL.md
---
name: parse-requirements
description: Parse a requirements document into structured features, architecture, and API contracts
user-invocable: false
context: fork
agent: general-purpose
model: opus
---

Parse the provided requirements document and produce:

1. **features.json** — Structured list of features with:
   - name, description, priority (P0/P1/P2)
   - dependencies (which features depend on others)
   - estimated complexity (simple/medium/complex)
   - UI routes involved
   - API endpoints needed
   - External APIs required

2. **architecture.json** — System architecture with:
   - Component diagram
   - API contracts (endpoint, method, request/response schemas)
   - Database schema (collections, fields, indexes)
   - External API dependencies (URL, auth method, endpoints used)

3. **test-plan.json** — Testing strategy with:
   - E2E test scenarios per feature
   - Visual test checkpoints (which screens to screenshot)
   - Mock requirements per external API

Output these as JSON files in the project's .nc-dev/ directory.
```

### /scaffold-project

```yaml
# .claude/skills/scaffold-project/SKILL.md
---
name: scaffold-project
description: Create a new project from the NC Dev System template with Docker, tests, and mock layer
user-invocable: false
context: fork
agent: general-purpose
model: sonnet
---

Create a new project based on the architecture from .nc-dev/architecture.json:

1. Create GitHub repository: `gh repo create {name} --public --clone`
2. Generate project structure from template
3. Set up Docker Compose (app services + MongoDB + Redis)
4. Set up Playwright configuration
5. Set up MSW (Mock Service Worker) with handlers for all external APIs
6. Set up pytest fixtures for backend mocking
7. Set up factory functions for test data
8. Create initial Playwright test that visits the home route
9. Commit and push: "feat: initial scaffold with mock layer and test infrastructure"

Use templates from: /Users/nrupal/dev/yensi/dev/nc-dev-system/templates/
```

### /build-feature

```yaml
# .claude/skills/build-feature/SKILL.md
---
name: build-feature
description: Build a single feature using Codex GPT 5.3 in an isolated worktree
user-invocable: false
context: fork
agent: general-purpose
model: sonnet
---

Build the feature specified in $ARGUMENTS using Codex CLI:

1. Read the feature spec from .nc-dev/features.json
2. Create worktree: `git worktree add .worktrees/$FEATURE_NAME -b nc-dev/$FEATURE_NAME`
3. Copy CLAUDE.md and project conventions into the worktree
4. Generate the Codex prompt from feature spec + conventions
5. Spawn Codex builder:
   ```bash
   codex exec --full-auto --json \
     --cd .worktrees/$FEATURE_NAME \
     "$(cat .nc-dev/prompts/build-$FEATURE_NAME.md)" \
     -o .nc-dev/codex-results/$FEATURE_NAME.json &
   ```
6. Monitor Codex JSONL output for progress
7. When Codex exits:
   - Read result JSON
   - Run `git diff` in worktree to review changes
   - Run tests: `cd .worktrees/$FEATURE_NAME && npm run test && pytest`
   - If tests pass → ready for merge
   - If tests fail → retry with Codex (include error context) OR fall back to Claude Sonnet
8. Report results to Team Lead

## Fallback Strategy
- Codex failure attempt 1: Retry with error context in prompt
- Codex failure attempt 2: Switch to Claude Code Sonnet subagent for this feature
- Sonnet failure: Escalate to user
```

### /visual-verify

```yaml
# .claude/skills/visual-verify/SKILL.md
---
name: visual-verify
description: Run Playwright tests, capture screenshots, and verify with AI vision
user-invocable: false
context: fork
agent: tester
model: sonnet
---

Verify the feature specified in $ARGUMENTS:

1. Start the application: `docker compose up -d`
2. Wait for health checks to pass
3. Run Playwright E2E tests for the feature
4. Capture screenshots:
   - Desktop (1440x900) for every route
   - Mobile (375x812) for every route
   - Key interaction states (forms filled, modals open, etc.)
5. Analyze screenshots with Ollama vision (pre-screen):
   ```bash
   curl -s http://localhost:11434/api/generate -d '{
     "model": "qwen2.5vl:7b",
     "prompt": "Analyze this web app screenshot. Check for: broken layouts, overlapping text, missing images, poor contrast, unresponsive elements, empty states that should have content. Return JSON: {\"pass\": bool, \"issues\": [...]}",
     "images": ["BASE64_IMAGE"],
     "stream": false
   }'
   ```
6. If local vision flags issues → escalate to Claude Vision for confirmation
7. If Claude Vision confirms → create issue, route to builder
8. If all pass → update task status, save screenshots as baselines
```

### /deliver

```yaml
# .claude/skills/deliver/SKILL.md
---
name: deliver
description: Generate final delivery package with screenshots, docs, and build report
user-invocable: true
argument-hint: "[project-path]"
---

Generate the delivery package for the completed project:

1. Capture final screenshots of ALL routes (desktop + mobile)
2. Generate usage documentation:
   - Feature-by-feature walkthrough with screenshots
   - API endpoint documentation
   - Setup instructions (Docker, env vars)
3. Generate build report:
   - Features implemented (list with status)
   - Test results (pass/fail counts, coverage %)
   - Known limitations
   - Mocked APIs documentation
   - Screenshots gallery
4. Push docs to repository
5. Create summary message for the user with:
   - Repository URL
   - Key screenshots (inline)
   - Quick start instructions
   - Test results summary
```

## Slash Commands (User-Invocable)

### /build

```yaml
# .claude/commands/build.md
---
name: build
description: Start an autonomous build from a requirements document
argument-hint: "<path-to-requirements.md>"
---

Start the NC Dev System autonomous build pipeline.

## Input
- Requirements document at: $ARGUMENTS

## Process
1. Read and parse the requirements document
2. Extract features, architecture, and test plan
3. Ask clarifying questions if requirements are ambiguous
4. Create GitHub repository
5. Scaffold project with mock layer
6. Build features in parallel (3 builders)
7. Test and verify each feature (Playwright + AI vision)
8. Iterate on failures
9. Harden (error handling, responsive, accessibility)
10. Generate delivery report with screenshots
11. Push everything to GitHub
12. Report back with results

## Output
- GitHub repository URL
- Screenshot gallery
- Usage documentation
- Build report
- Test results

Begin by reading the requirements file and asking any clarifying questions.
```

### /status

```yaml
# .claude/commands/status.md
---
name: status
description: Check the current build progress
---

Check the NC Dev System build progress:

1. Read the shared task list
2. Count: total tasks, completed, in-progress, pending, failed
3. List any blocked or failed tasks with reasons
4. Show current phase (Understand/Scaffold/Build/Test/Harden/Deliver)
5. Estimate remaining work

Format as a concise status report.
```

## Remote Interaction

### Triggering Builds Remotely

Option 1: Claude Code Web (claude.ai/code)
```
& Build the project from requirements at /path/to/requirements.md using NC Dev System
```

Option 2: Claude Code CLI remote mode
```bash
claude --remote "Read /path/to/requirements.md and build the project using the NC Dev System pipeline"
```

Option 3: Claude Code Remote (community tool — webhook-based)
```
# Configure Discord/Slack/Email webhook
# Send message: "Build /path/to/requirements.md"
# Receive results back in the same channel
```

Option 4: Programmatic via Agent SDK
```python
from claude_agent_sdk import query, ClaudeAgentOptions

async for message in query(
    prompt="Build the project from requirements.md using NC Dev System pipeline",
    options=ClaudeAgentOptions(
        cwd="/path/to/nc-dev-system",
        allowed_tools=["Read", "Write", "Edit", "Bash", "Glob", "Grep", "Task"],
        model="opus"
    )
):
    if hasattr(message, 'result'):
        print(message.result)  # Final delivery report
```

### Receiving Results

The Reporter agent generates and sends:

1. **Inline in the conversation**: Key screenshots, repository URL, quick summary
2. **In the repository**: Full docs/ folder with:
   - `docs/usage-guide.md` — Feature walkthrough with screenshots
   - `docs/screenshots/` — All captured screenshots
   - `docs/build-report.md` — Comprehensive build report
   - `docs/api-docs.md` — API documentation
   - `docs/mock-docs.md` — Mock layer documentation
3. **GitHub PR** (optional): If building on an existing repo, creates a PR with all changes

### Notification Flow

```
Build completes
    │
    ├──→ Reporter generates docs + screenshots
    │
    ├──→ Push to GitHub
    │
    ├──→ Team Lead composes summary message:
    │     "Build complete for [Project Name]
    │      Repository: https://github.com/user/project
    │      Features: 8/8 implemented, 7/8 tests passing
    │      Screenshots: [inline gallery]
    │      Known issues: [list]
    │      To run: docker compose up -d && open http://localhost:23000"
    │
    └──→ Delivered via:
          ├── Claude Code Web → appears in conversation
          ├── Claude Code Terminal → printed to stdout
          ├── Claude Code Remote → sent to Discord/Slack/Email
          └── Agent SDK → returned as final message
```
