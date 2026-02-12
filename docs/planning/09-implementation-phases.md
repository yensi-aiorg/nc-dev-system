# NC Dev System - Implementation Phases

## Overview

Build the NC Dev System itself in 5 phases, each delivering incremental value.

```
Phase A: Foundation (Week 1)
  → Claude Code project setup, skills, agents, basic pipeline
  → Can scaffold a project from requirements

Phase B: Build Engine (Week 2)
  → Multi-agent parallel building with worktrees
  → Can build features from specs

Phase C: Testing Pipeline (Week 3)
  → Playwright E2E, visual verification, mock layer
  → Can test what it builds

Phase D: Integration (Week 4)
  → Test Crafter MCP, Visual Designer MCP, local models
  → Full autonomous pipeline

Phase E: Remote & Delivery (Week 5)
  → Remote interaction, delivery reports, screenshots
  → Can be triggered remotely and reports back
```

## Phase A: Foundation

### Goal
Set up the NC Dev System project with Claude Code configuration, basic skills, and the ability to parse requirements and scaffold a project.

### Tasks

1. **Create project structure**
   ```
   mkdir nc-dev-system
   cd nc-dev-system
   git init
   mkdir -p .claude/{agents,skills,commands,teams}
   mkdir -p scripts templates prompts
   ```

2. **Write CLAUDE.md** — Project-level instructions for all agents

3. **Write agent definitions** — team-lead.md, builder.md, tester.md, reporter.md, mock-generator.md

4. **Write core skills**:
   - `parse-requirements` — Extract features from PRD
   - `scaffold-project` — Generate project from template

5. **Create project templates**:
   - `templates/scaffold-react-fastapi/` — Default project template
   - `templates/docker-compose/` — Docker infrastructure template
   - `templates/playwright-config/` — Playwright setup template

6. **Write /build command** — Entry point for autonomous builds

7. **Create setup script** — `scripts/setup.sh` that installs prerequisites

8. **Test manually** — Run `/build` with a simple requirements document, verify scaffold is created

### Definition of Done
- `claude /build requirements.md` creates a GitHub repo with scaffolded project
- Project has Docker Compose, basic React + FastAPI structure, and Playwright config
- All agents and skills are defined and loadable

---

## Phase B: Build Engine (Codex GPT 5.3 Builders)

### Goal
Enable parallel feature building using Codex CLI in git worktree isolation, managed by Claude Code.

### Tasks

1. **Install and configure Codex CLI** — `npm i -g @openai/codex`, auth with API key, set config.toml

2. **Write build-feature skill** — Spawns Codex in worktree, monitors output, handles results

3. **Configure Agent Teams** — Enable experimental agent teams, define team structure

4. **Implement Codex spawning pattern** — Team Lead runs 3 `codex exec` processes in background:
   ```bash
   # Each builder is a Codex CLI process (auth via `codex login`)
   codex exec --full-auto --json \
     --cd .worktrees/feature-a "build Feature A per spec" \
     -o .nc-dev/codex-results/feature-a.json &
   ```

5. **Implement worktree management**:
   ```bash
   git worktree add .worktrees/{feature} -b nc-dev/{feature}
   # ... Codex builds in worktree ...
   # ... Claude Code reviews, then:
   git worktree remove .worktrees/{feature}
   ```

6. **Implement Codex result parsing** — Read JSONL output, detect success/failure

7. **Implement fallback to Sonnet** — If Codex fails 2x, Claude Sonnet takes over

8. **Implement merge strategy**:
   - Standard merge first
   - If conflicts: `git merge -X theirs` (builder's version wins for non-critical files)
   - If still conflicts: escalate to Team Lead for AI resolution

9. **Test with multi-feature build** — Requirements doc with 4+ features, verify parallel Codex execution

### Definition of Done
- 3 Codex builders run in parallel on separate features (uses Codex tokens)
- Worktree isolation prevents conflicts
- Claude Code Opus reviews each Codex output before merging
- Fallback to Sonnet works when Codex fails
- Task list tracks feature status (pending → building → testing → done)

---

## Phase C: Testing Pipeline

### Goal
Every feature gets tested at 4 levels: unit, E2E, visual, and autonomous QA.

### Tasks

1. **Write run-tests skill** — Executes unit tests and Playwright E2E tests

2. **Write visual-verify skill** — Captures screenshots and analyzes with AI vision

3. **Implement Playwright test generation** — Builders create E2E tests alongside features

4. **Implement screenshot capture** — All routes, desktop + mobile viewports

5. **Implement local vision analysis** — Call Ollama Qwen2.5-VL for screenshot pre-screening

6. **Implement fix-retest loop** — Failed tests route back to Builder, then re-verify

7. **Write mock-layer template** — MSW + factory pattern scaffolded with every project

8. **Implement generate-mocks skill** — Uses Ollama for mock API data generation

9. **Test with visual-heavy requirements** — Build a dashboard app, verify all screenshots pass

### Definition of Done
- Every feature has unit tests + E2E tests
- Every route has desktop + mobile screenshots
- Ollama vision pre-screens screenshots (fast, free)
- Failed tests trigger fix → retest cycle
- Mock layer works with `MOCK_APIS=true`

---

## Phase D: Integration

### Goal
Connect Test Crafter, Visual Designer, and local models into the pipeline.

### Tasks

1. **Build Test Crafter MCP adapter** — Thin Python MCP server wrapping TC's REST API

2. **Build Visual Designer MCP adapter** — Thin Python MCP server wrapping VD's REST API

3. **Integrate Test Crafter into Phase 4** — After feature merges, run TC sweep

4. **Integrate Visual Designer into Phase 2** — Generate reference mockups during scaffold

5. **Implement reference comparison** — Compare Playwright screenshots against VD mockups

6. **Set up Ollama model pipeline**:
   - `scripts/setup-ollama.sh` — Download required models
   - Phase-based model switching (build → test → data configs)

7. **Implement harden skill** — Error handling, responsive, accessibility, performance

8. **Test full pipeline** — Requirements → scaffold → build → test → verify → harden

### Definition of Done
- Test Crafter runs autonomous QA sweep after build
- Visual Designer generates reference mockups
- Screenshots compared against references
- Local models generate mock data and pre-screen screenshots
- Full pipeline runs end-to-end without manual intervention

---

## Phase E: Remote & Delivery

### Goal
Trigger builds remotely, receive results with screenshots and documentation.

### Tasks

1. **Write deliver skill** — Generate usage docs, annotated screenshots, build report

2. **Implement screenshot annotation** — Numbered callouts on screenshots for docs

3. **Implement usage guide generation** — Feature-by-feature walkthrough with screenshots

4. **Implement build report generation** — Summary of everything built and tested

5. **Configure remote triggering**:
   - Claude Code Web (`& Build from requirements.md`)
   - Claude Code CLI (`claude --remote "..."`)
   - Webhook integration (optional)

6. **Implement Helyx integration** — Update project status after delivery

7. **Implement notification flow** — Delivery summary with inline screenshots

8. **Test remote build** — Trigger from claude.ai/code, receive full delivery

### Definition of Done
- Can trigger build from Claude Code Web or CLI remote mode
- Delivery includes: repo URL, screenshot gallery, usage guide, test results
- Build report documents everything built with evidence
- Helyx updated with project status

---

## Phase F: Optimization (Ongoing)

### Tasks (post-launch)

1. **Token optimization** — Measure cloud vs local usage, optimize routing
2. **Build time optimization** — Parallelize more, reduce waiting
3. **Template expansion** — Add templates for Next.js, Express, Django, etc.
4. **Memory system** — Learn from past builds to improve future ones
5. **Quality metrics** — Track build success rate, test pass rate over time
6. **Auto-retry intelligence** — Smart retry strategies based on error patterns

---

## Quick Start (After Implementation)

```bash
# One-time setup
cd /Users/nrupal/dev/yensi/dev/nc-dev-system
./scripts/setup.sh          # Install prerequisites
./scripts/setup-ollama.sh   # Download local models

# Start supporting services
docker compose -f /Users/nrupal/dev/yensi/dev/test-craftr/docker-compose.yml up -d
docker compose -f /Users/nrupal/dev/yensi/dev/visual-designer/docker-compose.yml up -d

# Run a build
cd /Users/nrupal/dev/yensi/dev/nc-dev-system
claude
> /build /path/to/requirements.md

# Or remotely
claude --remote "Build the project from /path/to/requirements.md using NC Dev System"

# Check status
claude
> /status
```

## Success Criteria

The NC Dev System is considered successful when:

1. **Given only a requirements.md**, it produces a working application
2. **All features are tested** with unit tests, E2E tests, and visual verification
3. **All external APIs are mocked** — the system runs without real API keys
4. **Screenshots and documentation** are generated automatically
5. **40%+ cloud tokens saved** via local model offloading
6. **Remote interaction works** — trigger from anywhere, receive results
7. **Build succeeds >80% of the time** for medium-complexity requirements
8. **Test coverage >80%** for generated code
9. **Visual verification passes** for all routes on desktop and mobile
10. **Delivery report** is comprehensive enough for the user to understand what was built
