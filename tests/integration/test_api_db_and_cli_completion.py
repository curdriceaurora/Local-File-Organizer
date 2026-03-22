"""Integration tests for api/db.py and cli/completion.py.

Covers:
- init_db: creates tables, uses :memory: SQLite, custom echo/pool params
- get_engine: returns Engine, custom params
- get_session_factory: returns sessionmaker, produces sessions
- create_session: returns Session, custom params
- complete_directory: empty incomplete, prefix match, no match, OSError, is_dir input
- complete_file: empty incomplete, prefix match, includes files, OSError, is_dir input
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# api/db.py
# ---------------------------------------------------------------------------


class TestInitDb:
    def test_creates_tables_in_memory(self) -> None:
        from sqlalchemy import inspect

        from file_organizer.api.db import init_db

        init_db(":memory:")
        from file_organizer.api.db import get_engine

        engine = get_engine(":memory:")
        inspector = inspect(engine)
        tables = inspector.get_table_names()
        # init_db creates all ORM tables — should be a non-empty list
        assert isinstance(tables, list)
        assert len(tables) > 0  # Base.metadata.create_all creates at least one table

    def test_init_db_with_custom_pool_params(self, tmp_path: Path) -> None:
        from file_organizer.api.db import init_db

        db_file = str(tmp_path / "test.db")
        init_db(db_file, pool_size=2, max_overflow=5, pool_pre_ping=False, echo=False)

    def test_init_db_with_echo(self, tmp_path: Path) -> None:
        from file_organizer.api.db import init_db

        db_file = str(tmp_path / "echo.db")
        init_db(db_file, echo=True)

    def test_init_db_twice_is_idempotent(self, tmp_path: Path) -> None:
        from file_organizer.api.db import init_db

        db_file = str(tmp_path / "idempotent.db")
        init_db(db_file)
        init_db(db_file)


class TestGetEngine:
    def test_returns_engine(self) -> None:
        from sqlalchemy.engine import Engine

        from file_organizer.api.db import get_engine

        engine = get_engine(":memory:")
        assert isinstance(engine, Engine)

    def test_engine_with_sqlite_file(self, tmp_path: Path) -> None:
        from sqlalchemy.engine import Engine

        from file_organizer.api.db import get_engine

        db_file = str(tmp_path / "engine_test.db")
        engine = get_engine(db_file, pool_size=1, max_overflow=0)
        assert isinstance(engine, Engine)

    def test_engine_pool_recycle_seconds(self, tmp_path: Path) -> None:
        from sqlalchemy.engine import Engine

        from file_organizer.api.db import get_engine

        engine = get_engine(":memory:", pool_recycle_seconds=600)
        assert isinstance(engine, Engine)


class TestGetSessionFactory:
    def test_returns_sessionmaker(self) -> None:
        from sqlalchemy.orm import sessionmaker

        from file_organizer.api.db import get_session_factory

        factory = get_session_factory(":memory:")
        assert isinstance(factory, sessionmaker)

    def test_factory_produces_sessions(self) -> None:
        from sqlalchemy.orm import Session

        from file_organizer.api.db import get_session_factory, init_db

        init_db(":memory:")
        factory = get_session_factory(":memory:")
        session = factory()
        assert isinstance(session, Session)
        session.close()

    def test_session_factory_with_custom_params(self, tmp_path: Path) -> None:
        from sqlalchemy.orm import sessionmaker

        from file_organizer.api.db import get_session_factory

        db_file = str(tmp_path / "factory_test.db")
        factory = get_session_factory(db_file, pool_size=2, max_overflow=4)
        assert isinstance(factory, sessionmaker)


class TestCreateSession:
    def test_returns_session(self) -> None:
        from sqlalchemy.orm import Session

        from file_organizer.api.db import create_session, init_db

        init_db(":memory:")
        session = create_session(":memory:")
        assert isinstance(session, Session)
        session.close()

    def test_session_with_echo(self, tmp_path: Path) -> None:
        from sqlalchemy.orm import Session

        from file_organizer.api.db import create_session, init_db

        db_file = str(tmp_path / "session_echo.db")
        init_db(db_file)
        session = create_session(db_file, echo=True)
        assert isinstance(session, Session)
        session.close()

    def test_session_with_custom_pool_params(self, tmp_path: Path) -> None:
        from sqlalchemy.orm import Session

        from file_organizer.api.db import create_session, init_db

        db_file = str(tmp_path / "session_pool.db")
        init_db(db_file)
        session = create_session(db_file, pool_size=1, max_overflow=2, pool_pre_ping=True)
        assert isinstance(session, Session)
        session.close()


# ---------------------------------------------------------------------------
# cli/completion.py
# ---------------------------------------------------------------------------


class TestCompleteDirectory:
    def test_empty_incomplete_lists_dirs(self, tmp_path: Path) -> None:
        from file_organizer.cli.completion import complete_directory

        (tmp_path / "alpha").mkdir()
        (tmp_path / "beta").mkdir()
        (tmp_path / "file.txt").write_text("x")

        import os

        orig = os.getcwd()
        try:
            os.chdir(tmp_path)
            results = list(complete_directory(""))
        finally:
            os.chdir(orig)

        names = [name for name, kind in results]
        assert "alpha" in names or any("alpha" in n for n in names)
        assert all(kind == "directory" for _, kind in results)

    def test_prefix_filters_directories(self, tmp_path: Path) -> None:
        from file_organizer.cli.completion import complete_directory

        (tmp_path / "abc_dir").mkdir()
        (tmp_path / "xyz_dir").mkdir()

        partial = str(tmp_path / "abc")
        results = list(complete_directory(partial))
        assert len(results) == 1
        assert "directory" in [kind for _, kind in results]

    def test_no_match_returns_empty(self, tmp_path: Path) -> None:
        from file_organizer.cli.completion import complete_directory

        (tmp_path / "subdir").mkdir()
        partial = str(tmp_path / "zzz_no_match")
        results = list(complete_directory(partial))
        assert results == []

    def test_excludes_files(self, tmp_path: Path) -> None:
        from file_organizer.cli.completion import complete_directory

        (tmp_path / "only_file.txt").write_text("data")
        partial = str(tmp_path / "only")
        results = list(complete_directory(partial))
        assert results == []

    def test_is_dir_input_lists_children(self, tmp_path: Path) -> None:
        from file_organizer.cli.completion import complete_directory

        sub = tmp_path / "fresh_subdir"
        sub.mkdir()
        (sub / "child_a").mkdir()
        (sub / "child_b").mkdir()

        results = list(complete_directory(str(sub)))
        kinds = [kind for _, kind in results]
        assert all(k == "directory" for k in kinds)
        assert len(results) == 2

    def test_oserror_returns_empty(self) -> None:
        from file_organizer.cli.completion import complete_directory

        results = list(complete_directory("/nonexistent_path_xyz/partial"))
        assert results == []


class TestCompleteFile:
    def test_empty_incomplete_lists_all(self, tmp_path: Path) -> None:
        from file_organizer.cli.completion import complete_file

        (tmp_path / "dir_a").mkdir()
        (tmp_path / "file_b.txt").write_text("x")

        import os

        orig = os.getcwd()
        try:
            os.chdir(tmp_path)
            results = list(complete_file(""))
        finally:
            os.chdir(orig)

        assert len(results) >= 1

    def test_prefix_filters_files(self, tmp_path: Path) -> None:
        from file_organizer.cli.completion import complete_file

        (tmp_path / "report.pdf").write_bytes(b"pdf")
        (tmp_path / "notes.txt").write_text("notes")

        partial = str(tmp_path / "rep")
        results = list(complete_file(partial))
        assert len(results) == 1
        name, kind = results[0]
        assert "report" in name
        assert kind == ".pdf"

    def test_directory_kind_for_dirs(self, tmp_path: Path) -> None:
        from file_organizer.cli.completion import complete_file

        (tmp_path / "subdir").mkdir()
        partial = str(tmp_path / "sub")
        results = list(complete_file(partial))
        assert len(results) == 1
        _, kind = results[0]
        assert kind == "directory"

    def test_no_extension_file_kind_is_file(self, tmp_path: Path) -> None:
        from file_organizer.cli.completion import complete_file

        (tmp_path / "Makefile").write_text("all:")
        partial = str(tmp_path / "Make")
        results = list(complete_file(partial))
        assert len(results) == 1
        _, kind = results[0]
        assert kind == "file"

    def test_is_dir_input_lists_all_children(self, tmp_path: Path) -> None:
        from file_organizer.cli.completion import complete_file

        sub = tmp_path / "fresh_subdir2"
        sub.mkdir()
        (sub / "d").mkdir()
        (sub / "f.py").write_text("")

        results = list(complete_file(str(sub)))
        assert len(results) == 2

    def test_oserror_returns_empty(self) -> None:
        from file_organizer.cli.completion import complete_file

        results = list(complete_file("/nonexistent_path_xyz/partial"))
        assert results == []

    def test_no_match_returns_empty(self, tmp_path: Path) -> None:
        from file_organizer.cli.completion import complete_file

        (tmp_path / "abc.txt").write_text("x")
        partial = str(tmp_path / "zzz")
        results = list(complete_file(partial))
        assert results == []
