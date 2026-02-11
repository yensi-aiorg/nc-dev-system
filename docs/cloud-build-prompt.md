# Claude Code Cloud Build Prompt

Copy everything below the --- line and paste it into Claude Code Cloud (claude.ai/code) or run with `claude --remote`.

---

## Context

You are building out the NC Dev System — an autonomous development agent that takes a requirements document and delivers a tested, production-ready codebase.

The project skeleton already exists at: https://github.com/yensi-aiorg/nc-dev-system

Clone it, then build out ALL the functional code so the system actually works end-to-end. The skeleton has agent definitions, skills, commands, prompts, and planning docs — but no actual implementation code yet.

## What You Must Build

### 1. Requirements Parser (Phase 1 engine)

Build a Python module at `src/parser/` that:
- Takes a markdown requirements document as input
- Extracts structured features (name, description, priority P0/P1/P2, dependencies, complexity, UI routes, API endpoints, external APIs)
- Generates `features.json`, `architecture.json`, and `test-plan.json`
- Uses Pydantic v2 models for all data structures
- Handles ambiguous requirements gracefully (flags them for clarification)

Files to create:
```
src/parser/__init__.py
src/parser/models.py          # Pydantic models: Feature, Architecture, TestPlan, APIContract, DBSchema
src/parser/extractor.py       # Core parsing logic — reads markdown, extracts structured data
src/parser/architect.py       # Generates architecture from features (API contracts, DB schema)
src/parser/test_planner.py    # Generates test plan from features (E2E scenarios, visual checkpoints)
```

### 2. Project Scaffolder (Phase 2 engine)

Build a Python module at `src/scaffolder/` that:
- Takes `architecture.json` as input
- Generates a complete project directory with React 19 + FastAPI + MongoDB + Docker
- Includes working Docker Compose config
- Includes working Playwright config
- Includes MSW mock handlers generated from API contracts
- Includes pytest fixtures generated from API contracts
- Includes factory functions for all database entities
- The generated project should actually boot with `docker compose up -d`

Files to create:
```
src/scaffolder/__init__.py
src/scaffolder/generator.py       # Main scaffolding orchestrator
src/scaffolder/templates.py       # Template rendering (use Jinja2)
src/scaffolder/docker_gen.py      # Docker Compose generation
src/scaffolder/playwright_gen.py  # Playwright config + base test generation
src/scaffolder/mock_gen.py        # MSW handler + pytest fixture generation
src/scaffolder/factory_gen.py     # Test data factory generation
```

Template files to create:
```
src/scaffolder/templates/
├── frontend/
│   ├── package.json.j2
│   ├── vite.config.ts.j2
│   ├── tsconfig.json.j2
│   ├── tailwind.config.js.j2
│   ├── index.html.j2
│   ├── src/
│   │   ├── main.tsx.j2
│   │   ├── App.tsx.j2
│   │   ├── vite-env.d.ts.j2
│   │   └── mocks/
│   │       ├── browser.ts.j2
│   │       ├── server.ts.j2
│   │       └── handlers.ts.j2
│   └── e2e/
│       └── smoke.spec.ts.j2
├── backend/
│   ├── requirements.txt.j2
│   ├── app/
│   │   ├── __init__.py.j2
│   │   ├── main.py.j2
│   │   ├── config.py.j2
│   │   ├── routers/__init__.py.j2
│   │   ├── services/__init__.py.j2
│   │   ├── models/__init__.py.j2
│   │   └── db/__init__.py.j2
│   └── tests/
│       ├── conftest.py.j2
│       └── test_health.py.j2
├── docker-compose.yml.j2
├── .env.example.j2
├── playwright.config.ts.j2
└── README.md.j2
```

### 3. Build Orchestrator (Phase 3 engine)

Build a Python module at `src/builder/` that:
- Manages git worktree creation/cleanup for parallel builders
- Generates Codex builder prompts from feature specs
- Spawns Codex CLI processes (or falls back to Claude Code Sonnet subagents)
- Monitors builder progress via JSONL output parsing
- Reviews builder output (runs tests, checks git diff)
- Merges completed features to main
- Handles the fallback strategy: Codex → Codex retry → Sonnet → escalate

Files to create:
```
src/builder/__init__.py
src/builder/worktree.py        # Git worktree management (create, cleanup, merge)
src/builder/prompt_gen.py      # Generate Codex prompts from feature specs
src/builder/codex_runner.py    # Spawn and monitor Codex CLI processes
src/builder/reviewer.py        # Review builder output (diff analysis, test running)
src/builder/fallback.py        # Fallback strategy (Codex → Sonnet → escalate)
```

### 4. Test & Verify Engine (Phase 4 engine)

Build a Python module at `src/tester/` that:
- Runs unit tests (Vitest + pytest) and collects results
- Runs Playwright E2E tests and collects results
- Captures screenshots at all routes (desktop 1440x900 + mobile 375x812)
- Analyzes screenshots with Ollama vision (Qwen2.5-VL 7B) for pre-screening
- Escalates to Claude Vision when local vision flags issues
- Compares screenshots against reference mockups (if available)
- Generates structured test results JSON
- Implements the fix-retest loop (route failures back to builders)

Files to create:
```
src/tester/__init__.py
src/tester/runner.py           # Test execution (unit + E2E + visual)
src/tester/screenshot.py       # Screenshot capture at all routes and viewports
src/tester/vision.py           # AI vision analysis (Ollama local + Claude escalation)
src/tester/comparator.py       # Compare actual vs reference screenshots
src/tester/results.py          # Test results collection and reporting
src/tester/fix_loop.py         # Fix-retest loop management
```

### 5. Hardening Engine (Phase 5)

Build a Python module at `src/hardener/` that:
- Audits error handling (missing error boundaries, unhandled promises, bare excepts)
- Checks responsive design (runs Playwright at 3 viewports)
- Runs accessibility checks (axe-core via Playwright)
- Checks performance basics (bundle size, obvious N+1 patterns)
- Generates a hardening report with issues found and fixed

Files to create:
```
src/hardener/__init__.py
src/hardener/error_audit.py      # Error handling analysis
src/hardener/responsive.py       # Responsive design verification
src/hardener/accessibility.py    # WCAG AA compliance checking
src/hardener/performance.py      # Basic performance audit
```

### 6. Delivery Engine (Phase 6)

Build a Python module at `src/reporter/` that:
- Captures final screenshots with annotation overlays
- Generates usage-guide.md (feature walkthrough with inline screenshots)
- Generates api-documentation.md (all endpoints with examples)
- Generates build-report.md (features, test results, known limitations)
- Generates mock-documentation.md (all mocked APIs with behavior)
- Generates setup-guide.md (Docker, env vars, prerequisites)

Files to create:
```
src/reporter/__init__.py
src/reporter/screenshots.py     # Final screenshot capture + annotation
src/reporter/usage_guide.py     # Usage documentation generator
src/reporter/api_docs.py        # API documentation generator
src/reporter/build_report.py    # Build report generator
src/reporter/mock_docs.py       # Mock documentation generator
```

### 7. Pipeline Orchestrator (ties everything together)

Build the main pipeline at `src/pipeline.py` that:
- Implements the full 6-phase pipeline
- Can be invoked by the `/build` command
- Manages state between phases
- Handles errors and recovery
- Reports progress at phase boundaries

Files to create:
```
src/__init__.py
src/pipeline.py               # Main pipeline orchestrator
src/config.py                 # Configuration (paths, models, ports, etc.)
src/ollama_client.py          # Ollama API wrapper (generate, vision)
src/utils.py                  # Shared utilities
```

### 8. Sample Requirements Document

Create a realistic sample requirements doc to test the system:

```
tests/fixtures/sample-requirements.md
```

This should describe a **Task Management App** with:
- User authentication (email/password)
- Task CRUD (create, read, update, delete) with priorities and due dates
- Task categories/tags
- Dashboard with task statistics
- Search and filter tasks
- Responsive design (mobile + desktop)

This is the document we'll use to test the full pipeline.

## Testing Strategy — THIS IS CRITICAL

### Layer 1: Unit Tests for NC Dev System itself

Test every module of the NC Dev System with pytest:

```
tests/
├── conftest.py                    # Shared fixtures
├── test_parser/
│   ├── test_extractor.py          # Test requirement parsing
│   ├── test_architect.py          # Test architecture generation
│   └── test_test_planner.py       # Test plan generation
├── test_scaffolder/
│   ├── test_generator.py          # Test project scaffolding
│   ├── test_docker_gen.py         # Test Docker Compose generation
│   ├── test_playwright_gen.py     # Test Playwright config generation
│   └── test_mock_gen.py           # Test mock handler generation
├── test_builder/
│   ├── test_worktree.py           # Test git worktree management
│   ├── test_prompt_gen.py         # Test Codex prompt generation
│   └── test_reviewer.py          # Test code review logic
├── test_tester/
│   ├── test_runner.py             # Test test execution
│   ├── test_screenshot.py         # Test screenshot capture
│   └── test_vision.py            # Test vision analysis
├── test_reporter/
│   ├── test_usage_guide.py        # Test docs generation
│   └── test_build_report.py       # Test report generation
└── test_pipeline.py               # Test full pipeline orchestration
```

Every test file must:
- Use pytest with proper fixtures
- Mock external dependencies (Ollama, Codex, GitHub, Docker)
- Test success cases, error cases, and edge cases
- Achieve 80%+ coverage for the module it tests

### Layer 2: Integration Test — Scaffold Validation

Create `tests/integration/test_scaffold_e2e.py` that:
1. Runs the parser on `tests/fixtures/sample-requirements.md`
2. Runs the scaffolder to generate a project in a temp directory
3. Verifies the generated project structure is correct:
   - All expected directories exist
   - `package.json` has correct dependencies
   - `requirements.txt` has correct dependencies
   - `docker-compose.yml` is valid YAML with correct services
   - `playwright.config.ts` is syntactically valid
   - MSW handlers exist for all API endpoints in the architecture
   - pytest fixtures exist for all external APIs
   - Factory functions exist for all database entities
4. Verifies the generated project can be linted:
   - TypeScript compiles without errors (`npx tsc --noEmit`)
   - Python passes syntax check (`python -m py_compile`)
5. Verifies Docker Compose config is valid: `docker compose config`

### Layer 3: Integration Test — Generated Project Boots

Create `tests/integration/test_generated_project_boots.py` that:
1. Scaffolds a project from the sample requirements
2. Runs `docker compose up -d` on the generated project
3. Waits for health checks (frontend responds on port, backend /health returns 200)
4. Verifies frontend serves HTML at the root route
5. Verifies backend API responds to /health and /api/docs
6. Tears down with `docker compose down`

This test proves the scaffolder generates a project that actually runs.

### Layer 4: Playwright E2E on Generated Project

Create `tests/integration/test_generated_project_e2e.py` that:
1. Scaffolds a project from the sample requirements
2. Boots it with Docker Compose
3. Runs the Playwright tests that were generated as part of the scaffold:
   - Smoke test: homepage loads
   - Navigation: all routes are reachable
   - API connectivity: frontend can reach backend
4. Captures screenshots at key routes (desktop + mobile)
5. Verifies screenshots are non-empty PNG files
6. Tears down

This test proves the generated project's own test suite works.

### Layer 5: Pipeline Smoke Test

Create `tests/integration/test_pipeline_smoke.py` that:
1. Runs the full pipeline (Phases 1-2 only — parse + scaffold) on sample requirements
2. Verifies all output artifacts were created:
   - `.nc-dev/features.json` exists and is valid
   - `.nc-dev/architecture.json` exists and is valid
   - `.nc-dev/test-plan.json` exists and is valid
   - Generated project directory exists with correct structure
3. This test does NOT require Codex or Docker — it tests the orchestration logic with mocked builders

### Test Configuration

Create `pyproject.toml` with:
```toml
[project]
name = "nc-dev-system"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.0",
    "jinja2>=3.1",
    "httpx>=0.27",
    "pyyaml>=6.0",
    "rich>=13.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
    "pytest-mock>=3.12",
    "pytest-timeout>=2.2",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
timeout = 120
markers = [
    "unit: Unit tests (no external deps)",
    "integration: Integration tests (may need Docker)",
    "e2e: End-to-end tests (needs Docker + browsers)",
    "slow: Tests that take >30 seconds",
]

[tool.coverage.run]
source = ["src"]
omit = ["src/scaffolder/templates/*"]

[tool.coverage.report]
fail_under = 80
show_missing = true
```

Create `tests/conftest.py` with shared fixtures:
- `tmp_project_dir` — temporary directory for generated projects (auto-cleanup)
- `sample_requirements` — path to the sample requirements.md
- `mock_ollama` — mocked Ollama API responses
- `mock_codex` — mocked Codex CLI responses
- `parsed_features` — pre-parsed features.json for tests that skip parsing
- `parsed_architecture` — pre-parsed architecture.json for tests that skip parsing

### Playwright Configuration for NC Dev System Tests

The generated projects include Playwright tests. But we also need Playwright installed in the NC Dev System itself for the integration tests. Create:

```
playwright.config.ts            # NC Dev System's own Playwright config
e2e/                            # NC Dev System's own E2E tests (test generated projects)
├── scaffold-boots.spec.ts      # Verify scaffolded project boots
├── routes-reachable.spec.ts    # Verify all generated routes load
└── screenshots-capture.spec.ts # Verify screenshot capture works
```

The `playwright.config.ts` should:
- Point to the generated project's URL (configurable via env var)
- Include Desktop Chrome + Mobile Safari projects
- Capture screenshots on every test
- Generate JSON + HTML reports

## Rules for Building

1. **Actually implement the code** — no stubs, no TODOs, no "implement later" comments. Every function must have real logic.
2. **Use Pydantic v2 throughout** — all data models must be Pydantic BaseModel with proper validation.
3. **Use async/await** — all I/O operations (file reads, HTTP calls, subprocess) should be async.
4. **Use httpx** — for all HTTP calls (Ollama, health checks, etc.).
5. **Use Rich** — for console output formatting (progress bars, tables, status).
6. **Handle errors gracefully** — every external call should have try/except with meaningful error messages.
7. **Mock all external dependencies in tests** — Ollama, Codex, Docker, GitHub. Tests must run without any external services.
8. **Make Jinja2 templates complete** — the generated project must be a real, bootable project, not a skeleton.
9. **Follow the project's CLAUDE.md conventions** strictly.
10. **Run all tests after building** — `pytest tests/ -v --tb=short` must pass before you consider the task done.

## Execution Order

1. First, clone the repo and read CLAUDE.md, AGENTS.md, and the planning docs in docs/planning/
2. Create `pyproject.toml` and install dependencies
3. Build `src/parser/` + its tests → run tests → fix until passing
4. Build `src/scaffolder/` with complete Jinja2 templates + its tests → run tests → fix until passing
5. Build `src/builder/` + its tests → run tests → fix until passing
6. Build `src/tester/` + its tests → run tests → fix until passing
7. Build `src/hardener/` + its tests → run tests → fix until passing
8. Build `src/reporter/` + its tests → run tests → fix until passing
9. Build `src/pipeline.py` + its test → run tests → fix until passing
10. Build the sample requirements doc
11. Run the integration tests (scaffold validation, boot test)
12. Run full test suite: `pytest tests/ -v --cov=src --cov-report=term-missing`
13. Fix any failures, iterate until all tests pass with 80%+ coverage
14. Install Playwright and run the E2E integration test
15. Commit and push all code

## Expected Final State

When you're done, running this should work:
```bash
# All unit tests pass
pytest tests/ -v --cov=src -m "unit"

# Integration tests pass (scaffold validation)
pytest tests/ -v -m "integration" -k "scaffold"

# Full pipeline smoke test
python -m src.pipeline tests/fixtures/sample-requirements.md --phases 1,2 --output /tmp/test-project

# The generated project at /tmp/test-project/ should have:
# - Valid Docker Compose config
# - Working React 19 frontend
# - Working FastAPI backend
# - MSW mock handlers
# - Playwright E2E tests
# - pytest unit tests
```

Begin by cloning the repo and reading the existing files to understand the full architecture.
