"""Unified database engine and session management.

Delegates to :mod:`file_organizer.api.auth_db` for engine / session creation
but ensures **all** ORM tables (including those from ``db_models``) are
registered on the shared ``Base.metadata`` before ``create_all`` is called.
"""
from __future__ import annotations

from sqlalchemy.engine import Engine

# Side-effect import: register db_models tables on Base.metadata so that
# ``Base.metadata.create_all`` picks up workspaces, organization_jobs, etc.
import file_organizer.api.db_models  # noqa: F401
from file_organizer.api.auth_db import (
    create_session,
    get_engine,
    get_session_factory,
)
from file_organizer.api.auth_models import Base


def init_db(db_path: str) -> None:
    """Create all tables (including new models) for the given *db_path*.

    This is a convenience wrapper that ensures the engine is instantiated and
    every table known to ``Base.metadata`` exists in the target database.

    Args:
        db_path: Filesystem path to the SQLite database, or ``":memory:"``.
    """
    engine: Engine = get_engine(db_path)
    Base.metadata.create_all(engine)


__all__ = [
    "init_db",
    "get_engine",
    "get_session_factory",
    "create_session",
]
