ARG BUILD_FROM
FROM $BUILD_FROM

# Install packages
RUN apk add --no-cache \
    python3 \
    py3-pip

# Copy and install Python requirements
COPY requirements.txt /requirements.txt
RUN pip3 install --no-cache-dir -r /requirements.txt --break-system-packages

# Copy application files
COPY trader_bot.py /trader_bot.py
COPY webui_assets.py /webui_assets.py
COPY default_config.yaml /default_config.yaml

# Create data directory and setup
RUN mkdir -p /data/tqqq-bot && \
    cp /default_config.yaml /data/tqqq-bot/config.yaml

# Set environment variables
ENV BOT_CONFIG="/data/tqqq-bot/config.yaml"
ENV LEDGER_DB="/data/tqqq-bot/ledger_v2.db"
ENV LOG_FILE="/data/tqqq-bot/bot.log"

# Run Python directly - no shell script
CMD ["python3", "/trader_bot.py"]
