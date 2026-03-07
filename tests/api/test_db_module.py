"""Tests for file_organizer.api.db — unified database helper module."""

from __future__ import annotations

import pytest
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool, StaticPool

pytestmark = pytest.mark.unit


class TestInitDb:
    """Tests for init_db()."""

    def test_init_db_creates_tables(self) -> None:
        """init_db should create expected tables in the target database."""
        from file_organizer.api.db import get_engine, init_db

        init_db(":memory:")

        engine = get_engine(":memory:")
        inspector = sa_inspect(engine)
        table_names = inspector.get_table_names()
        assert "users" in table_names

    def test_init_db_idempotent(self) -> None:
        """Calling init_db twice on same database is safe and tables remain."""
        from file_organizer.api.db import get_engine, init_db

        init_db(":memory:")
        init_db(":memory:")  # second call must not raise

        engine = get_engine(":memory:")
        inspector = sa_inspect(engine)
        assert "users" in inspector.get_table_names()


class TestGetEngine:
    """Tests for get_engine()."""

    def test_returns_engine(self) -> None:
        """get_engine should return a SQLAlchemy Engine."""
        from file_organizer.api.db import get_engine

        engine = get_engine(":memory:")
        assert isinstance(engine, Engine)

    def test_in_memory_uses_static_pool(self) -> None:
        """:memory: DB routes through StaticPool for deterministic behaviour."""
        from file_organizer.api.db import get_engine

        engine = get_engine(":memory:")
        assert isinstance(engine.pool, StaticPool)

    def test_custom_pool_size(self, tmp_path) -> None:
        """File-backed SQLite uses QueuePool and respects pool_size/max_overflow."""
        from file_organizer.api.db import get_engine

        db_url = str(tmp_path / "pool_test.db")
        engine = get_engine(db_url, pool_size=2, max_overflow=5)
        try:
            assert isinstance(engine, Engine)
            assert isinstance(engine.pool, QueuePool)
        finally:
            engine.dispose()

    def test_echo_flag(self, tmp_path) -> None:
        """get_engine with echo=True sets the engine echo attribute."""
        from file_organizer.api.db import get_engine

        db_url = str(tmp_path / "echo_test.db")
        engine = get_engine(db_url, echo=True)
        try:
            assert engine.echo is True
        finally:
            engine.dispose()


class TestGetSessionFactory:
    """Tests for get_session_factory()."""

    def test_returns_session_factory(self) -> None:
        """get_session_factory should return a sessionmaker."""
        from file_organizer.api.db import get_session_factory

        factory = get_session_factory(":memory:")
        assert isinstance(factory, sessionmaker)

    def test_factory_produces_sessions(self) -> None:
        """Session factory should produce valid Session objects."""
        from file_organizer.api.db import get_session_factory

        factory = get_session_factory(":memory:")
        session = factory()
        try:
            assert isinstance(session, Session)
        finally:
            session.close()


class TestCreateSession:
    """Tests for create_session()."""

    def test_returns_session(self) -> None:
        """create_session should return a usable SQLAlchemy Session."""
        from file_organizer.api.db import create_session

        session = create_session(":memory:")
        try:
            assert isinstance(session, Session)
        finally:
            session.close()

    def test_session_can_query(self) -> None:
        """Session returned by create_session should be able to execute queries."""
        from file_organizer.api.db import create_session, init_db

        init_db(":memory:")
        session = create_session(":memory:")
        try:
            result = session.execute(text("SELECT 1"))
            assert result.scalar() == 1
        finally:
            session.close()
