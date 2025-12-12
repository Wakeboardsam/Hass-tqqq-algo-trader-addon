#!/bin/sh
set -e

# Start the Python application
# We use 'exec' so Python takes over PID 1 from this script
echo "Starting TQQQ Bot..."
exec python3 main.py