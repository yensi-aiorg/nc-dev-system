#!/bin/bash
# NC Dev System — Setup Script
# Installs all prerequisites for the NC Dev System
set -e

echo "=== NC Dev System — Setup ==="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

check_command() {
    if command -v "$1" &> /dev/null; then
        echo -e "${GREEN}✓${NC} $1 found: $(command -v "$1")"
        return 0
    else
        echo -e "${RED}✗${NC} $1 not found"
        return 1
    fi
}

echo "--- Checking prerequisites ---"
echo ""

# Required tools
MISSING=0

echo "Core tools:"
check_command "git" || MISSING=1
check_command "node" || MISSING=1
check_command "npm" || MISSING=1
check_command "python3" || MISSING=1
check_command "pip3" || MISSING=1
check_command "docker" || MISSING=1

echo ""
echo "AI tools:"
check_command "claude" || MISSING=1
check_command "codex" || { echo -e "${YELLOW}  → Install with: npm i -g @openai/codex${NC}"; MISSING=1; }
check_command "ollama" || { echo -e "${YELLOW}  → Install from: https://ollama.ai${NC}"; MISSING=1; }

echo ""
echo "GitHub tools:"
check_command "gh" || { echo -e "${YELLOW}  → Install with: brew install gh${NC}"; MISSING=1; }

echo ""
echo "Browser testing:"
check_command "npx" || MISSING=1

if [ $MISSING -eq 1 ]; then
    echo ""
    echo -e "${RED}Some prerequisites are missing. Install them and re-run this script.${NC}"
    echo ""
fi

# Install missing npm tools if node is available
if command -v npm &> /dev/null; then
    echo "--- Installing npm dependencies ---"
    echo ""

    # Check for Codex CLI
    if ! command -v codex &> /dev/null; then
        echo "Installing Codex CLI..."
        npm i -g @openai/codex
    fi

    # Check for Playwright
    echo "Ensuring Playwright browsers are installed..."
    npx playwright install chromium 2>/dev/null || echo -e "${YELLOW}  Playwright browser install deferred (run 'npx playwright install' when needed)${NC}"
fi

# Check CLI authentication
# All AI and GitHub access is through CLIs, not API keys.
echo ""
echo "--- Checking CLI authentication ---"
echo ""

if command -v claude &> /dev/null; then
    echo -e "${GREEN}✓${NC} Claude Code CLI found"
    echo "  → Authenticate with: claude (OAuth flow)"
fi

if command -v codex &> /dev/null; then
    codex login status 2>/dev/null && echo -e "${GREEN}✓${NC} Codex authenticated" || echo -e "${YELLOW}⚠${NC} Codex not authenticated. Run: codex login"
fi

if command -v gh &> /dev/null; then
    gh auth status 2>/dev/null && echo -e "${GREEN}✓${NC} GitHub CLI authenticated" || echo -e "${YELLOW}⚠${NC} GitHub CLI not authenticated. Run: gh auth login"
fi

# Check Ollama
echo ""
echo "--- Checking Ollama ---"
if command -v ollama &> /dev/null; then
    if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} Ollama is running"
        echo "  Models available:"
        ollama list 2>/dev/null | head -10
        echo ""
        echo "  Run ./scripts/setup-ollama.sh to download required models"
    else
        echo -e "${YELLOW}⚠${NC} Ollama is installed but not running. Start with: ollama serve"
    fi
fi

# Check Docker
echo ""
echo "--- Checking Docker ---"
if command -v docker &> /dev/null; then
    if docker info > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} Docker is running"
    else
        echo -e "${YELLOW}⚠${NC} Docker is installed but not running. Start Docker Desktop."
    fi
fi

echo ""
echo "=== Setup check complete ==="
echo ""
echo "Next steps:"
echo "  1. Fix any missing prerequisites above"
echo "  2. Run ./scripts/setup-ollama.sh to download local AI models"
echo "  3. Start Claude Code: claude"
echo "  4. Run: /build /path/to/requirements.md"
