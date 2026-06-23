#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <resource-group> <location> <webapp-name>"
  exit 1
fi

RG_NAME="$1"
LOCATION="$2"
APP_NAME="$3"
SESSION_SIGNING_KEY="${SESSION_SIGNING_KEY:-}"
SIGNUP_ACCESS_CODE="${SIGNUP_ACCESS_CODE:-}"
CORS_ORIGINS="${CORS_ORIGINS:-*}"
INSTRUCTOR_EMAIL="${INSTRUCTOR_EMAIL:-}"
INSTRUCTOR_PASSWORD="${INSTRUCTOR_PASSWORD:-}"

if [[ -z "$SESSION_SIGNING_KEY" ]]; then
  echo "Set SESSION_SIGNING_KEY in your shell before running this script."
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "[1/5] Building frontend"
cd "$ROOT_DIR/frontend"
npm install
npm run build

cd "$ROOT_DIR"
echo "[2/5] Creating resource group"
az group create --name "$RG_NAME" --location "$LOCATION" >/dev/null

echo "[3/5] Provisioning Azure resources"
az deployment group create \
  --resource-group "$RG_NAME" \
  --template-file "$ROOT_DIR/infra/main.bicep" \
  --parameters appName="$APP_NAME" location="$LOCATION" sessionSigningKey="$SESSION_SIGNING_KEY" signupAccessCode="$SIGNUP_ACCESS_CODE" corsOrigins="$CORS_ORIGINS" >/dev/null

echo "[4/5] Packaging app"
ZIP_PATH="$(mktemp /tmp/nixor-lab-XXXXXX)"
rm -f "$ZIP_PATH"
ZIP_PATH="${ZIP_PATH}.zip"
zip -qr "$ZIP_PATH" . \
  -x "frontend/node_modules/*" \
     "backend/.venv/*" \
     "**/__pycache__/*" \
     "**/.DS_Store" \
     "**/.env" \
     "**/*.pyc"

echo "[5/5] Deploying code"
az webapp deploy \
  --resource-group "$RG_NAME" \
  --name "$APP_NAME" \
  --src-path "$ZIP_PATH" \
  --type zip >/dev/null

if [[ -n "$INSTRUCTOR_EMAIL" && -n "$INSTRUCTOR_PASSWORD" ]]; then
  az webapp config appsettings set \
    --resource-group "$RG_NAME" \
    --name "$APP_NAME" \
    --settings INSTRUCTOR_EMAIL="$INSTRUCTOR_EMAIL" INSTRUCTOR_PASSWORD="$INSTRUCTOR_PASSWORD" >/dev/null
fi

APP_URL="https://${APP_NAME}.azurewebsites.net"
echo "Live URL: $APP_URL"
