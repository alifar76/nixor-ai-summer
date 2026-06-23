"""Database engine + session helpers."""

from __future__ import annotations

from collections.abc import Iterator

from sqlmodel import Session, SQLModel, create_engine

from .config import settings

# check_same_thread=False is required because FastAPI may use the connection
# across threads (e.g. background tasks). SQLite-specific; ignored by Postgres.
_connect_args = (
    {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
)

engine = create_engine(settings.database_url, echo=False, connect_args=_connect_args)


def init_db() -> None:
    """Create tables. Import models first so they're registered on SQLModel.metadata."""
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    """FastAPI dependency that yields a DB session."""
    with Session(engine) as session:
        yield session
