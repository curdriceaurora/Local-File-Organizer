"""Database utilities for API authentication."""

from __future__ import annotations

from functools import cache

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from file_organizer.api.auth_models import Base
from file_organizer.api.database import (
    create_session as create_db_session,
)
from file_organizer.api.database import (
    get_engine as get_db_engine,
)
from file_organizer.api.database import (
    get_session_factory as get_db_session_factory,
)
from file_organizer.config.path_manager import get_config_dir


def _default_auth_db_path() -> str:
    """Return the default on-disk auth database path."""
    return str(get_config_dir() / "auth.db")


def _uses_default_auth_db(db_path: str) -> bool:
    """Return whether *db_path* points at the default auth database."""
    return db_path == _default_auth_db_path()


def _ensure_default_auth_db_dir() -> None:
    """Create the default auth DB directory when using the default DB path."""
    get_config_dir().mkdir(parents=True, exist_ok=True)


@cache
def get_engine(db_path: str) -> Engine:
    """Return a cached SQLAlchemy engine for the auth database."""
    # Keep auth defaults conservative; feature-specific callers can use
    # file_organizer.api.database directly for custom pool tuning.
    if _uses_default_auth_db(db_path):
        _ensure_default_auth_db_dir()
    engine = get_db_engine(
        db_path,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle_seconds=1800,
    )
    Base.metadata.create_all(engine)
    return engine


@cache
def get_session_factory(db_path: str) -> sessionmaker[Session]:
    """Return a cached session factory for the auth database."""
    # Ensure auth tables exist before handing out sessions.
    get_engine(db_path)
    return get_db_session_factory(
        db_path,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle_seconds=1800,
    )


def create_session(db_path: str) -> Session:
    """Create a new SQLAlchemy session for the auth database."""
    get_engine(db_path)
    return create_db_session(
        db_path,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle_seconds=1800,
    )
