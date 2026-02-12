---
name: generate-mocks
description: Generate comprehensive mock layer for all external API dependencies using Ollama
user-invocable: false
context: fork
agent: mock-generator
model: sonnet
---

Generate the mock layer for the project:

1. Read .nc-dev/architecture.json for external API dependencies
2. For each external API:
   - Generate MSW handler (frontend)
   - Generate pytest fixture (backend)
   - Generate 3 response variants: success, error, empty
3. Generate factory functions for all database entities
4. Use Ollama (localhost:11434) for domain-specific mock data:
   - qwen3-coder:30b for structured JSON responses
   - qwen3:8b for bulk test fixture generation
5. Create seed script for development database
6. Generate mock documentation (docs/mock-documentation.md)
7. Verify all mocks work with MOCK_APIS=true
