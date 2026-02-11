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

# Primary coding model (20GB)
echo "[1/4] Qwen 2.5 Coder 32B — Primary coding model (mock generation, code review)"
ollama pull qwen2.5-coder:32b

# Fast coding model (9GB)
echo "[2/4] Qwen 2.5 Coder 14B — Fast coding model (lighter tasks, parallel work)"
ollama pull qwen2.5-coder:14b

# Vision model (5GB)
echo "[3/4] Qwen2.5-VL 7B — Vision / screenshot analysis (pre-screening)"
ollama pull qwen2.5vl:7b

# Fast fixture model (5GB)
echo "[4/4] Llama 3.1 8B — High-volume test data generation"
ollama pull llama3.1:8b

echo ""
echo "=== All models downloaded ==="
echo ""
echo "Verify with: ollama list"
ollama list

echo ""
echo "VRAM configurations available:"
echo "  Build phase:  Qwen 2.5 Coder 32B (~20GB)"
echo "  Test phase:   Qwen2.5-VL 7B + Qwen 2.5 Coder 14B (~14GB)"
echo "  Data phase:   Llama 3.1 8B + Qwen 2.5 Coder 14B (~14GB)"
