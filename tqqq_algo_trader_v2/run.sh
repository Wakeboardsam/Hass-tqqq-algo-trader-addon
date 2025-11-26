#!/usr/bin/env bash
set -e

# 1. Load bashio library safely (Standard Home Assistant pattern)
if [ -f /usr/lib/bashio/bashio.sh ]; then
    source /usr/lib/bashio/bashio.sh
else
    echo "Bashio not found. Ensure this is running in a Home Assistant Add-on."
    exit 1
fi

bashio::log.info "Starting TQQQ Algo Trader V2 setup..."

# 2. Location for persistent data
mkdir -p /data/tqqq-bot

# Copy default config to /data on first run if it doesn't exist
if [ ! -f /data/tqqq-bot/config.yaml ]; then
  if [ -f /default_config.yaml ]; then
      cp /default_config.yaml /data/tqqq-bot/config.yaml
      bashio::log.info "Default config copied to /data/tqqq-bot/config.yaml"
  else
      bashio::log.warning "default_config.yaml not found!"
  fi
fi

# 3. Read options from config.json (Environment variables)
# We read the values defined in your config.json options
ALPACA_API_KEY=$(bashio::config 'alpaca_api_key')
ALPACA_SECRET_KEY=$(bashio::config 'alpaca_secret_key')
USE_PAPER=$(bashio::config 'use_paper')

# 4. Check for missing keys
if bashio::var.is_empty "${ALPACA_API_KEY}" || bashio::var.is_empty "${ALPACA_SECRET_KEY}"; then
    bashio::log.fatal "Alpaca API keys are missing! Check your Add-on Configuration."
    bashio::exit.nok
fi

# 5. Export variables for Python script
# trader_bot.py looks for "ALPACA_API_KEY" and "ALPACA_API_SECRET"
export ALPACA_API_KEY="${ALPACA_API_KEY}"
export ALPACA_API_SECRET="${ALPACA_SECRET_KEY}"
export BOT_CONFIG="/data/tqqq-bot/config.yaml"
export LEDGER_DB="/data/tqqq-bot/ledger_v2.db"
export LOG_FILE="/data/tqqq-bot/bot.log"

bashio::log.info "Configuration loaded. Launching Trader Bot..."

# 6. Start the bot as PID 1
# 'exec' is critical here to avoid the s6-overlay PID 1 error
exec python3 /trader_bot.py
