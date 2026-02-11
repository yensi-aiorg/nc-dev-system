# NC Dev System - Testing Pipeline

## Testing Philosophy

Every feature is tested at 4 levels before it's considered done:

```
Level 1: Unit Tests (Vitest + pytest)
  │ Fast, isolated, run in worktree before merge
  │
Level 2: Integration Tests (Playwright E2E)
  │ Feature-level user flows, run after merge
  │
Level 3: Visual Verification (Screenshots + AI Vision)
  │ Every route screenshotted and analyzed
  │
Level 4: Autonomous QA Sweep (Test Crafter)
  │ Full PRD-driven testing with issue generation
  │
  └──→ Feature is DONE only when all 4 levels pass
```

## Level 1: Unit Tests

### Frontend (Vitest)

Generated alongside every component:

```typescript
// src/features/auth/LoginForm.test.tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { LoginForm } from './LoginForm'
import { server } from '../../mocks/server'
import { http, HttpResponse } from 'msw'

describe('LoginForm', () => {
  it('renders email and password fields', () => {
    render(<LoginForm />)
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument()
  })

  it('submits valid credentials', async () => {
    render(<LoginForm />)
    fireEvent.change(screen.getByLabelText(/email/i), {
      target: { value: 'test@example.com' }
    })
    fireEvent.change(screen.getByLabelText(/password/i), {
      target: { value: 'password123' }
    })
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))
    // Verify mock API was called (MSW handler intercepts)
    await screen.findByText(/welcome/i)
  })

  it('shows validation errors on empty submit', async () => {
    render(<LoginForm />)
    fireEvent.click(screen.getByRole('button', { name: /sign in/i }))
    await screen.findByText(/email is required/i)
  })

  it('handles API error gracefully', async () => {
    server.use(
      http.post('/api/auth/login', () => {
        return HttpResponse.json(
          { error: 'Invalid credentials' },
          { status: 401 }
        )
      })
    )
    // ... test error state
  })
})
```

### Backend (pytest)

```python
# tests/test_auth.py
import pytest
from httpx import AsyncClient
from app.main import app

@pytest.fixture
async def client():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

@pytest.fixture
def mock_db(monkeypatch):
    """Mock MongoDB operations."""
    async def mock_find_user(email: str):
        if email == "test@example.com":
            return {"id": "1", "email": email, "name": "Test User"}
        return None
    monkeypatch.setattr("app.db.repositories.user_repo.find_by_email", mock_find_user)

class TestAuthEndpoints:
    async def test_login_success(self, client, mock_db):
        response = await client.post("/api/auth/login", json={
            "email": "test@example.com",
            "password": "password123"
        })
        assert response.status_code == 200
        assert "token" in response.json()

    async def test_login_invalid_credentials(self, client, mock_db):
        response = await client.post("/api/auth/login", json={
            "email": "wrong@example.com",
            "password": "wrong"
        })
        assert response.status_code == 401

    async def test_login_validation_error(self, client):
        response = await client.post("/api/auth/login", json={})
        assert response.status_code == 422
```

## Level 2: Playwright E2E Tests

### Configuration

```typescript
// playwright.config.ts
import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: [
    ['html', { outputFolder: 'test-results/html-report' }],
    ['json', { outputFile: 'test-results/results.json' }]
  ],
  use: {
    baseURL: process.env.BASE_URL || 'http://localhost:23000',
    trace: 'on-first-retry',
    screenshot: 'on',           // Capture on every test
    video: 'on-first-retry',    // Record video on failures
  },
  projects: [
    {
      name: 'Desktop Chrome',
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'Mobile Safari',
      use: { ...devices['iPhone 14'] },
    },
    {
      name: 'Desktop Firefox',
      use: { ...devices['Desktop Firefox'] },
    },
  ],
  webServer: {
    command: 'docker compose up -d && sleep 5',
    url: 'http://localhost:23000',
    reuseExistingServer: !process.env.CI,
    timeout: 120000,
  },
})
```

### Test Structure

```typescript
// e2e/auth/login.spec.ts
import { test, expect } from '@playwright/test'

test.describe('Login Flow', () => {
  test('should display login form', async ({ page }) => {
    await page.goto('/login')

    // Visual checkpoint
    await expect(page.getByRole('heading', { name: /sign in/i })).toBeVisible()
    await expect(page.getByLabel(/email/i)).toBeVisible()
    await expect(page.getByLabel(/password/i)).toBeVisible()

    // Screenshot for visual verification
    await page.screenshot({
      path: 'test-results/screenshots/login-form-desktop.png',
      fullPage: true
    })
  })

  test('should login successfully', async ({ page }) => {
    await page.goto('/login')
    await page.getByLabel(/email/i).fill('test@example.com')
    await page.getByLabel(/password/i).fill('password123')
    await page.getByRole('button', { name: /sign in/i }).click()

    // Wait for navigation
    await page.waitForURL('/dashboard')

    // Verify dashboard loaded
    await expect(page.getByRole('heading', { name: /dashboard/i })).toBeVisible()

    // Screenshot after login
    await page.screenshot({
      path: 'test-results/screenshots/dashboard-after-login.png',
      fullPage: true
    })
  })

  test('should show error on invalid credentials', async ({ page }) => {
    await page.goto('/login')
    await page.getByLabel(/email/i).fill('wrong@example.com')
    await page.getByLabel(/password/i).fill('wrong')
    await page.getByRole('button', { name: /sign in/i }).click()

    await expect(page.getByText(/invalid credentials/i)).toBeVisible()

    // Screenshot of error state
    await page.screenshot({
      path: 'test-results/screenshots/login-error-state.png',
      fullPage: true
    })
  })

  test('should be responsive on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 })
    await page.goto('/login')

    // Check responsive layout
    await expect(page.getByRole('heading', { name: /sign in/i })).toBeVisible()

    await page.screenshot({
      path: 'test-results/screenshots/login-form-mobile.png',
      fullPage: true
    })
  })
})
```

### Screenshot Capture Strategy

Every route gets screenshotted in these states:

```
For each route in the application:
  ├── Desktop (1440x900)
  │   ├── Initial load
  │   ├── After primary interaction (button click, form fill)
  │   ├── Error state (if applicable)
  │   └── Empty state (if applicable)
  │
  └── Mobile (375x812)
      ├── Initial load
      ├── After primary interaction
      └── Navigation menu open (if applicable)
```

Screenshot naming convention:
```
test-results/screenshots/
├── {route}-desktop-initial.png
├── {route}-desktop-interaction.png
├── {route}-desktop-error.png
├── {route}-desktop-empty.png
├── {route}-mobile-initial.png
├── {route}-mobile-interaction.png
└── {route}-mobile-nav-open.png
```

## Level 3: Visual Verification (AI Vision)

### Two-Tier Analysis

```
Screenshot captured
       │
       ▼
Tier 1: Local Vision (Qwen2.5-VL 7B via Ollama)
       │  Fast, free, catches obvious issues
       │
       ├── PASS (confidence > 0.8) → Accept, save baseline
       │
       ├── AMBIGUOUS (0.5 < confidence < 0.8) → Escalate to Tier 2
       │
       └── FAIL (confidence < 0.5) → Escalate to Tier 2
              │
              ▼
Tier 2: Cloud Vision (Claude Vision via Claude Code)
       │  Accurate, costs tokens, used sparingly
       │
       ├── PASS → Accept
       └── FAIL → Generate issue with evidence
```

### Local Vision Analysis Script

```python
#!/usr/bin/env python3
"""Visual verification using Ollama vision models."""
import base64
import json
import httpx
from pathlib import Path

OLLAMA_URL = "http://localhost:11434/api/generate"
VISION_MODEL = "qwen2.5vl:7b"

ANALYSIS_PROMPT = """Analyze this web application screenshot for visual quality.

Check for these issues:
1. LAYOUT: Overlapping elements, broken grids, content overflow
2. TEXT: Unreadable text, truncated content, wrong alignment
3. IMAGES: Missing images (broken placeholders), stretched/distorted images
4. SPACING: Inconsistent padding/margins, cramped elements
5. RESPONSIVE: Elements not fitting viewport, horizontal scrolling
6. CONTRAST: Poor color contrast, unreadable text on backgrounds
7. INTERACTIVE: Buttons/links not visually distinguishable
8. EMPTY STATES: Blank areas that should have content

Return JSON:
{
  "pass": true/false,
  "confidence": 0.0-1.0,
  "issues": [
    {
      "type": "LAYOUT|TEXT|IMAGES|SPACING|RESPONSIVE|CONTRAST|INTERACTIVE|EMPTY",
      "severity": "CRITICAL|HIGH|MEDIUM|LOW",
      "description": "Description of the issue",
      "location": "Approximate location on screen"
    }
  ],
  "summary": "One-sentence summary of overall quality"
}"""

async def analyze_screenshot(image_path: Path) -> dict:
    """Analyze a screenshot using local vision model."""
    image_data = base64.b64encode(image_path.read_bytes()).decode()

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(OLLAMA_URL, json={
            "model": VISION_MODEL,
            "prompt": ANALYSIS_PROMPT,
            "images": [image_data],
            "stream": False,
            "format": "json"
        })

    result = response.json()
    return json.loads(result["response"])

async def verify_all_screenshots(screenshots_dir: Path) -> dict:
    """Verify all screenshots in a directory."""
    results = {"pass": [], "fail": [], "ambiguous": []}

    for png in sorted(screenshots_dir.glob("*.png")):
        analysis = await analyze_screenshot(png)

        if analysis["confidence"] > 0.8 and analysis["pass"]:
            results["pass"].append({"file": png.name, "analysis": analysis})
        elif analysis["confidence"] < 0.5 or not analysis["pass"]:
            results["fail"].append({"file": png.name, "analysis": analysis})
        else:
            results["ambiguous"].append({"file": png.name, "analysis": analysis})

    return results
```

### Visual Comparison Against Reference Mockups

When Visual Designer has generated reference mockups:

```python
async def compare_with_reference(
    actual_path: Path,
    reference_path: Path
) -> dict:
    """Compare actual screenshot against reference mockup."""
    actual_b64 = base64.b64encode(actual_path.read_bytes()).decode()
    reference_b64 = base64.b64encode(reference_path.read_bytes()).decode()

    prompt = """Compare these two images:
    Image 1 (REFERENCE): The design mockup showing expected appearance.
    Image 2 (ACTUAL): The built application screenshot.

    Report differences:
    1. Layout differences (position, size, spacing)
    2. Color differences (background, text, accents)
    3. Content differences (missing elements, extra elements)
    4. Typography differences (font size, weight, alignment)

    Return JSON:
    {
      "match_score": 0.0-1.0,
      "pass": true if match_score > 0.7,
      "differences": [
        {
          "type": "LAYOUT|COLOR|CONTENT|TYPOGRAPHY",
          "severity": "HIGH|MEDIUM|LOW",
          "description": "What differs",
          "reference_area": "Location in reference",
          "actual_area": "Location in actual"
        }
      ]
    }"""

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(OLLAMA_URL, json={
            "model": VISION_MODEL,
            "prompt": prompt,
            "images": [reference_b64, actual_b64],
            "stream": False,
            "format": "json"
        })

    return json.loads(response.json()["response"])
```

## Level 4: Test Crafter Autonomous Sweep

After all features pass Levels 1-3, Test Crafter runs a comprehensive sweep:

```
Team Lead triggers Test Crafter:
    │
    ├── Input: Original requirements.md
    ├── Input: Target URL (http://localhost:23000)
    │
    └── Test Crafter autonomously:
        ├── Extracts user flows from requirements
        ├── Crawls the application via Playwright
        ├── Captures evidence (screenshots, console logs, network)
        ├── Runs visual comparison engine (5-level matching)
        ├── Runs accessibility checks (WCAG A/AA)
        ├── Runs performance analysis
        ├── Generates issue tickets with full debug pipeline
        └── Returns results to Team Lead
```

### MCP Integration with Test Crafter

```
# Claude Code calls Test Crafter via MCP:

Tool: test_crafter_run
Input: {
  "prd_path": "/path/to/requirements.md",
  "target_url": "http://localhost:23000",
  "analysis_level": "thorough",
  "checks": ["functionality", "visual", "accessibility", "performance"]
}

Tool: test_crafter_status
Input: { "run_id": "tc-run-12345" }

Tool: test_crafter_results
Input: { "run_id": "tc-run-12345" }
Output: {
  "issues": [...],
  "screenshots": [...],
  "quality_score": 87,
  "accessibility_score": 92
}
```

## Fix-Retest Loop

When any test level fails:

```
Issue detected at Level N
    │
    ├── Issue classified: CRITICAL / HIGH / MEDIUM / LOW
    │
    ├── If CRITICAL or HIGH:
    │   ├── Route to available Builder agent
    │   ├── Builder reads issue + evidence
    │   ├── Builder fixes in worktree
    │   ├── Merge fix to main
    │   └── Re-run Level N and all levels above
    │
    ├── If MEDIUM:
    │   ├── Queue for next available Builder
    │   ├── Fix and retest
    │   └── Don't block other features
    │
    └── If LOW:
        ├── Log in known-issues.md
        └── Include in build report as known limitation
```

Maximum retry attempts per issue: 3
After 3 failures: escalate to user with evidence.

## Test Results Format

```json
{
  "project": "my-project",
  "timestamp": "2026-02-11T10:30:00Z",
  "summary": {
    "total_tests": 47,
    "passed": 44,
    "failed": 2,
    "skipped": 1,
    "coverage": {
      "frontend": "83%",
      "backend": "79%"
    }
  },
  "levels": {
    "unit": { "passed": 32, "failed": 1, "total": 33 },
    "e2e": { "passed": 10, "failed": 1, "total": 11 },
    "visual": { "passed": 8, "failed": 0, "total": 8, "screenshots": 24 },
    "test_crafter": { "quality_score": 87, "issues_found": 3, "issues_fixed": 2 }
  },
  "screenshots": [
    { "route": "/login", "viewport": "desktop", "path": "screenshots/login-desktop.png" },
    { "route": "/login", "viewport": "mobile", "path": "screenshots/login-mobile.png" },
    { "route": "/dashboard", "viewport": "desktop", "path": "screenshots/dashboard-desktop.png" }
  ],
  "known_issues": [
    { "severity": "LOW", "description": "Minor alignment issue on settings page mobile view" }
  ]
}
```
