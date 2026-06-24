#!/usr/bin/env bash
# Provision the Nixor AI Lab student-app cluster: 5 × Standard_D8s_v5 VMs,
# each running the deploy-agent. Students' Streamlit apps run as Docker containers
# on ports 9000-9099 of these nodes.
#
# Idempotent: safe to re-run. Skips VM creation if the VM already exists.
#
# Usage:
#   AGENT_SECRET=<random> PLATFORM_VM_IP=<ip> \
#   ./provision_cluster.sh <resource-group> <location>
#
#   AGENT_SECRET  — shared secret between platform and agents (generate with openssl rand -hex 32)
#   PLATFORM_VM_IP — the public IP of the platform VM; agent port 8080 is restricted to it
#
# Outputs: infra/cluster/cluster_nodes.env  (node IPs, ready to paste into platform .env)
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: AGENT_SECRET=... PLATFORM_VM_IP=... $0 <resource-group> <location>" >&2
  exit 1
fi

RG="$1"
LOCATION="$2"
NODE_COUNT="${NODE_COUNT:-5}"
VM_SIZE="${VM_SIZE:-Standard_D8s_v5}"
ADMIN_USER="${ADMIN_USER:-azureuser}"
AGENT_PORT=8080
STUDENT_PORT_START=9000
STUDENT_PORT_END=9099

: "${AGENT_SECRET:?Set AGENT_SECRET in your shell before running.}"
: "${PLATFORM_VM_IP:?Set PLATFORM_VM_IP to the platform VM's public IP.}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENT_DIR="$SCRIPT_DIR/deploy-agent"
CLOUD_INIT="$SCRIPT_DIR/cloud-init-node.yaml"
OUTPUT_ENV="$SCRIPT_DIR/cluster_nodes.env"

echo "[0/3] Ensuring resource group $RG in $LOCATION"
az group create --name "$RG" --location "$LOCATION" \
  --tags course=nixor-ai-cloud component=student-cluster --output none

# Read existing IPs for idempotency check
declare -A EXISTING_IPS

echo "[1/3] Creating $NODE_COUNT VMs (skipping any that already exist)"
for i in $(seq 1 "$NODE_COUNT"); do
  VM_NAME="nixor-node-$i"
  if az vm show -g "$RG" -n "$VM_NAME" --query name -o tsv 2>/dev/null | grep -q "$VM_NAME"; then
    echo "      $VM_NAME already exists — skipping creation"
    EXISTING_IPS["$VM_NAME"]="$(az vm show -d -g "$RG" -n "$VM_NAME" --query publicIps -o tsv)"
  else
    echo "      Creating $VM_NAME ($VM_SIZE)..."
    az vm create \
      --resource-group "$RG" \
      --name "$VM_NAME" \
      --image Ubuntu2204 \
      --size "$VM_SIZE" \
      --admin-username "$ADMIN_USER" \
      --generate-ssh-keys \
      --public-ip-sku Standard \
      --assign-identity \
      --custom-data "$CLOUD_INIT" \
      --tags course=nixor-ai-cloud component=student-cluster node="$i" \
      --only-show-errors --output none
    echo "      $VM_NAME created."
  fi
done

echo "[2/3] Opening ports and pushing deploy-agent to each node"

# Load agent source files for embedding in run-command
AGENT_PY="$(cat "$AGENT_DIR/agent.py")"
AGENT_REQS="$(cat "$AGENT_DIR/requirements.txt")"
STUDENT_DOCKERFILE="$(cat "$AGENT_DIR/student.Dockerfile")"

# Build the systemd unit content
SYSTEMD_UNIT='[Unit]
Description=Nixor Deploy Agent
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=simple
EnvironmentFile=/etc/nixor-agent.env
WorkingDirectory=/opt/nixor-agent
ExecStart=/opt/nixor-agent/venv/bin/uvicorn agent:app --host 0.0.0.0 --port 8080
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target'

NODE_IPS=()
for i in $(seq 1 "$NODE_COUNT"); do
  VM_NAME="nixor-node-$i"
  NODE_IP="${EXISTING_IPS[$VM_NAME]:-$(az vm show -d -g "$RG" -n "$VM_NAME" --query publicIps -o tsv)}"
  NODE_IPS+=("$NODE_IP")
  echo "      $VM_NAME @ $NODE_IP"

  # Open student app ports (public) and agent port (platform VM only)
  NSG_NAME="${VM_NAME}NSG"
  az network nsg rule create --resource-group "$RG" --nsg-name "$NSG_NAME" \
    --name student-apps --priority 1001 --access Allow --protocol Tcp \
    --destination-port-ranges "$STUDENT_PORT_START-$STUDENT_PORT_END" \
    --only-show-errors --output none 2>/dev/null || true

  az network nsg rule create --resource-group "$RG" --nsg-name "$NSG_NAME" \
    --name deploy-agent --priority 1002 --access Allow --protocol Tcp \
    --destination-port-ranges "$AGENT_PORT" \
    --source-address-prefixes "$PLATFORM_VM_IP" \
    --only-show-errors --output none 2>/dev/null || true

  # Push agent files and start service via run-command
  az vm run-command invoke --resource-group "$RG" --name "$VM_NAME" \
    --command-id RunShellScript --only-show-errors --output none \
    --scripts "
set -e
# Write agent files
mkdir -p /opt/nixor-agent /opt/nixor-builds /var/log/nixor-agent
cat > /opt/nixor-agent/agent.py <<'PYEOF'
$AGENT_PY
PYEOF
cat > /opt/nixor-agent/requirements.txt <<'REQEOF'
$AGENT_REQS
REQEOF
cat > /opt/nixor-agent/student.Dockerfile <<'DFEOF'
$STUDENT_DOCKERFILE
DFEOF

# Write env file (secrets stay off disk in git)
umask 077
cat > /etc/nixor-agent.env <<'ENVEOF'
AGENT_SECRET=$AGENT_SECRET
NODE_PUBLIC_IP=$NODE_IP
BUILD_ROOT=/opt/nixor-builds
ENVEOF

# Set up Python venv and install deps
if [ ! -d /opt/nixor-agent/venv ]; then
  python3 -m venv /opt/nixor-agent/venv
fi
/opt/nixor-agent/venv/bin/pip install --quiet -r /opt/nixor-agent/requirements.txt

# Write and enable systemd service
cat > /etc/systemd/system/nixor-agent.service <<'SVCEOF'
$SYSTEMD_UNIT
SVCEOF

systemctl daemon-reload
systemctl enable nixor-agent
systemctl restart nixor-agent
echo 'Agent started.'
"
  echo "      ✓ $VM_NAME agent deployed"
done

echo "[3/3] Writing $OUTPUT_ENV"
# Build comma-separated list of node URLs for CLUSTER_NODE_URLS
NODE_URLS=""
for IP in "${NODE_IPS[@]}"; do
  NODE_URLS="${NODE_URLS:+$NODE_URLS,}http://$IP:$AGENT_PORT"
done

cat > "$OUTPUT_ENV" <<EOF
# Generated by provision_cluster.sh — paste into platform .env or az vm run-command env push
# Node IPs (in order: node 1 → node 5)
$(for i in "${!NODE_IPS[@]}"; do echo "# Node $((i+1)): ${NODE_IPS[$i]}"; done)

CLUSTER_NODE_URLS=$NODE_URLS
CLUSTER_AGENT_SECRET=$AGENT_SECRET
EOF

echo ""
echo "Done. Cluster nodes:"
for i in "${!NODE_IPS[@]}"; do
  echo "  nixor-node-$((i+1)) : ${NODE_IPS[$i]}"
done
echo ""
echo "Next steps:"
echo "  1. Wait ~3 min for cloud-init to finish on new VMs."
echo "  2. Verify each agent: curl http://<node-ip>:8080/health"
echo "  3. Add the values in $OUTPUT_ENV to the platform VM's /etc/nixor-lab.env:"
echo "       CLUSTER_NODE_URLS=..."
echo "       CLUSTER_AGENT_SECRET=..."
echo "     Then: az vm run-command invoke -g <platform-rg> -n <platform-vm> \\"
echo "            --command-id RunShellScript \\"
echo "            --scripts 'echo \"CLUSTER_NODE_URLS=...\" >> /etc/nixor-lab.env && systemctl restart nixor-lab.service'"
echo "  4. Test a deploy from the platform browser UI."
