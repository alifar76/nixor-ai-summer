# Nixor Lab Platform

Full browser-based teaching platform for your 4-day AI + Cloud course:

- Student signup/login
- Course walkthrough from markdown sessions
- Progress tracking per student
- Built-in code editor (Monaco)
- Built-in Linux terminal (xterm websocket)
- Built-in coding chatbot (Azure OpenAI / Foundry)

## Local run

### 1) Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

### 2) Frontend (separate terminal)

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

## Deploy to Azure Web App

Set environment values in your shell first:

```bash
export SESSION_SIGNING_KEY="$(openssl rand -hex 32)"
export INSTRUCTOR_EMAIL="you@example.com"
export INSTRUCTOR_PASSWORD="StrongPass123!"
# Optional
export SIGNUP_ACCESS_CODE="nixor2026"
export CORS_ORIGINS="https://<your-app>.azurewebsites.net"
```

Then run:

```bash
cd infra
./deploy_platform.sh <resource-group> <location> <webapp-name>
```

Example:

```bash
./deploy_platform.sh rg-nixor-lab swedencentral nixor-lab-2026
```

The script will:

1. Build the React frontend.
2. Provision App Service + Azure OpenAI + model deployment from `infra/main.bicep`.
3. Zip-deploy backend + frontend to Web App.
4. Optionally set instructor credentials.

## Notes

- `WORKSPACE_DRIVER=local` is used for Azure Web App compatibility.
- Student workspace files are stored in `/home/site/workspaces`.
- SQLite DB is stored in `/home/site/data/lab_platform.db`.
- Terminal sessions are hardened to run as a non-root sandbox UID/GID.
- High-risk destructive terminal commands (for example `rm -rf /`) are blocked by policy.
