# TestCraftr Issues Report

**Run ID**: 695013ca63fd02b95a217371
**Target URL**: http://localhost:15900/
**Date**: 2025-12-28
**Status**: Completed

## Summary

| Metric | Value |
|--------|-------|
| Flows Total | 30 |
| Flows Passed | 0 |
| Flows Failed | 30 |
| Issues Found | 2 |

---

## Issue #1: Failed: Go to home page

| Field | Value |
|-------|-------|
| **Severity** | High |
| **Type** | Functionality |
| **Status** | Open |
| **URL** | http://localhost:15900/ |

### Description
Navigation to the home page failed due to a validation error in the testing framework.

### Expected Behavior
Step should succeed: navigate /

### Actual Behavior
```
1 validation error for ConsoleLog
level
  Input should be 'log', 'warn', 'error', 'info' or 'debug'
```

### Evidence
- Screenshot: `evidence/695013ca63fd02b95a217371/step_error_1766913954994.png`

### Notes
This is a **testing framework bug**, not an application bug.

---

## Issue #2: Failed: Hover over first product card

| Field | Value |
|-------|-------|
| **Severity** | High |
| **Type** | Functionality |
| **Status** | Open |
| **URL** | http://localhost:15900/platform |

### Description
The hover action on the first product card timed out after 30 seconds.

### Expected Behavior
Step should succeed: hover .product-card:first-child

### Actual Behavior
```
Timeout 30000ms exceeded.
```

### Evidence
- Screenshot: `evidence/695013ca63fd02b95a217371/step_error_1766914401397.png`

### Possible Causes
1. Element `.product-card:first-child` does not exist on the page
2. Element exists but is not visible/interactable
3. CSS selector is incorrect for the actual DOM structure

### Recommended Action
Review the platform page DOM structure and verify the correct CSS selector for product cards.
