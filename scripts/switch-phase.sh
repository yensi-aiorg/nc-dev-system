#!/bin/bash
# NC Dev System — VRAM Phase Switching
# Loads/unloads Ollama models based on current pipeline phase
# RTX 4090 has 24GB VRAM — manage carefully

case "$1" in
  "build")
    echo "Switching to BUILD phase — loading Qwen3 Coder 30B (~19GB)"
    ollama stop qwen2.5vl:7b 2>/dev/null
    ollama stop qwen3:8b 2>/dev/null
    curl -s http://localhost:11434/api/generate -d '{"model":"qwen3-coder:30b","keep_alive":"30m","prompt":"warmup"}' > /dev/null
    echo "Ready for build phase"
    ;;
  "test")
    echo "Switching to TEST phase — loading Qwen2.5-VL 7B + Qwen3 Coder 30B (~24GB)"
    ollama stop qwen3:8b 2>/dev/null
    curl -s http://localhost:11434/api/generate -d '{"model":"qwen2.5vl:7b","keep_alive":"30m","prompt":"warmup"}' > /dev/null
    curl -s http://localhost:11434/api/generate -d '{"model":"qwen3-coder:30b","keep_alive":"30m","prompt":"warmup"}' > /dev/null
    echo "Ready for test phase"
    ;;
  "data")
    echo "Switching to DATA phase — loading Qwen3 8B + Qwen3 Coder 30B (~24GB)"
    ollama stop qwen2.5vl:7b 2>/dev/null
    curl -s http://localhost:11434/api/generate -d '{"model":"qwen3:8b","keep_alive":"30m","prompt":"warmup"}' > /dev/null
    curl -s http://localhost:11434/api/generate -d '{"model":"qwen3-coder:30b","keep_alive":"30m","prompt":"warmup"}' > /dev/null
    echo "Ready for data phase"
    ;;
  *)
    echo "Usage: ./switch-phase.sh [build|test|data]"
    echo ""
    echo "Phases:"
    echo "  build  — Qwen3 Coder 30B for code review/mock gen (~19GB VRAM)"
    echo "  test   — Qwen2.5-VL 7B (vision) + Qwen3 Coder 30B (~24GB VRAM)"
    echo "  data   — Qwen3 8B (fixtures) + Qwen3 Coder 30B (~24GB VRAM)"
    exit 1
    ;;
esac
