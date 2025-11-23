# Inside tqqq_algo_trader/Dockerfile

ARG BUILD_FROM
FROM ${BUILD_FROM}

# Install jq, Python3 and pip
RUN apk add --no-cache jq python3 py3-pip

# Copy requirements and install Python dependencies
COPY requirements.txt /requirements.txt
RUN pip3 install --no-cache-dir -r /requirements.txt --break-system-packages

# Copy application files
COPY trader_bot.py /trader_bot.py
COPY run.sh /run.sh

# IMPORTANT: Make run script executable (required for s6-overlay v3)
RUN chmod a+x /run.sh

# Use s6-overlay's init as entrypoint (no CMD override)
CMD [ "/run.sh" ]
