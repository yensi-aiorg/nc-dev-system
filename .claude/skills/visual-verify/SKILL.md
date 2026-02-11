---
name: visual-verify
description: Run Playwright tests, capture screenshots, and verify with AI vision
user-invocable: false
context: fork
agent: tester
model: sonnet
---

Verify the feature specified in $ARGUMENTS:

1. Start the application: `docker compose up -d`
2. Wait for health checks to pass
3. Run Playwright E2E tests for the feature
4. Capture screenshots:
   - Desktop (1440x900) for every route
   - Mobile (375x812) for every route
   - Key interaction states (forms filled, modals open, etc.)
5. Analyze screenshots with Ollama vision (pre-screen):
   ```bash
   curl -s http://localhost:11434/api/generate -d '{
     "model": "qwen2.5vl:7b",
     "prompt": "Analyze this web app screenshot. Check for: broken layouts, overlapping text, missing images, poor contrast, unresponsive elements, empty states that should have content. Return JSON: {\"pass\": bool, \"issues\": [...]}",
     "images": ["BASE64_IMAGE"],
     "stream": false
   }'
   ```
6. If local vision flags issues: escalate to Claude Vision for confirmation
7. If Claude Vision confirms: create issue, route to builder
8. If all pass: update task status, save screenshots as baselines
