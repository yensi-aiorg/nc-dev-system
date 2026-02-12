#!/bin/bash
# NC Dev System — Ollama Model Setup
# Downloads all required models for local AI processing
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
echo ""

# Primary coding model (~19GB)
echo "[1/3] Qwen3 Coder 30B — Primary coding model (mock generation, code review)"
ollama pull qwen3-coder:30b

# Vision model (5GB)
echo "[2/3] Qwen2.5-VL 7B — Vision / screenshot analysis (pre-screening)"
ollama pull qwen2.5vl:7b

# Fast fixture model (~5GB)
echo "[3/3] Qwen3 8B — High-volume test data generation"
ollama pull qwen3:8b

echo ""
echo "=== All models downloaded ==="
echo ""
echo "Verify with: ollama list"
ollama list

echo ""
echo "VRAM configurations available:"
echo "  Build phase:  Qwen3 Coder 30B (~19GB)"
echo "  Test phase:   Qwen2.5-VL 7B + Qwen3 Coder 30B (~24GB)"
echo "  Data phase:   Qwen3 8B + Qwen3 Coder 30B (~24GB)"
