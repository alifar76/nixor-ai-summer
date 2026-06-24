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
RUN apt-get update && apt-get install -y --no-install-recommends \
        bash coreutils procps nano git curl ca-certificates \
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
