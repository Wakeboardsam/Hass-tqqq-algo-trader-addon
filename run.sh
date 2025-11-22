#!/usr/bin/with-contenv bashio
# Inside tqqq_algo_trader/run.sh

# 1. Read the API keys securely from the Add-on Options and export them
# This keeps the keys out of your public GitHub repo.
export ALPACA_API_KEY_ID=$(bashio::config 'alpaca_api_key_id')
export ALPACA_SECRET_KEY=$(bashio::config 'alpaca_secret_key')

# Check if keys were successfully loaded
if [ -z "$ALPACA_API_KEY_ID" ] || [ -z "$ALPACA_SECRET_KEY" ]; then
    echo "FATAL ERROR: Alpaca API keys are missing. Please check the Add-on configuration settings!"
    exit 1
fi

# 2. Start the main Python script
echo "Starting TQQQ Algo Trader bot..."
python3 /trader_bot.py
