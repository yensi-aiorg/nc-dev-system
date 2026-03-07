# NC Dev System - Website SaaS Operating Spec

## Status

This document defines the current operating model for NC Dev System.

It narrows the practical target from a broad, multi-domain autonomous builder to a focused controller for website-based, data-intensive SaaS products. It also clarifies the execution split:

- Claude Code is the controller, planner, reviewer, and verifier.
- Codex is the primary implementation engine.
- All product code and tests are written into the target project repository, not into `nc-dev-system`.

This document should be treated as the active delivery model for near-term implementation and runtime behavior.

## Why This Narrowing Exists

The system became slower to reason about when it tried to solve too many categories at once:

- greenfield and brownfield
- web, mobile, telephony, media, and infra platforms
- discovery, design, build, verification, and release across all project shapes

The practical and valuable target is narrower:

- website-only
- data-intensive SaaS products
- local-first harness
- deterministic test and evidence loop
- minimal human prompting during execution

This is the category where Claude Code and Codex already provide strong raw capability, and where NC Dev System can add durable value through standards, orchestration, verification, and evidence packaging.

## Product Definition

NC Dev System is a thin autonomous controller for target repositories.

It does five things:

1. Reads source material and the target repository.
2. Uses Claude to determine phases, features, acceptance criteria, and test requirements.
3. Uses Codex to implement one bounded phase at a time in isolated worktrees.
4. Runs local verification with unit, integration, and Playwright evidence capture.
5. Uses Claude to review evidence and decide the next phase, repair prompt, escalation, or release recommendation.

NC Dev System is not the product repository.

## Scope

### In Scope

- website SaaS products
- dashboards, internal tools, admin systems, operator systems
- data-heavy applications with backend APIs and React frontends
- auth, CRUD, reporting, analytics dashboards, workflow systems
- products that can be booted locally and verified in a browser

### Out of Scope for the Default Mode

- native mobile apps
- telephony-first systems
- audio/video-heavy products
- broad research-only projects with no build target
- infrastructure platforms treated as a single undifferentiated app

These are not forbidden forever. They are deferred unless a project-specific controller mode is added later.

## Core Operating Model

### Claude Code Role

Claude owns:

- source ingestion and repo understanding
- requirements determination
- phase decomposition
- feature extraction
- test planning
- design direction selection
- prompt generation for Codex
- review of diffs, reports, screenshots, traces, and failures
- next-step decision making
- escalation to human only when justified

Claude is the operating intelligence of the system.

### Codex Role

Codex owns:

- implementation of bounded phases
- writing application code
- writing tests
- fixing test failures
- making changes directly inside the target repository
- operating in isolated worktrees or branches

Codex is not responsible for product direction. It is responsible for accurate implementation of Claude's prompts and the artifacts in the target repository.

### Human Role

Humans are not expected to continuously prompt during development.

Human intervention is reserved for:

- conflicting or ambiguous business requirements
- high-risk compliance or security decisions
- multiple valid product directions with no clear winner
- final release approval

## Target Repository Rule

This is a mandatory architectural rule.

- `nc-dev-system` stores orchestration metadata, prompts, logs, and evidence indexes.
- The target repository stores product code, test code, Playwright suites, screenshots, reports, and generated user-facing artifacts.

NC Dev System must work by inspecting and modifying the target repository directly.

It must not behave as though product code belongs inside `nc-dev-system`.

## Universal Project Standards

The following standards are the default baseline for every website SaaS target unless the input documents explicitly require a different stack or architecture.

These standards are derived from `/Users/nrupal/dev/yensi/dev/docs-only/technical.md` and `/Users/nrupal/dev/yensi/dev/docs-only/prompt.md`.

### Backend Standard

- Python 3.12+
- FastAPI
- MongoDB with Motor async driver
- Pydantic v2
- OpenAPI/Swagger
- pytest, pytest-asyncio, pytest-cov

### Frontend Standard

- React 19 or latest approved stable version
- Vite
- TypeScript in strict mode
- Zustand for state management
- Axios with interceptors
- Tailwind CSS
- Vitest
- React Testing Library
- Playwright for E2E

### Infrastructure Standard

- Docker Compose first
- local development via containerized services and hot reload where appropriate
- custom sequential ports starting at `23000`
- no default ports such as `3000`, `8000`, `8080`, `27017`, or `5432`

### Authentication Standard

- Keycloak is the default auth approach for products with real auth needs
- omit Keycloak only when the target is explicitly auth-free or internal enough to justify it

### AI Integration Standard

- provider adapter pattern is mandatory
- no business logic may couple directly to a specific AI provider
- provider/model selection must be configuration-driven

## Frontend Architecture Rule

This rule is strict.

- React components do not call APIs directly.
- Zustand stores own state and API actions.
- Axios is the HTTP layer and owns interceptors.

This separation must be reflected in target-repo structure, code review, and verification prompts.

## Feature-First Planning Rule

Claude must plan by user-facing feature, not by technical layer.

Wrong:

- create backend models
- build endpoints
- set up frontend
- create stores

Correct:

- user registration
- invoice workflow
- account reconciliation dashboard
- transaction import and review
- approval and audit trail flow

Each feature phase must include:

1. tests
2. implementation
3. execution of tests
4. repair until pass or escalation
5. commit/merge into the target repository

## Evidence-Heavy Verification Standard

The verification model should follow the pattern already proven in `/Users/nrupal/dev/yensi/dev/aigizmo/redact-agent`.

Playwright is not just a smoke layer. It is a primary evidence system.

### Mandatory Evidence Outputs

Every target project must emit:

- unit test results
- integration test results
- Playwright E2E results
- Playwright HTML report
- named screenshots for key user flows
- traces for retry or failure cases
- videos where appropriate for hard-to-debug interactions
- verification summary artifacts

### Screenshot Policy

Screenshots are not only for failures.

They must be captured at intentional steps across core flows, for example:

- login page
- authenticated dashboard
- feature entry state
- intermediate processing state
- completed state
- export/download state
- admin or settings state when applicable

These screenshots must be stored in the target repository using stable names so Claude can review them and downstream scripts can reuse them.

### Flow Coverage Standard

Playwright suites should cover complete business workflows, not just page presence:

- auth flow
- main feature flow
- secondary feature flow
- admin or settings flow
- error and empty states
- key permissions or redirect behavior

### Documentation Reuse

Where valuable, screenshots should support generated output such as:

- usage guides
- feature walkthroughs
- delivery summaries
- review packs

This pattern is proven by the usage-guide generation flow in `redact-agent`.

## Closed Development Loop

The loop is the heart of the system.

### Phase 0 - Ingest and Determine

Claude must:

- read all relevant documents
- inspect the target repository
- identify user-facing features
- identify constraints, dependencies, and integration points
- determine whether the project is one target or multiple deliverables

If the source describes multiple products or packages, Claude must split them into separate targets or phases rather than collapsing them into one generic app.

### Phase 1 - Plan

Claude produces:

- phase list
- feature map
- acceptance criteria
- test requirements
- design brief
- implementation prompt for the next bounded phase

### Phase 2 - Implement

Codex executes the current phase:

- in an isolated worktree
- directly against the target repository
- with tests added or updated in the target repository

### Phase 3 - Verify

The local harness runs:

- backend tests
- frontend tests
- integration tests
- Playwright tests
- screenshot capture
- trace and report collection

### Phase 4 - Review

Claude reviews:

- code change summary
- test results
- Playwright results
- screenshots
- traces and diagnostics

Claude then chooses one of:

- advance to next phase
- create a repair prompt
- re-scope the remaining phases
- escalate to human

### Phase 5 - Release Recommendation

Claude may recommend release readiness, but final release still requires explicit human approval.

## Escalation Policy

The system should not default to asking humans for help.

Escalation should happen only when:

- requirements conflict materially
- multiple product directions are equally plausible
- legal, compliance, or security judgment is required
- verification cannot distinguish whether the result is acceptable
- the local environment prevents trustworthy execution

## Website SaaS Mode Defaults

This mode should be the default runtime profile.

Defaults:

- target type: web
- stack: FastAPI + React + MongoDB
- state management: Zustand
- transport: Axios with interceptors
- local harness: Docker Compose
- auth: Keycloak by default when auth is required
- E2E: Playwright
- evidence: named screenshots, HTML report, traces, test-results artifacts

This mode is what should be used for products such as accounting SaaS, workflow systems, CRM-like apps, admin portals, and internal ops tools.

## How Keystone Fits This Model

Keystone is buildable under this model only if Claude first determines that Keystone is a multi-target program, not a single app.

Example target decomposition:

1. `keystone-sdk`
2. `keystone-react`
3. `keystone-infra`
4. `integration-demo`

Claude should decide that decomposition during Phase 0 based on the source material.

Codex should then implement each target or phase separately.

## Required Artifacts

NC Dev System should preserve at least:

- phase plan
- acceptance criteria
- per-phase prompts
- per-phase execution logs
- verification summaries
- evidence index
- release recommendation

The target repository should preserve at least:

- product code
- test code
- Playwright suites
- screenshots
- Playwright report
- traces and videos where configured
- scripts for local boot and verification

## Definition of Done

For the default website SaaS mode, a phase is done only when:

- the scoped feature is implemented in the target repository
- the required tests exist in the target repository
- the local harness executes successfully
- Playwright evidence has been produced
- Claude review does not identify unresolved blockers

A project is ready for human review only when:

- all planned phases are complete
- verification is passing
- evidence is complete
- no unresolved high-severity blockers remain

## Immediate Implementation Implication

All future work on NC Dev System should bias toward this operating model:

- target-repo first
- Claude-led phase controller
- Codex implementation engine
- website SaaS first
- feature-first planning
- evidence-heavy Playwright verification
- house stack and architecture standards by default

Anything that pulls the system back toward a generic framework without improving this loop should be treated as lower priority.
