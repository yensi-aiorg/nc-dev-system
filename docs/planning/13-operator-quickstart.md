# NC Dev System - Operator Quickstart

## Purpose

This guide is the shortest reliable path for using NC Dev System in its current operating mode:

- website SaaS projects
- Claude-led planning and review
- Codex implementation
- target-repo-first execution
- evidence-heavy Playwright verification

Use this guide with [`12-website-saas-operating-spec.md`](./12-website-saas-operating-spec.md).

## Prerequisites

- Python 3.12+
- Node.js and npm
- `pytest`
- Claude Code CLI installed and authenticated
- Codex CLI installed and authenticated
- Docker and Docker Compose when the target project uses local services

## Recommended Inputs

You should have:

- a requirements file or planning folder
- an existing target Git repository

Examples:

- a PRD markdown file
- a docs folder containing planning and architecture docs
- a target repo with `frontend/` and `backend/`

## Setup

From the NC Dev System repository:

```bash
cd /Users/nrupal/dev/yensi/dev/nc-dev-system
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Recommended Flow

### 1. Run Discovery First

This is the safest first pass. It lets you inspect the generated phases and target contract before implementation starts.

```bash
PYTHONPATH=src python -m ncdev.cli discover-v2 \
  --source /path/to/requirements-or-doc-folder \
  --target-repo /path/to/target-repo \
  --dry-run
```

Inspect the run directory printed by the command.

Important artifacts:

- `source-pack.json`
- `feature-map.json`
- `build-plan.json`
- `phase-plan.json`
- `target-project-contract.json`

## 2. Prepare the Target Repository

This step prepares the actual target repo for the loop. It adds evidence and verification scaffolding in the target project when needed.

```bash
PYTHONPATH=src python -m ncdev.cli prepare-v2 \
  --source /path/to/requirements-or-doc-folder \
  --target-repo /path/to/target-repo
```

This should produce:

- `scaffold-manifest.json`
- `verification-contract.json`
- `job-queue.json`

The target repo will also gain or reuse:

- `docs/evidence/`
- `frontend/e2e/screenshots/`
- `scripts/run-evidence-checks.sh`

## 3. Run the Full Loop

For a real run:

```bash
PYTHONPATH=src python -m ncdev.cli full-v2 \
  --source /path/to/requirements-or-doc-folder \
  --target-repo /path/to/target-repo \
  --base-url http://localhost:23000
```

For the same run with the live terminal dashboard:

```bash
PYTHONPATH=src python -m ncdev.cli full-v2 \
  --source /path/to/requirements-or-doc-folder \
  --target-repo /path/to/target-repo \
  --base-url http://localhost:23000 \
  --ui headed
```

For a rehearsal:

```bash
PYTHONPATH=src python -m ncdev.cli full-v2 \
  --source /path/to/requirements-or-doc-folder \
  --target-repo /path/to/target-repo \
  --base-url http://localhost:23000 \
  --dry-run
```

## 4. Inspect the Run Outputs

Run outputs land under:

```text
.nc-dev/v2/runs/<run-id>/outputs/
```

The most important files are:

- `phase-plan.json`
- `job-queue.json`
- `job-run-log.json`
- `verification-run.json`
- `verification-issues.json`
- `evidence-index.json`
- `delivery-summary.json`
- `full-run-report.json`

## 5. Review the Target Repo Evidence

Inside the target repo, inspect:

- `frontend/e2e/screenshots/`
- `frontend/playwright-report/`
- `frontend/test-results/`
- `docs/evidence/`

These are the artifacts Claude should be able to review during the loop, and they are the primary material for final human review.

If you use `--ui headed`, NC Dev also renders a single live terminal dashboard showing:

- pipeline task states
- active and recent jobs
- provider/model pools acting as agent counts
- the latest log tail from job execution or verification

## Suggested Usage Pattern

### For Existing Products

Use an existing repo and let NC Dev System operate directly on it:

```bash
PYTHONPATH=src python -m ncdev.cli full-v2 \
  --source /path/to/docs \
  --target-repo /path/to/existing-repo \
  --base-url http://localhost:23000
```

### For New Products

If you do not have a real target repo yet, you can omit `--target-repo` and let the system generate one under `.nc-dev/v2/generated/`.

That is useful for prototypes, but the preferred mode is still target-repo-first.

## What the System Assumes

Default operating assumptions:

- target type is web
- backend is FastAPI
- frontend is React + Vite + TypeScript
- state management is Zustand
- transport is Axios with interceptors
- Playwright is mandatory for E2E evidence
- custom ports start at `23000`
- Docker Compose is the default local harness

If your project deviates from these assumptions, make that explicit in the source documents.

## When to Use Dry Run

Use `--dry-run` when:

- you are validating ingestion and phase decomposition
- you want to inspect generated prompts and contracts
- provider CLIs are not ready yet
- you are testing the orchestration itself

Do not use `--dry-run` to make a release decision.

## Release Expectation

The system can recommend readiness, but final release still requires human approval.

That approval should review:

- the run report
- the screenshots
- the Playwright report
- the verification issues
- the actual target-repo diff
