---
name: deliver
description: Generate final delivery package with screenshots, docs, and build report
user-invocable: true
argument-hint: "[project-path]"
---

Generate the delivery package for the completed project:

1. Capture final screenshots of ALL routes (desktop + mobile)
2. Generate usage documentation:
   - Feature-by-feature walkthrough with screenshots
   - API endpoint documentation
   - Setup instructions (Docker, env vars)
3. Generate build report:
   - Features implemented (list with status)
   - Test results (pass/fail counts, coverage %)
   - Known limitations
   - Mocked APIs documentation
   - Screenshots gallery
4. Push docs to repository
5. Create summary message for the user with:
   - Repository URL
   - Key screenshots (inline)
   - Quick start instructions
   - Test results summary
