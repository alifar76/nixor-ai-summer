"""Database engine + session helpers.

Security note: the live SQLite file is kept on a path the student terminal cannot
reach (a root-owned directory on local disk, see config.Settings.database_url).
For durability across restarts we optionally snapshot it to a persistent backup
path and restore from there on boot (see backup_database / restore_from_backup).
"""

from __future__ import annotations

import logging
import sqlite3
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import NullPool
from sqlmodel import Session, SQLModel, create_engine

from .config import settings

logger = logging.getLogger(__name__)

# check_same_thread=False is required because FastAPI may use the connection
# across threads (e.g. background tasks). SQLite-specific; ignored by Postgres.
_is_sqlite = settings.database_url.startswith("sqlite")
_connect_args = (
    {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
)


def _sqlite_file_path() -> Path | None:
    """Filesystem path of the SQLite DB, or None for non-file URLs (e.g. Postgres,
    in-memory)."""
    url = settings.database_url
    if not url.startswith("sqlite"):
        return None
    # sqlite:////abs/path  -> /abs/path  ;  sqlite:///rel/path -> rel/path
    if url.startswith("sqlite:////"):
        return Path("/" + url.removeprefix("sqlite:////"))
    if url.startswith("sqlite:///"):
        return Path(url.removeprefix("sqlite:///"))
    return None


def _prepare_sqlite_dir() -> None:
    db_file = _sqlite_file_path()
    if db_file is None:
        return
    parent = db_file.parent
    parent.mkdir(parents=True, exist_ok=True)
    # Lock the directory down to the owner (the API process, which runs as root on
    # App Service). The unprivileged terminal sandbox user then cannot delete the DB.
    try:
        parent.chmod(0o700)
    except OSError:
        logger.debug("Could not chmod DB directory %s", parent, exc_info=True)


def restore_from_backup() -> None:
    """If the live SQLite DB is missing/empty but a persistent backup exists, restore it.
    Called once at startup so ordinary restarts keep student data."""
    db_file = _sqlite_file_path()
    backup = settings.db_backup_path.strip()
    if db_file is None or not backup:
        return
    backup_path = Path(backup)
    if not backup_path.is_file():
        return
    if db_file.is_file() and db_file.stat().st_size > 0:
        return
    try:
        _prepare_sqlite_dir()
        with sqlite3.connect(str(backup_path)) as src, sqlite3.connect(str(db_file)) as dst:
            src.backup(dst)
        logger.info("Restored database from backup %s", backup_path)
    except Exception:
        logger.warning("Failed to restore database from backup %s", backup_path, exc_info=True)


def backup_database() -> None:
    """Snapshot the live SQLite DB to the persistent backup path using SQLite's online
    backup API (safe while the DB is in use). No-op for non-SQLite or when unconfigured."""
    db_file = _sqlite_file_path()
    backup = settings.db_backup_path.strip()
    if db_file is None or not backup or not db_file.is_file():
        return
    backup_path = Path(backup)
    try:
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(db_file)) as src, sqlite3.connect(str(backup_path)) as dst:
            src.backup(dst)
    except Exception:
        logger.debug("Database backup to %s failed", backup_path, exc_info=True)


_prepare_sqlite_dir()
engine = create_engine(
    settings.database_url,
    echo=False,
    connect_args=_connect_args,
    poolclass=NullPool if _is_sqlite else None,
)


def _ensure_schema() -> None:
    # Defensive self-heal for this short-course environment:
    # if the SQLite file or its directory was removed (for example by a malicious
    # terminal command), recreate the directory and tables on the next request so the
    # platform never gets stuck returning 500s.
    from . import models  # noqa: F401

    try:
        SQLModel.metadata.create_all(engine)
    except OperationalError:
        logger.warning("Database unavailable; recreating schema.", exc_info=True)
        _prepare_sqlite_dir()
        SQLModel.metadata.create_all(engine)


def init_db() -> None:
    """Create tables. Import models first so they're registered on SQLModel.metadata."""
    from . import models  # noqa: F401

    _prepare_sqlite_dir()
    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency that yields a DB session."""
    if _is_sqlite:
        _ensure_schema()
    with Session(engine) as session:
        yield session
