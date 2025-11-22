#!/usr/bin/with-contenv bashio
# Inside tqqq_algo_trader/run.sh

echo "Starting TQQQ Algo Trader setup..."

# 1. Export API keys securely
export ALPACA_API_KEY_ID=$(bashio::config 'alpaca_api_key_id')
export ALPACA_SECRET_KEY=$(bashio::config 'alpaca_secret_key')

# 2. Check for missing keys
if [ -z "$ALPACA_API_KEY_ID" ] || [ -z "$ALPACA_SECRET_KEY" ]; then
    echo "FATAL ERROR: Alpaca API keys are missing. Please check the Add-on configuration settings!"
    # Do not use exec here, allow script to exit gracefully
    exit 1
fi

# 3. Use 'exec' to replace the current shell process with the Python script.
# This forces the Python script to run as PID 1, resolving the s6-overlay error.
echo "Launching main Python process..."
exec python3 /trader_bot.py
