# Inside tqqq_algo_trader/Dockerfile (Final Version)

# Use the official Home Assistant base image provided by the builder
ARG BUILD_FROM
FROM ${BUILD_FROM}

# Install any required system dependencies (none needed here for python)
# We rely on the builder to inject python/pip, which maintains bashio compatibility.
# The previous manual apk add was the source of the bashio lookup error.

# Copy requirements and install Python dependencies
COPY requirements.txt /requirements.txt
RUN pip3 install --no-cache-dir -r /requirements.txt --break-system-packages

# Copy application files
COPY trader_bot.py /trader_bot.py
COPY run.sh /run.sh

# IMPORTANT: Make run script executable
RUN chmod a+x /run.sh

# The command that runs when the Docker container starts
CMD [ "/run.sh" ]
