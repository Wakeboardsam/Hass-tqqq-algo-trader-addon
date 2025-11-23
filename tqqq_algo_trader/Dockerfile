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

# Copy run script to the correct s6-overlay v3 location
RUN mkdir -p /etc/s6-overlay/s6-rc.d/tqqq_algo_trader && \
    mkdir -p /etc/s6-overlay/s6-rc.d/user/contents.d

COPY run.sh /etc/s6-overlay/s6-rc.d/tqqq_algo_trader/run
RUN chmod a+x /etc/s6-overlay/s6-rc.d/tqqq_algo_trader/run

# Define service type (longrun = continuously running service)
RUN echo "longrun" > /etc/s6-overlay/s6-rc.d/tqqq_algo_trader/type

# Enable the service
RUN touch /etc/s6-overlay/s6-rc.d/user/contents.d/tqqq_algo_trader

# DO NOT override CMD - let s6-overlay init handle it
