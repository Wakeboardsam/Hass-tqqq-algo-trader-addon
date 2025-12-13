ARG BUILD_FROM
FROM $BUILD_FROM

# 1. Install packages
RUN apk add --no-cache python3 py3-pip jq

# 2. Install Python requirements
COPY requirements.txt /requirements.txt
RUN pip3 install --no-cache-dir -r /requirements.txt --break-system-packages

# 3. Copy YOUR SPECIFIC new bot file
# You mentioned the script is 'main.py', so we copy that.
COPY main.py /main.py

# 4. GENERATE THE RUN SCRIPT INTERNALLY (The Fix)
# We write the script right here to guarantee Linux formatting.
# It simply says: "Start main.py using python3"
RUN printf "#!/bin/sh\n\
set -e\n\
\n\
echo \"[INFO] Starting TQQQ Volatility Bot...\"\n\
\n\
# Start Bot with Unbuffered Output (-u) to see logs instantly\n\
exec python3 -u /main.py\n\
" > /run.sh && chmod a+x /run.sh

# 5. Start Command
CMD [ "/run.sh" ]