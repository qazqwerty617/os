#!/bin/bash

# ==========================================
# 🚀 MEXC PUMP MONITOR - SYSTEM LAUNCHER
# The "Brain" Starter
# ==========================================

# Colors
GREEN='\033[0;32m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}"
echo "╔══════════════════════════════════════════════════════╗"
echo "║                                                      ║"
echo "║   🧠 MEXC PUMP MONITOR - SYSTEM ORCHESTRATOR 🧠     ║"
echo "║                                                      ║"
echo "╚══════════════════════════════════════════════════════╝"
echo -e "${NC}"

# 1. Environment Check
echo -e "🔎 Checking environment..."

if [ ! -f .env ] && [ ! -f config.py ]; then
    echo -e "${RED}❌ Error: Configuration not found! (.env or config.py)${NC}"
    exit 1
fi

# 2. Python Check
if command -v python3 &> /dev/null; then
    PYTHON_CMD=python3
elif command -v python &> /dev/null; then
    PYTHON_CMD=python
else
    echo -e "${RED}❌ Error: Python not found!${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Environment OK${NC}"

# Cleaning up old instances (Force Kill Ports)
lsof -t -i :8081 | xargs kill -9 2>/dev/null
lsof -t -i :8000 | xargs kill -9 2>/dev/null
pkill -9 -f "python3 main.py" > /dev/null 2>&1
sleep 1

# 3. System Diagnostics (Pre-flight check)
echo -e "🏥 Running Pre-flight Diagnostics..."
$PYTHON_CMD system_check.py
if [ $? -ne 0 ]; then
    echo -e "${RED}⚠️ Diagnostics reported issues. Proceeding anyway? (y/n)${NC}"
    read -r response
    if [[ "$response" != "y" ]]; then
        exit 1
    fi
fi

# 4. Launch Orchestrator
echo -e "\nRocket engines engaging... 🚀"
echo -e "Starting System Orchestrator (Main Brain)..."
echo -e "Dashboard: http://localhost:8000"
echo -e "----------------------------------------------------"

# Run Main
echo -e "🤖 Starting with AGGRESSIVE mode..."
$PYTHON_CMD main.py --mode both --risk aggressive

# Exit handler
echo -e "${CYAN}System shutdown complete.${NC}"
