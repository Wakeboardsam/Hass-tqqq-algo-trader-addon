ARG BUILD_FROM
FROM $BUILD_FROM

# 1. Install packages
RUN apk add --no-cache python3 py3-pip jq

# 2. Install Python requirements
COPY requirements.txt /requirements.txt
RUN pip3 install --no-cache-dir -r /requirements.txt --break-system-packages

# 3. Copy ONLY the python files and config
# (Do NOT copy run.sh here, we will generate it below)
COPY bot_tester.py /bot_tester.py
COPY webui_assets.py /webui_assets.py
COPY default_config.yaml /default_config.yaml

# 4. GENERATE THE RUN SCRIPT INTERNALLY (The Nuclear Fix)
# This creates a perfect run.sh file inside the container, 
# ignoring whatever corrupted file you might have on your computer.
RUN printf "#!/bin/sh\n\
set -e\n\
\n\
# Define config path\n\
CONFIG_PATH=\"/data/options.json\"\n\
\n\
echo \"[INFO] Starting TQQQ Bot...\"\n\
\n\
# Export Paths\n\
export BOT_CONFIG=\"/data/options.json\"\n\
export LEDGER_DB=\"/config/tqqq-bot-tester/tester_ledger.db\"\n\
export LOG_FILE=\"/config/tqqq-bot-tester/tester.log\"\n\
\n\
# Setup data directory\n\
mkdir -p /data/tqqq-bot-tester\n\
\n\
# Start Bot (PID 1) with Unbuffered Output\n\
echo \"[INFO] Launching Python process...\"\n\
exec python3 -u /bot_tester.py\n\
" > /run.sh && chmod a+x /run.sh

# 5. Start Command
CMD [ "/run.sh" ]
