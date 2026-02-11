---
name: scaffold-project
description: Create a new project from the NC Dev System template with Docker, tests, and mock layer
user-invocable: false
context: fork
agent: general-purpose
model: sonnet
---

Create a new project based on the architecture from .nc-dev/architecture.json:

1. Create GitHub repository: `gh repo create {name} --public --clone`
2. Generate project structure from template
3. Set up Docker Compose (app services + MongoDB + Redis)
4. Set up Playwright configuration
5. Set up MSW (Mock Service Worker) with handlers for all external APIs
6. Set up pytest fixtures for backend mocking
7. Set up factory functions for test data
8. Create initial Playwright test that visits the home route
9. Commit and push: "feat: initial scaffold with mock layer and test infrastructure"
