ARG BUILD_FROM
FROM $BUILD_FROM

# Install packages
RUN apk add --no-cache \
    jq \
    python3 \
    py3-pip \
    bash

WORKDIR /app

# Copy and install Python requirements
COPY requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir -r /app/requirements.txt --break-system-packages

# Copy application files
COPY trader_bot.py /app/trader_bot.py
COPY webui_assets.py /app/webui_assets.py
COPY default_config.yaml /app/default_config.yaml

# Copy run script
COPY run.sh /run.sh

# Fix line endings (in case of Windows CRLF) and make executable
RUN sed -i 's/\r$//' /run.sh && chmod a+x /run.sh

# Use s6-overlay's init as entrypoint
CMD [ "/run.sh" ]
