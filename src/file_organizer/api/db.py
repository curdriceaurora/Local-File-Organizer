"""Unified database engine/session helpers for web API persistence.

This module provides:
- full table initialization for auth + web models
- pooled engine/session factory access for SQLite and PostgreSQL
- a stable import surface used by repositories and tests
"""

from __future__ import annotations

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

# Side-effect import: register db_models tables on Base.metadata so that
# ``Base.metadata.create_all`` picks up workspaces, organization_jobs, etc.
import file_organizer.api.db_models  # noqa: F401
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


def init_db(
    database: str,
    *,
    pool_size: int = 10,
    max_overflow: int = 20,
    pool_pre_ping: bool = True,
    pool_recycle_seconds: int = 1800,
    echo: bool = False,
) -> None:
    """Create all tables (including new models) for the given *database*.

    This is a convenience wrapper that ensures the engine is instantiated and
    every table known to ``Base.metadata`` exists in the target database.

    Args:
        database: SQLite path/``:memory:`` or SQLAlchemy URL.
        pool_size: Number of connections to keep in the pool.
        max_overflow: Extra connections beyond pool_size allowed.
        pool_pre_ping: Test connections for liveness before use.
        pool_recycle_seconds: Recycle connections after this many seconds.
        echo: Log SQL statements when True.
    """
    engine: Engine = get_db_engine(
        database,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=pool_pre_ping,
        pool_recycle_seconds=pool_recycle_seconds,
        echo=echo,
    )
    Base.metadata.create_all(engine)


def get_engine(
    database: str,
    *,
    pool_size: int = 10,
    max_overflow: int = 20,
    pool_pre_ping: bool = True,
    pool_recycle_seconds: int = 1800,
    echo: bool = False,
) -> Engine:
    """Return a pooled engine for *database* without mutating schema."""
    return get_db_engine(
        database,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=pool_pre_ping,
        pool_recycle_seconds=pool_recycle_seconds,
        echo=echo,
    )


def get_session_factory(
    database: str,
    *,
    pool_size: int = 10,
    max_overflow: int = 20,
    pool_pre_ping: bool = True,
    pool_recycle_seconds: int = 1800,
    echo: bool = False,
) -> sessionmaker[Session]:
    """Return a pooled SQLAlchemy session factory for *database*."""
    return get_db_session_factory(
        database,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=pool_pre_ping,
        pool_recycle_seconds=pool_recycle_seconds,
        echo=echo,
    )


def create_session(
    database: str,
    *,
    pool_size: int = 10,
    max_overflow: int = 20,
    pool_pre_ping: bool = True,
    pool_recycle_seconds: int = 1800,
    echo: bool = False,
) -> Session:
    """Create a SQLAlchemy session for *database*."""
    return create_db_session(
        database,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=pool_pre_ping,
        pool_recycle_seconds=pool_recycle_seconds,
        echo=echo,
    )


__all__ = [
    "init_db",
    "get_engine",
    "get_session_factory",
    "create_session",
]
