ARG BUILD_FROM
FROM $BUILD_FROM

# Install packages
RUN apk add --no-cache \
    jq \
    python3 \
    py3-pip \
    bash

# Copy and install Python requirements
COPY requirements.txt /requirements.txt
RUN pip3 install --no-cache-dir -r /requirements.txt --break-system-packages

# Copy application files
COPY trader_bot.py /trader_bot.py
COPY webui_assets.py /webui_assets.py
COPY default_config.yaml /default_config.yaml

# Copy run script to S6 services directory
COPY run.sh /etc/services.d/tqqq-bot/run

# Fix line endings and make executable
RUN sed -i 's/\r$//' /etc/services.d/tqqq-bot/run && \
    chmod a+x /etc/services.d/tqqq-bot/run
