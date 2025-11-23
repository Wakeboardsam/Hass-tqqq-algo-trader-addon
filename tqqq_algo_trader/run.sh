#!/command/with-contenv bash
# Inside tqqq_algo_trader/run.sh

# Source bashio library
source /usr/lib/bashio/bashio.sh

bashio::log.info "Starting TQQQ Algo Trader setup..."

# 1. Export API keys securely
export ALPACA_API_KEY_ID=$(bashio::config 'alpaca_api_key_id')
export ALPACA_SECRET_KEY=$(bashio::config 'alpaca_secret_key')

# 2. Check for missing keys
if bashio::var.is_empty "${ALPACA_API_KEY_ID}" || bashio::var.is_empty "${ALPACA_SECRET_KEY}"; then
    bashio::log.fatal "Alpaca API keys are missing. Please check the Add-on configuration settings!"
    exit 1
fi

# 3. Launch main Python process with exec
bashio::log.info "Launching main Python process..."
exec python3 /trader_bot.py
