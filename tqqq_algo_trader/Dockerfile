# Inside tqqq_algo_trader/Dockerfile

ARG BUILD_FROM
FROM ${BUILD_FROM}

# Install Python3 and pip
RUN apk add --no-cache python3 py3-pip

# Copy requirements and install Python dependencies
COPY requirements.txt /requirements.txt
RUN pip3 install --no-cache-dir -r /requirements.txt --break-system-packages

# Copy application files
COPY trader_bot.py /trader_bot.py

# Copy run script to s6-overlay services directory
# This is the correct location for Home Assistant add-ons
COPY run.sh /etc/services.d/tqqq_algo_trader/run
RUN chmod a+x /etc/services.d/tqqq_algo_trader/run

# No CMD needed - s6-overlay handles initialization
