# Migration plan: App Service → privileged Docker on an Azure VM

**Goal:** run the platform where the per-terminal chroot/bind-mount jail actually engages,
so a student's `rm -rf /` is confined to their own workspace — system binaries, the DB,
other students, and the running shell's cwd all survive (no more "`ls` broken until
re-login").

**Status:** PLAN ONLY. Nothing here has been applied. Implementation is gated on approval.

---

## Why a VM (not Container Apps, not ACI)

The jail needs `unshare(CLONE_NEWNS)` + `mount()`, which require `CAP_SYS_ADMIN`.

| Platform | Grants CAP_SYS_ADMIN / privileged? | Jail works? |
|---|---|---|
| App Service (today) | No | No → falls back to guard-only |
| Container Apps | No (no privileged, no custom caps) | No |
| Container Instances (ACI) | No privileged | No |
| **VM + Docker `--privileged`** | **Yes** | **Yes** |
| AKS w/ `securityContext.privileged` | Yes | Yes (heavier ops) |

Recommendation: **single Linux VM running the container with `--privileged`.** Simplest,
single-tenant is fine for one class, and scaling up (bigger VM) beats scaling out
(which would need a shared DB + websocket session affinity). AKS is overkill until we
need autoscaling/multi-node. The AKS variant is sketched at the bottom.

**Implemented under `infra/vm/`** (built on the `dev` branch) — see
`infra/vm/README.md`. Sizing for **40+ concurrent students**: default `Standard_D16s_v5`
(16 vCPU / 64 GB), override to `Standard_D32s_v5` for more headroom. The image is built
server-side with `az acr build` from your local checkout, so the branch you deploy from
is what runs.

---

## Bonus wins this migration unlocks

1. **`ls` survives `rm -rf`.** Inside the jail, `HOME=/workspace` is a bind mount; the
   mountpoint itself can't be unlinked, so the shell's cwd remains valid even after its
   contents are wiped. No re-login needed.
2. **python/pip shims become unnecessary.** A real `python:3.11` base image puts
   `python`/`pip` at `/usr/local/bin` (on PATH, root-owned). The Oryx `antenv` hack and
   the `/var/lib/nixor-bin` shims can be removed (or kept harmlessly).
3. **`TERMINAL_ISOLATION=required`** can finally be set (fail-closed) once we confirm
   "Terminal isolation: ACTIVE" in the logs.

---

## Target architecture

```
Internet
  │  443 (HTTPS, auto-cert)
  ▼
[ Caddy reverse proxy ]  ← on the VM, terminates TLS for a domain
  │  127.0.0.1:8000
  ▼
[ docker run --privileged nixor-lab ]
  ├─ uvicorn app.main:app :8000
  ├─ /var/lib/nixor-lab     → named volume  (live SQLite DB, root-owned 0700)
  ├─ /home/site/data        → named volume  (DB backup target)
  ├─ /home/site/workspaces  → named volume  (student workspaces, persist across restarts)
  └─ per-terminal chroot jail (now functional)
```

- **One Azure VM**: `Standard_B2s` (2 vCPU / 4 GB) ≈ $30/mo, or `B2as_v2`. Deallocate
  outside class hours to cut cost. (B1s 1 vCPU/1 GB is too tight for the frontend build +
  concurrent terminals.)
- **OS**: Ubuntu 22.04 LTS.
- **TLS**: Caddy with automatic Let's Encrypt on a DNS name. Options for the name:
  - point a real subdomain (e.g. `lab.nixor.example`) A-record at the VM's static public IP, or
  - use `https://<ip>.nip.io` for a quick test cert.
- **NSG**: allow 80+443 from anywhere, 22 (SSH) only from instructor IP.

---

## New files to add (under `infra/`)

1. **`Dockerfile`** (repo root of `lab-platform`)
   ```dockerfile
   # Frontend build stage
   FROM node:20-slim AS web
   WORKDIR /web
   COPY frontend/package*.json ./
   RUN npm ci
   COPY frontend/ ./
   RUN npm run build

   # Runtime
   FROM python:3.11-slim
   RUN apt-get update && apt-get install -y --no-install-recommends \
         bash coreutils procps nano ca-certificates && \
       rm -rf /var/lib/apt/lists/*
   # sandbox user the terminals drop to
   RUN useradd -m -u 1000 -s /bin/bash sandbox
   WORKDIR /app
   COPY backend/requirements.txt backend/requirements.txt
   RUN pip install --no-cache-dir -r backend/requirements.txt
   COPY backend/ backend/
   COPY course-content/ course-content/
   COPY student-app/ student-app/
   COPY --from=web /web/dist frontend/dist
   ENV PORT=8000
   # container starts as root (needed to build jail + drop privs); uvicorn stays root,
   # each terminal forks → jail → setuid(1000).
   CMD ["bash", "backend/startup.sh"]
   ```

2. **`infra/vm/cloud-init.yaml`** — installs Docker + Caddy, pulls/runs the image,
   creates the named volumes, wires the systemd unit. Idempotent.

3. **`infra/vm/run-container.sh`** — the exact `docker run` invocation:
   ```bash
   docker run -d --name nixor-lab --restart unless-stopped \
     --privileged \
     -p 127.0.0.1:8000:8000 \
     -v nixor-db:/var/lib/nixor-lab \
     -v nixor-backup:/home/site/data \
     -v nixor-workspaces:/home/site/workspaces \
     --env-file /etc/nixor-lab.env \
     <registry>/nixor-lab:latest
   ```
   (`--privileged` can be tightened later to
   `--cap-add SYS_ADMIN --security-opt apparmor=unconfined --security-opt seccomp=unconfined`
   once verified.)

4. **`infra/vm/Caddyfile`**
   ```
   lab.example.com {
       reverse_proxy 127.0.0.1:8000
   }
   ```

5. **`infra/vm/deploy_vm.sh`** — `az vm create` (Ubuntu, B2s, static IP, NSG rules) +
   `--custom-data cloud-init.yaml`. Mirrors the structure of today's `deploy_platform.sh`.

6. **Image registry**: either build on the VM directly (`docker build`) — simplest, no
   registry — or push to a small **Azure Container Registry** (Basic ≈ $5/mo). Plan
   assumes build-on-VM to start.

---

## Backend changes required (small)

- **`config.py`**: default `terminal_isolation` stays `preferred`; after we confirm the
  jail engages, flip the env to `required` in the VM env file.
- **`startup.sh`**: unchanged in spirit. `DATABASE_URL` / `DB_BACKUP_PATH` already point
  at `/var/lib/nixor-lab` and `/home/site/data`, which are now Docker volumes. The
  `/var/lib/nixor-bin` python shims become dead weight but are harmless; can delete in a
  follow-up.
- **`local_driver.py`**: no change needed — the jail code already exists and self-tests at
  startup. We just expect `jail_self_test()` → True here.
- **CORS**: set `CORS_ORIGINS` to the new domain.

No application logic changes — this is purely a hosting move.

---

## Cutover steps (once approved)

1. Add the files above; build the image on a scratch VM and smoke-test locally
   (`/api/health`, login, open terminal, run `rm -rf --no-preserve-root /`, confirm
   `ls`/`python`/`pip` still work and logs say **ACTIVE**).
2. Provision the real VM via `deploy_vm.sh`; point DNS at its static IP.
3. **Migrate data**: copy the latest `/home/site/data/lab_platform.backup.db` off the App
   Service (via Kudu) into the `nixor-backup` volume; the app restores from it on boot, so
   existing accounts/progress carry over.
4. Verify on the new domain; set `TERMINAL_ISOLATION=required`.
5. Keep App Service running in parallel until the VM is confirmed, then stop/delete it.
6. Update `course-content` session-3 deploy URLs if they reference the old host.

---

## Rollback

App Service stays live and untouched during cutover. If anything fails, DNS/usage simply
stays on App Service; delete the VM. No destructive step happens to the current prod app
until step 5.

---

## Cost delta

| Item | Monthly (approx) |
|---|---|
| App Service B1 (today) | ~$13 |
| VM B2s (running 24/7) | ~$30 |
| VM B2s (deallocated outside class) | ~$8–12 |
| ACR Basic (optional) | ~$5 |
| Static public IP | ~$3 |

Net: a few dollars more than today if deallocated when idle; ~$20/mo more if always-on.

---

## AKS variant (only if we outgrow one VM)

- One small node pool (`Standard_B2s`).
- Deployment pod with `securityContext: { privileged: true }`.
- `Service` type LoadBalancer + ingress-nginx + cert-manager for TLS.
- PersistentVolumeClaims replace the Docker named volumes.
- More moving parts (kubelet, ingress, cert-manager) for no functional gain at one class's
  scale — defer unless needed.
