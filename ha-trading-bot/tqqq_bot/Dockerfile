ARG BUILD_FROM
FROM $BUILD_FROM

# 1. Install Python and dependencies
RUN apk add --no-cache python3 py3-pip
COPY requirements.txt /tmp/
RUN pip3 install -r /tmp/requirements.txt --break-system-packages

# 2. Set working directory
WORKDIR /app

# 3. Copy files
COPY . /app

# 4. THE FIX: Copy run.sh and strip Windows line endings
# We copy it to root (/) as is standard for HA add-on startup scripts
COPY run.sh /run.sh
RUN sed -i 's/\r$//' /run.sh && chmod a+x /run.sh

# 5. Define the command to run
CMD [ "/run.sh" ]