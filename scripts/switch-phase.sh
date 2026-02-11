#!/bin/bash
# NC Dev System — VRAM Phase Switching
# Loads/unloads Ollama models based on current pipeline phase
# RTX 4090 has 24GB VRAM — manage carefully

case "$1" in
  "build")
    echo "Switching to BUILD phase — loading Qwen 2.5 Coder 32B (~20GB)"
    ollama stop qwen2.5vl:7b 2>/dev/null
    ollama stop llama3.1:8b 2>/dev/null
    curl -s http://localhost:11434/api/generate -d '{"model":"qwen2.5-coder:32b","keep_alive":"30m","prompt":"warmup"}' > /dev/null
    echo "Ready for build phase"
    ;;
  "test")
    echo "Switching to TEST phase — loading Qwen2.5-VL 7B + Qwen 2.5 Coder 14B (~14GB)"
    ollama stop qwen2.5-coder:32b 2>/dev/null
    curl -s http://localhost:11434/api/generate -d '{"model":"qwen2.5vl:7b","keep_alive":"30m","prompt":"warmup"}' > /dev/null
    curl -s http://localhost:11434/api/generate -d '{"model":"qwen2.5-coder:14b","keep_alive":"30m","prompt":"warmup"}' > /dev/null
    echo "Ready for test phase"
    ;;
  "data")
    echo "Switching to DATA phase — loading Llama 3.1 8B + Qwen 2.5 Coder 14B (~14GB)"
    ollama stop qwen2.5-coder:32b 2>/dev/null
    ollama stop qwen2.5vl:7b 2>/dev/null
    curl -s http://localhost:11434/api/generate -d '{"model":"llama3.1:8b","keep_alive":"30m","prompt":"warmup"}' > /dev/null
    curl -s http://localhost:11434/api/generate -d '{"model":"qwen2.5-coder:14b","keep_alive":"30m","prompt":"warmup"}' > /dev/null
    echo "Ready for data phase"
    ;;
  *)
    echo "Usage: ./switch-phase.sh [build|test|data]"
    echo ""
    echo "Phases:"
    echo "  build  — Qwen 2.5 Coder 32B for code review/mock gen (~20GB VRAM)"
    echo "  test   — Qwen2.5-VL 7B (vision) + Qwen 14B (mocks) (~14GB VRAM)"
    echo "  data   — Llama 3.1 8B (fixtures) + Qwen 14B (mocks) (~14GB VRAM)"
    exit 1
    ;;
esac
