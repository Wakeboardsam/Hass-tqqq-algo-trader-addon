#!/bin/sh
set -e

echo "[INFO] Starting TQQQ Algo Trader V2..."

# 1. Define config path (Standard HA location)
CONFIG_PATH="/data/options.json"

# 2. Read configuration using jq (Matches your config.json keys)
ALPACA_API_KEY=$(jq -r '.alpaca_api_key' "$CONFIG_PATH")
ALPACA_SECRET_KEY=$(jq -r '.alpaca_secret_key' "$CONFIG_PATH")
USE_PAPER=$(jq -r '.use_paper' "$CONFIG_PATH")

# 3. Validate Keys
if [ -z "$ALPACA_API_KEY" ] || [ "$ALPACA_API_KEY" = "null" ] || \
   [ -z "$ALPACA_SECRET_KEY" ] || [ "$ALPACA_SECRET_KEY" = "null" ]; then
    echo "[FATAL] Alpaca API keys are missing! Please check the Add-on Configuration."
    exit 1
fi

# 4. Export variables for Python
export ALPACA_API_KEY
export ALPACA_API_SECRET
# Convert boolean to string if needed, or just export
export USE_PAPER

# 5. Setup data directory
mkdir -p /data/tqqq-bot

# Copy default config if missing
if [ ! -f /data/tqqq-bot/config.yaml ]; then
    if [ -f /default_config.yaml ]; then
        cp /default_config.yaml /data/tqqq-bot/config.yaml
        echo "[INFO] Default config copied."
    else
        echo "[WARN] default_config.yaml not found."
    fi
fi

# 6. Export Paths
export BOT_CONFIG="/data/tqqq-bot/config.yaml"
export LEDGER_DB="/data/tqqq-bot/ledger_v2.db"
export LOG_FILE="/data/tqqq-bot/bot.log"

# 7. Start Bot (PID 1)
echo "[INFO] Launching Python process..."
exec python3 /trader_bot.py
