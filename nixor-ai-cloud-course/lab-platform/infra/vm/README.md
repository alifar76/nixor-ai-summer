# VM + privileged Docker deployment

This is the hosting target where the per-terminal **chroot/bind-mount jail actually
engages** (it needs `CAP_SYS_ADMIN`, which App Service / Container Apps / ACI don't grant
but `docker run --privileged` on a VM does). With the jail active, a student's
`rm -rf /` is confined to their own workspace: system binaries, the database, other
students, and even the shell's own cwd survive — no "`ls` broken until re-login".

## Files

| File | Purpose |
|---|---|
| `../../Dockerfile` | Builds the platform image (frontend build + FastAPI runtime). |
| `deploy_vm.sh` | One-shot, idempotent provisioner: RG + ACR + image build + VM + config. |
| `cloud-init.yaml.template` | VM bootstrap: Docker, Azure CLI, Caddy, systemd unit. No secrets. |
| `run-container.sh` | `docker run --privileged …` the image with persistent volumes. |

## Prerequisites

- `az` logged in (`az login`) to the subscription holding your credits.
- Docker NOT required locally — the image is built server-side via `az acr build` from
  your current checkout, so **whatever branch you're on is what deploys**. Use `dev`.
- A DNS name you can point at the VM (or use `<publicip>.nip.io` for a quick test cert).

## Deploy (from the `dev` branch)

```bash
git checkout dev
cd nixor-ai-cloud-course/lab-platform/infra/vm

export SESSION_SIGNING_KEY="$(openssl rand -hex 32)"
export INSTRUCTOR_EMAIL="you@example.com"
export INSTRUCTOR_PASSWORD="…"
# optional: AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY for the in-app chatbot
# optional: SIGNUP_ACCESS_CODE to gate signups to your cohort

./deploy_vm.sh rg-nixor-lab-dev eastus nixor-lab-dev lab.yourdomain.com
```

The script prints the VM's public IP and the exact commands to verify health and confirm
the jail is **ACTIVE**.

## Sizing (40+ concurrent students)

Default is **`Standard_D16s_v5`** (16 vCPU / 64 GB) — comfortable for 40+ concurrent
terminals each potentially running `streamlit run` + `pip install`. Override:

```bash
VM_SIZE=Standard_D32s_v5 ./deploy_vm.sh …    # 32 vCPU / 128 GB, extra headroom
```

A single large VM is intentional: the jail is per-process inside one container, so
scaling up (bigger VM) is simpler and more robust than scaling out (which would require a
shared DB and websocket session affinity). With your credits, size generously.

## Migrating existing accounts/progress

The app restores its DB from `DB_BACKUP_PATH` on boot. To carry over data from the App
Service instance, copy its latest `lab_platform.backup.db` into the VM's `nixor-backup`
volume before first start:

```bash
# from the App Service (Kudu/SSH): download /home/site/data/lab_platform.backup.db
az vm run-command invoke -g rg-nixor-lab-dev -n nixor-lab-dev --command-id RunShellScript \
  --scripts "docker run --rm -v nixor-backup:/b -i busybox sh -c 'cat > /b/lab_platform.backup.db' < lab_platform.backup.db"
```

(Or just start fresh on dev for testing — accounts re-create on signup.)

## Updating the app

Re-run `deploy_vm.sh` with the same arguments: it rebuilds the image from your checkout
and restarts the container. Volumes (DB, backup, workspaces) persist across updates.

## Lock it down once verified

After logs show `Terminal isolation: ACTIVE`, flip to fail-closed so a terminal refuses to
open if the jail ever can't build:

```bash
az vm run-command invoke -g rg-nixor-lab-dev -n nixor-lab-dev --command-id RunShellScript \
  --scripts "sed -i 's/TERMINAL_ISOLATION=preferred/TERMINAL_ISOLATION=required/' /etc/nixor-lab.env && systemctl restart nixor-lab"
```

## Teardown

```bash
az group delete --name rg-nixor-lab-dev --yes --no-wait
```

## Cost

With $30k of credits over a 4-day program this is negligible: a `D16s_v5` is ~$0.77/hr
(~$18/day) plus a Basic ACR (~$0.17/day) and a Premium data disk. Deallocate the VM
between days (`az vm deallocate`) if you want to pause billing.
