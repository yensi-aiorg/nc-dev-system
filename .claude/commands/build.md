---
name: build
description: Start an autonomous build from a requirements document
argument-hint: "<path-to-requirements.md>"
---

Start the NC Dev System autonomous build pipeline.

## Input
- Requirements document at: $ARGUMENTS

## Process
1. Read and parse the requirements document
2. Extract features, architecture, and test plan
3. Ask clarifying questions if requirements are ambiguous
4. Create GitHub repository
5. Scaffold project with mock layer
6. Build features in parallel (3 Codex GPT 5.3 builders)
7. Test and verify each feature (Playwright + AI vision)
8. Iterate on failures
9. Harden (error handling, responsive, accessibility)
10. Generate delivery report with screenshots
11. Push everything to GitHub
12. Report back with results

## Output
- GitHub repository URL
- Screenshot gallery
- Usage documentation
- Build report
- Test results

Begin by reading the requirements file and asking any clarifying questions.
