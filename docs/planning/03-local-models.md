# NC Dev System - Local Model Strategy

## Hardware

- **GPU**: NVIDIA RTX 4090
- **VRAM**: 24GB GDDR6X
- **Runtime**: Ollama (already installed)
- **OS**: Darwin (macOS) — Note: RTX 4090 implies a separate Linux build machine or eGPU. If running on macOS with Apple Silicon, adjust models accordingly.

## Model Inventory

### Required Models (Download First)

```bash
# Primary coding model — best open-source coder, GPT-4o competitive
ollama pull qwen2.5-coder:32b
# Size: ~20GB VRAM (Q4_K_M quantization)
# Use: Mock API generation, structured data, code review pre-screening

# Fast coding model — for parallel work alongside vision
ollama pull qwen2.5-coder:14b
# Size: ~9GB VRAM
# Use: Lighter coding tasks, mock generation when 32B is unavailable

# Vision model — screenshot and UI analysis
ollama pull qwen2.5vl:7b
# Size: ~5GB VRAM
# Use: Pre-screen Playwright screenshots before escalating to Claude Vision

# Fast fixture generator — high-volume test data
ollama pull llama3.1:8b
# Size: ~5GB VRAM
# Use: Generate thousands of realistic test records quickly

# Compact vision alternative — outstanding single-image understanding
ollama pull minicpm-v
# Size: ~5GB VRAM
# Use: Alternative vision model, beats GPT-4V on single-image benchmarks
```

### Optional Models (Pull When Needed)

```bash
# Next-gen MoE coding model (if available)
ollama pull qwen3-coder:30b
# Size: ~19GB VRAM, 262K context, only 3.3B active params
# Use: Alternative primary coder with massive context window

# Deep reasoning model
ollama pull deepseek-r1:32b
# Size: ~20GB VRAM
# Use: Complex architectural decisions, hard debugging

# Ultra-fast autocomplete
ollama pull qwen2.5-coder:7b
# Size: ~5GB VRAM
# Use: Rapid code completion, simple transformations

# Multi-language coding
ollama pull codestral:22b
# Size: ~13GB VRAM
# Use: When project uses non-standard languages (Rust, Go, etc.)
```

## Setup Script

```bash
#!/bin/bash
# scripts/setup-ollama.sh
# Downloads all required models for NC Dev System

set -e

echo "=== NC Dev System — Ollama Model Setup ==="
echo "GPU: RTX 4090 (24GB VRAM)"
echo ""

# Check Ollama is running
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "ERROR: Ollama is not running. Start it with: ollama serve"
    exit 1
fi

echo "Pulling required models..."

# Primary coding model (20GB)
echo "[1/4] Qwen 2.5 Coder 32B — Primary coding model"
ollama pull qwen2.5-coder:32b

# Fast coding model (9GB)
echo "[2/4] Qwen 2.5 Coder 14B — Fast coding model"
ollama pull qwen2.5-coder:14b

# Vision model (5GB)
echo "[3/4] Qwen2.5-VL 7B — Vision / screenshot analysis"
ollama pull qwen2.5vl:7b

# Fast fixture model (5GB)
echo "[4/4] Llama 3.1 8B — High-volume test data generation"
ollama pull llama3.1:8b

echo ""
echo "=== All models downloaded ==="
echo "Verify with: ollama list"
ollama list
```

## Token Optimization Strategy

### What Runs Locally vs Cloud

| Task | Local Model | Cloud Model | Savings |
|------|------------|-------------|---------|
| **Mock API responses** | Qwen 2.5 Coder 32B | — | 100% saved |
| **Test fixtures** | Llama 3.1 8B | — | 100% saved |
| **Bulk seed data** | Llama 3.1 8B | — | 100% saved |
| **Screenshot pre-screen** | Qwen2.5-VL 7B | — | ~70% saved (only failures go to cloud) |
| **Code review pre-filter** | Qwen 2.5 Coder 32B | — | ~50% saved |
| **Simple refactoring** | Qwen 2.5 Coder 32B | — | 100% saved |
| **Feature implementation** | — | Sonnet 4.5 | Cloud (quality critical) |
| **Architecture decisions** | — | Opus 4.6 | Cloud (reasoning critical) |
| **Complex test generation** | — | Sonnet 4.5 | Cloud (context needed) |
| **Final visual verification** | — | Claude Vision | Cloud (accuracy critical) |
| **Delivery report** | — | Sonnet 4.5 | Cloud (quality matters) |

**Estimated cloud token savings: 40-60%** compared to running everything on Claude.

### Local Model Invocation from Claude Code

Claude Code agents call Ollama via Bash tool:

```bash
# Generate mock data
curl -s http://localhost:11434/api/generate \
  -d '{
    "model": "qwen2.5-coder:32b",
    "prompt": "Generate a JSON array of 20 realistic user objects with fields: id, name, email, avatar_url, created_at, role. Use realistic data.",
    "stream": false,
    "format": "json"
  }' | jq -r '.response'

# Analyze a screenshot
curl -s http://localhost:11434/api/generate \
  -d '{
    "model": "qwen2.5vl:7b",
    "prompt": "Analyze this screenshot of a web application. Report any visual issues: broken layouts, overlapping text, missing images, poor contrast, unresponsive elements.",
    "images": ["'$(base64 -i screenshot.png)'"],
    "stream": false
  }' | jq -r '.response'
```

### Ollama Python Client (for scripts)

```python
import ollama

# Generate mock API response
response = ollama.generate(
    model='qwen2.5-coder:32b',
    prompt='''Generate a realistic mock API response for a GET /api/users endpoint.
    Return JSON with: users array (10 items), pagination metadata.
    Each user has: id, name, email, avatar, role, created_at, last_login.''',
    format='json'
)
mock_data = response['response']

# Analyze screenshot
with open('screenshot.png', 'rb') as f:
    image_data = f.read()

response = ollama.generate(
    model='qwen2.5vl:7b',
    prompt='Describe any visual issues in this web application screenshot.',
    images=[image_data]
)
analysis = response['response']
```

## VRAM Management

### Phase-Based Model Loading

The orchestrator manages VRAM by loading/unloading models per phase:

| Phase | Models Loaded | VRAM Used |
|-------|--------------|-----------|
| Phase 1: Understand | None (cloud only) | 0 GB |
| Phase 2: Scaffold + Mock Gen | Qwen 2.5 Coder 32B | 20 GB |
| Phase 3: Build | Qwen 2.5 Coder 14B (backup code review) | 9 GB |
| Phase 4: Test + Verify | Qwen2.5-VL 7B + Qwen 2.5 Coder 14B | 14 GB |
| Phase 5: Harden | Llama 3.1 8B + Qwen2.5-VL 7B | 10 GB |
| Phase 6: Deliver | None (cloud only) | 0 GB |

### Automatic Model Switching

Ollama handles model loading/unloading automatically, but to prevent thrashing:

```bash
# Set keep_alive to prevent premature unloading
export OLLAMA_KEEP_ALIVE=30m

# Or per-request:
curl http://localhost:11434/api/generate -d '{
  "model": "qwen2.5-coder:32b",
  "keep_alive": "30m",
  "prompt": "..."
}'
```

### Monitoring VRAM Usage

```bash
# Check what's loaded
curl -s http://localhost:11434/api/ps | jq '.models[] | {name, size_vram}'

# Check GPU memory
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
```

## Quantization Notes

All 24GB recommendations use Q4_K_M quantization:
- **Quality**: ~95% of full precision for coding tasks
- **Speed**: ~30-35 tokens/sec on RTX 4090
- **HumanEval retention**: Same pass@1 score as FP16

If you want slightly better quality at the cost of tighter VRAM:
- Q5_K_M for the 32B model uses ~23GB (barely fits, no room for second model)
- Only recommended if running a single model at a time

## Fallback Strategy

If Ollama is unavailable or a local model fails:

1. **Automatic fallback to cloud**: The orchestrator detects Ollama failure and routes to Sonnet
2. **Graceful degradation**: Mock data generation falls back to smaller Sonnet requests
3. **Vision fallback**: Screenshot analysis goes directly to Claude Vision
4. **No data loss**: All prompts are logged, can be replayed when Ollama recovers

```python
async def generate_with_fallback(prompt: str, local_model: str = "qwen2.5-coder:32b"):
    try:
        # Try local first
        response = ollama.generate(model=local_model, prompt=prompt)
        return {"source": "local", "response": response["response"]}
    except Exception:
        # Fall back to cloud
        # (handled by Claude Code agent sending to Sonnet)
        return {"source": "cloud", "fallback": True, "prompt": prompt}
```
