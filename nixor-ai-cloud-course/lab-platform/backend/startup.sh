#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# App Service writable locations for runtime state.
mkdir -p /home/site/data
mkdir -p /home/site/workspaces

# One-time migration in case an older deployment wrote DB at /home/site/lab_platform.db.
if [[ -f /home/site/lab_platform.db && ! -f /home/site/data/lab_platform.db ]]; then
  cp /home/site/lab_platform.db /home/site/data/lab_platform.db
fi

exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
