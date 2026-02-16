"""Tests for shared database utilities (URL resolution + pooled engine config)."""
from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.pool import QueuePool, StaticPool

import file_organizer.api.database as database_mod
from file_organizer.api.database import get_engine, resolve_database_url


def test_resolve_database_url_memory() -> None:
    assert resolve_database_url(":memory:") == "sqlite+pysqlite:///:memory:"


def test_resolve_database_url_file_path(tmp_path: Path) -> None:
    db_path = tmp_path / "db" / "test.db"
    url = resolve_database_url(str(db_path))
    assert url.startswith("sqlite+pysqlite:///")
    assert "test.db" in url


def test_resolve_database_url_passthrough() -> None:
    postgres = "postgresql+psycopg://user:pass@localhost:5432/file_organizer"
    assert resolve_database_url(postgres) == postgres


def test_resolve_database_url_normalizes_backslashes() -> None:
    assert resolve_database_url(r"folder\db.sqlite") == "sqlite+pysqlite:///folder/db.sqlite"


def test_resolve_database_url_rejects_empty_path() -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        resolve_database_url("   ")


def test_resolve_database_url_rejects_null_byte() -> None:
    with pytest.raises(ValueError, match="null byte"):
        resolve_database_url("db.sqlite3\x00")


def test_get_engine_sqlite_memory_uses_static_pool() -> None:
    engine = get_engine(":memory:")
    assert isinstance(engine.pool, StaticPool)


def test_get_engine_sqlite_file_uses_queue_pool(tmp_path: Path) -> None:
    db_path = tmp_path / "queue.db"
    engine = get_engine(str(db_path), pool_size=3, max_overflow=2, pool_recycle_seconds=120)
    assert isinstance(engine.pool, QueuePool)


def test_get_engine_non_sqlite_forwards_pool_args(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class _FakeEngine:
        pass

    def _fake_create_engine(url: str, **kwargs: object) -> _FakeEngine:
        captured["url"] = url
        captured.update(kwargs)
        return _FakeEngine()

    monkeypatch.setattr(database_mod, "create_engine", _fake_create_engine)
    engine = database_mod.get_engine(
        "postgresql+psycopg://u:p@localhost:5432/dbname",
        pool_size=11,
        max_overflow=7,
        pool_pre_ping=False,
        pool_recycle_seconds=55,
    )
    assert isinstance(engine, _FakeEngine)
    assert captured["url"] == "postgresql+psycopg://u:p@localhost:5432/dbname"
    assert captured["pool_size"] == 11
    assert captured["max_overflow"] == 7
    assert captured["pool_pre_ping"] is False
    assert captured["pool_recycle"] == 55
