"""Integration tests for api/database.py, api/utils.py, and api/exceptions.py.

Covers uncovered branches in:
  - api/database.py  — resolve_database_url error paths, get_engine variants,
                        get_session_factory, create_session
  - api/utils.py     — resolve_path, is_hidden, file_info_from_path error paths
  - api/exceptions.py — ApiError, setup_exception_handlers
"""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.api.database import (
    create_session,
    get_engine,
    get_session_factory,
    resolve_database_url,
)
from file_organizer.api.exceptions import ApiError
from file_organizer.api.utils import file_info_from_path, is_hidden, resolve_path

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# resolve_database_url
# ---------------------------------------------------------------------------


class TestResolveDatabaseUrl:
    def test_memory_returns_sqlite_url(self) -> None:
        assert resolve_database_url(":memory:") == "sqlite+pysqlite:///:memory:"

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            resolve_database_url("")

    def test_whitespace_only_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            resolve_database_url("   ")

    def test_null_byte_raises(self) -> None:
        with pytest.raises(ValueError, match="null byte"):
            resolve_database_url("db\x00.sqlite")

    def test_semicolon_raises(self) -> None:
        with pytest.raises(ValueError, match="invalid characters"):
            resolve_database_url("db.sqlite; DROP TABLE users")

    def test_sql_comment_raises(self) -> None:
        with pytest.raises(ValueError, match="invalid characters"):
            resolve_database_url("db.sqlite -- comment")

    def test_relative_path_gets_sqlite_prefix(self) -> None:
        url = resolve_database_url("mydb.sqlite")
        assert url.startswith("sqlite+pysqlite:///")
        assert "mydb.sqlite" in url

    def test_absolute_path(self, tmp_path: Path) -> None:
        db_path = str(tmp_path / "data.db")
        url = resolve_database_url(db_path)
        assert url.startswith("sqlite+pysqlite:///")

    def test_full_url_passthrough(self) -> None:
        url = resolve_database_url("sqlite+pysqlite:///test.db")
        assert "sqlite" in url

    def test_invalid_full_url_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid database URL"):
            resolve_database_url("notascheme://://://bad")


# ---------------------------------------------------------------------------
# get_engine
# ---------------------------------------------------------------------------


class TestGetEngine:
    def test_in_memory_engine(self) -> None:
        from sqlalchemy.pool import StaticPool

        engine = get_engine(":memory:")
        assert engine is not None
        # In-memory uses StaticPool
        assert isinstance(engine.pool, StaticPool)

    def test_file_sqlite_engine(self, tmp_path: Path) -> None:
        from sqlalchemy.pool import QueuePool

        db = str(tmp_path / "test.db")
        engine = get_engine(db)
        assert engine is not None
        assert isinstance(engine.pool, QueuePool)

    def test_engine_is_cached(self) -> None:
        e1 = get_engine(":memory:")
        e2 = get_engine(":memory:")
        assert e1 is e2


# ---------------------------------------------------------------------------
# get_session_factory + create_session
# ---------------------------------------------------------------------------


class TestGetSessionFactory:
    def test_returns_session_factory(self) -> None:
        factory = get_session_factory(":memory:")
        assert callable(factory)

    def test_factory_produces_session(self) -> None:
        factory = get_session_factory(":memory:")
        session = factory()
        try:
            assert session is not None
        finally:
            session.close()


class TestCreateSession:
    def test_returns_session(self) -> None:
        from sqlalchemy.orm import Session

        session = create_session(":memory:")
        try:
            assert isinstance(session, Session)
        finally:
            session.close()


# ---------------------------------------------------------------------------
# ApiError
# ---------------------------------------------------------------------------


class TestApiError:
    def test_is_exception(self) -> None:
        err = ApiError(status_code=400, error="bad_request", message="Invalid input")
        assert isinstance(err, Exception)

    def test_fields_set(self) -> None:
        err = ApiError(status_code=404, error="not_found", message="Missing")
        assert err.status_code == 404
        assert err.error == "not_found"
        assert err.message == "Missing"

    def test_str_includes_status(self) -> None:
        err = ApiError(status_code=500, error="server_error", message="Oops")
        assert "500" in str(err)

    def test_details_none_by_default(self) -> None:
        err = ApiError(status_code=200, error="ok", message="")
        assert err.details is None

    def test_details_can_be_set(self) -> None:
        err = ApiError(status_code=422, error="validation", message="bad", details={"field": "x"})
        assert err.details == {"field": "x"}


# ---------------------------------------------------------------------------
# resolve_path
# ---------------------------------------------------------------------------


class TestResolvePath:
    def test_allowed_path_returns_resolved(self, tmp_path: Path) -> None:
        allowed = str(tmp_path)
        sub = tmp_path / "sub"
        sub.mkdir()
        result = resolve_path(str(sub), allowed_paths=[allowed])
        assert result == sub.resolve()

    def test_no_allowed_paths_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ApiError) as exc_info:
            resolve_path(str(tmp_path), allowed_paths=None)
        assert exc_info.value.status_code == 403

    def test_empty_allowed_paths_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ApiError) as exc_info:
            resolve_path(str(tmp_path), allowed_paths=[])
        assert exc_info.value.status_code == 403

    def test_outside_root_raises(self, tmp_path: Path) -> None:
        root = str(tmp_path / "allowed")
        Path(root).mkdir()
        outside = str(tmp_path / "other")
        with pytest.raises(ApiError) as exc_info:
            resolve_path(outside, allowed_paths=[root])
        assert exc_info.value.status_code == 403

    def test_exact_root_allowed(self, tmp_path: Path) -> None:
        allowed = str(tmp_path)
        result = resolve_path(str(tmp_path), allowed_paths=[allowed])
        assert result == tmp_path.resolve()


# ---------------------------------------------------------------------------
# is_hidden
# ---------------------------------------------------------------------------


class TestIsHidden:
    def test_hidden_file(self) -> None:
        assert is_hidden(Path("user/.dotfile")) is True

    def test_hidden_dir(self) -> None:
        assert is_hidden(Path("user/.git/config")) is True

    def test_normal_file(self) -> None:
        assert is_hidden(Path("user/documents/report.pdf")) is False

    def test_root_is_not_hidden(self) -> None:
        assert is_hidden(Path("/home")) is False


# ---------------------------------------------------------------------------
# file_info_from_path
# ---------------------------------------------------------------------------


class TestFileInfoFromPath:
    def test_existing_file_returns_info(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_text("hello world")
        info = file_info_from_path(f)
        assert info.name == "test.txt"
        assert info.size > 0
        assert info.file_type == ".txt"

    def test_missing_file_raises_api_error_404(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent.pdf"
        with pytest.raises(ApiError) as exc_info:
            file_info_from_path(missing)
        assert exc_info.value.status_code == 404

    def test_mime_type_detected(self, tmp_path: Path) -> None:
        f = tmp_path / "report.pdf"
        f.write_text("fake pdf content")
        info = file_info_from_path(f)
        assert info.mime_type == "application/pdf"

    def test_no_extension_empty_type(self, tmp_path: Path) -> None:
        f = tmp_path / "makefile"
        f.write_text("target:")
        info = file_info_from_path(f)
        assert info.file_type == ""

    def test_created_and_modified_are_datetime(self, tmp_path: Path) -> None:
        from datetime import datetime

        f = tmp_path / "ts.txt"
        f.write_text("ts")
        info = file_info_from_path(f)
        assert isinstance(info.created, datetime)
        assert isinstance(info.modified, datetime)
