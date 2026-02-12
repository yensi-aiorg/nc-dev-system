# NC Dev System

You are part of the NC Dev System — an autonomous development agent that takes
requirements and delivers tested, production-ready codebases.

## Technology Stack (Default)

### Backend
- **Language**: Python 3.12+
- **Framework**: FastAPI
- **Database**: MongoDB (via Motor async driver)
- **Authentication**: KeyCloak (optional — only when auth is required, with dedicated PostgreSQL)
- **API Documentation**: Auto-generated OpenAPI/Swagger
- **Validation**: Pydantic v2
- **Testing**: pytest, pytest-asyncio, pytest-cov

### Frontend
- **Framework**: React 19 (or latest stable)
- **Build Tool**: Vite
- **State Management**: Zustand (MANDATORY)
- **HTTP Client**: Axios (with interceptors — MANDATORY)
- **Styling**: Tailwind CSS
- **Testing**: Vitest, React Testing Library, Playwright (E2E)
- **Type Safety**: TypeScript (strict mode)

### Infrastructure
- **Containerization**: Docker & Docker Compose
- **Development**: Hot Module Reloading via volume mounts
- **Ports**: Custom ports only, sequential starting at 23000 (NEVER use 3000, 5000, 8000, 8080, 27017, 5432)

### Port Allocation

| Service | Port |
|---------|------|
| Frontend | 23000 |
| Backend | 23001 |
| MongoDB | 23002 |
| Redis | 23003 |
| KeyCloak | 23004 |
| KeyCloak Postgres | 23005 |

## AI Tier Architecture

- **Claude Code Opus 4.6**: Orchestrator (Team Lead), reviewer, architecture, delivery
- **OpenAI Codex GPT 5.3**: Builders (x3 parallel), feature implementation, unit tests — uses Codex tokens, NOT Claude tokens
- **Claude Code Sonnet 4.5**: Tester (Playwright + AI Vision), fallback builder if Codex fails
- **Claude Code Haiku 4.5**: Quick validation, lint checks, simple fixes
- **Ollama Local Models**: Mock data, test fixtures, bulk generation, vision pre-screening (free)

## AI Integration (Adapter Pattern - MANDATORY)

All AI features in generated projects MUST use the adapter pattern:
- **Development/Testing**: CLI-based access via Python subprocesses (NOT SDK integrations)
  - Claude CLI (Anthropic)
  - Codex CLI (OpenAI)
  - Gemini CLI (Google)
- **Production**: Open Router (multi-model access)
- **Local**: Ollama API (localhost:11434)
- **RAG**: Citex (external plug-and-play RAG system, when needed)

Requirements:
- Abstract base class/interface for all AI operations
- Concrete implementations per provider (CLI for dev/test, Open Router for production)
- Configuration-driven model/provider selection
- No direct coupling to specific AI providers in business logic
- Seamless switching between development (CLI) and production (Open Router) modes

## Local Model Usage

For mock data and test fixtures, use Ollama (localhost:11434):
- Mock API responses: qwen3-coder:30b
- Bulk test data: qwen3:8b
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
- Commit format: `feat(scope): description` / `fix(scope): description` / `test(scope): description`
- Worktrees: Each Codex builder uses isolated worktree in .worktrees/
- Small, incremental commits after each logical unit of work
- All tests must pass before committing

## Codex Builder Invocation

Builders are OpenAI Codex CLI processes, NOT Claude Code agents.
Authentication is handled by the Codex CLI itself (`codex login`), not API keys.
```bash
codex exec --full-auto --json \
  --cd .worktrees/feature-name \
  "$(cat .nc-dev/prompts/build-feature-name.md)" \
  -o .nc-dev/codex-results/feature-name.json 2>&1 &
```

Fallback: If Codex fails 2x on a feature, Claude Code Sonnet takes over as subagent.

## Generated Project Structure (MANDATORY)

Generated projects MUST follow this structure:

```
project-name/
├── docker-compose.yml          # Production
├── docker-compose.dev.yml      # Development with hot reload
├── docker-compose.test.yml     # Test environment
├── .env.example
├── .env.development
├── .env.test
├── Makefile
├── README.md
├── .github/
│   └── workflows/
│       └── ci.yml              # GitHub Actions CI/CD
│
├── backend/
│   ├── Dockerfile              # Production (multi-stage, non-root user)
│   ├── Dockerfile.dev          # Development with hot reload
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── pyproject.toml
│   │
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py             # FastAPI app with lifespan (graceful shutdown)
│   │   ├── config.py           # Pydantic Settings (env-driven)
│   │   │
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── deps.py         # Dependency injection (get_db, get_current_user)
│   │   │   ├── middleware.py   # CORS, security headers, rate limiting
│   │   │   └── v1/
│   │   │       ├── __init__.py
│   │   │       ├── router.py   # API router aggregation
│   │   │       └── endpoints/
│   │   │           ├── __init__.py
│   │   │           ├── health.py   # /health and /ready endpoints
│   │   │           ├── auth.py
│   │   │           └── [feature].py
│   │   │
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── security.py     # KeyCloak integration (when auth required)
│   │   │   ├── exceptions.py   # AppException, NotFoundException, etc.
│   │   │   └── logging.py      # Structured JSON logging
│   │   │
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── base.py         # Base MongoDB document model
│   │   │   └── [feature].py
│   │   │
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── base.py         # Base Pydantic request/response schemas
│   │   │   └── [feature].py
│   │   │
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── base.py         # BaseService(ABC, Generic[T]) with CRUD
│   │   │   └── [feature]_service.py
│   │   │
│   │   └── db/
│   │       ├── __init__.py
│   │       ├── mongodb.py      # MongoDB connection + get_database()
│   │       ├── indexes.py      # Database index creation
│   │       └── migrations/     # Seeds and migrations
│   │
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py         # Pytest fixtures (test_db, client, mock deps)
│       ├── unit/
│       │   └── test_services/
│       ├── integration/
│       │   └── test_api/
│       └── e2e/
│           └── test_workflows/
│
├── frontend/
│   ├── Dockerfile              # Production (multi-stage with nginx)
│   ├── Dockerfile.dev          # Development with HMR
│   ├── nginx.conf              # Production nginx config
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── vitest.config.ts
│   ├── playwright.config.ts
│   │
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── vite-env.d.ts
│   │   │
│   │   ├── api/
│   │   │   ├── index.ts        # Axios instance with interceptors
│   │   │   ├── endpoints.ts    # API endpoint definitions
│   │   │   └── types.ts        # API response types
│   │   │
│   │   ├── stores/
│   │   │   ├── index.ts
│   │   │   ├── useAuthStore.ts
│   │   │   └── [feature]Store.ts
│   │   │
│   │   ├── components/
│   │   │   ├── ui/             # Reusable UI (Button, Input, Modal, etc.)
│   │   │   ├── layout/         # Header, Sidebar, Footer
│   │   │   └── features/       # Feature-specific components
│   │   │
│   │   ├── pages/
│   │   │   ├── HomePage.tsx
│   │   │   ├── LoginPage.tsx
│   │   │   └── [Feature]Page.tsx
│   │   │
│   │   ├── hooks/              # Custom React hooks
│   │   ├── types/              # TypeScript type definitions
│   │   ├── utils/              # Constants, helpers, validators
│   │   ├── styles/
│   │   │   └── globals.css
│   │   │
│   │   └── mocks/
│   │       ├── browser.ts      # MSW browser setup
│   │       ├── server.ts       # MSW server setup (for tests)
│   │       └── handlers.ts     # Mock API handlers
│   │
│   ├── e2e/                    # Playwright E2E tests
│   └── tests/
│       ├── unit/
│       ├── integration/
│       └── e2e/
│
├── keycloak/                   # Only when auth is required
│   ├── Dockerfile
│   ├── realm-export.json       # Realm configuration
│   └── themes/                 # Custom themes (optional)
│
├── scripts/
│   ├── setup.sh
│   ├── seed-data.sh
│   ├── run-tests.sh
│   └── validate-system.sh
│
└── docs/                       # Generated documentation
    ├── usage-guide.md
    ├── api-documentation.md
    ├── build-report.md
    ├── mock-documentation.md
    ├── setup-guide.md
    └── screenshots/
```

## Frontend Architecture Rules (STRICTLY ENFORCED)

### The Golden Rule: Components NEVER Call APIs Directly

```
Component Layer (UI only, no API calls)
        │
        ▼
Zustand Stores (state management + API call actions)
        │
        ▼
Axios Interceptor Layer (auth headers, error handling, logging)
        │
        ▼
Backend API
```

### Zustand Store Pattern (MANDATORY)

All API calls MUST go through Zustand stores. Components consume store state and call store actions.

```typescript
// stores/useFeatureStore.ts
import { create } from 'zustand';
import { devtools } from 'zustand/middleware';
import { api } from '@/api';

interface FeatureState {
  items: Item[];
  isLoading: boolean;
  error: string | null;
  fetchItems: () => Promise<void>;
  createItem: (data: CreateItemDTO) => Promise<Item>;
}

export const useFeatureStore = create<FeatureState>()(
  devtools((set) => ({
    items: [],
    isLoading: false,
    error: null,
    fetchItems: async () => {
      set({ isLoading: true, error: null });
      try {
        const response = await api.get<Item[]>('/items');
        set({ items: response.data, isLoading: false });
      } catch (error) {
        set({ error: 'Failed to fetch items', isLoading: false });
        throw error;
      }
    },
    // ... other actions
  }), { name: 'feature-store' })
);
```

### Axios Interceptor Setup (MANDATORY)

```typescript
// api/index.ts
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:23001/api/v1';

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

// Request interceptor: auth token + request ID
// Response interceptor: 401 → redirect to login, error logging
```

## Backend Architecture Rules (STRICTLY ENFORCED)

### Service Layer Pattern (MANDATORY)

```python
# services/base.py
class BaseService(ABC, Generic[T]):
    def __init__(self, collection: AsyncIOMotorCollection):
        self.collection = collection

    async def get_by_id(self, id: str) -> Optional[T]: ...
    async def get_all(self, skip: int = 0, limit: int = 100) -> List[T]: ...
    async def create(self, data: dict) -> T: ...
    async def update(self, id: str, data: dict) -> Optional[T]: ...
    async def delete(self, id: str) -> bool: ...
```

### Dependency Injection (MANDATORY)

```python
# api/deps.py
async def get_db() -> AsyncIOMotorDatabase: ...
async def get_current_active_user(credentials, db) -> dict: ...
```

### API Endpoint Pattern

```python
# api/v1/endpoints/[feature].py
@router.get("/", response_model=List[ItemResponse])
async def list_items(
    service: Annotated[ItemService, Depends(get_item_service)],
    current_user: Annotated[dict, Depends(get_current_active_user)],
): ...
```

### Error Handling (MANDATORY)

Custom exception hierarchy:
- `AppException` — base
- `NotFoundException` — 404
- `UnauthorizedException` — 401
- `ForbiddenException` — 403

## Production Readiness (MANDATORY in generated projects)

Every generated project MUST include:

1. **Health endpoints**: `/health` (basic) and `/ready` (with DB ping)
2. **Structured logging**: JSON format in production, human-readable in dev
3. **Database indexes**: Created on startup via `db/indexes.py`
4. **Rate limiting**: slowapi on sensitive endpoints (login, signup)
5. **Graceful shutdown**: FastAPI lifespan context manager
6. **Security headers**: X-Content-Type-Options, X-Frame-Options, X-XSS-Protection
7. **CORS**: Restricted origins in production, localhost in dev
8. **Production Dockerfiles**: Multi-stage builds, non-root user
9. **CI/CD**: GitHub Actions workflow (lint → test → build → e2e)
10. **Makefile**: dev, test-all, lint-all, format-all, clean targets

## Docker Configuration

Generated projects MUST have 3 Docker Compose files:
- `docker-compose.yml` — Production
- `docker-compose.dev.yml` — Development with hot reload (volume mounts)
- `docker-compose.test.yml` — Test environment

Services:
- Frontend (Vite dev / nginx prod)
- Backend (uvicorn with reload in dev, gunicorn in prod)
- MongoDB
- Redis
- KeyCloak + Postgres (when auth required)

## Testing Requirements

- Every feature must have unit tests (80%+ coverage target)
- Every route must have a Playwright E2E test
- Every route must be screenshotted (desktop 1440x900 + mobile 375x812)
- All external APIs must be mocked (MSW frontend, pytest fixtures backend)
- Visual verification must pass before feature is considered done
- Two-tier vision: Ollama Qwen2.5-VL pre-screens (fast, free) → Claude Vision escalation (accurate)
- Tests MUST pass before any commit

### Test Pyramid
```
      E2E (Playwright) — few, critical user journeys
    Integration (pytest/vitest) — API & component integration
  Unit (pytest/vitest) — many, fast, isolated tests
```

## Mocking Strategy

- Frontend: MSW (Mock Service Worker) intercepts Axios calls in browser
- Backend: httpx MockTransport + pytest fixtures
- Data: Factory functions + Ollama-generated domain-specific data
- Environment: MOCK_APIS=true/false switches between mock and real APIs
- Coverage: Every external API mocked with success, error, and empty responses

## No Incomplete Code (STRICTLY ENFORCED)

Generated code and builder output must NEVER contain:
- TODO comments
- Placeholder implementations (`pass`, `return True # Placeholder`)
- "Coming soon" or "Not yet implemented" text
- Empty exception handlers (`except: pass`)
- Commented-out code blocks
- Hardcoded test data in production code
- console.log debugging statements
- Disabled functionality

Every file must be fully functional, syntactically correct, linted, type-checked, and tested.
If a feature cannot be completed, it must not be committed — inform the user and adjust scope.

## Delivery Requirements

Every completed build must include:
- GitHub repository with full source code
- Docker Compose deployment configs (dev + prod + test)
- Comprehensive test suite (unit + E2E + visual)
- Mock system for all external APIs
- Screenshots (desktop + mobile) for every route
- Usage documentation with annotated screenshots
- Build report (features, test results, known limitations)
- CI/CD pipeline configuration
- Makefile with standard targets
