ARG BUILD_FROM
FROM $BUILD_FROM

# 1. Install packages
# 'jq' is required for the run.sh script to parse options if needed, 
# and python3/pip are obviously needed for the bot.
RUN apk add --no-cache python3 py3-pip jq

# 2. Install Python requirements
# We copy the requirements file first to leverage Docker layer caching
COPY requirements.txt /requirements.txt
# --break-system-packages is required on newer Alpine/Python versions to install pip packages globally
RUN pip3 install --no-cache-dir -r /requirements.txt --break-system-packages

# 3. Copy application files
# The main trading logic
COPY trader_bot.py /trader_bot.py
# The Web UI logic (CRITICAL: You must have created this file in the previous step)
COPY webui_assets.py /webui_assets.py
# The default config file (used by Home Assistant to populate options)
COPY default_config.yaml /default_config.yaml
# The startup script
COPY run.sh /run.sh

# 4. FIX LINE ENDINGS & PERMISSIONS (CRITICAL STEP)
# This prevents the "s6-overlay-suexec: fatal: can only run as pid 1" error
# and "standard_init_linux.go: exec user process caused: no such file or directory"
RUN sed -i 's/\r$//' /run.sh && chmod a+x /run.sh

# 5. Create data directory
# This ensures the folder exists, though the persistence logic in Python also handles subfolders
RUN mkdir -p /data/tqqq-bot

# 6. Start Command
CMD [ "/run.sh" ]

