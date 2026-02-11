---
name: parse-requirements
description: Parse a requirements document into structured features, architecture, and API contracts
user-invocable: false
context: fork
agent: general-purpose
model: opus
---

Parse the provided requirements document and produce:

1. **features.json** — Structured list of features with:
   - name, description, priority (P0/P1/P2)
   - dependencies (which features depend on others)
   - estimated complexity (simple/medium/complex)
   - UI routes involved
   - API endpoints needed
   - External APIs required

2. **architecture.json** — System architecture with:
   - Component diagram
   - API contracts (endpoint, method, request/response schemas)
   - Database schema (collections, fields, indexes)
   - External API dependencies (URL, auth method, endpoints used)

3. **test-plan.json** — Testing strategy with:
   - E2E test scenarios per feature
   - Visual test checkpoints (which screens to screenshot)
   - Mock requirements per external API

Output these as JSON files in the project's .nc-dev/ directory.
