#!/bin/bash
set -e

echo "[start] Starting ICS Bridge services..."

python web_admin.py &
WEB_PID=$!

python main.py &
SYNC_PID=$!

trap "kill $WEB_PID $SYNC_PID 2>/dev/null; exit" SIGINT SIGTERM

wait
