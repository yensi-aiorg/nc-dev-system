# Opus-Citex-Codex Pipeline & Build Metrics

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this spec.

**Goal:** Replace the static prompt builder with an Opus-authored context ingestion layer that front-loads Citex, then give Codex lean prompts that tell it to pull what it needs from Citex at build time. Track feature effectiveness metrics across runs.

**Architecture:** Opus reads discovery artifacts + actual project code and ingests structured context into Citex (localhost:20160). Codex receives a short, focused brief per feature with Citex query instructions — it calls Citex via HTTP during its build session to retrieve whatever context it needs. Metrics are captured per-feature and per-run, stored as JSON locally and in Citex for cross-run trend analysis.

**Tech Stack:** Python 3.12+, Citex RAG API (localhost:20160), Codex CLI (GPT 5.4), Claude CLI (Opus 4.6), Pydantic v2

---

## 1. Current Problem

The prompt builder (`v3/prompt_builder.py`) is a string concatenation function. It:
- Dumps the raw spec (up to 20k chars, unfiltered)
- Lists filenames (no code content)
- Shows git log titles (no detail)
- Appends hardcoded convention boilerplate

Codex receives no architectural guidance, no actual code to integrate with, no specific file instructions. It guesses — and frequently guesses wrong, triggering repair loops.

## 2. New Architecture

```
Phase 1: DISCOVERY (unchanged)
    Claude Opus runs discovery → artifacts on disk
                    |
Phase 2: CONTEXT INGESTION (NEW)
    Claude Opus reads artifacts + actual project code
    Opus structures and ingests into Citex:
        - design brief (tokens, patterns, rules)
        - API contracts (routes, schemas, models)
        - existing code (key interfaces, services, stores)
        - feature specs (descriptions, criteria, dependencies)
        - architectural decisions and constraints
        - prior feature results (if sequential build)
                    |
Phase 3: BUILD (modified)
    For each feature:
        prompt_builder creates a LEAN prompt:
            - feature title + acceptance criteria
            - Citex API endpoint + project_id
            - query examples for context retrieval
            - verification protocol
        Codex runs with that prompt
        Codex calls Citex HTTP API as needed during build
                    |
Phase 4: METRICS (NEW)
    After each feature: record result
    After all features: compute run metrics
    Store in JSON + Citex for cross-run analysis
```

## 3. Context Ingestion Module

**File:** `src/ncdev/v3/context_ingestion.py`

### 3.1 What Opus Ingests

Opus reads discovery artifacts and the actual target project, then ingests categorized documents into Citex. Each document has a `category` tag for targeted retrieval.

| Category | Content | Source |
|----------|---------|--------|
| `design` | Full design brief — colors, typography, spacing, component rules, motion | `design-brief.json` |
| `feature_spec` | Per-feature: title, description, acceptance criteria, test requirements, dependencies | `feature-queue.json` |
| `api_contract` | Existing API routes, endpoint signatures, request/response schemas | Target project `backend/app/api/` |
| `data_model` | MongoDB collection schemas, Pydantic models, field definitions | Target project `backend/app/models/` |
| `frontend_pattern` | Existing component structure, store patterns, page layout conventions | Target project `frontend/src/` |
| `service_layer` | Backend service interfaces, dependency injection patterns | Target project `backend/app/services/` |
| `test_pattern` | Existing test structure, fixtures, conftest setup | Target project `tests/` |
| `architecture` | Stack decisions, conventions, constraints, CLAUDE.md rules | Discovery artifacts + project config |
| `prior_feature` | What the prior feature built: files created, patterns used, integration points | `StepResult` from completed features |

### 3.2 Ingestion Function

```python
def ingest_project_context(
    run_dir: Path,
    target_path: Path,
    feature_queue: FeatureQueueDoc,
    citex_api: str = "http://localhost:20160",
) -> IngestionReport:
```

This function:
1. Reads discovery artifacts from `run_dir/outputs/`
2. Reads actual code from `target_path` (key files only — models, services, routes, stores, components)
3. Calls Claude Opus to synthesize each category into a structured document
4. POSTs each document to `POST {citex_api}/api/v1/documents/ingest` with `project_id` and `category` metadata
5. Returns an `IngestionReport` listing what was ingested, document counts, and any failures

### 3.3 Opus Synthesis Call

Opus doesn't just dump raw files into Citex. It reads the code and writes a structured summary. Example for the `api_contract` category:

```
Opus reads: backend/app/api/v1/endpoints/*.py
Opus writes to Citex:
    "## API Routes
    
    ### GET /api/v1/users
    Returns: List[UserResponse] (id, email, name, role, created_at)
    Auth: requires JWT token
    
    ### POST /api/v1/users
    Body: CreateUserRequest (email: str, name: str, role: str = 'user')
    Returns: UserResponse
    Validation: email must be unique
    
    ### GET /api/v1/projects
    Returns: List[ProjectResponse] (id, title, status, owner_id, created_at)
    Auth: requires JWT token, scoped to user's projects
    ..."
```

This is what Codex retrieves when it queries "what API routes exist?" — not raw source code, but a precise contract it can implement against.

### 3.4 Incremental Ingestion

After each feature completes (pass or fail), ingest a `prior_feature` document:

```python
def ingest_feature_result(
    feature: FeatureStep,
    result: StepResult,
    target_path: Path,
    citex_api: str = "http://localhost:20160",
) -> bool:
```

This tells Citex what was built, so the next feature's Codex session can query "what did the previous feature create?" and get actual integration points.

## 4. Lean Prompt Builder

**File:** `src/ncdev/v3/prompt_builder.py` (rewrite)

### 4.1 Prompt Structure

The new prompt is short and directive. Codex is told **what** to build and **where** to find context — not given the context inline.

```markdown
# Build: {feature.title}

## Your Task
{feature.description}

## Acceptance Criteria
- {criteria_1}
- {criteria_2}
...

## Context Retrieval
You have access to a project knowledge base at http://localhost:20160.
Query it for any context you need during implementation.

### How to query
```bash
curl -s -X POST http://localhost:20160/api/v1/retrieval/query \
  -H "Content-Type: application/json" \
  -d '{"project_id": "{project_id}", "query": "your question", "limit": 5}' \
  | python3 -c "import sys,json; [print(d.get('content','')) for d in json.load(sys.stdin).get('results',[])]"
```

### What to query for
- "design tokens colors typography" — before writing any UI
- "existing API routes and schemas" — before adding endpoints
- "data models and MongoDB schemas" — before creating models
- "frontend store patterns" — before adding Zustand stores
- "prior feature {prev_feature_id} integration points" — to see what was just built
- "test patterns and fixtures" — before writing tests
- "architectural constraints and conventions" — before making structural decisions

## Verification Protocol
After implementing:
1. Run backend tests: `cd backend && python -m pytest -q`
2. Run frontend tests: `cd frontend && npx vitest run`
3. Verify backend boots: `cd backend && python -c "from app.main import app; print('OK')"`
4. Fix ALL failures before finishing.

## Rules
- READ existing code before writing new code
- Build ON TOP of what exists — do not rewrite working code
- Every file must be importable and functional
- No placeholder stubs, no TODO comments
```

### 4.2 What Changed

| Before | After |
|--------|-------|
| 20k char raw spec dump | Feature brief only (~500 chars) |
| File tree (names only) | Citex query instructions |
| Hardcoded conventions | Codex queries Citex for conventions |
| No design tokens | Codex queries Citex for design brief |
| No existing code context | Codex queries Citex for models, routes, patterns |
| No prior feature awareness | Codex queries Citex for what was just built |
| ~25k char prompt | ~2k char prompt |

## 5. Build Metrics

### 5.1 Metric Definitions

**Feature Effectiveness (FE):** Did the feature pass verification on first build, without any repair attempts?

```
FE = 1 if (status == PASSED and repair_attempts == 0) else 0
```

**First-Pass Success Rate (FPSR):** Percentage of features that passed first time in a run.

```
FPSR = count(FE == 1) / total_features * 100
```

**Repair Rate (RR):** Percentage of features that needed at least one repair.

```
RR = count(repair_attempts > 0) / total_features * 100
```

**Mean Repair Attempts (MRA):** Average repair attempts across features that needed repair.

```
MRA = sum(repair_attempts where repair_attempts > 0) / count(repair_attempts > 0)
```

**Build Efficiency (BE):** Ratio of build time to total time (build + verify + repair).

```
BE = sum(build_duration) / sum(build_duration + verify_duration) * 100
```

**Feature Throughput:** Features per hour.

```
FT = completed_features / total_run_duration_hours
```

### 5.2 Metrics Model

**File:** `src/ncdev/v3/metrics.py`

```python
class FeatureMetric(BaseModel):
    feature_id: str
    title: str
    status: str  # passed, failed
    first_pass: bool  # passed with 0 repair attempts
    repair_attempts: int
    build_duration_seconds: float
    verify_duration_seconds: float
    total_duration_seconds: float
    files_created: int
    files_modified: int
    test_results: dict  # {suite: {passed, failed, errors}}

class RunMetrics(BaseModel):
    run_id: str
    project_name: str
    started_at: str
    completed_at: str
    total_duration_seconds: float
    total_features: int
    passed_features: int
    failed_features: int
    first_pass_success_rate: float  # 0.0 - 1.0
    repair_rate: float  # 0.0 - 1.0
    mean_repair_attempts: float
    build_efficiency: float  # 0.0 - 1.0
    feature_throughput_per_hour: float
    features: list[FeatureMetric]
    builder_primary: str  # "codex" or "claude"
    builder_model: str
    citex_documents_ingested: int
    citex_queries_by_codex: int  # how many times Codex hit Citex during builds
```

### 5.3 Metrics Collection

```python
def compute_run_metrics(
    state: V3RunState,
    ingestion_report: IngestionReport | None = None,
) -> RunMetrics:
```

Called at the end of `run_v3_full()` after all features complete. Computes all metrics from `StepResult` data that already exists.

### 5.4 Metrics Storage

1. **Local JSON:** `{run_dir}/outputs/metrics.json` — immediate visibility, queryable
2. **Citex:** Stored as a `metrics` category document with the run_id — enables cross-run queries like "what's our FPSR trend over the last 10 runs?"

### 5.5 Metrics Display

After the existing V3 summary table, print a metrics panel:

```
╭─ Build Metrics ─────────────────────────────╮
│ First-Pass Success Rate:  75% (6/8)         │
│ Repair Rate:              25% (2/8)         │
│ Mean Repair Attempts:     1.5               │
│ Build Efficiency:         82%               │
│ Feature Throughput:       4.2/hr            │
│ Citex Documents Ingested: 34                │
╰─────────────────────────────────────────────╯
```

## 6. Integration Points

### 6.1 Changes to `v3/engine.py`

After discovery (Phase 1) and before building (Phase 5), add:

```python
# ── Phase 2.5: Context Ingestion ──────────────
from ncdev.v3.context_ingestion import ingest_project_context

ingestion_report = ingest_project_context(
    run_dir=run_dir,
    target_path=target_path,
    feature_queue=feature_queue,
)
```

After each feature completes, add:

```python
from ncdev.v3.context_ingestion import ingest_feature_result

ingest_feature_result(feature, result, target_path)
```

After all features complete, add:

```python
from ncdev.v3.metrics import compute_run_metrics

metrics = compute_run_metrics(state, ingestion_report)
write_json(run_dir / "outputs" / "metrics.json", metrics.model_dump(mode="json"))
```

### 6.2 Changes to `v3/step_executor.py`

Pass `project_id` to `build_feature_prompt()` so it can include Citex query instructions.

### 6.3 Changes to `v3/prompt_builder.py`

Full rewrite — replace string concatenation with the lean prompt template from Section 4.

### 6.4 Citex Dependency

Citex is **required**. It is the shared context layer between all CLI agent instances (Opus, Codex, Claude repair). Without it, agents start blind and build quality degrades.

- The pipeline checks Citex availability at startup (health check to `GET {citex_api}/api/v1/health`)
- If Citex is unreachable, the pipeline **fails fast** with a clear error: `"Citex RAG (localhost:20160) is required but unreachable. Start Citex before running ncdev full."`
- `ncdev doctor` checks Citex alongside Claude/Codex/git/node
- Citex is added to the required tools list in preflight checks

## 7. New Files

| File | Purpose | Lines (est.) |
|------|---------|-------------|
| `src/ncdev/v3/context_ingestion.py` | Opus reads project, ingests into Citex | ~250 |
| `src/ncdev/v3/metrics.py` | Metric models + compute_run_metrics | ~150 |
| `src/ncdev/v3/citex_client.py` | Thin HTTP client for Citex API | ~80 |
| `tests/test_ncdev_v3/test_context_ingestion.py` | Tests for ingestion | ~150 |
| `tests/test_ncdev_v3/test_metrics.py` | Tests for metric computation | ~100 |
| `tests/test_ncdev_v3/test_prompt_builder.py` | Tests for new lean prompts | ~80 |

## 8. Modified Files

| File | Change |
|------|--------|
| `src/ncdev/v3/engine.py` | Add context ingestion phase, metrics collection, metrics display |
| `src/ncdev/v3/step_executor.py` | Pass project_id, call ingest_feature_result after each step |
| `src/ncdev/v3/prompt_builder.py` | Full rewrite — lean prompts with Citex query instructions |
| `src/ncdev/v3/models.py` | Add IngestionReport model |

## 9. Success Criteria

The system is working when:
1. Pipeline requires Citex at startup — fails fast if unreachable
2. Codex receives prompts under 3k chars (down from ~25k)
3. Codex successfully queries Citex during builds (visible in build logs)
4. First-pass success rate is tracked and displayed after every run
5. Cross-run metrics are queryable from Citex
6. `ncdev doctor` checks Citex availability
