# syntax=docker/dockerfile:1
#
# Nixor AI Lab platform image.
#
# Runs the FastAPI backend (which serves the built React frontend as static files) and
# hosts the per-student interactive terminals. The container is started as root so the
# backend can build each terminal's chroot/bind-mount jail and then drop to the sandbox
# user (uid 1000). On a host that grants CAP_SYS_ADMIN (e.g. `docker run --privileged`
# on our VM), the jail engages and confines `rm -rf /` to the student's own workspace.

# ---- Frontend build stage --------------------------------------------------------------
FROM node:20-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- Runtime ---------------------------------------------------------------------------
FROM python:3.11-slim

# Tools the interactive terminal and the jail need:
#  - bash/coreutils/procps: the shell and ps/top inside the jail
#  - git/curl: conveniences students reach for
#  - ca-certificates: TLS for pip/httpx
#  - nano: a beginner-friendly editor
#  - vim: the `vi`/`vim` editor students reach for (provides both via update-alternatives)
RUN apt-get update && apt-get install -y --no-install-recommends \
        bash coreutils procps nano vim git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Azure CLI — used by the server-side one-click deploy (Session 3) to run
# `az webapp up` into each student's resource group on their behalf. Installed in
# the runtime image (root-owned, on PATH); the jailed student terminal does NOT
# bind it in, so students never get ambient `az` access — only the backend uses it.
RUN curl -sL https://aka.ms/InstallAzureCLIDeb | bash \
    && rm -rf /var/lib/apt/lists/*

# Sandbox user that every terminal drops to. uid/gid 1000 must match
# LOCAL_SANDBOX_UID/GID in the environment.
RUN useradd -m -u 1000 -s /bin/bash sandbox

WORKDIR /app

# Install backend deps first for layer caching.
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Pre-install the STUDENT app's dependencies into the image's system site-packages. Without
# this, every student's `pip install -r requirements.txt` in the terminal downloads ~0.5 GB
# (streamlit + pyarrow/pandas/numpy/...) into their per-student ~/.local, which fills the
# shared workspace volume and fails with "[Errno 28] No space left on device:
# '/workspace/.local'". Pre-installed here, pip reports "Requirement already satisfied" and
# writes nothing to .local. System site-packages live under /usr, which is bind-mounted
# read-only into every terminal jail, so the packages import fine inside the sandbox too.
COPY student-app/requirements.txt student-app/requirements.txt
RUN pip install --no-cache-dir -r student-app/requirements.txt

# App code + course assets the backend serves / seeds workspaces from.
COPY backend/ backend/
COPY course-content/ course-content/
COPY student-app/ student-app/

# Built frontend from the web stage (backend mounts ../frontend/dist relative to the app).
COPY --from=web /web/dist frontend/dist

ENV PORT=8000
EXPOSE 8000

# startup.sh prepares the root-owned DB dir and execs uvicorn (as root). Terminals fork
# from there, build the jail, and setuid(1000).
CMD ["bash", "backend/startup.sh"]
