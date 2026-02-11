# NC Dev System - Remote Interaction & Delivery

## Remote Interaction Model

The system is designed so you can send a message from anywhere and receive a fully built project back.

```
USER (anywhere)
  │
  ├── Option A: Claude Code Web (claude.ai/code)
  │   "& Build a task management app from requirements.md"
  │   → Runs on Anthropic cloud VM
  │   → Creates PR when done
  │
  ├── Option B: Claude Code Terminal (remote mode)
  │   $ claude --remote "Build from /path/to/requirements.md"
  │   → Runs locally in background
  │   → Results appear in /tasks
  │
  ├── Option C: Claude Code Remote (webhook)
  │   Discord/Slack: "Build from requirements.md"
  │   → Webhook triggers Claude Code
  │   → Results sent back to channel
  │
  └── Option D: Agent SDK (programmatic)
      Python script triggers build
      → Results returned as structured data
```

## Interaction Flow

### Step 1: User Sends Requirements

```
User: "Build this for me. Here are the requirements: [paste or file path]"
```

### Step 2: System Asks Clarifying Questions

Before building, the Team Lead agent analyzes requirements and asks questions about:

```
Team Lead: "I've analyzed your requirements. Before I build, I have a few questions:

1. **Authentication**: The PRD mentions user accounts. Should I use:
   a) Email/password (simple, mocked auth)
   b) OAuth (Google/GitHub login, mocked in dev)
   c) No auth (single-user, local-first)

2. **External APIs**: I see references to:
   - Payment processing → I'll mock with Stripe-like responses
   - Email notifications → I'll mock with SendGrid-like responses
   - Maps/Location → I'll mock with static coordinates
   Does this match your expectations?

3. **Design**: Should I:
   a) Generate UI mockups first for your approval (adds 30 min)
   b) Use sensible defaults and show screenshots after build

4. **Repository**: Create as:
   a) Public repo under your GitHub account
   b) Private repo
   c) Under a specific org (which one?)

I'll proceed with sensible defaults if you don't respond within 10 minutes."
```

### Step 3: System Builds Autonomously

```
Team Lead: "Starting build. I'll update you at each phase.

Phase 1/6: Understanding requirements...
  ✓ Extracted 8 features (3 P0, 3 P1, 2 P2)
  ✓ Identified 3 external API dependencies
  ✓ Architecture designed (12 API endpoints, 6 DB collections)

Phase 2/6: Scaffolding project...
  ✓ Created repo: github.com/user/task-manager
  ✓ React 19 + FastAPI + MongoDB scaffold ready
  ✓ Mock layer generated (Stripe, SendGrid, Maps)
  ✓ Playwright configured with 3 viewports

Phase 3/6: Building features (3 builders parallel)...
  ✓ Builder 1: User authentication (email/password) — DONE
  ✓ Builder 2: Task CRUD with categories — DONE
  ◐ Builder 3: Dashboard with analytics — IN PROGRESS

Phase 4/6: Testing & verification...
  ✓ 32/33 unit tests passing
  ✓ 10/11 E2E tests passing
  ⚠ 1 visual issue detected: Dashboard chart overlaps on mobile
  → Routing to Builder 3 for fix...
  ✓ Fix applied, retested — PASS

Phase 5/6: Hardening...
  ✓ Error boundaries added
  ✓ Loading states for all API calls
  ✓ Responsive verified (desktop, tablet, mobile)
  ✓ Accessibility: WCAG AA compliant

Phase 6/6: Generating delivery..."
```

### Step 4: System Delivers Results

```
Team Lead: "Build complete! Here's your project:

## Repository
https://github.com/user/task-manager

## Quick Start
```bash
git clone https://github.com/user/task-manager
cd task-manager
docker compose up -d
open http://localhost:23000
```

## Features Built (8/8)

### 1. User Authentication
Login and registration with email/password. Sessions managed via JWT.
[Screenshot: Login Page — Desktop]
[Screenshot: Login Page — Mobile]

### 2. Task Management
Create, edit, delete, and categorize tasks with due dates and priorities.
[Screenshot: Task List — Desktop]
[Screenshot: Create Task Modal]
[Screenshot: Task Detail View]

### 3. Dashboard
Overview with task statistics, upcoming deadlines, and completion chart.
[Screenshot: Dashboard — Desktop]
[Screenshot: Dashboard — Mobile]

... (all 8 features with screenshots)

## Test Results
- Unit tests: 33/33 passing (84% coverage)
- E2E tests: 11/11 passing
- Visual verification: All routes verified
- Accessibility: WCAG AA compliant

## Mocked APIs
- **Stripe**: Payment mock (see docs/mock-documentation.md)
- **SendGrid**: Email mock (logs to console)
- **Google Maps**: Static coordinates mock

Set `MOCK_APIS=false` in `.env` and add real API keys for production.

## Known Limitations
- Real-time updates not yet implemented (WebSocket planned)
- File upload limited to 5MB in mock mode
- Dashboard chart renders slowly with 1000+ tasks

## Full Documentation
- Usage guide: docs/usage-guide.md
- API docs: docs/api-documentation.md
- Setup guide: docs/setup-guide.md
"
```

## Delivery Package Structure

Every delivery includes these files in the repository:

```
project-root/
├── docs/
│   ├── usage-guide.md              # Feature walkthrough with screenshots
│   │   └── Inline screenshots for every feature
│   │
│   ├── api-documentation.md        # API endpoint reference
│   │   └── Every endpoint with request/response examples
│   │
│   ├── setup-guide.md              # How to run locally
│   │   └── Docker, env vars, prerequisites
│   │
│   ├── mock-documentation.md       # Mocked API documentation
│   │   └── Every mock with behavior description
│   │
│   ├── build-report.md             # Build summary
│   │   ├── Features implemented
│   │   ├── Test results
│   │   ├── Known limitations
│   │   ├── Architecture decisions
│   │   └── Token usage breakdown
│   │
│   └── screenshots/
│       ├── desktop/
│       │   ├── 01-login.png
│       │   ├── 02-dashboard.png
│       │   ├── 03-task-list.png
│       │   └── ...
│       ├── mobile/
│       │   ├── 01-login.png
│       │   ├── 02-dashboard.png
│       │   └── ...
│       └── annotated/
│           ├── 01-login-annotated.png     # With numbered callouts
│           └── ...
│
├── test-results/
│   ├── results.json                # Machine-readable test results
│   ├── html-report/                # Playwright HTML report
│   └── screenshots/                # Test screenshots (all states)
│
└── README.md                       # Auto-generated with:
    ├── Project description
    ├── Quick start (docker compose up)
    ├── Feature list
    ├── Tech stack
    ├── API overview
    └── Links to detailed docs
```

## Screenshot Annotation System

The Reporter agent annotates screenshots for the delivery:

```python
"""Generate annotated screenshots with numbered callouts."""
from playwright.sync_api import sync_playwright

def capture_annotated_screenshot(
    url: str,
    annotations: list[dict],  # [{x, y, label, description}]
    output_path: str
):
    """Capture a screenshot and overlay numbered annotations."""
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.goto(url)
        page.wait_for_load_state("networkidle")

        # Inject annotation overlay
        for i, ann in enumerate(annotations, 1):
            page.evaluate(f"""
                const marker = document.createElement('div');
                marker.style.cssText = `
                    position: fixed; z-index: 99999;
                    left: {ann['x']}px; top: {ann['y']}px;
                    width: 28px; height: 28px; border-radius: 50%;
                    background: #FF4444; color: white;
                    display: flex; align-items: center; justify-content: center;
                    font-weight: bold; font-size: 14px; font-family: Arial;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.3);
                `;
                marker.textContent = '{i}';
                document.body.appendChild(marker);
            """)

        page.screenshot(path=output_path, full_page=True)
        browser.close()

    # Generate legend markdown
    legend = "### Screenshot Legend\\n\\n"
    for i, ann in enumerate(annotations, 1):
        legend += f"{i}. **{ann['label']}**: {ann['description']}\\n"

    return legend
```

## Usage Documentation Template

```markdown
# [Project Name] — Usage Guide

## Getting Started

### Prerequisites
- Docker Desktop installed
- Git installed

### Quick Start
```bash
git clone [repo-url]
cd [project-name]
cp .env.example .env
docker compose up -d
open http://localhost:23000
```

### Default Credentials
- Email: test@example.com
- Password: password123

---

## Features

### 1. [Feature Name]

[Screenshot with annotations]

**What it does**: [Description]

**How to use**:
1. Navigate to [route]
2. Click [element]
3. Fill in [fields]
4. Click [submit button]

**API Endpoint**: `POST /api/[endpoint]`

---

### 2. [Next Feature]
...

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MOCK_APIS` | `true` | Use mock APIs (set false for production) |
| `MONGODB_URI` | `mongodb://localhost:23002/app` | MongoDB connection |
| `REDIS_URL` | `redis://localhost:23003` | Redis connection |

### Switching to Production APIs

1. Set `MOCK_APIS=false` in `.env`
2. Add your API keys:
   - `STRIPE_API_KEY=sk_live_...`
   - `SENDGRID_API_KEY=SG...`
3. Restart: `docker compose restart`

---

## Architecture

[Auto-generated architecture overview]

### Tech Stack
- Frontend: React 19, TypeScript, Tailwind CSS, Zustand
- Backend: FastAPI, Python 3.12, MongoDB
- Infrastructure: Docker Compose
```

## Helyx Integration

After delivery, the Team Lead updates Helyx with the build results:

```
POST http://localhost:15650/api/projects/{project_id}/update
{
  "status": "built",
  "github_repo": "https://github.com/user/task-manager",
  "build_report": {
    "features_count": 8,
    "tests_passing": 44,
    "tests_total": 44,
    "coverage": "84%",
    "build_duration": "4h 23m",
    "token_usage": {
      "cloud": 245000,
      "local": 180000,
      "savings": "42%"
    }
  }
}
```

This allows Helyx to track all built projects and their status.
