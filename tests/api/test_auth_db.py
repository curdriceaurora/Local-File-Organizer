"""Tests for file_organizer.api.auth_db."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from sqlalchemy import inspect

from file_organizer.api import auth_db, database

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_caches():
    """Clear the engine/session caches on both layers around each test."""
    caches = (
        auth_db.get_engine,
        auth_db.get_session_factory,
        database.get_engine,
        database.get_session_factory,
    )
    for cache in caches:
        cache.cache_clear()
    yield
    for cache in caches:
        cache.cache_clear()


class TestGetEngineConcurrency:
    """``get_engine`` runs ``create_all`` in its body, so it must serialize.

    ``functools.cache`` guards the *result*, not the call: every thread that
    arrives before the first one returns executes the body too. That let N
    threads issue ``CREATE TABLE`` against the same file-backed SQLite DB,
    which is the concurrent writer behind the Playwright
    ``database is locked`` flake, and which fails outright as
    ``table users already exists`` when the loser gets that far.
    """

    def test_concurrent_first_touch_does_not_race_on_ddl(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "auth.db")
        threads = 12
        barrier = threading.Barrier(threads)
        errors: list[BaseException] = []

        def _first_touch(_: int) -> None:
            barrier.wait(timeout=30)
            try:
                auth_db.get_engine(db_path)
            except BaseException as exc:  # collecting every failure for the assertion
                errors.append(exc)

        with ThreadPoolExecutor(max_workers=threads) as pool:
            list(pool.map(_first_touch, range(threads)))

        assert not errors, f"{len(errors)}/{threads} concurrent callers failed: {errors[0]!r}"

    def test_concurrent_first_touch_creates_schema(self, tmp_path: Path) -> None:
        """Serializing must still leave a usable schema behind, not skip it."""
        db_path = str(tmp_path / "auth.db")
        threads = 8
        barrier = threading.Barrier(threads)

        def _first_touch(_: int) -> None:
            barrier.wait(timeout=30)
            auth_db.get_engine(db_path)

        with ThreadPoolExecutor(max_workers=threads) as pool:
            list(pool.map(_first_touch, range(threads)))

        assert "users" in inspect(auth_db.get_engine(db_path)).get_table_names()

    def test_engine_is_cached_per_path(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "auth.db")
        assert auth_db.get_engine(db_path) is auth_db.get_engine(db_path)
