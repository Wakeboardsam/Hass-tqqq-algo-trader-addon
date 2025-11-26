#!/bin/sh
set -e

# Define config path
CONFIG_PATH="/data/options.json"

echo "[INFO] Starting TQQQ Algo Trader V2..."

# Check if options.json exists
if [ ! -f "$CONFIG_PATH" ]; then
    echo "[FATAL] $CONFIG_PATH not found! Is this running as a Home Assistant Add-on?"
    exit 1
fi

# Read configuration using jq
echo "[INFO] Reading configuration..."
ALPACA_API_KEY=$(jq -r '.alpaca_api_key // empty' "$CONFIG_PATH")
ALPACA_SECRET_KEY=$(jq -r '.alpaca_secret_key // empty' "$CONFIG_PATH")
USE_PAPER=$(jq -r '.use_paper // true' "$CONFIG_PATH")

# Debug: Check if keys were found (without printing them)
if [ -z "$ALPACA_API_KEY" ]; then
    echo "[WARNING] ALPACA_API_KEY is empty or missing in Add-on Configuration!"
else
    echo "[INFO] ALPACA_API_KEY loaded (length: ${#ALPACA_API_KEY})"
fi

if [ -z "$ALPACA_SECRET_KEY" ]; then
    echo "[WARNING] ALPACA_SECRET_KEY is empty or missing in Add-on Configuration!"
else
    echo "[INFO] ALPACA_SECRET_KEY loaded (length: ${#ALPACA_SECRET_KEY})"
fi

# Export variables for Python
export ALPACA_API_KEY
export ALPACA_SECRET_KEY
export USE_PAPER

# Setup data directory
mkdir -p /data/tqqq-bot

# Handle default config
if [ ! -f /data/tqqq-bot/config.yaml ]; then
    if [ -f /default_config.yaml ]; then
        cp /default_config.yaml /data/tqqq-bot/config.yaml
        echo "[INFO] Default config copied to /data/tqqq-bot/config.yaml"
    else
        echo "[WARN] /default_config.yaml not found in container"
    fi
fi

# Export Paths
export BOT_CONFIG="/data/tqqq-bot/config.yaml"
export LEDGER_DB="/data/tqqq-bot/ledger_v2.db"
export LOG_FILE="/data/tqqq-bot/bot.log"

# Start Bot (PID 1) with Unbuffered Output (-u)
# The -u flag is critical to seeing why it crashes immediately
echo "[INFO] Launching Python process..."
exec python3 -u /trader_bot.py
