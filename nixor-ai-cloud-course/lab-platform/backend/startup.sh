#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# --- Live database lives on local disk, OUT of reach of the student terminal ----------
# /home on App Service is a world-writable Azure Files mount, so the unprivileged
# terminal sandbox user (uid 1000) can delete anything there. We keep the live SQLite DB
# in a root-owned 0700 directory on the container's local disk instead, so a malicious
# `rm -rf /` in the terminal gets permission-denied on the DB and login/signup keep
# working. Durability comes from the app's periodic backup to /home (DB_BACKUP_PATH).
#
# These are exported here (not just set as App Service app settings) so the security
# guarantee holds even on apps whose existing DATABASE_URL setting still points at /home.
LOCAL_DB_DIR="${LOCAL_DB_DIR:-/var/lib/nixor-lab}"
export DATABASE_URL="sqlite:///${LOCAL_DB_DIR}/lab_platform.db"
export DB_BACKUP_PATH="${DB_BACKUP_PATH:-/home/site/data/lab_platform.backup.db}"

mkdir -p "$LOCAL_DB_DIR"
chmod 700 "$LOCAL_DB_DIR"

# Persistent (terminal-reachable) locations for backups and student workspaces.
mkdir -p /home/site/data
mkdir -p /home/site/workspaces

# One-time migration: seed the persistent backup from any older on-/home DB so existing
# accounts survive the move. The app restores the live DB from DB_BACKUP_PATH on boot.
if [[ ! -f "$DB_BACKUP_PATH" ]]; then
  for legacy in /home/site/data/lab_platform.db /home/site/lab_platform.db; do
    if [[ -f "$legacy" ]]; then
      cp "$legacy" "$DB_BACKUP_PATH" 2>/dev/null || true
      break
    fi
  done
fi

exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
