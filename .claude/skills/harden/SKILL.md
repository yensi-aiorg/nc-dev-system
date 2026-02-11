---
name: harden
description: Add error handling, responsive design, accessibility, and performance improvements
user-invocable: false
context: fork
agent: general-purpose
model: sonnet
---

Harden the project for near-production readiness:

1. **Error Handling**:
   - Add error boundaries to React components
   - Add loading states for all async operations
   - Add empty states for list views
   - Add proper HTTP error responses on backend

2. **Responsive Design**:
   - Verify all pages on desktop (1440x900), tablet (768x1024), mobile (375x812)
   - Fix any layout issues found
   - Capture screenshots at all viewports

3. **Accessibility**:
   - Run axe-core via Playwright
   - Fix WCAG AA violations
   - Ensure proper aria labels, focus management, keyboard navigation

4. **Performance**:
   - Check for obvious performance issues (N+1 queries, large bundles)
   - Add proper pagination where needed
   - Ensure images are optimized

5. Re-run full test suite after hardening changes
