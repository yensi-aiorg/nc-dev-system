# NC Dev System - Integration Map

## How Existing Tools Connect

```
┌─────────────────────────────────────────────────────────────────┐
│                        NC DEV SYSTEM                             │
│                   (Claude Code Teams + Skills)                   │
│                                                                  │
│  ┌──────────────┐                                               │
│  │ Team Lead    │                                               │
│  │ Orchestrator │                                               │
│  └──────┬───────┘                                               │
│         │                                                        │
│         ├──→ PHASE 1: Parse Requirements                        │
│         │    ├── Claude Code Opus (native)                      │
│         │    └── PRD Agent (optional pre-step)                  │
│         │                                                        │
│         ├──→ PHASE 2: Scaffold + Reference Mockups               │
│         │    ├── Claude Code Sonnet (scaffolding)               │
│         │    ├── Visual Designer (MCP) → reference PNGs          │
│         │    ├── Ollama Qwen 32B → mock API data                │
│         │    └── GitHub MCP → create repository                  │
│         │                                                        │
│         ├──→ PHASE 3: Build Features                             │
│         │    ├── Builder 1 (Codex GPT 5.3, worktree-1)          │
│         │    ├── Builder 2 (Codex GPT 5.3, worktree-2)          │
│         │    └── Builder 3 (Codex GPT 5.3, worktree-3)          │
│         │                                                        │
│         ├──→ PHASE 4: Test + Verify                              │
│         │    ├── Playwright MCP → E2E tests + screenshots        │
│         │    ├── Ollama Qwen2.5-VL → vision pre-screening       │
│         │    ├── Claude Vision → verification (escalation)       │
│         │    └── Test Crafter (MCP) → autonomous QA sweep        │
│         │                                                        │
│         ├──→ PHASE 5: Harden                                     │
│         │    ├── Claude Sonnet / Codex → error handling, edge cases│
│         │    ├── Playwright MCP → responsive + accessibility     │
│         │    └── Ollama → additional mock scenarios              │
│         │                                                        │
│         └──→ PHASE 6: Deliver                                    │
│              ├── Claude Code Sonnet → docs + screenshots         │
│              ├── GitHub MCP → push, README, PR                   │
│              └── Helyx API → update project status               │
└─────────────────────────────────────────────────────────────────┘
```

## Integration Details

### 1. PRD Agent → NC Dev System (Input)

PRD Agent produces structured output that NC Dev System consumes:

```
PRD Agent Output:
├── spec.md           → requirements document (NC Dev System input)
├── features.json     → structured feature list
├── user-flows/       → Mermaid diagrams of user journeys
├── ui-mockups/       → Generated UI screen mockups
└── architecture.json → Suggested tech architecture

NC Dev System reads spec.md as primary input.
Optional: If features.json and architecture.json exist, skip Phase 1 parsing.
```

Connection: File system (PRD Agent saves to project directory, NC Dev reads from there).

### 2. Visual Designer → NC Dev System (Reference Mockups)

```
NC Dev System calls Visual Designer during Phase 2:

1. Send journey description (extracted from requirements)
   POST http://localhost:12101/journey/parse

2. Generate layout variations
   POST http://localhost:12101/layout/generate

3. Capture reference screenshots
   POST http://localhost:12101/screenshot/capture

4. Save reference PNGs to project:
   .nc-dev/references/
   ├── home-desktop.png
   ├── home-mobile.png
   ├── dashboard-desktop.png
   └── ...

5. During Phase 4, compare Playwright screenshots against references.
```

MCP wrapper needed: Visual Designer needs a thin MCP adapter over its REST API.

### 3. Test Crafter → NC Dev System (QA Verification)

```
NC Dev System calls Test Crafter during Phase 4:

1. Submit test run
   test_crafter_run({
     prd_path: "requirements.md",
     target_url: "http://localhost:23000",
     analysis_level: "thorough"
   })

2. Poll status
   test_crafter_status({ run_id: "tc-run-123" })

3. Get results
   test_crafter_results({ run_id: "tc-run-123" })
   Returns: { issues: [...], quality_score: 87 }

4. Process results:
   - CRITICAL/HIGH issues → route to Builder for fix
   - MEDIUM issues → fix if time allows
   - LOW issues → document in known-issues.md
```

MCP wrapper needed: Test Crafter needs an MCP adapter over its REST API (port 16630).

### 4. Ollama → NC Dev System (Local AI)

```
NC Dev System calls Ollama for:

A. Mock data generation (Phase 2)
   POST http://localhost:11434/api/generate
   Model: qwen3-coder:30b
   → Structured JSON mock responses

B. Test fixture generation (Phase 2)
   POST http://localhost:11434/api/generate
   Model: qwen3:8b
   → Bulk realistic test data

C. Screenshot pre-screening (Phase 4)
   POST http://localhost:11434/api/generate
   Model: qwen2.5vl:7b
   Images: [base64 screenshot]
   → Visual quality assessment JSON

D. Code review pre-filter (Phase 3, optional)
   POST http://localhost:11434/api/generate
   Model: qwen3-coder:30b
   → Quick code quality check before Claude review
```

No MCP needed: Called directly via HTTP from Bash tool.

### 5. GitHub → NC Dev System (Repository Management)

```
NC Dev System uses GitHub CLI (gh) for:

Phase 1:
  gh repo create {name} --public --clone
  → Creates repository

Phase 3:
  git worktree add .worktrees/{feature} -b nc-dev/{feature}
  → Isolated build environments

Phase 6:
  git add . && git commit -m "..."
  git push origin main
  → Push final code

Optional:
  gh pr create --title "..." --body "..."
  → Create PR if building on existing repo
```

GitHub MCP server provides additional capabilities (issue management, etc.)
but gh CLI is sufficient for core operations.

### 6. Playwright → NC Dev System (Browser Automation)

```
NC Dev System uses Playwright for:

Phase 4: E2E Testing
  npx playwright test
  → Run all E2E test specs

Phase 4: Screenshot Capture
  page.screenshot({ path: '...', fullPage: true })
  → Capture every route in desktop + mobile

Phase 5: Accessibility
  @axe-core/playwright
  → WCAG compliance checking

Phase 5: Performance
  page.evaluate(() => performance.getEntries())
  → Lighthouse-like metrics

Phase 6: Annotated Screenshots
  → Screenshots with numbered callouts for docs
```

Playwright MCP server provides tool-level access for interactive testing.
Direct npx commands used for batch test execution.

### 7. Helyx → NC Dev System (Project Tracking)

```
NC Dev System updates Helyx after delivery:

POST http://localhost:15650/api/projects
{
  "name": "Task Manager",
  "status": "built",
  "github_url": "https://github.com/user/task-manager",
  "tech_stack": ["React 19", "FastAPI", "MongoDB"],
  "build_metrics": {
    "features": 8,
    "tests": 44,
    "coverage": "84%",
    "duration": "4h 23m"
  }
}
```

Optional: Helyx can also trigger builds via its AI agent system.

### 8. Citex → NC Dev System (Knowledge Base, Optional)

```
For projects that reference existing documentation:

NC Dev System queries Citex for context:
  POST http://localhost:20161/api/search
  { "query": "authentication best practices", "limit": 5 }
  → Returns relevant documentation chunks

This enriches the architecture decisions with organizational knowledge.
```

## MCP Server Setup Summary

Services that need MCP adapters:

| Service | Port | MCP Status | Priority |
|---------|------|-----------|----------|
| **Playwright** | — | Ready (npx @playwright/mcp@latest) | P0 - Critical |
| **GitHub** | — | Ready (gh CLI + MCP server) | P0 - Critical |
| **Test Crafter** | 16630 | Needs MCP adapter | P1 - Important |
| **Visual Designer** | 12101 | Needs MCP adapter | P2 - Nice to have |
| **Ollama** | 11434 | Direct HTTP (no MCP needed) | P0 - Critical |
| **Helyx** | 15650 | Direct HTTP (no MCP needed) | P3 - Optional |
| **Citex** | 20161 | Direct HTTP (no MCP needed) | P3 - Optional |

### Test Crafter MCP Adapter (to build)

Thin wrapper over Test Crafter's REST API:

```python
# test-crafter-mcp/server.py
from mcp.server import Server
from mcp.types import Tool, TextContent
import httpx

TC_URL = "http://localhost:16630"
server = Server("test-crafter")

@server.tool()
async def test_crafter_run(prd_path: str, target_url: str, analysis_level: str = "standard") -> str:
    """Start a Test Crafter test run against a target URL."""
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{TC_URL}/api/runs", json={
            "prd_path": prd_path,
            "target_url": target_url,
            "analysis_level": analysis_level
        })
    return response.text

@server.tool()
async def test_crafter_status(run_id: str) -> str:
    """Check the status of a Test Crafter run."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{TC_URL}/api/runs/{run_id}")
    return response.text

@server.tool()
async def test_crafter_results(run_id: str) -> str:
    """Get the results of a completed Test Crafter run."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{TC_URL}/api/runs/{run_id}/results")
    return response.text
```

### Visual Designer MCP Adapter (to build)

```python
# visual-designer-mcp/server.py
from mcp.server import Server
import httpx

VD_URL = "http://localhost:12101"
server = Server("visual-designer")

@server.tool()
async def generate_mockups(journey_text: str, style: str = "minimal") -> str:
    """Generate UI mockups from a journey description."""
    async with httpx.AsyncClient(timeout=120.0) as client:
        # Parse journey
        parse_resp = await client.post(f"{VD_URL}/journey/parse", json={
            "text": journey_text
        })

        # Generate layouts
        gen_resp = await client.post(f"{VD_URL}/generation/start", json={
            "journey": parse_resp.json(),
            "style": style
        })

        return gen_resp.text

@server.tool()
async def capture_mockup_screenshot(job_id: str, screen_name: str) -> str:
    """Capture a screenshot of a generated mockup."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(f"{VD_URL}/screenshot/capture", json={
            "job_id": job_id,
            "screen_name": screen_name
        })
    return response.text
```

## Dependency Graph

```
NC Dev System depends on:
│
├── REQUIRED (won't work without these)
│   ├── Claude Code CLI (orchestration, review, testing)
│   ├── Codex CLI — OpenAI GPT 5.3 (feature builders x3)
│   ├── Git + GitHub CLI (version control)
│   ├── Docker + Docker Compose (infrastructure)
│   ├── Node.js + npm (frontend builds)
│   └── Python 3.12+ (backend)
│
├── RECOMMENDED (significantly better with these)
│   ├── Ollama + models (local AI, token savings)
│   ├── Playwright (visual testing)
│   └── Test Crafter (autonomous QA)
│
└── OPTIONAL (nice to have)
    ├── Visual Designer (reference mockups)
    ├── Helyx (project tracking)
    ├── Citex (knowledge base)
    └── PRD Agent (requirements generation)
```
