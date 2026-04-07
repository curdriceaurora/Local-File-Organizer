"""Integration tests for FileMetadataRepository against a real SQLite DB."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

# Register all models with Base before create_all
import file_organizer.api.db_models  # noqa: F401
from file_organizer.api.auth_models import Base
from file_organizer.api.cache import InMemoryCache
from file_organizer.api.repositories.file_metadata_repo import FileMetadata, FileMetadataRepository

pytestmark = [pytest.mark.integration, pytest.mark.ci]


@pytest.fixture()
def db_session() -> Session:
    """Yield a real in-memory SQLite session with all tables created."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


def _upsert(session: Session, **kwargs: object) -> FileMetadata:
    """Helper: call upsert with sensible defaults, overridden by kwargs."""
    defaults: dict[str, object] = {
        "workspace_id": "ws-1",
        "path": "/root/docs/readme.md",
        "relative_path": "docs/readme.md",
        "name": "readme.md",
        "size_bytes": 1024,
    }
    defaults.update(kwargs)
    return FileMetadataRepository.upsert(session, **defaults)  # type: ignore[arg-type]


class TestUpsert:
    """Tests for FileMetadataRepository.upsert."""

    def test_creates_new_row(self, db_session: Session) -> None:
        """upsert inserts a row and assigns a UUID primary key."""
        row = _upsert(db_session)
        db_session.flush()
        assert row.id is not None
        assert row.workspace_id == "ws-1"
        assert row.relative_path == "docs/readme.md"
        assert row.size_bytes == 1024

    def test_updates_existing_row(self, db_session: Session) -> None:
        """upsert on an existing (workspace_id, relative_path) updates rather than inserts."""
        _upsert(db_session, size_bytes=100)
        db_session.flush()
        _upsert(db_session, size_bytes=999)
        db_session.flush()
        rows = FileMetadataRepository.list_for_workspace(db_session, workspace_id="ws-1")
        assert len(rows) == 1
        assert rows[0].size_bytes == 999

    def test_upsert_with_optional_fields(self, db_session: Session) -> None:
        """upsert persists all optional fields correctly."""
        ts = datetime(2025, 6, 1, tzinfo=UTC)
        row = _upsert(
            db_session,
            mime_type="text/markdown",
            checksum_sha256="deadbeef",
            last_modified=ts,
            extra_json='{"tag": "docs"}',
        )
        db_session.flush()
        assert row.mime_type == "text/markdown"
        assert row.checksum_sha256 == "deadbeef"
        assert row.last_modified == ts
        assert row.extra_json == '{"tag": "docs"}'

    def test_upsert_writes_to_cache(self, db_session: Session) -> None:
        """upsert with a cache argument writes the row into the cache."""
        cache = InMemoryCache()
        _upsert(db_session, cache=cache)
        db_session.flush()
        # Cache hit — get_by_relative_path should find the entry via cache
        result = FileMetadataRepository.get_by_relative_path(
            db_session,
            workspace_id="ws-1",
            relative_path="docs/readme.md",
            cache=cache,
        )
        assert result is not None
        assert result.name == "readme.md"


class TestGetByRelativePath:
    """Tests for FileMetadataRepository.get_by_relative_path."""

    def test_returns_row_when_exists(self, db_session: Session) -> None:
        """get_by_relative_path returns the row for a known path."""
        _upsert(db_session)
        db_session.flush()
        row = FileMetadataRepository.get_by_relative_path(
            db_session, workspace_id="ws-1", relative_path="docs/readme.md"
        )
        assert row is not None
        assert row.name == "readme.md"

    def test_returns_none_when_missing(self, db_session: Session) -> None:
        """get_by_relative_path returns None for a path that does not exist."""
        row = FileMetadataRepository.get_by_relative_path(
            db_session, workspace_id="ws-1", relative_path="does/not/exist.md"
        )
        assert row is None


class TestListForWorkspace:
    """Tests for FileMetadataRepository.list_for_workspace."""

    def test_returns_all_rows_for_workspace(self, db_session: Session) -> None:
        """list_for_workspace returns every row belonging to the workspace."""
        _upsert(db_session, relative_path="a.txt", name="a.txt", path="/root/a.txt")
        _upsert(db_session, relative_path="b.txt", name="b.txt", path="/root/b.txt")
        db_session.flush()
        rows = FileMetadataRepository.list_for_workspace(db_session, workspace_id="ws-1")
        assert len(rows) == 2
        paths = [r.relative_path for r in rows]
        assert "a.txt" in paths
        assert "b.txt" in paths

    def test_does_not_return_other_workspace(self, db_session: Session) -> None:
        """list_for_workspace excludes rows from a different workspace."""
        _upsert(
            db_session,
            workspace_id="ws-1",
            relative_path="mine.txt",
            name="mine.txt",
            path="/root/mine.txt",
        )
        _upsert(
            db_session,
            workspace_id="ws-2",
            relative_path="theirs.txt",
            name="theirs.txt",
            path="/root/theirs.txt",
        )
        db_session.flush()
        rows = FileMetadataRepository.list_for_workspace(db_session, workspace_id="ws-1")
        assert len(rows) == 1
        assert rows[0].relative_path == "mine.txt"

    def test_pagination(self, db_session: Session) -> None:
        """limit/offset pagination returns non-overlapping pages of the correct size."""
        for i in range(5):
            _upsert(
                db_session,
                relative_path=f"file_{i}.txt",
                name=f"file_{i}.txt",
                path=f"/root/file_{i}.txt",
            )
        db_session.flush()
        page1 = FileMetadataRepository.list_for_workspace(
            db_session, workspace_id="ws-1", limit=2, offset=0
        )
        page2 = FileMetadataRepository.list_for_workspace(
            db_session, workspace_id="ws-1", limit=2, offset=2
        )
        assert len(page1) == 2
        assert len(page2) == 2
        assert {r.relative_path for r in page1}.isdisjoint({r.relative_path for r in page2})


class TestDeleteByRelativePath:
    """Tests for FileMetadataRepository.delete_by_relative_path."""

    def test_deletes_existing_row(self, db_session: Session) -> None:
        """delete_by_relative_path removes the row and returns True."""
        _upsert(db_session)
        db_session.flush()
        deleted = FileMetadataRepository.delete_by_relative_path(
            db_session, workspace_id="ws-1", relative_path="docs/readme.md"
        )
        db_session.flush()
        assert deleted is True
        row = FileMetadataRepository.get_by_relative_path(
            db_session, workspace_id="ws-1", relative_path="docs/readme.md"
        )
        assert row is None

    def test_returns_false_when_row_missing(self, db_session: Session) -> None:
        """delete_by_relative_path returns False when the row does not exist."""
        result = FileMetadataRepository.delete_by_relative_path(
            db_session, workspace_id="ws-1", relative_path="ghost.txt"
        )
        assert result is False

    def test_clears_cache_on_delete(self, db_session: Session) -> None:
        """delete_by_relative_path evicts the cache entry for the deleted path."""
        cache = InMemoryCache()
        _upsert(db_session, cache=cache)
        db_session.flush()
        # Confirm the cache is warm
        cached = FileMetadataRepository.get_by_relative_path(
            db_session,
            workspace_id="ws-1",
            relative_path="docs/readme.md",
            cache=cache,
        )
        assert cached is not None
        # Delete with the same cache — should evict the entry
        FileMetadataRepository.delete_by_relative_path(
            db_session,
            workspace_id="ws-1",
            relative_path="docs/readme.md",
            cache=cache,
        )
        db_session.flush()
        # Cache miss + DB miss — must return None
        result = FileMetadataRepository.get_by_relative_path(
            db_session,
            workspace_id="ws-1",
            relative_path="docs/readme.md",
            cache=cache,
        )
        assert result is None
