# Inside tqqq_algo_trader/Dockerfile

ARG BUILD_FROM
FROM $BUILD_FROM

# Set shell
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install Python and pip FIRST
RUN apk add --no-cache \
    python3 \
    py3-pip \
    && ln -sf python3 /usr/bin/python

# Copy files
COPY run.sh /run.sh
COPY trader_bot.py /trader_bot.py
COPY requirements.txt /requirements.txt

# Install Python dependencies - use pip3
RUN pip3 install --no-cache-dir -r /requirements.txt

# Make run script executable
RUN chmod a+x /run.sh

# Run the script
CMD [ "/run.sh" ]
