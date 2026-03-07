# NC Dev System - V2 Control Plane Spec

## Status

This document defines the V2 direction for NC Dev System.

It supersedes the V1 assumption that NC Dev System should be a heavy autonomous framework with custom team orchestration. V2 treats NC Dev System as an opinionated control plane that coordinates native Claude Code and Codex capabilities, generates target-project artifacts, and enforces design, testing, and delivery standards.

## Why V2

The surrounding ecosystem has changed:

- Claude Code now provides native primitives such as slash commands, subagents via `/agents`, hooks, MCP integration, and SDK surfaces.
- Codex has become a stronger implementation engine and should be used as the default code builder rather than wrapped in a large custom runtime.
- Existing sibling projects already cover important adjacent concerns:
  - `auto-coder` - worktree safety, spec artifacts, merge governance
  - `test-craftr` - evidence-rich QA and issue packages
  - `visual-designer` - design variation generation and agent-oriented export
  - `prd-agent` - upstream discovery and requirement shaping

V2 exists to avoid rebuilding commodity orchestration while preserving the durable value that is specific to Yensi's workflow.

## Product Definition

NC Dev System V2 is an opinionated product-build control plane that:

1. Ingests source material such as PRDs, repos, URLs, screenshots, transcripts, or call flows.
2. Performs discovery, market research, and UX analysis when those artifacts do not already exist.
3. Produces a machine-readable design pack before implementation starts.
4. Plans implementation and testing using Claude Code.
5. Delegates implementation and test authoring into the target project to Codex by default.
6. Boots a local harness for the target project and runs evidence-producing verification.
7. Delivers a target project plus artifacts, not just source code.

## Non-Goals

V2 does not attempt to:

- build a generic agent runtime
- reimplement Claude Code Teams or subagents
- own a separate long-lived task/state framework unless native tooling is insufficient
- keep tests, mocks, or feature code inside `nc-dev-system`
- be limited to web-only projects

## What NC Dev System Owns

NC Dev System owns:

- source ingestion and normalization
- discovery and research workflows
- design direction and design pack generation
- target-project scaffolding contracts
- provider/model routing policy
- build batch generation
- verification policy and evidence contracts
- release gates and delivery packaging

NC Dev System does not own:

- generic low-level agent scheduling
- provider-specific agent UX
- target-project business logic

## Lessons Carried Forward

### From `auto-coder`

Keep:

- artifact-oriented workflow with `requirements`, `context`, `implementation_plan`, `qa_report`, and fix requests
- worktree isolation
- local-first merge review
- conflict-only AI merge handling
- file-based memory as the default memory layer

Do not carry forward:

- a large custom orchestration runtime
- framework-specific task board semantics as a hard dependency

### From `test-craftr`

Keep:

- PRD-derived flow extraction
- issue packages containing screenshots, console logs, network traces, and expected vs actual behavior
- promotion of discovered issues into verification and regression tests

Do not carry forward:

- a separate ownership model for tests; generated tests belong in the target project

### From `visual-designer`

Keep:

- journey to layout to asset to composition to screenshot pipeline
- design variation generation
- agent-spec export
- multi-provider abstraction pattern

Do not carry forward:

- any assumption that design is optional or post-build

### From `claude-tools`

Keep as concepts:

- context broker
- verifier
- stuck-task recovery

Do not carry forward:

- custom team/orchestrator runtime as the default operating model

## Core Architecture

V2 is split into six layers.

### 1. Ingress Layer

Accepted inputs:

- requirements markdown
- existing repositories
- app URLs
- screenshots
- exported support conversations
- call recordings and transcripts
- app store descriptions
- design references

The output of ingress is a normalized `source-pack.json`.

### 2. Discovery Layer

The discovery layer decides whether a project already has enough product definition.

If high-quality discovery artifacts already exist, the layer validates them for freshness and completeness.

If they do not exist, the layer generates:

- `market-research.json`
- `user-segments.json`
- `pain-points.json`
- `feature-map.json`
- `ux-principles.json`
- `platform-recommendation.json`
- `architecture-brief.json`

Discovery must be able to operate on:

- greenfield ideas
- partially specified projects
- brownfield repositories

### 3. Design Layer

Design is a first-class stage.

Inputs:

- feature map
- UX principles
- user segments
- pain points
- reference screenshots or competitor references

Outputs:

- `design-brief.json`
- `theme-tokens.json`
- `component-specs.json`
- `layout-rules.json`
- `motion-rules.json`
- `reference-screens/`
- `agent-spec.json`

The design layer must support multiple design directions for the same product, such as:

- gloss
- electric
- editorial
- premium enterprise
- minimal luxury
- neo-brutalist

The selected design direction becomes part of the target-project contract and is implemented through theme tokens and composition rules rather than entangled business logic.

### 4. Planning Layer

The planning layer is primarily a Claude Code responsibility.

Responsibilities:

- define change batches
- define acceptance criteria
- define risk map
- define test matrix per feature
- define delivery scope
- define fallback plan

Outputs:

- `build-plan.json`
- `test-plan.json`
- `risk-map.json`
- `change-batches/`

### 5. Build Layer

The build layer writes code into the target project.

Default builder:

- Codex

Default reviewer:

- Claude Code

Rules:

- every batch executes in an isolated git worktree
- all code lands in the target project
- all tests land in the target project
- every merge must produce a machine-readable batch result
- merge conflicts use git-first, conflict-only AI second, full-file AI fallback

### 6. Verification and Delivery Layer

The verification layer boots a local harness for the target project and generates evidence.

Outputs:

- `run-report.json`
- `evidence-index.json`
- `screenshots/`
- `videos/`
- `traces/`
- `test-results/`
- `delivery-report.json`

Human release remains the final gate.

## Native Capability Strategy

V2 must prefer native provider features over custom reimplementation.

### Claude Code

Use native Claude Code for:

- `/agents` based specialization
- slash-command workflows
- hooks for enforcement and context injection
- MCP integrations
- `/model` switching or equivalent provider-level model selection
- SDK-driven automation where terminal invocation is insufficient

### Codex

Use Codex for:

- implementation
- test implementation
- fix loops
- code transformations and refactors

Reasoning effort should be treated as a routing knob rather than a hardcoded constant.

### Future Providers

Gemini CLI or other providers should slot in via the same adapter contract, not by adding one-off branches through the engine.

## Provider Adapter Architecture

V2 must route by capabilities, not by hardcoded model names.

### Adapter Interface

Each provider adapter must implement:

- `name()`
- `healthcheck()`
- `version_info()`
- `available_models()`
- `capabilities(model)`
- `run_task(task_type, artifact_path, options)`
- `supports_feature(feature_name)`

### Capability Schema

Capabilities must include:

- planning
- implementation
- test_planning
- test_implementation
- code_review
- image_input
- audio_input
- video_input
- shell_execution
- mcp
- subagents
- hooks
- structured_output
- reasoning_effort_levels
- long_context
- snapshot_support

### Initial Adapters

Initial adapters:

- `anthropic_claude_code`
- `openai_codex`
- `gemini_cli` (disabled by default)
- `local_ollama`
- `visual_designer`
- `test_craftr`

## Task Taxonomy

V2 must normalize work into stable task types.

Core task types:

- `source_ingest`
- `repo_analysis`
- `market_research`
- `feature_extraction`
- `ux_analysis`
- `design_brief`
- `design_reference_generation`
- `scaffold_project`
- `build_batch`
- `test_plan_generation`
- `test_authoring`
- `qa_sweep`
- `issue_triage`
- `fix_batch`
- `delivery_pack`

Routing uses task type plus provider capability plus user policy.

## Artifact Contracts

Every stage must read and write versioned artifacts.

Common artifact fields:

- `version`
- `generated_at`
- `generator`
- `schema_id`
- `source_inputs`
- `content`

Minimum artifact set:

- `source-pack.json`
- `research-pack.json`
- `feature-map.json`
- `design-pack.json`
- `build-plan.json`
- `test-plan.json`
- `batch-result.json`
- `run-report.json`
- `evidence-index.json`
- `delivery-report.json`

Artifacts are the integration boundary between stages and providers.

## Target Project Contract

All product code, tests, mocks, and harness scripts are generated into the target project.

NC Dev System must only produce:

- orchestration artifacts
- metadata
- evidence
- delivery reports

### Web Targets

Generate into target project:

- frontend and backend code
- unit tests
- integration tests
- Playwright tests
- visual baseline support
- docker compose
- run scripts
- mock services or fixtures

### Mobile Targets

Generate into target project:

- app code
- platform-specific test harnesses
- screenshot flows
- simulator/emulator scripts

The exact harness depends on the selected mobile stack.

### Telephony and AI Targets

Generate into target project:

- fixture packs
- simulation scripts
- evaluation datasets
- regression suites
- scoring harnesses

## Verification Architecture

Verification is evidence-first.

Every target project must support:

- unit tests
- contract tests
- integration tests
- functional tests
- E2E tests
- visual checks
- accessibility checks
- performance checks

Optional domain-specific verification includes:

- AI evaluation
- media input testing
- telephony simulation
- mobile device/simulator coverage

### Evidence Package

Every run should collect:

- screenshots
- trace files
- videos where supported
- console logs
- network traces
- failing selectors or assertions
- structured issue bundles

Issue bundles should be compatible with Test Craftr style evidence and should be reusable as fix requests.

## Design System Contract

The design stage must enforce separation between:

- business logic
- interaction behavior
- design tokens
- screen composition

This ensures that design can be changed later without breaking features or UX.

Every design pack should include:

- typography system
- color tokens
- spacing tokens
- radius and shadow tokens
- iconography rules
- motion guidance
- page shell rules
- component density rules

## Hooks Strategy

Claude Code hooks should be used for policy enforcement instead of building custom enforcement loops into prompts.

Recommended hooks:

- `UserPromptSubmit` - attach current project run context
- `PreToolUse` - block unsafe shell or file operations
- `PostToolUse` - run lightweight validation after edits
- `SubagentStop` - verify expected artifacts were produced
- `Stop` - require required evidence before concluding a run

## Routing Policy

Default routing policy:

- discovery -> Claude Code
- market research -> Claude Code
- design brief -> Claude Code + Visual Designer
- implementation -> Codex
- test authoring -> Codex
- review and adjudication -> Claude Code
- visual analysis escalation -> Claude Code
- bulk fixture generation -> local models where adequate

Fallbacks should be configurable in user policy.

## Configuration Model

V2 should move from simple model-command config to a provider-capability config.

Illustrative structure:

```yaml
providers:
  anthropic_claude_code:
    enabled: true
    preferred_models:
      planning: "opus"
      review: "sonnet"
    features:
      use_subagents: true
      use_hooks: true
      use_mcp: true

  openai_codex:
    enabled: true
    preferred_models:
      implementation: "gpt-5.2-codex"
      test_implementation: "gpt-5.2-codex"
    defaults:
      reasoning_effort: "high"

  gemini_cli:
    enabled: false

routing:
  discovery: ["anthropic_claude_code"]
  planning: ["anthropic_claude_code"]
  implementation: ["openai_codex"]
  test_authoring: ["openai_codex"]
  review: ["anthropic_claude_code"]
  second_opinion: ["anthropic_claude_code", "openai_codex"]

quality_gates:
  require_local_harness: true
  require_artifacts: true
  require_human_release: true
```

## Capability Probing and Upgrades

To stay current with provider features, NC Dev System must support capability probing.

At startup:

1. detect installed CLI versions
2. detect available model aliases
3. detect supported flags
4. detect MCP availability
5. persist a capability snapshot

Routing decisions should depend on the capability snapshot instead of fixed assumptions embedded in code.

This is how V2 remains upgrade-safe as Claude Code, Codex, and future tools evolve.

## Migration From Current Repo

### Keep

- the existing CLI entry points
- run state persistence
- dry-run support
- scaffolding concepts

### Replace or Deeply Refactor

- shallow requirements parser
- lexical consensus gate
- simplistic builder prompt generation
- simplistic test pipeline
- assumptions tied to a fixed pair of model CLIs

### Target Module Layout

```text
src/ncdev/
  adapters/
  artifacts/
  discovery/
  design/
  orchestration/
  scaffolding/
  build/
  verification/
  reporter/
```

## Delivery Contract

The final deliverable for a run is not just a repository path.

It should include:

- target project path
- build summary
- test summary
- design direction summary
- evidence index
- known limitations
- next recommended actions

## Implementation Phases

### Phase 1 - Contracts and Routing

- define artifact schemas
- define provider adapter interface
- define task taxonomy
- add capability probing
- add new config model

### Phase 2 - Discovery and Design

- implement source ingestion
- implement discovery artifact generation
- implement design brief and design pack generation
- integrate Visual Designer as a first-class source of reference outputs

### Phase 3 - Target Project Build Path

- implement scaffolders for initial target types
- implement batch generation
- improve worktree and merge governance
- route implementation to Codex through adapter layer

### Phase 4 - Verification and Evidence

- implement target harness runner
- integrate Test Craftr evidence patterns
- add screenshot, trace, and video collection
- add issue bundle generation

### Phase 5 - Domain Expansion

- telephony harnesses
- AI eval harnesses
- media input testing
- mobile target support

## Acceptance Criteria For V2

V2 is ready when:

- model/provider selection is capability-driven
- Claude Code native features replace custom team orchestration
- all generated code and tests land in target projects
- discovery, design, build, and verification all communicate through versioned artifacts
- the system can swap providers for tasks without redesign
- design packs are first-class and selectable before implementation
- verification produces reusable evidence packages

## References

- Claude Code slash commands: https://docs.anthropic.com/en/docs/claude-code/slash-commands
- Claude Code hooks: https://docs.anthropic.com/en/docs/claude-code/hooks
- Claude Code MCP: https://docs.anthropic.com/en/docs/claude-code/mcp
- Claude Code SDK overview: https://docs.anthropic.com/s/claude-code-sdk
- OpenAI GPT-5.2-Codex: https://platform.openai.com/docs/models/gpt-5.2-codex
- OpenAI latest model guidance: https://platform.openai.com/docs/guides/latest-model
- OpenAI shell tool: https://platform.openai.com/docs/guides/tools-shell
- OpenAI Docs MCP: https://platform.openai.com/docs/docs-mcp
