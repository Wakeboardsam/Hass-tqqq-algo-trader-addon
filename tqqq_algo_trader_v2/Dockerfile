ARG BUILD_FROM
FROM $BUILD_FROM

# Install packages (bashio is usually included in the base image)
RUN apk add --no-cache python3 py3-pip

# Copy and install Python requirements
COPY requirements.txt /requirements.txt
RUN pip3 install --no-cache-dir -r /requirements.txt --break-system-packages

# Copy application files
COPY trader_bot.py /trader_bot.py
COPY webui_assets.py /webui_assets.py
COPY default_config.yaml /default_config.yaml
COPY run.sh /run.sh

# Make run.sh executable
RUN chmod a+x /run.sh

# Create data directory
RUN mkdir -p /data/tqqq-bot

# Set S6 Entrypoint to run.sh
CMD [ "/run.sh" ]
