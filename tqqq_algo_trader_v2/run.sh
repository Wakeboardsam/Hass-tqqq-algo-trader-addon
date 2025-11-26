#!/usr/bin/env bash
# tqqq_algo_trader_v2/run.sh
set -euo pipefail

echo "[INFO] Starting TQQQ Algo Trader V2 initialization..."

# Location for persistent data
mkdir -p /data/tqqq-bot
echo "[INFO] Created /data/tqqq-bot directory"

# Copy default config to /data on first run
if [ ! -f /data/tqqq-bot/config.yaml ]; then
  echo "[INFO] Copying default config..."
  cp /app/default_config.yaml /data/tqqq-bot/config.yaml || {
    echo "[ERROR] Failed to copy config file"
    exit 1
  }
fi

# Expose environment variables from addon options (Home Assistant will set them)
export BOT_CONFIG="/data/tqqq-bot/config.yaml"
export LEDGER_DB="/data/tqqq-bot/ledger_v2.db"
export LOG_FILE="/data/tqqq-bot/bot.log"

echo "[INFO] Environment configured:"
echo "  BOT_CONFIG=$BOT_CONFIG"
echo "  LEDGER_DB=$LEDGER_DB"
echo "  LOG_FILE=$LOG_FILE"

# Verify Python script exists
if [ ! -f /app/trader_bot.py ]; then
  echo "[ERROR] trader_bot.py not found at /app/trader_bot.py"
  exit 1
fi

echo "[INFO] Launching TQQQ Algo Trader V2..."
exec python3 /app/trader_bot.py
