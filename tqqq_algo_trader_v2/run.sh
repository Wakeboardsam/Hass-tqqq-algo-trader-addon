#!/bin/sh
set -e

# 1. Define config path
CONFIG_PATH="/data/options.json"

# 2. Read configuration using jq
ALPACA_API_KEY=$(jq -r '.alpaca_api_key' "$CONFIG_PATH")
ALPACA_SECRET_KEY=$(jq -r '.alpaca_secret_key' "$CONFIG_PATH")
USE_PAPER=$(jq -r '.use_paper' "$CONFIG_PATH")

# 3. Export variables for Python
export ALPACA_API_KEY
export ALPACA_API_SECRET
export USE_PAPER

# 4. Setup data directory
mkdir -p /data/tqqq-bot
if [ ! -f /data/tqqq-bot/config.yaml ]; then
    if [ -f /default_config.yaml ]; then
        cp /default_config.yaml /data/tqqq-bot/config.yaml
    fi
fi

# 5. Export Paths
export BOT_CONFIG="/data/tqqq-bot/config.yaml"
export LEDGER_DB="/data/tqqq-bot/ledger_v2.db"
export LOG_FILE="/data/tqqq-bot/bot.log"

# 6. Start Bot (PID 1)
echo "[INFO] Launching Python process..."
exec python3 /trader_bot.py
