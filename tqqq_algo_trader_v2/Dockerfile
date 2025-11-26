ARG BUILD_FROM
FROM $BUILD_FROM

# Install Python AND jq (Required for the new run.sh)
RUN apk add --no-cache python3 py3-pip jq

# Install Python requirements
COPY requirements.txt /requirements.txt
RUN pip3 install --no-cache-dir -r /requirements.txt --break-system-packages

# Copy application files
COPY trader_bot.py /trader_bot.py
COPY webui_assets.py /webui_assets.py
COPY default_config.yaml /default_config.yaml
COPY run.sh /run.sh

# Make run.sh executable (Critical step)
RUN chmod a+x /run.sh

# Create data directory
RUN mkdir -p /data/tqqq-bot

# Start using run.sh
CMD [ "/run.sh" ]
