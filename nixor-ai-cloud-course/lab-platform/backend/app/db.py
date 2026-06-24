"""Database engine + session helpers."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy.pool import NullPool
from sqlmodel import Session, SQLModel, create_engine

from .config import settings

# check_same_thread=False is required because FastAPI may use the connection
# across threads (e.g. background tasks). SQLite-specific; ignored by Postgres.
_is_sqlite = settings.database_url.startswith("sqlite")
_connect_args = (
    {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
)


def _prepare_sqlite_dir() -> None:
    if not settings.database_url.startswith("sqlite:////"):
        return
    db_file = Path(settings.database_url.removeprefix("sqlite:////"))
    db_file.parent.mkdir(parents=True, exist_ok=True)


_prepare_sqlite_dir()
engine = create_engine(
    settings.database_url,
    echo=False,
    connect_args=_connect_args,
    poolclass=NullPool if _is_sqlite else None,
)


def _ensure_schema() -> None:
    # Defensive self-heal for this short-course environment:
    # if SQLite file is recreated (for example after accidental deletion),
    # lazily recreate tables on the next request.
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def init_db() -> None:
    """Create tables. Import models first so they're registered on SQLModel.metadata."""
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency that yields a DB session."""
    if _is_sqlite:
        _ensure_schema()
    with Session(engine) as session:
        yield session
