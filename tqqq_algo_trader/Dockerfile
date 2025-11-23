# Inside tqqq_algo_trader/Dockerfile

ARG BUILD_FROM
FROM ${BUILD_FROM}

# Install Python3 and pip explicitly
RUN apk add --no-cache python3 py3-pip bash && \
    ln -sf python3 /usr/bin/python

# Copy files
COPY run.sh /run.sh
COPY trader_bot.py /trader_bot.py
COPY requirements.txt /requirements.txt

# Install the Python dependencies (alpaca-py and pandas)
# FIX: Use --break-system-packages to override PEP 668 restriction 
RUN pip3 install --no-cache-dir -r /requirements.txt --break-system-packages

# Make run script executable
RUN chmod a+x /run.sh

# 🚨 FIX: Use the bash shell to execute the run script, forcing it to take PID 1.
CMD [ "/bin/bash", "/run.sh" ]
