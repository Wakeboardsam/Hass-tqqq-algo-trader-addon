# Inside tqqq_algo_trader/Dockerfile

# Use the official Home Assistant Add-on base image
ARG BUILD_FROM
FROM ${BUILD_FROM}

# Install Python3 and pip explicitly, just in case the base image is minimal
# This addresses the 'pip not found' issue reliably.
RUN apk add --no-cache python3 py3-pip && \
    ln -sf python3 /usr/bin/python

# Copy files
COPY run.sh /run.sh
COPY trader_bot.py /trader_bot.py
COPY requirements.txt /requirements.txt

# Install the Python dependencies (alpaca-py and pandas)
# 🚨 FIX: Use --break-system-packages to override PEP 668 restriction 
RUN pip3 install --no-cache-dir -r /requirements.txt --break-system-packages

# Make run script executable
RUN chmod a+x /run.sh

# The command that executes when the Docker container starts
CMD [ "/run.sh" ]
