# Nixor Lab Platform

Full browser-based teaching platform for your 4-day AI + Cloud course:

- Student signup/login
- Course walkthrough from markdown sessions
- Progress tracking per student
- Built-in code editor (Monaco)
- Built-in Linux terminal (xterm websocket)
- Built-in coding chatbot (Azure OpenAI / Foundry)

## Architecture

```
Internet
  │  443 (HTTPS, auto-cert via Let's Encrypt)
  ▼
[ Caddy reverse proxy ]                       ← on the VM, terminates TLS
  │  127.0.0.1:8000  (websocket-aware)
  ▼
[ docker run --privileged nixor-lab ]         ← single Azure VM (Standard_D16s_v5)
  ├─ uvicorn app.main:app  (serves API + built frontend)
  ├─ per-terminal chroot/bind-mount jail       ← needs CAP_SYS_ADMIN (→ --privileged)
  ├─ /var/lib/nixor-lab     → named volume  (live SQLite DB, root-owned 0700)
  ├─ /home/site/data        → named volume  (DB backup, restored on boot)
  └─ /home/site/workspaces  → named volume  (per-student workspaces)
```

The platform runs as **one privileged Docker container on an Azure VM**. The VM is the
hosting target because the per-terminal isolation jail needs `CAP_SYS_ADMIN`
(`unshare(CLONE_NEWNS)` + `mount`), which App Service / Container Apps / ACI do not grant
but `docker run --privileged` does. With the jail active, a student's `rm -rf /` is
confined to their own workspace — system binaries, the database, and other students all
survive.

> **History:** earlier revisions targeted Azure App Service (see
> `infra/deploy_platform.sh` and `infra/MIGRATION-vm-docker.md`). On App Service the jail
> could not engage (no `CAP_SYS_ADMIN`), so the platform was migrated to the VM. The App
> Service script is kept only as a legacy fallback.

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

> Note: the chroot jail only engages when the API process runs as root with
> `CAP_SYS_ADMIN` (i.e. inside the privileged container). On a normal local run
> `TERMINAL_ISOLATION=preferred` falls back to a non-jailed shell — the destructive
> command guard still applies, but isolation is not enforced. Test the jail on the VM.

## Deploy (VM + privileged Docker)

This is the production path. The image is built server-side with `az acr build` from your
local checkout, so **whatever branch you're on is what deploys** — deploy from `main`.

```bash
cd infra/vm

export SESSION_SIGNING_KEY="$(openssl rand -hex 32)"
export INSTRUCTOR_EMAIL="you@example.com"
export INSTRUCTOR_PASSWORD="StrongPass123!"
# optional: AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY for the in-app chatbot
# optional: SIGNUP_ACCESS_CODE to gate signups to your cohort

./deploy_vm.sh <resource-group> <location> <vm-name> <domain>
```

Example:

```bash
./deploy_vm.sh rg-nixor-lab eastus nixor-lab 20.91.209.250.nip.io
```

The script (idempotent — safe to re-run to update):

1. Creates the resource group + an Azure Container Registry (Basic).
2. Builds the image from your checkout via `az acr build`.
3. Creates an Ubuntu 22.04 VM (default `Standard_D16s_v5`, 16 vCPU / 64 GB) with a managed
   identity granted `AcrPull`, bootstrapped (Docker + Caddy) via cloud-init.
4. Pushes app config to `/etc/nixor-lab.env` (secrets never touch git) and starts the
   `nixor-lab` systemd service.

See **`infra/vm/README.md`** for sizing (40+ concurrent students), data migration,
updating, locking down with `TERMINAL_ISOLATION=required`, and teardown.

### Confirm the jail engaged

```bash
az vm run-command invoke -g <resource-group> -n <vm-name> --command-id RunShellScript \
  --scripts "docker logs nixor-lab 2>&1 | grep -i 'Terminal isolation'"
# Expect: Terminal isolation: ACTIVE (chroot jail; mode=preferred)
```

## Security model

- **Per-terminal chroot/bind-mount jail.** Each terminal `unshare`s a mount namespace,
  bind-mounts system dirs (`/usr`, `/bin`, `/lib`, `/etc`, …) **read-only**, mounts only
  the student's workspace writable at `HOME`, then `chroot`s in. `rm -rf /` can therefore
  only wipe the student's own workspace; everything else reports "Read-only file system".
- **Non-root shell.** The terminal drops to an unprivileged sandbox UID/GID (1000) before
  exec; startup verifies it is not root (`TERMINAL_REQUIRE_NON_ROOT=true`).
- **Destructive-command guard.** High-risk commands (`rm -rf /`, `dd`, `mkfs`,
  `wipefs`, …) are intercepted at the websocket layer and blocked before reaching the PTY,
  with the readline buffer cleared so a re-press of Enter can't replay them.
- **DB out of reach.** SQLite lives at `/var/lib/nixor-lab` (root-owned, `0700`) — not on
  a student-writable mount — so a wipe can't delete it and break login/signup. It is
  hot-backed-up to `/home/site/data` and restored on boot, so accounts/progress survive
  container restarts and image updates.
- **Self-healing workspaces.** Starter/course files are re-seeded per-entry on
  `ensure_workspace`, so a student who deletes them gets them back on the next terminal
  open or editor refresh (their own created files are preserved).

## Configuration (env)

| Variable | Purpose |
|---|---|
| `SESSION_SIGNING_KEY` | Signs session tokens (required). |
| `DATABASE_URL` | `sqlite:////var/lib/nixor-lab/lab_platform.db` on the VM. |
| `DB_BACKUP_PATH` | `/home/site/data/lab_platform.backup.db` — hot backup target. |
| `WORKSPACE_DRIVER` | `local` (per-student dirs under `LOCAL_WORKSPACE_ROOT`). |
| `LOCAL_WORKSPACE_ROOT` | `/home/site/workspaces`. |
| `TERMINAL_ISOLATION` | `preferred` (fall back if jail can't build) or `required` (fail-closed). |
| `TERMINAL_REQUIRE_NON_ROOT` | Refuse to open a terminal that would run as root. |
| `TERMINAL_BLOCK_DANGEROUS_COMMANDS` | Enable the destructive-command guard. |
| `CORS_ORIGINS` | The public domain (e.g. `https://<vm>.nip.io`). |
| `INSTRUCTOR_EMAIL` / `INSTRUCTOR_PASSWORD` | Bootstrap the instructor account. |
| `SIGNUP_ACCESS_CODE` | Optional gate so only your cohort can sign up. |
| `AZURE_OPENAI_*` | Endpoint/key/deployment for the in-app chatbot. |
