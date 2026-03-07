"""Tests for file_organizer.api.db — unified database helper module."""

from __future__ import annotations

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

pytestmark = pytest.mark.unit


@pytest.fixture
def in_memory_db() -> str:
    return "sqlite:///:memory:"


class TestInitDb:
    """Tests for init_db()."""

    def test_init_db_creates_tables(self, in_memory_db: str) -> None:
        """init_db should create all tables without error."""
        from file_organizer.api.db import init_db

        init_db(in_memory_db)  # should not raise

    def test_init_db_idempotent(self, in_memory_db: str) -> None:
        """Calling init_db twice on same database is safe."""
        from file_organizer.api.db import init_db

        init_db(in_memory_db)
        init_db(in_memory_db)  # second call must not raise


class TestGetEngine:
    """Tests for get_engine()."""

    def test_returns_engine(self, in_memory_db: str) -> None:
        """get_engine should return a SQLAlchemy Engine."""
        from file_organizer.api.db import get_engine

        engine = get_engine(in_memory_db)
        assert isinstance(engine, Engine)

    def test_custom_pool_size(self, in_memory_db: str) -> None:
        """get_engine accepts custom pool_size without raising."""
        from file_organizer.api.db import get_engine

        engine = get_engine(in_memory_db, pool_size=2, max_overflow=5)
        assert isinstance(engine, Engine)

    def test_echo_flag(self, in_memory_db: str) -> None:
        """get_engine accepts echo=True without raising."""
        from file_organizer.api.db import get_engine

        engine = get_engine(in_memory_db, echo=True)
        assert isinstance(engine, Engine)


class TestGetSessionFactory:
    """Tests for get_session_factory()."""

    def test_returns_session_factory(self, in_memory_db: str) -> None:
        """get_session_factory should return a sessionmaker."""
        from file_organizer.api.db import get_session_factory

        factory = get_session_factory(in_memory_db)
        assert isinstance(factory, sessionmaker)

    def test_factory_produces_sessions(self, in_memory_db: str) -> None:
        """Session factory should produce valid Session objects."""
        from file_organizer.api.db import get_session_factory

        factory = get_session_factory(in_memory_db)
        session = factory()
        try:
            assert isinstance(session, Session)
        finally:
            session.close()


class TestCreateSession:
    """Tests for create_session()."""

    def test_returns_session(self, in_memory_db: str) -> None:
        """create_session should return a usable SQLAlchemy Session."""
        from file_organizer.api.db import create_session

        session = create_session(in_memory_db)
        try:
            assert isinstance(session, Session)
        finally:
            session.close()

    def test_session_can_query(self, in_memory_db: str) -> None:
        """Session returned by create_session should be able to execute queries."""
        from sqlalchemy import text

        from file_organizer.api.db import create_session, init_db

        init_db(in_memory_db)
        session = create_session(in_memory_db)
        try:
            result = session.execute(text("SELECT 1"))
            assert result.scalar() == 1
        finally:
            session.close()
