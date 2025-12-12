# Use the community standard image which supports VNC and headless
FROM ghcr.io/gnzsnz/ib-gateway:stable

# Environment variables to configure the gateway
ENV TWS_USERID=""
ENV TWS_PASSWORD=""
ENV TRADING_MODE="live"
ENV VNC_SERVER_PASSWORD="password" 
# ^ You will use this password to VNC in for the 2FA step

# The addon system passes options as JSON, but this image expects ENV vars.
# We use a simple launch script to map them if needed, but for simplicity
# we will rely on HA injecting them or setting them via the Options tab.
