"""Shared SQLAlchemy engine/session helpers for API persistence.

This module provides a single place for:
- Database URL/path normalization (SQLite path or full DB URL)
- Engine creation with connection pooling defaults
- Cached session factory construction

It is intentionally generic so both auth-specific and feature-specific
persistence layers can reuse the same connection behavior.
"""
from __future__ import annotations

from functools import lru_cache
from re import compile as re_compile

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool, StaticPool

_URL_SCHEME_RE = re_compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


def resolve_database_url(database: str) -> str:
    """Resolve *database* to a SQLAlchemy database URL.

    Supported inputs:
    - ``:memory:`` -> in-memory SQLite
    - absolute/relative filesystem path -> SQLite file URL
    - full SQLAlchemy URL (e.g. ``postgresql+psycopg://...``)
    """
    value = database.strip()
    if not value:
        raise ValueError("Database path/URL cannot be empty")
    if "\x00" in value:
        raise ValueError("Database path/URL contains null byte")
    if value == ":memory:":
        return "sqlite+pysqlite:///:memory:"
    if _URL_SCHEME_RE.match(value):
        return value

    # Preserve relative-vs-absolute semantics expected by SQLAlchemy:
    # - "db.sqlite" -> sqlite:///db.sqlite (relative)
    # - "/tmp/db.sqlite" -> sqlite:////tmp/db.sqlite (absolute)
    normalized = value.replace("\\", "/")
    return f"sqlite+pysqlite:///{normalized}"


def _is_sqlite_url(url: str) -> bool:
    return url.startswith("sqlite")


@lru_cache(maxsize=64)
def get_engine(
    database: str,
    *,
    pool_size: int = 10,
    max_overflow: int = 20,
    pool_pre_ping: bool = True,
    pool_recycle_seconds: int = 1800,
    echo: bool = False,
) -> Engine:
    """Return a cached SQLAlchemy engine for *database*.

    Pooling behavior:
    - SQLite in-memory: ``StaticPool`` for deterministic tests.
    - SQLite file: ``QueuePool`` with ``check_same_thread=False``.
    - Other engines (e.g. PostgreSQL): standard pooled engine.
    """
    url = resolve_database_url(database)
    base_kwargs = {"future": True, "echo": echo}

    if url == "sqlite+pysqlite:///:memory:":
        return create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            **base_kwargs,
        )

    if _is_sqlite_url(url):
        return create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=QueuePool,
            pool_size=max(1, pool_size),
            max_overflow=max(0, max_overflow),
            pool_pre_ping=pool_pre_ping,
            pool_recycle=max(1, pool_recycle_seconds),
            **base_kwargs,
        )

    return create_engine(
        url,
        pool_size=max(1, pool_size),
        max_overflow=max(0, max_overflow),
        pool_pre_ping=pool_pre_ping,
        pool_recycle=max(1, pool_recycle_seconds),
        **base_kwargs,
    )


@lru_cache(maxsize=64)
def get_session_factory(
    database: str,
    *,
    pool_size: int = 10,
    max_overflow: int = 20,
    pool_pre_ping: bool = True,
    pool_recycle_seconds: int = 1800,
    echo: bool = False,
) -> sessionmaker[Session]:
    """Return a cached SQLAlchemy session factory for *database*."""
    engine = get_engine(
        database,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=pool_pre_ping,
        pool_recycle_seconds=pool_recycle_seconds,
        echo=echo,
    )
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


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
    factory = get_session_factory(
        database,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=pool_pre_ping,
        pool_recycle_seconds=pool_recycle_seconds,
        echo=echo,
    )
    return factory()
