#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title ICS Bridge Sync
# @raycast.mode compact

# Optional parameters:
# @raycast.icon 📅
# @raycast.packageName ICS Bridge

# Documentation:
# @raycast.description Manually trigger ICS to Google Calendar sync

set -euo pipefail

cd "$(dirname "$0")"

PYTHON=".venv/bin/python"
if [ ! -x "$PYTHON" ]; then
    echo "No .venv found. Run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
    exit 1
fi

# Load environment variables from .env (handles quoted values and spaces)
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# Run sync once and exit
if "$PYTHON" -c "from main import sync_once; sync_once()"; then
    echo "Calendar sync complete"
else
    echo "Calendar sync failed"
    exit 1
fi
