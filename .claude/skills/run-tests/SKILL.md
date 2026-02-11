---
name: run-tests
description: Execute unit tests and Playwright E2E tests for the project
user-invocable: false
context: fork
agent: tester
model: sonnet
---

Run the full test suite:

1. Run frontend unit tests: `cd frontend && npm run test -- --reporter=json`
2. Run backend unit tests: `cd backend && pytest --tb=short -q --json-report`
3. Run Playwright E2E tests: `npx playwright test --reporter=json`
4. Collect and summarize results:
   - Total tests, passed, failed, skipped
   - Coverage percentages (frontend + backend)
   - Failed test details with error messages
5. If any tests fail:
   - Classify severity (CRITICAL if core flow breaks, HIGH if feature broken, etc.)
   - Route to builder for fix
6. Save results to .nc-dev/test-results.json
