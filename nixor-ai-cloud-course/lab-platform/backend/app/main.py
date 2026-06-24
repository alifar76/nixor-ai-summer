"""FastAPI application entrypoint for the Nixor AI Lab platform.

Serves the JSON/websocket API and, in production, the built React frontend as
static files from the same origin.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session, select

from .auth import get_user_by_email, hash_password
from .config import settings
from .db import backup_database, engine, init_db, restore_from_backup
from .models import User
from .routers import (
    admin,
    auth_routes,
    chat,
    course_routes,
    files,
    terminal,
    workspace,
)
from .workspaces.local_driver import _write_global_python_shims

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("nixor-lab")

app = FastAPI(title="Nixor AI Lab", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API + websocket routers
app.include_router(auth_routes.router)
app.include_router(course_routes.router)
app.include_router(workspace.router)
app.include_router(files.router)
app.include_router(chat.router)
app.include_router(admin.router)
app.include_router(terminal.router)


@app.on_event("startup")
def on_startup() -> None:
    # Restore from the persistent backup (if any) BEFORE creating tables, so an
    # ordinary restart keeps existing accounts/progress.
    restore_from_backup()
    init_db()
    _bootstrap_instructor()
    if settings.workspace_driver == "local":
        _write_global_python_shims()
    # Probe isolation (forks) before starting background threads, so the fork happens
    # while the process is still single-threaded.
    _log_terminal_isolation()
    _start_backup_loop()
    logger.info("Nixor AI Lab started. Course content: %s", settings.course_content_dir)


def _log_terminal_isolation() -> None:
    """Report whether the per-terminal chroot jail can actually engage on this host."""
    mode = settings.terminal_isolation.lower().strip()
    if settings.workspace_driver != "local" or mode == "off":
        logger.info("Terminal isolation: mode=%s driver=%s", mode, settings.workspace_driver)
        return
    try:
        from .workspaces.local_driver import jail_self_test

        ok = jail_self_test()
    except Exception:
        ok = False
    if ok:
        logger.info("Terminal isolation: ACTIVE (chroot jail; mode=%s)", mode)
    elif mode == "required":
        logger.error(
            "Terminal isolation REQUIRED but the host blocks namespace/mount syscalls; "
            "terminals will refuse to open. Set TERMINAL_ISOLATION=preferred to allow fallback."
        )
    else:
        logger.warning(
            "Terminal isolation UNAVAILABLE on this host (namespace/mount syscalls blocked); "
            "falling back to unjailed shells with command-guard only (mode=%s).",
            mode,
        )


def _start_backup_loop() -> None:
    """Periodically snapshot the protected live DB to the persistent backup path."""
    interval = settings.db_backup_interval_sec
    if not settings.db_backup_path.strip() or interval <= 0:
        return

    def _loop() -> None:
        while True:
            time.sleep(interval)
            backup_database()

    threading.Thread(target=_loop, name="db-backup", daemon=True).start()
    logger.info("DB backup loop started (every %ss -> %s)", interval, settings.db_backup_path)


def _bootstrap_instructor() -> None:
    """Create an instructor account from env vars if it doesn't exist yet.
    Set INSTRUCTOR_EMAIL and INSTRUCTOR_PASSWORD to enable."""
    email = os.getenv("INSTRUCTOR_EMAIL", "").lower().strip()
    password = os.getenv("INSTRUCTOR_PASSWORD", "")
    if not email or not password:
        return
    with Session(engine) as session:
        existing = get_user_by_email(session, email)
        if existing:
            if not existing.is_instructor:
                existing.is_instructor = True
                session.commit()
            return
        session.add(
            User(
                email=email,
                name="Instructor",
                password_hash=hash_password(password),
                is_instructor=True,
            )
        )
        session.commit()
        logger.info("Bootstrapped instructor account: %s", email)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


# --------------------------------------------------------------------------- #
# Serve the built frontend (production). In dev, Vite serves it on :5173.
# --------------------------------------------------------------------------- #
_FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"

if _FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=_FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        # API/ws paths are handled above; everything else returns the SPA shell.
        candidate = _FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_FRONTEND_DIST / "index.html")
else:
    logger.warning("Frontend build not found at %s (run `npm run build`).", _FRONTEND_DIST)
