ARG BUILD_FROM
FROM $BUILD_FROM

# 1. Install packages
# 'jq' is required for the run.sh script to parse options
RUN apk add --no-cache python3 py3-pip jq

# 2. Install Python requirements
COPY requirements.txt /requirements.txt
RUN pip3 install --no-cache-dir -r /requirements.txt --break-system-packages

# 3. Copy application files
COPY trader_bot.py /trader_bot.py
# Only uncomment webui_assets.py if you actually have this file in your folder
COPY webui_assets.py /webui_assets.py
COPY default_config.yaml /default_config.yaml
COPY run.sh /run.sh

# 4. FIX LINE ENDINGS & PERMISSIONS (CRITICAL STEP)
# This prevents the "s6-overlay-suexec: fatal: can only run as pid 1" error
RUN sed -i 's/\r$//' /run.sh && chmod a+x /run.sh

# 5. Create data directory
RUN mkdir -p /data/tqqq-bot

# 6. Start Command
CMD [ "/run.sh" ]
