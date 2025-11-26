ARG BUILD_FROM
FROM $BUILD_FROM

# 1. Install packages
# Added 'jq' because your run.sh needs it
RUN apk add --no-cache python3 py3-pip jq

# 2. Install Python requirements
COPY requirements.txt /requirements.txt
RUN pip3 install --no-cache-dir -r /requirements.txt --break-system-packages

# 3. Copy application files
COPY trader_bot.py /trader_bot.py
COPY webui_assets.py /webui_assets.py
COPY default_config.yaml /default_config.yaml
COPY run.sh /run.sh

# 4. FIX LINE ENDINGS & PERMISSIONS (CRITICAL STEP)
# This removes Windows \r characters and makes the script executable
RUN sed -i 's/\r$//' /run.sh && chmod a+x /run.sh

# 5. Create data directory
RUN mkdir -p /data/tqqq-bot

# 6. Start Command
CMD [ "/run.sh" ]
