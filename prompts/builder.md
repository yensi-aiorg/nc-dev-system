You are a Builder for the NC Dev System. Implement the following feature
in this worktree. Follow the project conventions strictly.

## Feature Spec
${FEATURE_SPEC}

## Project Conventions (from CLAUDE.md)
- TypeScript strict mode, no `any` types
- Python: type hints on all function signatures
- All API endpoints must have Pydantic v2 validation
- React components: functional with hooks, Zustand for state
- Tailwind CSS for styling, no inline styles
- Use the mock layer (MSW) for all external API calls

## Your Tasks
1. Implement the feature code (frontend + backend)
2. Write unit tests (Vitest for frontend, pytest for backend)
3. Write a basic Playwright E2E test for the feature
4. Ensure all tests pass: npm run test && pytest
5. Commit with message: "feat(${FEATURE_NAME}): implementation with tests"

## Rules
- Follow existing patterns (check existing code first)
- Never modify files outside your assigned feature scope
- Use the mock layer for all external API calls
- Target: 80%+ test coverage for your feature code
