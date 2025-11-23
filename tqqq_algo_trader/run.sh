#!/command/with-contenv sh
# Inside tqqq_algo_trader/run.sh

echo "[INFO] Starting TQQQ Algo Trader setup..."

# 1. Read config using jq (available in base image)
CONFIG_PATH="/data/options.json"

ALPACA_API_KEY_ID=$(jq -r '.alpaca_api_key_id' "$CONFIG_PATH")
ALPACA_SECRET_KEY=$(jq -r '.alpaca_secret_key' "$CONFIG_PATH")

export ALPACA_API_KEY_ID
export ALPACA_SECRET_KEY

# 2. Check for missing keys
if [ -z "$ALPACA_API_KEY_ID" ] || [ "$ALPACA_API_KEY_ID" = "null" ] || \
   [ -z "$ALPACA_SECRET_KEY" ] || [ "$ALPACA_SECRET_KEY" = "null" ]; then
    echo "[FATAL] Alpaca API keys are missing. Please check the Add-on configuration settings!"
    exit 1
fi

# 3. Launch main Python process with exec
echo "[INFO] Launching main Python process..."
exec python3 /trader_bot.py
