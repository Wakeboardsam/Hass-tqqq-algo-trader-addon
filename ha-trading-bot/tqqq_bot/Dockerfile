ARG BUILD_FROM
FROM $BUILD_FROM

# Install Python and libraries
RUN apk add --no-cache python3 py3-pip
COPY requirements.txt /tmp/
RUN pip3 install -r /tmp/requirements.txt --break-system-packages

WORKDIR /app
COPY . /app

CMD [ "python3", "main.py" ]
