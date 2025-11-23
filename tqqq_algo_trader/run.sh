#!/usr/bin/with-contenv bashio
# Inside tqqq_algo_trader/run.sh

echo "Starting TQQQ Algo Trader setup..."

# 1. Export API keys securely
export ALPACA_API_KEY_ID=$(bashio::config 'alpaca_api_key_id')
export ALPACA_SECRET_KEY=$(bashio::config 'alpaca_secret_key')

# 2. Check for missing keys
if [ -z "$ALPACA_API_KEY_ID" ] || [ -z "$ALPACA_SECRET_KEY" ]; then
    bashio::log.fatal "Alpaca API keys are missing. Please check the Add-on configuration settings!"
    exit 1
fi

# 3. Launch main Python process with exec (keeps PID 1 chain)
bashio::log.info "Launching main Python process..."
exec python3 /trader_bot.py
