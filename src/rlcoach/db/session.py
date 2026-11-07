"""Open the SQLite database once per process and hand out sessions on it."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from .models import Base

_engine: Engine | None = None
_sessions: sessionmaker[Session] | None = None


def init_db(db_path: Path | None = None) -> Engine:
    """Open the database at db_path, or in memory, creating any missing tables.

    New tables appear in an existing database. Changed ones don't, because
    there are no migrations: reload the games instead.
    """
    global _engine, _sessions
    if db_path is not None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{db_path}" if db_path is not None else "sqlite://"
    # The API and the replay watcher share it from different threads
    _engine = create_engine(url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(_engine)
    _sessions = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def create_session() -> Session:
    """A new session. Close it when you're done."""
    if _sessions is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _sessions()


def get_session() -> Iterator[Session]:
    """A session for one API request, as a FastAPI dependency."""
    session = create_session()
    try:
        yield session
    finally:
        session.close()


def reset_engine() -> None:
    """Close the database, as tests do between cases."""
    global _engine, _sessions
    if _engine is not None:
        _engine.dispose()
    _engine = _sessions = None
