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

## AI Tier Architecture

- **Claude Code Opus 4.6**: Orchestrator (Team Lead), reviewer, architecture, delivery
- **OpenAI Codex GPT 5.3**: Builders (x3 parallel), feature implementation, unit tests — uses Codex tokens, NOT Claude tokens
- **Claude Code Sonnet 4.5**: Tester (Playwright + AI Vision), fallback builder if Codex fails
- **Claude Code Haiku 4.5**: Quick validation, lint checks, simple fixes
- **Ollama Local Models**: Mock data, test fixtures, bulk generation, vision pre-screening (free)

## AI Integration (Adapter Pattern - Mandatory)

All AI features in generated projects must use the adapter pattern:
- Development: Claude CLI via subprocess
- Production: Open Router API
- Local: Ollama API (localhost:11434)

## Local Model Usage

For mock data and test fixtures, use Ollama (localhost:11434):
- Mock API responses: qwen2.5-coder:32b or qwen2.5-coder:14b
- Bulk test data: llama3.1:8b
- Screenshot analysis: qwen2.5vl:7b (pre-screen before Claude Vision)

Always try local models first, fall back to cloud only when local fails.

## Build Pipeline

```
Phase 1: UNDERSTAND (Opus) — Parse requirements, extract features, design architecture
Phase 2: SCAFFOLD (Sonnet/Codex) — Create repo, generate project, set up mocks
Phase 3: BUILD (3x Codex GPT 5.3) — Parallel feature building in isolated worktrees
Phase 4: VERIFY (Sonnet) — Unit tests, E2E tests, screenshots, AI vision analysis
Phase 5: HARDEN (Sonnet/Codex) — Error handling, responsive, accessibility, performance
Phase 6: DELIVER (Opus) — Usage docs, screenshots, build report, push to GitHub
```

## Git Conventions

- Repository: Created on GitHub under the user's account or org
- Branch strategy: main + feature branches (nc-dev/feature-name)
- Commit format: "feat: description" / "fix: description" / "test: description"
- Worktrees: Each Codex builder uses isolated worktree in .worktrees/

## Codex Builder Invocation

Builders are OpenAI Codex CLI processes, NOT Claude Code agents:
```bash
OPENAI_API_KEY="${OPENAI_API_KEY}" codex exec --full-auto --json \
  --cd .worktrees/feature-name \
  "$(cat .nc-dev/prompts/build-feature-name.md)" \
  -o .nc-dev/codex-results/feature-name.json 2>&1 &
```

Fallback: If Codex fails 2x on a feature, Claude Code Sonnet takes over as subagent.

## File Organization (Generated Projects)

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
- Every route must be screenshotted (desktop 1440x900 + mobile 375x812)
- All external APIs must be mocked (MSW frontend, pytest fixtures backend)
- Visual verification must pass before feature is considered done
- Two-tier vision: Ollama Qwen2.5-VL pre-screens (fast, free) → Claude Vision escalation (accurate)

## Mocking Strategy

- Frontend: MSW (Mock Service Worker) intercepts fetch() in browser
- Backend: httpx MockTransport + pytest fixtures
- Data: Factory functions + Ollama-generated domain-specific data
- Environment: MOCK_APIS=true/false switches between mock and real APIs
- Coverage: Every external API mocked with success, error, and empty responses

## Delivery Requirements

Every completed build must include:
- GitHub repository with full source code
- Docker Compose deployment configs
- Comprehensive test suite (unit + E2E + visual)
- Mock system for all external APIs
- Screenshots (desktop + mobile) for every route
- Usage documentation with annotated screenshots
- Build report (features, test results, known limitations)
