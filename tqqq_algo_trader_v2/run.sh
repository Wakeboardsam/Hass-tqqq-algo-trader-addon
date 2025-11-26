#!/usr/bin/with-contenv bashio
set -e

bashio::log.info "Starting TQQQ Algo Trader V2..."

# Location for persistent data
mkdir -p /data/tqqq-bot

# Copy default config to /data on first run
if [ ! -f /data/tqqq-bot/config.yaml ]; then
  cp /default_config.yaml /data/tqqq-bot/config.yaml
fi

# Expose environment variables
export BOT_CONFIG="/data/tqqq-bot/config.yaml"
export LEDGER_DB="/data/tqqq-bot/ledger_v2.db"
export LOG_FILE="/data/tqqq-bot/bot.log"

# Run the bot (s6 will manage it as a service)
exec python3 /trader_bot.py
