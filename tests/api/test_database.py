"""Tests for file_organizer.api.database."""

from __future__ import annotations

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from file_organizer.api.database import (
    create_session,
    get_engine,
    get_session_factory,
    resolve_database_url,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_lru_caches():
    """Clear engine/session LRU caches before and after each test."""
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    yield
    get_engine.cache_clear()
    get_session_factory.cache_clear()


class TestResolveDatabaseUrl:
    """Tests for resolve_database_url."""

    def test_memory_database(self):
        assert resolve_database_url(":memory:") == "sqlite+pysqlite:///:memory:"

    def test_memory_with_whitespace(self):
        assert resolve_database_url("  :memory:  ") == "sqlite+pysqlite:///:memory:"

    def test_relative_path(self):
        result = resolve_database_url("data/app.db")
        assert result == "sqlite+pysqlite:///data/app.db"

    def test_absolute_path(self):
        result = resolve_database_url("/tmp/app.db")
        assert result == "sqlite+pysqlite:////tmp/app.db"

    def test_backslash_normalized(self):
        result = resolve_database_url("data\\app.db")
        assert result == "sqlite+pysqlite:///data/app.db"

    def test_full_sqlite_url_passthrough(self):
        url = "sqlite+pysqlite:///mydb.sqlite"
        result = resolve_database_url(url)
        assert "mydb.sqlite" in result

    def test_postgresql_url_passthrough(self):
        url = "postgresql+psycopg://user:pass@localhost/dbname"
        result = resolve_database_url(url)
        assert "postgresql" in result
        assert "dbname" in result

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            resolve_database_url("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            resolve_database_url("   ")

    def test_null_byte_raises(self):
        with pytest.raises(ValueError, match="null byte"):
            resolve_database_url("db\x00.sqlite")

    def test_semicolon_raises(self):
        with pytest.raises(ValueError, match="invalid characters"):
            resolve_database_url("db.sqlite; DROP TABLE users")

    def test_sql_comment_raises(self):
        with pytest.raises(ValueError, match="invalid characters"):
            resolve_database_url("db.sqlite--malicious")


class TestGetEngine:
    """Tests for get_engine."""

    def test_memory_engine_uses_static_pool(self):
        engine = get_engine(":memory:")
        assert isinstance(engine, Engine)
        assert isinstance(engine.pool, StaticPool)

    def test_engine_is_cached(self):
        engine1 = get_engine(":memory:")
        engine2 = get_engine(":memory:")
        assert engine1 is engine2

    def test_different_databases_different_engines(self):
        engine1 = get_engine(":memory:")
        engine2 = get_engine("test_other.db")
        assert engine1 is not engine2
        engine2.dispose()

    def test_echo_flag(self):
        engine = get_engine(":memory:", echo=True)
        assert engine.echo is True
        get_engine.cache_clear()


class TestGetSessionFactory:
    """Tests for get_session_factory."""

    def test_factory_returns_callable(self):
        factory = get_session_factory(":memory:")
        assert callable(factory)

    def test_factory_is_cached(self):
        f1 = get_session_factory(":memory:")
        f2 = get_session_factory(":memory:")
        assert f1 is f2


class TestCreateSession:
    """Tests for create_session."""

    def test_create_session_returns_session(self):
        session = create_session(":memory:")
        assert isinstance(session, Session)
        session.close()

    def test_create_session_multiple_calls_return_different_sessions(self):
        s1 = create_session(":memory:")
        s2 = create_session(":memory:")
        assert s1 is not s2
        s1.close()
        s2.close()
