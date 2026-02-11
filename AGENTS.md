# NC Dev System — Agent Topology

## Cloud Agents (Claude Code)

| Agent | Model | Role | Instances |
|-------|-------|------|-----------|
| **Team Lead** | Opus 4.6 | Orchestrator, planner, reviewer | 1 |
| **Tester** | Sonnet 4.5 | Playwright E2E, visual verification, fallback builder | 1 |
| **Reporter** | Sonnet 4.5 | Docs, screenshots, build report | 1 |
| **Mock Generator** | Sonnet 4.5 | MSW handlers, pytest fixtures, factory functions | 1 |

## External Builders (OpenAI Codex)

| Agent | Model | Role | Instances |
|-------|-------|------|-----------|
| **Builder** | Codex GPT 5.3 | Feature implementation in isolated worktrees | 3 parallel |

Builders are Codex CLI processes spawned by the Team Lead via `codex exec --full-auto`.
They use Codex tokens, NOT Claude tokens.

## Local Agents (Ollama)

| Agent | Model | VRAM | Role |
|-------|-------|------|------|
| **Mock Gen** | Qwen 2.5 Coder 32B | ~20GB | Structured mock API responses |
| **Test Data** | Qwen 2.5 Coder 14B | ~9GB | Lighter coding tasks, parallel work |
| **Vision QA** | Qwen2.5-VL 7B | ~5GB | Screenshot pre-screening |
| **Fixture Factory** | Llama 3.1 8B | ~5GB | Bulk test data generation |

## Integration Agents (MCP Servers)

| Service | Port | Role |
|---------|------|------|
| **Playwright** | npx | Browser automation, screenshots |
| **GitHub** | npx | Repository management |
| **Test Crafter** | 16630 | Autonomous QA sweeps |
| **Visual Designer** | 12101 | Reference UI mockups |

## Communication Flow

```
User → Team Lead (Opus)
         ├── Codex Builder 1 (GPT 5.3, worktree-1)
         ├── Codex Builder 2 (GPT 5.3, worktree-2)
         ├── Codex Builder 3 (GPT 5.3, worktree-3)
         ├── Tester (Sonnet, Playwright + Ollama Vision)
         ├── Mock Generator (Sonnet + Ollama)
         └── Reporter (Sonnet)
              └── Delivery → User
```
