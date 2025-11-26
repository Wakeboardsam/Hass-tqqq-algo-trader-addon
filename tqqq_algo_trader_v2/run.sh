#!/usr/bin/env bash
# tqqq_algo_trader_v2/run.sh
set -euo pipefail

# Location for persistent data
mkdir -p /data/tqqq-bot
# Copy default config to /data on first run
if [ ! -f /data/tqqq-bot/config.yaml ]; then
  cp /app/default_config.yaml /data/tqqq-bot/config.yaml
fi

# Expose environment variables from addon options (Home Assistant will set them)
# This wrapper keeps compatibility with Supervisor env variables
export BOT_CONFIG="/data/tqqq-bot/config.yaml"
export LEDGER_DB="/data/tqqq-bot/ledger_v2.db"
export LOG_FILE="/data/tqqq-bot/bot.log"

# Start the bot as PID 1
echo "[INFO] Launching TQQQ Algo Trader V2..."
exec python3 /app/trader_bot.py
