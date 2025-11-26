#!/usr/bin/env bash
# tqqq_algo_trader_v2/run.sh

set -euo pipefail

# Load bashio helpers (standard HA practice)
if [ -f /usr/lib/bashio/bashio.sh ]; then
  . /usr/lib/bashio/bashio.sh
fi

# 1. Read configuration secrets from /data/options.json
# Using bashio::config is the preferred way to read addon options.
# We assume the option names in your V2 config are similar to your working bot's names.
ALPACA_API_KEY=$(bashio::config 'alpaca_api_key_id')
ALPACA_API_SECRET=$(bashio::config 'alpaca_secret_key')

# 2. Check for missing keys (critical step from your working bot)
if [ -z "$ALPACA_API_KEY" ] || [ "$ALPACA_API_KEY" = "null" ] || \
   [ -z "$ALPACA_API_SECRET" ] || [ "$ALPACA_API_SECRET" = "null" ]; then
    bashio::log.fatal "Alpaca API keys are missing. Please ensure 'alpaca_api_key_id' and 'alpaca_secret_key' are set in the Add-on Configuration."
    exit 1
fi

# 3. Expose secrets as environment variables for Python script
# The trader_bot.py code needs these exact variable names.
export ALPACA_API_KEY
export ALPACA_API_SECRET

# 4. Location for persistent data & default config setup
mkdir -p /data/tqqq-bot
# Copy default config to /data on first run
if [ ! -f /data/tqqq-bot/config.yaml ]; then
  cp /app/default_config.yaml /data/tqqq-bot/config.yaml
fi

# 5. Expose other environment variables
export BOT_CONFIG="/data/tqqq-bot/config.yaml"
export LEDGER_DB="/data/tqqq-bot/ledger_v2.db"
export LOG_FILE="/data/tqqq-bot/bot.log"

# Start the bot as PID 1 of this container process
# 'exec' is the critical fix for the s6-overlay: fatal: can only run as pid 1 error.
echo "[INFO] Launching TQQQ Algo Trader V2..."
exec python3 /app/trader_bot.py
