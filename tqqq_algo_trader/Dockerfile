# Inside tqqq_algo_trader/Dockerfile

# Base image for Home Assistant Add-ons that require Python
ARG BUILD_FROM
FROM $BUILD_FROM

# Copy all the necessary files into the container's working directory
COPY run.sh /run.sh
COPY trader_bot.py /trader_bot.py
COPY requirements.txt /requirements.txt

# Install the Python dependencies (alpaca-py and pandas)
RUN pip install -r /requirements.txt --no-cache-dir

# Ensure the run script is executable
RUN chmod a+x /run.sh

# The command that executes when the Docker container starts
CMD [ "/run.sh" ]
