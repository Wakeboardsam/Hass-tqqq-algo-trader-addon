# tqqq_algo_trader_v2/Dockerfile
ARG BUILD_FROM
FROM $BUILD_FROM

# install packages
RUN apk add --no-cache python3 py3-pip bash

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir -r /app/requirements.txt --break-system-packages

COPY run.sh /run.sh
COPY trader_bot.py /app/trader_bot.py
COPY webui_assets.py /app/webui_assets.py
COPY default_config.yaml /app/default_config.yaml
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
