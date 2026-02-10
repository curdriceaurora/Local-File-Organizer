"""Database utilities for API authentication."""
from __future__ import annotations

from functools import cache
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from file_organizer.api.auth_models import Base


def _normalize_db_path(db_path: str) -> str:
    if db_path == ":memory:":
        return db_path
    resolved = Path(db_path).expanduser()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return str(resolved)


@cache
def get_engine(db_path: str) -> Engine:
    """Return a cached SQLAlchemy engine for the auth database."""
    normalized = _normalize_db_path(db_path)
    if normalized == ":memory:":
        engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            future=True,
        )
    else:
        engine = create_engine(
            f"sqlite+pysqlite:///{normalized}",
            connect_args={"check_same_thread": False},
            future=True,
        )
    Base.metadata.create_all(engine)
    return engine


@cache
def get_session_factory(db_path: str) -> sessionmaker[Session]:
    """Return a cached session factory for the auth database."""
    engine = get_engine(db_path)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def create_session(db_path: str) -> Session:
    """Create a new SQLAlchemy session for the auth database."""
    factory = get_session_factory(db_path)
    return factory()
