#!/usr/bin/env bash
# Pull and (re)start the platform container. Invoked by the nixor-lab systemd unit on the
# VM. Idempotent: stops/removes any existing container, logs into ACR via the VM's managed
# identity, pulls the image, and runs it --privileged so the per-terminal jail can engage.
set -euo pipefail

IMAGE="${NIXOR_IMAGE:?set NIXOR_IMAGE (e.g. myacr.azurecr.io/nixor-lab:latest)}"
ACR_NAME="${NIXOR_ACR:-}"          # registry name without .azurecr.io; enables az acr login
ENV_FILE="${NIXOR_ENV_FILE:-/etc/nixor-lab.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Env file $ENV_FILE not found; refusing to start without configuration." >&2
  exit 1
fi

# Authenticate to ACR using the VM's system-assigned managed identity (granted AcrPull).
if [[ -n "$ACR_NAME" ]]; then
  az login --identity >/dev/null
  az acr login --name "$ACR_NAME" >/dev/null
fi

docker pull "$IMAGE"

docker rm -f nixor-lab >/dev/null 2>&1 || true

# --privileged grants CAP_SYS_ADMIN so unshare(CLONE_NEWNS)+mount work and the chroot jail
# engages. Named volumes persist the DB, its backup, and student workspaces across restarts
# and image updates.
exec docker run --rm --name nixor-lab \
  --privileged \
  -p 127.0.0.1:8000:8000 \
  -v nixor-db:/var/lib/nixor-lab \
  -v nixor-backup:/home/site/data \
  -v nixor-workspaces:/home/site/workspaces \
  --env-file "$ENV_FILE" \
  --memory-swappiness 0 \
  "$IMAGE"
