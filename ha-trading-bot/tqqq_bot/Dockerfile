ARG BUILD_FROM
FROM $BUILD_FROM

# Install Python and dependencies
RUN apk add --no-cache python3 py3-pip
COPY requirements.txt /tmp/
RUN pip3 install -r /tmp/requirements.txt

# Copy App
WORKDIR /app
COPY . /app

# Run
CMD [ "python3", "main.py" ]
