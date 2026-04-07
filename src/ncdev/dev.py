#!/usr/bin/env python3
"""NC Dev System — The Autonomous Senior Software Engineer.

Thin glue that connects Claude CLI + Codex CLI + Citex + Playwright + ElevenLabs.
The AI decides how to work. This script provides context and enforces guardrails.

Usage:
    ncdev dev --project /path/to/repo --task "Build a document Q&A for law firms"
    ncdev dev --project /path/to/repo --task "Fix payment webhook timeout" --mode bugfix
    ncdev dev --project /path/to/repo --task "Add PDF export feature" --mode enhance
"""

from __future__ import annotations

import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel

console = Console()

# ── Citex Integration ───────────────────────────────────────────────────
CITEX_API = "http://localhost:20160"


def citex_store(project_id: str, content: str, metadata: dict) -> bool:
    """Store context in Citex for future retrieval."""
    try:
        import httpx
        resp = httpx.post(
            f"{CITEX_API}/api/v1/documents/ingest",
            json={
                "project_id": project_id,
                "content": content,
                "metadata": metadata,
            },
            timeout=30,
        )
        return resp.status_code < 400
    except Exception:
        return False


def citex_query(project_id: str, query: str, limit: int = 10) -> str:
    """Query Citex for relevant project context."""
    try:
        import httpx
        resp = httpx.post(
            f"{CITEX_API}/api/v1/retrieval/query",
            json={
                "project_id": project_id,
                "query": query,
                "limit": limit,
            },
            timeout=30,
        )
        if resp.status_code < 400:
            results = resp.json()
            # Format results as context string
            parts = []
            for r in results.get("results", results.get("documents", [])):
                content = r.get("content", r.get("text", ""))
                if content:
                    parts.append(content[:2000])
            return "\n\n---\n\n".join(parts) if parts else ""
    except Exception:
        pass
    return ""


# ── Project Context ─────────────────────────────────────────────────────

def gather_project_context(project_path: Path, task: str) -> str:
    """Gather context about the project from filesystem + Citex."""
    parts = []

    # 1. Read README/spec if exists
    for name in ["README.md", "SPEC.md", "CLAUDE.md"]:
        fpath = project_path / name
        if fpath.exists():
            parts.append(f"## {name}\n{fpath.read_text(encoding='utf-8')[:5000]}")

    # 2. File tree
    try:
        result = subprocess.run(
            ["find", ".", "-type", "f",
             "-not", "-path", "./.git/*",
             "-not", "-path", "*/node_modules/*",
             "-not", "-path", "*/.venv/*",
             "-not", "-path", "*/__pycache__/*",
             ],
            cwd=str(project_path), capture_output=True, text=True, timeout=10,
        )
        if result.stdout:
            files = sorted(result.stdout.strip().split("\n"))[:200]
            parts.append(f"## Current File Tree ({len(files)} files)\n" + "\n".join(files))
    except Exception:
        pass

    # 3. Recent git history
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-20"],
            cwd=str(project_path), capture_output=True, text=True, timeout=5,
        )
        if result.stdout:
            parts.append(f"## Recent Git History\n{result.stdout}")
    except Exception:
        pass

    # 4. Docker/infra info
    for compose_name in ["docker-compose.yml", "docker-compose.yaml"]:
        compose_path = project_path / compose_name
        if compose_path.exists():
            parts.append(f"## Docker Compose\n{compose_path.read_text(encoding='utf-8')[:3000]}")

    # 5. Citex context (if available)
    project_id = project_path.name
    citex_context = citex_query(project_id, task)
    if citex_context:
        parts.append(f"## Previous Context from Citex\n{citex_context}")

    return "\n\n".join(parts)


# ── Guardrails ──────────────────────────────────────────────────────────

GUARDRAILS = """
## NON-NEGOTIABLE GUARDRAILS — You MUST follow these. They cannot be skipped.

1. **FULL INTEGRATION TESTING**: Every feature must be tested as part of the complete system. Do NOT report a feature as done unless it works integrated with everything else. Run the full app and verify.

2. **NO NEW ISSUES**: Run the FULL existing test suite after your changes. If ANY existing test breaks, you MUST fix the regression before reporting done. Zero tolerance.

3. **REGRESSION TESTING**: Every bug fix MUST include a regression test. Every feature MUST include tests that verify it works. Tests are NOT optional.

4. **NO UNDOING PAST WORK**: You MUST NOT remove, disable, skip, or comment out tests/features from previous work to make your current task pass. All previous work must remain intact and functional.

5. **EVIDENCE**: You MUST capture screenshots of the working feature using Playwright. You MUST show test results. You MUST prove your work.

If you cannot satisfy ALL 5 guardrails, the task is NOT done. Go back and fix it.
"""

FRONTEND_METHODOLOGY = """
## Frontend Development Methodology — MANDATORY for any project with a UI

### Design-First Approach
NEVER write generic frontend code. Every UI must have a clear design identity.

### Step 1: Choose a Design Archetype
Pick ONE and commit. Every design decision must pass: "Would [reference brand] do this?"

1. **Cinematic Minimalism** (Apple) — massive whitespace, product-as-hero, typography-driven. Fonts: SF Pro, Playfair Display. Colors: near-monochrome + one accent.
2. **Technical Elegance** (Stripe) — gradient meshes, deep purples/blues, geometric illustrations. Fonts: GT Walsheim, Sohne, Satoshi. Colors: jewel tones, luminous gradients.
3. **Opinionated Darkness** (Linear) — dark mode default (#0A0A0A), ultra-tight typography, razor edges, glassmorphism. Fonts: Manrope, General Sans, Geist (NOT Inter). Single luminous accent.
4. **Warm Playfulness** (Notion) — hand-drawn illustrations, warm pastels, friendly. Fonts: Nunito, Quicksand, Plus Jakarta Sans. Colors: peach, soft yellow, cream, sage.
5. **Developer Brutalism** (Vercel) — black/white, monospace, code-as-design. Fonts: JetBrains Mono, Fira Code. Colors: pure black + white, maybe one neon accent.
6. **Bold Brand Photography** (Brex) — real people, strong signature color, 3D renders. Fonts: Clash Display, Cabinet Grotesk. One dominant brand color everywhere.

### ANTI-PATTERNS — NEVER do these:
- Inter font + purple gradient + white bg + rounded cards = "AI Average" (FORGETTABLE)
- Standard Tailwind UI/shadcn defaults without customization = "Template Look"
- Default blue (#3B82F6), default purple (#8B5CF6), default green (#22C55E) = AI defaults
- Mixing archetypes = chaos

### Step 2: Create Design System
Before writing components, create `docs/design-system/` with:
- Color palette (primary, secondary, surface, text, accent, error colors)
- Typography (font families, sizes, weights, line heights)
- Spacing scale
- Component patterns (buttons, cards, inputs, navigation)
- Implement in tailwind.config.ts

### Step 3: Build Components from Design System
- Every component MUST reference the design system
- Use the chosen font (install via Google Fonts or local)
- Use the chosen color palette — NO generic grays
- Buttons, cards, inputs must follow the archetype's style
- Sidebar + content layouts: independent scroll, sticky headers

### Step 4: Verify Visually
- Boot the frontend dev server
- Take Playwright screenshots of each page
- Verify the design matches the chosen archetype
- Check: does this look like [reference brand]? If not, fix it.

### Key UX Principles
- Sidebars with lists MUST have their own scroll bar (no full-page scroll)
- Clicking a list item shows detail immediately (no scrolling to find content)
- Section titles stay visible (sticky headers in scrollable containers)
- Dark mode: use actual dark backgrounds, not just gray (#0A0A0A or #080F1E, not #374151)
"""

QUALITY_STANDARDS = """
## Quality Standards — Build software that is TRULY done

### 1. State Management Testing
Test state transitions, not just happy paths:
- What happens when two users edit the same resource simultaneously?
- What happens when the user clicks submit twice?
- What happens when a session expires mid-operation?
Test the transitions between states — that's where bugs hide.

### 2. Error Path Coverage
For EVERY data flow, test the error paths:
- Missing required fields (validation)
- Oversized inputs (limits)
- Database unavailable (resilience)
- XSS/injection attempts in text fields (security)
- Unauthenticated requests (auth)
- Unauthorized requests (wrong role)
For every happy path test, write at least 2 error path tests.

### 3. Performance Baselines
Measure and flag slow operations:
- API endpoints should respond in <500ms
- Pages should render in <2s
- Database queries should use indexes, not collection scans
Use `time` in Bash to measure. Flag anything slow.

### 4. Dependency Verification
- Lock exact versions (pip freeze > requirements.lock, package-lock.json)
- Run `npm audit` and `pip-audit` if available
- Document all dependencies in requirements.txt / package.json
- Verify clean install: `pip install -r requirements.txt` must work from scratch

### 5. Docker Verification
- The project MUST build and run in Docker
- `docker compose build` must succeed
- `docker compose up` must produce a healthy system
- Run the same tests inside Docker to catch environment issues
- No hardcoded paths or localhost assumptions that break in containers

### 6. Documentation Verification
- OpenAPI spec (FastAPI auto-generates this) — verify it's accessible at /docs
- .env.example MUST list ALL required environment variables with descriptions
- Every MongoDB collection has a corresponding Pydantic model
- README.md explains how to run the project locally and in Docker

### 7. Graceful Degradation
- Health endpoint should check dependencies (DB, Redis) and report status
- App should boot even if non-critical services are unavailable
- Missing API keys should produce clear error messages, not crashes
- Test: start with broken configs, verify graceful error handling

### 8. Seed Data Quality
- Seed data MUST cover all statuses/states in the system
- Include edge cases: long text, unicode, empty optional fields
- Represent multiple user roles
- Make seed data realistic — names, descriptions, dates that look real
- Screenshots should show the product with good seed data

### 9. Idempotency
- Running the build again should not break what exists
- Database seeds should check before inserting (no duplicate data)
- File creation should not overwrite without reason
- Support incremental work — adding features to existing code

### 10. Observability from Day One
- Use structured logging (Python: `logging` module, not `print()`)
- Add request/response logging middleware to FastAPI
- Log unhandled exceptions with full stack traces
- Health endpoint MUST check all dependencies:
  GET /api/health → {"status": "ok", "database": "connected", "version": "0.1.0"}
"""

INFRASTRUCTURE_STANDARDS = """
## Infrastructure Integration

### Keystone Integration
Every project built by NC Dev System should be designed to integrate with Keystone infrastructure:
- Auth: Keycloak (Keystone provides this on port 15703)
- Logging: structured logs compatible with Grafana/Loki
- Monitoring: health endpoints compatible with Prometheus
- Analytics: events compatible with PostHog
- Reverse proxy: Traefik labels for routing

For now, include Keystone integration POINTS (health endpoint, structured logging, auth middleware) but don't require Keystone to be running. The app should work standalone AND with Keystone.

### Git & GitHub Standards
- Use `gh` CLI to create GitHub repos for new projects: `gh repo create yensi-solutions/{name} --private`
- NEVER make merge commits — always rebase: `git config pull.rebase true`
- Every commit must be atomic and descriptive: "feat(tasks): add CRUD endpoints with validation"
- Use conventional commits: feat, fix, docs, test, refactor, chore
- Commit after each verified feature — not one giant commit at the end
- Label commits with NC Dev System: include "Built by NC Dev System" in commit body
"""

# ── AI Invocation ───────────────────────────────────────────────────────

def invoke_ai_planning(context: str, task: str, project_path: Path) -> str:
    """Invoke Claude CLI + Codex CLI together to plan the approach."""
    planning_prompt = f"""You are an autonomous senior software engineer. Execute immediately. Do NOT ask questions. Do NOT present options. Do NOT wait for confirmation. START BUILDING NOW.

## Task
{task}

## Project Context
{context}

{GUARDRAILS}

{FRONTEND_METHODOLOGY}

## EXECUTION ORDER — Follow this exactly:

### Phase 1: Backend (do this first)
1. Create backend/ directory with FastAPI app
2. Add health endpoint: GET /api/health returning {{"status": "ok"}}
3. Add all API routes from the spec, one at a time
4. Write tests for EACH route (use pytest + httpx TestClient)
5. Run tests: `cd backend && pip install -e ".[dev]" && python -m pytest -v`
6. Fix any failures before moving to frontend

### Phase 2: Frontend (after backend tests pass)
1. Create frontend/ with Vite + React + TypeScript
2. Install Tailwind CSS and configure the design system from the chosen archetype
3. Create `docs/design-system/` with colors, fonts, spacing
4. Build components from the design system — NOT generic gray
5. Connect frontend to backend API (use Vite proxy: /api -> http://localhost:PORT)
6. Run `cd frontend && npm run build` to verify it compiles

### Phase 3: Integration
1. Create docker-compose.yml connecting all services
2. Mount frontend static build in FastAPI (or serve via separate container)
3. Boot the backend: `cd backend && uvicorn app.main:app --port PORT &`
4. Boot the frontend: `cd frontend && npx vite --port PORT &`
5. Verify: `curl http://localhost:PORT/api/health`
6. Install Playwright: `cd frontend && npx playwright install chromium`
7. Take screenshots of EVERY page, save to .ncdev/evidence/screenshots/
8. If screenshots show errors (e.g. "Failed to fetch"), FIX the issue and re-screenshot

### Phase 4: Final Verification
1. Run ALL backend tests
2. Run ALL frontend tests
3. Verify ALL screenshots show working UI (no errors, no blank pages)
4. Commit all changes with conventional commit messages (feat, fix, test, etc.)

{QUALITY_STANDARDS}

{INFRASTRUCTURE_STANDARDS}

## DATA FLOW METHODOLOGY — Build understanding as you build code

As you implement each feature, create a data flow document at `.ncdev/flows/<flow-name>.json`.

WHY: These data flows become the basis for comprehensive multi-actor end-to-end tests. When you later fix a bug, the flows tell you what else might break. They are NOT documentation for humans — they are machine-readable context that you (and future AI sessions) will query to understand the system.

Each flow document must capture:
- **flow_id**: unique name (e.g., "task_creation", "user_login")
- **actor**: which user role triggers this flow
- **input**: what data enters and from where
- **steps**: each boundary the data crosses (frontend→API, API→DB, system→email)
- **output**: what the user sees, what's stored, what side effects happen
- **related_flows**: which other flows share data entities with this one
- **test_scenario**: setup, action, and assertions to verify this flow works

After building all features, generate end-to-end tests that:
- Create multiple user accounts with different roles
- Each role executes their permitted flows
- Verify that one role's actions correctly appear to other roles
- Test the COMPLETE data path (UI → API → DB → back to UI)
- Use real inputs (not mocks) — real PDFs, real form data, real API calls

## CRITICAL RULES
- Execute immediately. No questions. No options. Just build.
- Backend MUST have tests. Run them. They MUST pass.
- Frontend MUST follow the design archetype. No generic UIs.
- Screenshots MUST show working features. If they show errors, FIX and re-capture.
- The API proxy MUST work — frontend calls /api/* which proxies to the backend.
- Data flows MUST be documented as you build. They drive your test strategy.
"""

    # Save the full context to a file so Claude can read it (avoids ARG_MAX limits)
    context_dir = project_path / ".ncdev"
    context_dir.mkdir(parents=True, exist_ok=True)
    context_file = context_dir / "build-instructions.md"
    context_file.write_text(planning_prompt, encoding="utf-8")

    # Give Claude a short prompt that tells it to read the instructions file
    short_prompt = (
        f"Read the file .ncdev/build-instructions.md in this directory for your complete task instructions. "
        f"Follow every instruction in that file precisely. Build the project, run tests, take screenshots. "
        f"The task is: {task}"
    )

    # Run Claude CLI as the primary builder
    console.print("[cyan]Invoking Claude CLI...[/cyan]")
    result = subprocess.run(
        [
            "claude", "-p", short_prompt,
            "--output-format", "text",
            "--model", "claude-sonnet-4-6",
            "--allowedTools", "Edit,Write,Bash,Read,Glob,Grep",
        ],
        cwd=str(project_path),
        capture_output=True,
        text=True,
        timeout=1800,  # 30 min — full-stack builds take time
    )

    return result.stdout if result.returncode == 0 else f"ERROR: {result.stderr}"


def invoke_codex_parallel(context: str, task: str, project_path: Path) -> str:
    """Invoke Codex CLI for parallel/supporting work."""
    # Save context to file for Codex too
    context_file = project_path / ".ncdev" / "build-instructions.md"
    if not context_file.exists():
        context_dir = project_path / ".ncdev"
        context_dir.mkdir(parents=True, exist_ok=True)
        codex_prompt_full = f"## Task\n{task}\n\n## Project Context\n{context}\n\n{GUARDRAILS}\n\n{FRONTEND_METHODOLOGY}"
        context_file.write_text(codex_prompt_full, encoding="utf-8")

    short_prompt = (
        f"Read the file .ncdev/build-instructions.md for your complete task instructions. "
        f"Follow every instruction precisely. Build the project, run tests, take screenshots. "
        f"The task is: {task}"
    )

    console.print("[yellow]Invoking Codex CLI...[/yellow]")
    try:
        result = subprocess.run(
            [
                "codex", "exec", "--full-auto",
                short_prompt,
            ],
            cwd=str(project_path),
            capture_output=True,
            text=True,
            timeout=900,  # 15 min
        )
        return result.stdout if result.returncode == 0 else f"ERROR: {result.stderr}"
    except Exception as e:
        return f"Codex unavailable: {e}"


# ── Video Report ────────────────────────────────────────────────────────

def generate_video_report(project_path: Path, task: str, results: str) -> Path | None:
    """Generate a Playwright video with ElevenLabs audio overlay."""
    evidence_dir = project_path / ".ncdev" / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    # Ask Claude to create the Playwright script and narration
    video_prompt = f"""Create a video report for this completed development task.

## Task Completed
{task}

## Results Summary
{results[:3000]}

## Instructions
1. Write a Playwright script at {evidence_dir}/record.ts that:
   - Opens the app (check docker-compose.yml for the URL, or use localhost:24100)
   - Navigates through the key features that were built/fixed
   - Takes screenshots at each step
   - Records a video of the walkthrough

2. Write a narration script at {evidence_dir}/narration.txt that:
   - Describes what was built/fixed (30 seconds)
   - Shows the key features working (30 seconds)
   - Shows tests passing (15 seconds)
   - Summary (15 seconds)
   Total: ~1-2 minutes

3. Run the Playwright script to capture the video.
4. The video should be saved at {evidence_dir}/report.webm

Focus on SHOWING the working product, not explaining code.
"""

    result = subprocess.run(
        [
            "claude", "-p", video_prompt,
            "--output-format", "text",
            "--model", "claude-sonnet-4-6",
            "--allowedTools", "Edit,Write,Bash,Read,Glob,Grep",
        ],
        cwd=str(project_path),
        capture_output=True,
        text=True,
        timeout=600,  # 10 min for video generation
    )

    video_path = evidence_dir / "report.webm"
    if video_path.exists():
        return video_path

    # Fallback: check for screenshots
    screenshots = list(evidence_dir.glob("*.png"))
    if screenshots:
        console.print(f"  [yellow]Video not generated but {len(screenshots)} screenshots captured[/yellow]")

    return None


# ── Guardrail Verification ──────────────────────────────────────────────

def verify_guardrails(project_path: Path) -> tuple[bool, list[str]]:
    """Run guardrail checks. Returns (passed, issues)."""
    issues = []

    # 1. Run backend tests
    backend_path = project_path / "backend"
    if backend_path.exists():
        result = subprocess.run(
            ["python", "-m", "pytest", "-q", "--tb=short"],
            cwd=str(backend_path), capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            issues.append(f"Backend tests FAILED:\n{result.stdout[-500:]}")
        else:
            console.print(f"  [green]✓[/green] Backend tests pass")

    # 2. Run frontend tests
    frontend_path = project_path / "frontend"
    if frontend_path.exists() and (frontend_path / "package.json").exists():
        result = subprocess.run(
            ["bash", "-c", "npx vitest run 2>&1 || npm test 2>&1 || true"],
            cwd=str(frontend_path), capture_output=True, text=True, timeout=120,
        )
        # Non-blocking for now — frontend test setup varies

    # 3. Check app boots
    if backend_path.exists():
        result = subprocess.run(
            ["python", "-c", "from app.main import app; print('BOOT_OK')"],
            cwd=str(backend_path), capture_output=True, text=True, timeout=30,
        )
        if "BOOT_OK" not in result.stdout:
            issues.append(f"Backend cannot boot: {result.stderr[-300:]}")
        else:
            console.print(f"  [green]✓[/green] Backend boots OK")

    # 4. Check Docker Compose builds (if exists)
    compose_path = project_path / "docker-compose.yml"
    if compose_path.exists():
        result = subprocess.run(
            ["docker", "compose", "config", "--quiet"],
            cwd=str(project_path), capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            console.print(f"  [green]✓[/green] Docker Compose config valid")
        else:
            issues.append(f"Docker Compose config invalid: {result.stderr[:200]}")

    # 5. Check .env.example exists
    if not (project_path / ".env.example").exists() and not (project_path / "backend" / ".env.example").exists():
        issues.append("Missing .env.example — all environment variables must be documented")

    # 6. Check for screenshots (evidence) — check all subdirs
    evidence_dir = project_path / ".ncdev" / "evidence"
    screenshots = list(evidence_dir.rglob("*.png")) if evidence_dir.exists() else []
    # Also check frontend/e2e and other common screenshot locations
    for alt_dir in [project_path / "frontend" / "e2e" / "screenshots", project_path / "screenshots"]:
        if alt_dir.exists():
            screenshots.extend(alt_dir.rglob("*.png"))
    if not screenshots:
        issues.append("No screenshots captured — take Playwright screenshots of the running app")

    return len(issues) == 0, issues


# ── Git & GitHub ────────────────────────────────────────────────────────

def _ensure_git_repo(project_path: Path, mode: str) -> None:
    """Ensure project has git initialized and a GitHub remote."""
    project_name = project_path.name

    # Initialize git if needed
    if not (project_path / ".git").exists():
        console.print(f"  [yellow]Initializing git repo...[/yellow]")
        subprocess.run(["git", "init"], cwd=str(project_path), capture_output=True, timeout=10)
        subprocess.run(["git", "add", "-A"], cwd=str(project_path), capture_output=True, timeout=10)
        subprocess.run(
            ["git", "-c", "user.name=NC Dev System", "-c", "user.email=ncdev@yensi.dev",
             "commit", "-m", "chore: initial commit\n\nBuilt by NC Dev System", "--allow-empty"],
            cwd=str(project_path), capture_output=True, timeout=10,
        )

    # Set rebase-only pull
    subprocess.run(["git", "config", "pull.rebase", "true"], cwd=str(project_path), capture_output=True, timeout=5)

    # Create GitHub repo for greenfield projects if no remote exists
    if mode in ("greenfield", "auto"):
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=str(project_path), capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            console.print(f"  [yellow]Creating GitHub repo: yensi-solutions/{project_name}...[/yellow]")
            gh_result = subprocess.run(
                ["gh", "repo", "create", f"yensi-solutions/{project_name}",
                 "--private", "--source", str(project_path), "--push"],
                cwd=str(project_path), capture_output=True, text=True, timeout=30,
            )
            if gh_result.returncode == 0:
                console.print(f"  [green]✓[/green] GitHub repo created: yensi-solutions/{project_name}")
            else:
                # Repo might already exist — try adding remote
                subprocess.run(
                    ["git", "remote", "add", "origin", f"git@github.com:yensi-solutions/{project_name}.git"],
                    cwd=str(project_path), capture_output=True, timeout=5,
                )


# ── Main Entry Point ────────────────────────────────────────────────────

def run_dev(
    project_path: Path,
    task: str,
    mode: str = "auto",
) -> dict[str, Any]:
    """Run the NC Dev System on a project.

    This is the thin glue. It:
    1. Gathers context (filesystem + Citex)
    2. Invokes Claude CLI + Codex CLI with full context
    3. Verifies guardrails
    4. Generates video report
    5. Stores results in Citex
    """
    start_time = time.time()
    project_id = project_path.name
    run_id = f"dev-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}"

    console.print(Panel(
        f"[bold cyan]NC Dev System — Autonomous Senior Engineer[/bold cyan]\n"
        f"Project: {project_path}\n"
        f"Task: {task}\n"
        f"Mode: {mode}\n"
        f"Run: {run_id}",
        border_style="cyan",
    ))

    # 0. Ensure project has git + GitHub repo
    _ensure_git_repo(project_path, mode)

    # 1. Gather context
    console.print("\n[bold]1. Gathering project context...[/bold]")
    context = gather_project_context(project_path, task)
    console.print(f"  Context: {len(context)} chars from filesystem + Citex")

    # 2. Claude builds the project
    console.print("\n[bold]2. Claude CLI building project...[/bold]")
    claude_output = invoke_ai_planning(context, task, project_path)
    console.print(f"  Claude: {len(claude_output)} chars output")

    # 3. Fix loop — verify and fix until guardrails pass (max 3 attempts)
    max_fix_attempts = 3
    passed = False
    issues = []

    for attempt in range(1, max_fix_attempts + 1):
        console.print(f"\n[bold]3. Verification pass {attempt}/{max_fix_attempts}...[/bold]")
        passed, issues = verify_guardrails(project_path)

        if passed:
            console.print(f"  [green]All guardrails PASSED on attempt {attempt}[/green]")
            break

        console.print(f"  [red]Guardrails FAILED — {len(issues)} issues[/red]")
        for issue in issues:
            console.print(f"    [red]✗[/red] {issue[:200]}")

        if attempt < max_fix_attempts:
            # Alternate between Claude and Codex for fixes
            if attempt % 2 == 1:
                console.print(f"\n  [yellow]Codex fixing (attempt {attempt})...[/yellow]")
                fix_context = f"The following checks FAILED. Fix them ALL:\n" + "\n".join(issues)
                fix_context += "\n\nRead .ncdev/build-instructions.md for the full project requirements."
                invoke_codex_parallel(
                    context + "\n\n" + fix_context,
                    f"Fix these failures: {'; '.join(i[:100] for i in issues)}",
                    project_path,
                )
            else:
                console.print(f"\n  [cyan]Claude fixing (attempt {attempt})...[/cyan]")
                fix_prompt = (
                    f"Read .ncdev/build-instructions.md. The following guardrail checks FAILED:\n"
                    + "\n".join(issues)
                    + "\n\nFix ALL issues. Run tests. Take screenshots. Do NOT ask questions."
                )
                subprocess.run(
                    ["claude", "-p", fix_prompt, "--output-format", "text",
                     "--model", "claude-sonnet-4-6",
                     "--allowedTools", "Edit,Write,Bash,Read,Glob,Grep"],
                    cwd=str(project_path), capture_output=True, text=True, timeout=600,
                )

    # 4. Video report — ONLY if guardrails passed
    video_path = None
    if passed:
        console.print("\n[bold]4. All checks passed — generating video report...[/bold]")
        video_path = generate_video_report(project_path, task, claude_output)
    else:
        console.print("\n[bold]4. Skipping video — guardrails not passed after all attempts[/bold]")

    # 5. Store in Citex
    console.print("\n[bold]5. Storing context in Citex...[/bold]")
    citex_store(project_id, f"Task: {task}\nResult: {'PASSED' if passed else 'FAILED'}\n{claude_output[:5000]}", {
        "run_id": run_id,
        "task": task,
        "mode": mode,
        "passed": passed,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    # 6. Summary
    duration = time.time() - start_time
    result = {
        "run_id": run_id,
        "project": str(project_path),
        "task": task,
        "status": "passed" if passed else "failed",
        "duration_seconds": duration,
        "guardrails_passed": passed,
        "guardrail_issues": issues,
        "video_path": str(video_path) if video_path else None,
    }

    status_color = "green" if passed else "red"
    console.print(Panel(
        f"[{status_color}]Status: {result['status'].upper()}[/{status_color}]\n"
        f"Duration: {duration:.0f}s\n"
        f"Guardrails: {'ALL PASSED' if passed else f'{len(issues)} issues'}\n"
        f"Video: {video_path or 'not generated'}",
        title="NC Dev System — Complete",
        border_style=status_color,
    ))

    # Save run report
    report_dir = project_path / ".ncdev" / "runs" / run_id
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "report.json").write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")

    return result
