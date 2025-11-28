#!/bin/sh
set -e

# Define config path
CONFIG_PATH="/data/options.json"

echo "[INFO] Starting TQQQ Bot Tester (Simulation Mode)..."

# Check if options.json exists
if [ ! -f "$CONFIG_PATH" ]; then
    echo "[FATAL] $CONFIG_PATH not found! Is this running as a Home Assistant Add-on?"
    exit 1
fi

# Read configuration using jq
echo "[INFO] Reading configuration..."
# For the tester, we don't strictly need API keys, but we can read them if present
# Just to be safe, we mainly care about the manual_market_price for the simulation
MANUAL_PRICE=$(jq -r '.manual_market_price // 100' "$CONFIG_PATH")
echo "[INFO] Simulation Start Price: $MANUAL_PRICE"

# Setup data directory
mkdir -p /data/tqqq-bot-tester

# Export Paths
export BOT_CONFIG="/data/options.json"
export LEDGER_DB="/config/tqqq-bot-tester/tester_ledger.db"
export LOG_FILE="/config/tqqq-bot-tester/tester.log"

# Start Bot Tester (PID 1) with Unbuffered Output (-u)
echo "[INFO] Launching Python Simulation process..."
exec python3 -u /bot_tester.py