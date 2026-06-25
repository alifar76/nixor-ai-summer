#!/usr/bin/env bash
# Provision the Nixor AI Lab on a privileged Docker VM in Azure — the setup where the
# per-terminal chroot jail actually engages (CAP_SYS_ADMIN available via --privileged).
#
# What it does (idempotent; safe to re-run):
#   1. Create resource group + Azure Container Registry (Basic).
#   2. Build the image server-side with `az acr build` from your LOCAL checkout (so it
#      deploys exactly the branch you're on — use the `dev` branch for testing).
#   3. Create an Ubuntu 22.04 VM (default Standard_D16s_v5) with a system-assigned managed
#      identity, grant it AcrPull, and bootstrap Docker+Caddy via cloud-init.
#   4. Push the app config to /etc/nixor-lab.env and the container runner to the VM, then
#      start the systemd service.
#
# Secrets (SESSION_SIGNING_KEY etc.) come from your environment and are pushed via
# `az vm run-command` — they are NEVER written into cloud-init/custom-data or git.
#
# Usage:
#   SESSION_SIGNING_KEY=... [INSTRUCTOR_EMAIL=... INSTRUCTOR_PASSWORD=... SIGNUP_ACCESS_CODE=... \
#     EXTRA_CORS_ORIGINS="https://<ip>.nip.io,https://other.example"] \
#   ./deploy_vm.sh <resource-group> <location> <vm-name> <domain>
#
#   EXTRA_CORS_ORIGINS — optional, comma-separated origins appended to CORS_ORIGINS in
#     addition to https://<domain>. Use when the VM is served under multiple hostnames.
#
#   <domain> must already have a DNS A record pointing at the VM's public IP for Caddy to
#   get a TLS cert. For a quick test you can re-run after the IP is known, or use
#   "<publicip>.nip.io".
set -euo pipefail

if [[ $# -lt 4 ]]; then
  echo "Usage: SESSION_SIGNING_KEY=... $0 <resource-group> <location> <vm-name> <domain>" >&2
  exit 1
fi

RG="$1"; LOCATION="$2"; VM_NAME="$3"; DOMAIN="$4"
VM_SIZE="${VM_SIZE:-Standard_D16s_v5}"     # 16 vCPU / 64 GB. Bump to Standard_D32s_v5 for more headroom.
DATA_DISK_GB="${DATA_DISK_GB:-128}"        # premium SSD for DB + workspaces IO
ACR_NAME="${ACR_NAME:-nixoracr$RANDOM}"    # must be globally unique, alphanumeric
IMAGE_TAG="${IMAGE_TAG:-nixor-lab:latest}"
ADMIN_USER="${ADMIN_USER:-azureuser}"
AZURE_OPENAI_ENDPOINT="${AZURE_OPENAI_ENDPOINT:-}"
AZURE_OPENAI_API_KEY="${AZURE_OPENAI_API_KEY:-}"
# Deployment that backs the in-app coding chatbot (the platform tutor) — GPT-5.5 on the
# Azure OpenAI resource. AZURE_OPENAI_* (endpoint/key/deployment) must all be the same
# resource; the Foundry resource below hosts the other three catalog models.
AZURE_OPENAI_DEPLOYMENT="${AZURE_OPENAI_DEPLOYMENT:-gpt-5-5}"
AZURE_OPENAI_API_VERSION="${AZURE_OPENAI_API_VERSION:-2024-10-21}"
CHAT_DEFAULT_MODEL_ID="${CHAT_DEFAULT_MODEL_ID:-gpt-5.5}"
AZURE_FOUNDRY_ENDPOINT="${AZURE_FOUNDRY_ENDPOINT:-}"
AZURE_FOUNDRY_API_KEY="${AZURE_FOUNDRY_API_KEY:-}"
# The 4 deployable catalog models students use in their own apps. GPT-5.5 lives on the
# Azure OpenAI resource; grok/deepseek/mistral live on the Foundry resource.
MODEL_GPT55_DEPLOYMENT="${MODEL_GPT55_DEPLOYMENT:-gpt-5-5}"
MODEL_GROK43_DEPLOYMENT="${MODEL_GROK43_DEPLOYMENT:-xai-grok43}"
MODEL_DEEPSEEK_V4_PRO_DEPLOYMENT="${MODEL_DEEPSEEK_V4_PRO_DEPLOYMENT:-ds-v4pro}"
MODEL_MISTRAL_MEDIUM_35_DEPLOYMENT="${MODEL_MISTRAL_MEDIUM_35_DEPLOYMENT:-mstr-med35}"
AI_MODEL_CATALOG_JSON="${AI_MODEL_CATALOG_JSON:-}"
SIGNUP_ACCESS_CODE="${SIGNUP_ACCESS_CODE:-}"
# Extra CORS origins beyond https://<domain>, comma-separated. Use this when the VM is
# reachable under more than one hostname (e.g. a friendly cloudapp.azure.com label plus
# the <ip>.nip.io fallback). They are appended to CORS_ORIGINS so a redeploy doesn't
# clobber a manually-added origin.
#   e.g. EXTRA_CORS_ORIGINS="https://4.223.137.167.nip.io"
EXTRA_CORS_ORIGINS="${EXTRA_CORS_ORIGINS:-}"
INSTRUCTOR_EMAIL="${INSTRUCTOR_EMAIL:-}"
INSTRUCTOR_PASSWORD="${INSTRUCTOR_PASSWORD:-}"
# Service principal for the Session 3 one-click deploy (runs `az webapp up` on students'
# behalf). Optional — leave blank to disable the /api/workspace/deploy endpoint.
AZURE_CLIENT_ID="${AZURE_CLIENT_ID:-}"
AZURE_CLIENT_SECRET="${AZURE_CLIENT_SECRET:-}"
AZURE_TENANT_ID="${AZURE_TENANT_ID:-}"
AZURE_SUBSCRIPTION_ID="${AZURE_SUBSCRIPTION_ID:-}"

: "${SESSION_SIGNING_KEY:?Set SESSION_SIGNING_KEY in your shell before running.}"

LAB_DIR="$(cd "$(dirname "$0")/../.." && pwd)"   # .../lab-platform (Docker build context)
VM_DIR="$LAB_DIR/infra/vm"
ACR_LOGIN_SERVER=""

echo "[1/7] Resource group"
az group create --name "$RG" --location "$LOCATION" --tags course=nixor-ai-cloud >/dev/null

echo "[2/7] Container registry ($ACR_NAME)"
az acr create --resource-group "$RG" --name "$ACR_NAME" --sku Basic --only-show-errors >/dev/null
ACR_LOGIN_SERVER="$(az acr show -n "$ACR_NAME" --query loginServer -o tsv)"

echo "[3/7] Building image from local checkout ($(git -C "$LAB_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')) via az acr build"
az acr build --registry "$ACR_NAME" --image "$IMAGE_TAG" --file "$LAB_DIR/Dockerfile" "$LAB_DIR" >/dev/null
FULL_IMAGE="$ACR_LOGIN_SERVER/$IMAGE_TAG"

echo "[4/7] Rendering cloud-init"
CLOUD_INIT="$(mktemp)"
sed -e "s|__DOMAIN__|$DOMAIN|g" \
    -e "s|__IMAGE__|$FULL_IMAGE|g" \
    -e "s|__ACR_NAME__|$ACR_NAME|g" \
    "$VM_DIR/cloud-init.yaml.template" > "$CLOUD_INIT"

echo "[5/7] Creating VM ($VM_SIZE)"
az vm create \
  --resource-group "$RG" \
  --name "$VM_NAME" \
  --image Ubuntu2204 \
  --size "$VM_SIZE" \
  --admin-username "$ADMIN_USER" \
  --generate-ssh-keys \
  --public-ip-sku Standard \
  --assign-identity \
  --data-disk-sizes-gb "$DATA_DISK_GB" \
  --storage-sku Premium_LRS \
  --custom-data "$CLOUD_INIT" \
  --only-show-errors >/dev/null

PUBLIC_IP="$(az vm show -d -g "$RG" -n "$VM_NAME" --query publicIps -o tsv)"
VM_PRINCIPAL="$(az vm show -g "$RG" -n "$VM_NAME" --query identity.principalId -o tsv)"
ACR_ID="$(az acr show -n "$ACR_NAME" --query id -o tsv)"

echo "      Granting the VM AcrPull on $ACR_NAME"
az role assignment create --assignee-object-id "$VM_PRINCIPAL" --assignee-principal-type ServicePrincipal \
  --role AcrPull --scope "$ACR_ID" --only-show-errors >/dev/null

echo "      Opening 80/443; restricting SSH(22) to your IP"
MY_IP="$(curl -s https://api.ipify.org || echo '*')"
az vm open-port --resource-group "$RG" --name "$VM_NAME" --port 80,443 --priority 1001 --only-show-errors >/dev/null
az network nsg rule create --resource-group "$RG" --nsg-name "${VM_NAME}NSG" --name ssh-restricted \
  --priority 1100 --access Allow --protocol Tcp --destination-port-ranges 22 \
  --source-address-prefixes "$MY_IP" --only-show-errors >/dev/null 2>&1 || true

echo "[6/7] Pushing app config + container runner to the VM"
# Assemble the CORS origin list: the primary domain plus any extras (deduped, trimmed).
CORS_ORIGINS="https://$DOMAIN"
if [[ -n "$EXTRA_CORS_ORIGINS" ]]; then
  IFS=',' read -ra _extra <<<"$EXTRA_CORS_ORIGINS"
  for _origin in "${_extra[@]}"; do
    _origin="$(echo "$_origin" | xargs)"   # trim whitespace
    [[ -z "$_origin" ]] && continue
    [[ ",$CORS_ORIGINS," == *",$_origin,"* ]] && continue   # skip duplicates
    CORS_ORIGINS="$CORS_ORIGINS,$_origin"
  done
fi
echo "      CORS origins: $CORS_ORIGINS"

# App env (secrets) — written to /etc/nixor-lab.env on the VM, never in git/custom-data.
ENV_CONTENT=$(cat <<EOF
DATABASE_URL=sqlite:////var/lib/nixor-lab/lab_platform.db
DB_BACKUP_PATH=/home/site/data/lab_platform.backup.db
WORKSPACE_DRIVER=local
LOCAL_WORKSPACE_ROOT=/home/site/workspaces
TERMINAL_REQUIRE_NON_ROOT=true
LOCAL_SANDBOX_UID=1000
LOCAL_SANDBOX_GID=1000
TERMINAL_BLOCK_DANGEROUS_COMMANDS=true
TERMINAL_ISOLATION=preferred
SESSION_SIGNING_KEY=$SESSION_SIGNING_KEY
SIGNUP_ACCESS_CODE=$SIGNUP_ACCESS_CODE
CORS_ORIGINS=$CORS_ORIGINS
AZURE_OPENAI_ENDPOINT=$AZURE_OPENAI_ENDPOINT
AZURE_OPENAI_API_KEY=$AZURE_OPENAI_API_KEY
AZURE_OPENAI_DEPLOYMENT=$AZURE_OPENAI_DEPLOYMENT
AZURE_OPENAI_API_VERSION=$AZURE_OPENAI_API_VERSION
CHAT_DEFAULT_MODEL_ID=$CHAT_DEFAULT_MODEL_ID
AZURE_FOUNDRY_ENDPOINT=$AZURE_FOUNDRY_ENDPOINT
AZURE_FOUNDRY_API_KEY=$AZURE_FOUNDRY_API_KEY
MODEL_GPT55_DEPLOYMENT=$MODEL_GPT55_DEPLOYMENT
MODEL_GROK43_DEPLOYMENT=$MODEL_GROK43_DEPLOYMENT
MODEL_DEEPSEEK_V4_PRO_DEPLOYMENT=$MODEL_DEEPSEEK_V4_PRO_DEPLOYMENT
MODEL_MISTRAL_MEDIUM_35_DEPLOYMENT=$MODEL_MISTRAL_MEDIUM_35_DEPLOYMENT
AI_MODEL_CATALOG_JSON=$AI_MODEL_CATALOG_JSON
AZURE_CLIENT_ID=$AZURE_CLIENT_ID
AZURE_CLIENT_SECRET=$AZURE_CLIENT_SECRET
AZURE_TENANT_ID=$AZURE_TENANT_ID
AZURE_SUBSCRIPTION_ID=$AZURE_SUBSCRIPTION_ID
INSTRUCTOR_EMAIL=$INSTRUCTOR_EMAIL
INSTRUCTOR_PASSWORD=$INSTRUCTOR_PASSWORD
EOF
)
RUNNER_CONTENT="$(cat "$VM_DIR/run-container.sh")"

# Use run-command to drop both files with correct perms, then (re)start the service.
az vm run-command invoke --resource-group "$RG" --name "$VM_NAME" \
  --command-id RunShellScript --only-show-errors \
  --scripts "
    set -e
    mkdir -p /opt/nixor
    cat > /opt/nixor/run-container.sh <<'RUNNER'
$RUNNER_CONTENT
RUNNER
    chmod 0755 /opt/nixor/run-container.sh
    umask 077
    cat > /etc/nixor-lab.env <<'ENVEOF'
$ENV_CONTENT
ENVEOF
    systemctl daemon-reload
    systemctl restart nixor-lab.service
  " >/dev/null

echo "[7/7] Done."
cat <<EOF

  VM public IP : $PUBLIC_IP
  Image        : $FULL_IMAGE
  Domain       : https://$DOMAIN

  Next:
    1. Point a DNS A record for $DOMAIN at $PUBLIC_IP (skip if you used <ip>.nip.io).
    2. Wait ~2-3 min for cloud-init + first container start. Then check:
         curl -s https://$DOMAIN/api/health
    3. Confirm the jail engaged:
         az vm run-command invoke -g $RG -n $VM_NAME --command-id RunShellScript \\
           --scripts "docker logs nixor-lab 2>&1 | grep -i 'Terminal isolation'"
       Expect: "Terminal isolation: ACTIVE (chroot jail; mode=preferred)"
    4. Once ACTIVE, set TERMINAL_ISOLATION=required in /etc/nixor-lab.env and restart.
EOF
rm -f "$CLOUD_INIT"
