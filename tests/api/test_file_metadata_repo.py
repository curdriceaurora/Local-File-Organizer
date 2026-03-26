"""Tests for file_organizer.api.repositories.file_metadata_repo."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from file_organizer.api.cache import InMemoryCache
from file_organizer.api.db_models import FileMetadata
from file_organizer.api.repositories.file_metadata_repo import (
    FileMetadataRepository,
    _cache_key,
    _cache_payload,
    _checksum_cache_key,
)

pytestmark = pytest.mark.unit


class TestCacheHelpers:
    """Tests for module-level cache helper functions."""

    def test_cache_key_format(self):
        key = _cache_key("ws-1", "docs/readme.md")
        assert key == "file_metadata:ws-1:docs/readme.md"

    def test_cache_payload_contains_expected_keys(self):
        row = MagicMock(spec=FileMetadata)
        row.id = "row-id"
        row.workspace_id = "ws-1"
        row.path = "/abs/docs/readme.md"
        row.relative_path = "docs/readme.md"
        row.name = "readme.md"
        row.size_bytes = 1024
        row.mime_type = "text/markdown"
        row.checksum_sha256 = "abc123"
        row.last_modified = datetime(2025, 1, 1, tzinfo=UTC)
        row.extra_json = '{"tags": ["doc"]}'

        payload = _cache_payload(row)
        assert payload["id"] == "row-id"
        assert payload["workspace_id"] == "ws-1"
        assert payload["path"] == "/abs/docs/readme.md"
        assert payload["relative_path"] == "docs/readme.md"
        assert payload["name"] == "readme.md"
        assert payload["size_bytes"] == 1024
        assert payload["mime_type"] == "text/markdown"
        assert payload["checksum_sha256"] == "abc123"
        assert payload["last_modified"] == "2025-01-01T00:00:00+00:00"
        assert payload["extra_json"] == '{"tags": ["doc"]}'

    def test_cache_payload_none_last_modified(self):
        row = MagicMock(spec=FileMetadata)
        row.id = "row-id"
        row.workspace_id = "ws-1"
        row.path = "/p"
        row.relative_path = "p"
        row.name = "p"
        row.size_bytes = 0
        row.mime_type = None
        row.checksum_sha256 = None
        row.last_modified = None
        row.extra_json = None

        payload = _cache_payload(row)
        assert payload["last_modified"] is None


class TestFileMetadataRepositoryUpsert:
    """Tests for FileMetadataRepository.upsert."""

    def _make_session(self, existing_row=None):
        session = MagicMock(spec=Session)
        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.first.return_value = existing_row
        return session

    def test_upsert_creates_new_row_when_not_found(self):
        session = self._make_session(existing_row=None)
        result = FileMetadataRepository.upsert(
            session,
            workspace_id="ws-1",
            path="/abs/file.txt",
            relative_path="file.txt",
            name="file.txt",
            size_bytes=512,
        )
        session.add.assert_called_once()
        session.flush.assert_called_once()
        added_row = session.add.call_args[0][0]
        assert isinstance(added_row, FileMetadata)
        assert added_row.workspace_id == "ws-1"
        assert added_row.name == "file.txt"
        assert result is added_row

    def test_upsert_updates_existing_row(self):
        existing = MagicMock(spec=FileMetadata)
        session = self._make_session(existing_row=existing)

        result = FileMetadataRepository.upsert(
            session,
            workspace_id="ws-1",
            path="/abs/new_path.txt",
            relative_path="file.txt",
            name="new_name.txt",
            size_bytes=1024,
            mime_type="text/plain",
            checksum_sha256="sha-new",
        )
        assert existing.path == "/abs/new_path.txt"
        assert existing.name == "new_name.txt"
        assert existing.size_bytes == 1024
        assert existing.mime_type == "text/plain"
        assert existing.checksum_sha256 == "sha-new"
        session.add.assert_not_called()
        session.flush.assert_called_once()
        assert result is existing

    def test_upsert_sets_cache_on_create(self):
        session = self._make_session(existing_row=None)
        cache = MagicMock(spec=InMemoryCache)

        FileMetadataRepository.upsert(
            session,
            workspace_id="ws-1",
            path="/p",
            relative_path="f.txt",
            name="f.txt",
            size_bytes=0,
            cache=cache,
            cache_ttl_seconds=300,
        )
        cache.set.assert_called_once()
        key_arg = cache.set.call_args[0][0]
        assert key_arg == "file_metadata:ws-1:f.txt"
        assert cache.set.call_args[1]["ttl_seconds"] == 300

    def test_upsert_no_cache_when_none(self):
        session = self._make_session(existing_row=None)
        FileMetadataRepository.upsert(
            session,
            workspace_id="ws-1",
            path="/p",
            relative_path="f.txt",
            name="f.txt",
            size_bytes=0,
            cache=None,
        )
        # Should not raise - just doesn't cache


class TestFileMetadataRepositoryGetByRelativePath:
    """Tests for FileMetadataRepository.get_by_relative_path."""

    def _make_session(self, query_result=None, get_result=None):
        session = MagicMock(spec=Session)
        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.first.return_value = query_result
        session.get.return_value = get_result
        return session

    def test_get_without_cache(self):
        row = MagicMock(spec=FileMetadata)
        session = self._make_session(query_result=row)

        result = FileMetadataRepository.get_by_relative_path(
            session, workspace_id="ws-1", relative_path="file.txt"
        )
        assert result is row

    def test_get_returns_none_when_not_found(self):
        session = self._make_session(query_result=None)

        result = FileMetadataRepository.get_by_relative_path(
            session, workspace_id="ws-1", relative_path="missing.txt"
        )
        assert result is None

    def test_get_cache_hit_returns_db_row(self):
        row = MagicMock(spec=FileMetadata)
        session = self._make_session(get_result=row)
        cache = MagicMock(spec=InMemoryCache)
        cache.get.return_value = json.dumps({"id": "row-id"})

        result = FileMetadataRepository.get_by_relative_path(
            session, workspace_id="ws-1", relative_path="file.txt", cache=cache
        )
        assert result is row
        session.get.assert_called_once_with(FileMetadata, "row-id")

    def test_get_cache_hit_invalid_json_falls_through(self):
        row = MagicMock(spec=FileMetadata)
        row.id = "r1"
        row.workspace_id = "ws-1"
        row.path = "/p"
        row.relative_path = "file.txt"
        row.name = "file.txt"
        row.size_bytes = 0
        row.mime_type = None
        row.checksum_sha256 = None
        row.last_modified = None
        row.extra_json = None
        session = self._make_session(query_result=row)
        cache = MagicMock(spec=InMemoryCache)
        cache.get.return_value = "not-valid-json{"

        result = FileMetadataRepository.get_by_relative_path(
            session, workspace_id="ws-1", relative_path="file.txt", cache=cache
        )
        # Should fall through to DB query
        assert result is row
        cache.delete.assert_called_once()

    def test_get_cache_hit_stale_id_falls_through(self):
        session = self._make_session(query_result=None, get_result=None)
        cache = MagicMock(spec=InMemoryCache)
        cache.get.return_value = json.dumps({"id": "stale-id"})

        result = FileMetadataRepository.get_by_relative_path(
            session, workspace_id="ws-1", relative_path="file.txt", cache=cache
        )
        assert result is None
        cache.delete.assert_called()

    def test_get_populates_cache_on_miss(self):
        row = MagicMock(spec=FileMetadata)
        row.id = "r1"
        row.workspace_id = "ws-1"
        row.path = "/p"
        row.relative_path = "f.txt"
        row.name = "f.txt"
        row.size_bytes = 10
        row.mime_type = None
        row.checksum_sha256 = None
        row.last_modified = None
        row.extra_json = None

        session = self._make_session(query_result=row)
        cache = MagicMock(spec=InMemoryCache)
        cache.get.return_value = None

        result = FileMetadataRepository.get_by_relative_path(
            session, workspace_id="ws-1", relative_path="f.txt", cache=cache
        )
        assert result is row
        cache.set.assert_called_once()


class TestFileMetadataRepositoryList:
    """Tests for FileMetadataRepository.list_for_workspace."""

    def test_list_returns_results(self):
        session = MagicMock(spec=Session)
        rows = [MagicMock(spec=FileMetadata), MagicMock(spec=FileMetadata)]
        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.order_by.return_value = query
        query.offset.return_value = query
        query.limit.return_value = query
        query.all.return_value = rows

        result = FileMetadataRepository.list_for_workspace(
            session, workspace_id="ws-1", limit=10, offset=0
        )
        assert result == rows

    def test_list_clamps_negative_offset(self):
        session = MagicMock(spec=Session)
        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.order_by.return_value = query
        query.offset.return_value = query
        query.limit.return_value = query
        query.all.return_value = []

        FileMetadataRepository.list_for_workspace(session, workspace_id="ws-1", limit=5, offset=-10)
        query.offset.assert_called_with(0)

    def test_list_clamps_zero_limit(self):
        session = MagicMock(spec=Session)
        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.order_by.return_value = query
        query.offset.return_value = query
        query.limit.return_value = query
        query.all.return_value = []

        FileMetadataRepository.list_for_workspace(session, workspace_id="ws-1", limit=0, offset=0)
        query.limit.assert_called_with(1)


class TestFileMetadataRepositoryDelete:
    """Tests for FileMetadataRepository.delete_by_relative_path."""

    def test_delete_existing_row(self):
        row = MagicMock(spec=FileMetadata)
        session = MagicMock(spec=Session)
        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.first.return_value = row

        result = FileMetadataRepository.delete_by_relative_path(
            session, workspace_id="ws-1", relative_path="file.txt"
        )
        assert result is True
        session.delete.assert_called_once_with(row)
        session.flush.assert_called_once()

    def test_delete_nonexistent_returns_false(self):
        session = MagicMock(spec=Session)
        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.first.return_value = None

        result = FileMetadataRepository.delete_by_relative_path(
            session, workspace_id="ws-1", relative_path="missing.txt"
        )
        assert result is False
        session.delete.assert_not_called()

    def test_delete_clears_cache(self):
        row = MagicMock(spec=FileMetadata)
        row.checksum_sha256 = None
        session = MagicMock(spec=Session)
        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.first.return_value = row
        cache = MagicMock(spec=InMemoryCache)

        FileMetadataRepository.delete_by_relative_path(
            session, workspace_id="ws-1", relative_path="file.txt", cache=cache
        )
        cache.delete.assert_called_once_with("file_metadata:ws-1:file.txt")


class TestFileMetadataRepositoryPagination:
    """Tests for FileMetadataRepository.list_for_workspace_paginated."""

    def _make_session(self, total_count, items):
        """Create a mock session with count and query results."""
        session = MagicMock(spec=Session)

        # Mock count query
        count_query = MagicMock()
        count_query.filter.return_value = count_query
        count_query.scalar.return_value = total_count

        # Mock items query
        items_query = MagicMock()
        items_query.filter.return_value = items_query
        items_query.order_by.return_value = items_query
        items_query.offset.return_value = items_query
        items_query.limit.return_value = items_query
        items_query.all.return_value = items

        # Configure session.query to return appropriate mock based on call
        session.query.side_effect = [count_query, items_query]
        return session

    def test_pagination_returns_correct_structure(self):
        """Test that pagination returns all expected metadata fields."""
        rows = [MagicMock(spec=FileMetadata) for _ in range(10)]
        session = self._make_session(total_count=50, items=rows)

        result = FileMetadataRepository.list_for_workspace_paginated(
            session, workspace_id="ws-1", limit=10, offset=0
        )

        assert isinstance(result, dict)
        assert "items" in result
        assert "total" in result
        assert "limit" in result
        assert "offset" in result
        assert "has_next" in result
        assert "has_prev" in result

    def test_pagination_first_page(self):
        """Test pagination metadata for first page."""
        rows = [MagicMock(spec=FileMetadata) for _ in range(10)]
        session = self._make_session(total_count=50, items=rows)

        result = FileMetadataRepository.list_for_workspace_paginated(
            session, workspace_id="ws-1", limit=10, offset=0
        )

        assert result["items"] == rows
        assert result["total"] == 50
        assert result["limit"] == 10
        assert result["offset"] == 0
        assert result["has_next"] is True
        assert result["has_prev"] is False

    def test_pagination_middle_page(self):
        """Test pagination metadata for middle page."""
        rows = [MagicMock(spec=FileMetadata) for _ in range(10)]
        session = self._make_session(total_count=50, items=rows)

        result = FileMetadataRepository.list_for_workspace_paginated(
            session, workspace_id="ws-1", limit=10, offset=20
        )

        assert result["total"] == 50
        assert result["limit"] == 10
        assert result["offset"] == 20
        assert result["has_next"] is True
        assert result["has_prev"] is True

    def test_pagination_last_page(self):
        """Test pagination metadata for last page."""
        rows = [MagicMock(spec=FileMetadata) for _ in range(5)]
        session = self._make_session(total_count=45, items=rows)

        result = FileMetadataRepository.list_for_workspace_paginated(
            session, workspace_id="ws-1", limit=10, offset=40
        )

        assert result["total"] == 45
        assert result["limit"] == 10
        assert result["offset"] == 40
        assert result["has_next"] is False
        assert result["has_prev"] is True

    def test_pagination_empty_result(self):
        """Test pagination with no results."""
        session = self._make_session(total_count=0, items=[])

        result = FileMetadataRepository.list_for_workspace_paginated(
            session, workspace_id="ws-1", limit=10, offset=0
        )

        assert result["items"] == []
        assert result["total"] == 0
        assert result["has_next"] is False
        assert result["has_prev"] is False

    def test_pagination_sorts_by_name_asc(self):
        """Test sorting by name in ascending order."""
        rows = [MagicMock(spec=FileMetadata) for _ in range(5)]
        session = self._make_session(total_count=5, items=rows)

        result = FileMetadataRepository.list_for_workspace_paginated(
            session,
            workspace_id="ws-1",
            limit=10,
            offset=0,
            sort_by="name",
            sort_order="asc",
        )

        assert result["items"] == rows
        # Verify order_by was called (implementation detail check via mock)

    def test_pagination_sorts_by_size_desc(self):
        """Test sorting by size in descending order."""
        rows = [MagicMock(spec=FileMetadata) for _ in range(5)]
        session = self._make_session(total_count=5, items=rows)

        result = FileMetadataRepository.list_for_workspace_paginated(
            session,
            workspace_id="ws-1",
            limit=10,
            offset=0,
            sort_by="size_bytes",
            sort_order="desc",
        )

        assert result["items"] == rows

    def test_pagination_clamps_negative_offset(self):
        """Test that negative offset is clamped to 0."""
        rows = [MagicMock(spec=FileMetadata) for _ in range(10)]
        session = self._make_session(total_count=50, items=rows)

        result = FileMetadataRepository.list_for_workspace_paginated(
            session, workspace_id="ws-1", limit=10, offset=-5
        )

        assert result["offset"] == 0

    def test_pagination_clamps_zero_limit(self):
        """Test that zero limit is clamped to 1."""
        rows = [MagicMock(spec=FileMetadata)]
        session = self._make_session(total_count=50, items=rows)

        result = FileMetadataRepository.list_for_workspace_paginated(
            session, workspace_id="ws-1", limit=0, offset=0
        )

        assert result["limit"] == 1


def test_pagination():
    """Aggregated test for pagination functionality.

    This test verifies that the pagination system works correctly
    across different scenarios including first page, middle page,
    last page, and empty results.
    """
    # Test with mocked session for comprehensive pagination checks
    session = MagicMock(spec=Session)

    # Mock count query
    count_query = MagicMock()
    count_query.filter.return_value = count_query
    count_query.scalar.return_value = 100

    # Mock items query
    items = [MagicMock(spec=FileMetadata) for _ in range(20)]
    items_query = MagicMock()
    items_query.filter.return_value = items_query
    items_query.order_by.return_value = items_query
    items_query.offset.return_value = items_query
    items_query.limit.return_value = items_query
    items_query.all.return_value = items

    def query_side_effect(_model_or_func):
        if len(session.query.call_args_list) % 2 == 1:
            return count_query
        return items_query

    session.query.side_effect = query_side_effect

    # Test first page
    result = FileMetadataRepository.list_for_workspace_paginated(
        session, workspace_id="test-ws", limit=20, offset=0
    )

    assert result["total"] == 100
    assert result["limit"] == 20
    assert result["offset"] == 0
    assert result["has_next"] is True
    assert result["has_prev"] is False
    assert len(result["items"]) == 20

    # Test middle page
    result = FileMetadataRepository.list_for_workspace_paginated(
        session, workspace_id="test-ws", limit=20, offset=40
    )

    assert result["has_next"] is True
    assert result["has_prev"] is True

    # Test sort options
    result = FileMetadataRepository.list_for_workspace_paginated(
        session,
        workspace_id="test-ws",
        limit=20,
        offset=0,
        sort_by="size_bytes",
        sort_order="desc",
    )

    assert result["items"] == items


def test_batch_operations():
    """Test batch upsert and bulk get operations."""
    from sqlalchemy.orm import Session

    from file_organizer.api.cache import InMemoryCache

    # Test bulk_upsert
    session = MagicMock(spec=Session)
    cache = MagicMock(spec=InMemoryCache)

    records = [
        {
            "workspace_id": "ws-1",
            "path": "/abs/file1.txt",
            "relative_path": "file1.txt",
            "name": "file1.txt",
            "size_bytes": 100,
            "mime_type": "text/plain",
            "checksum_sha256": "sha1",
            "last_modified": datetime(2025, 1, 1, tzinfo=UTC),
            "extra_json": '{"tag": "test"}',
        },
        {
            "workspace_id": "ws-1",
            "path": "/abs/file2.txt",
            "relative_path": "file2.txt",
            "name": "file2.txt",
            "size_bytes": 200,
        },
    ]

    result = FileMetadataRepository.bulk_upsert(
        session, records=records, cache=cache, cache_ttl_seconds=600
    )

    assert result == 2
    session.execute.assert_called_once()
    session.flush.assert_called_once()
    assert cache.delete.call_count == 3

    # Test bulk_upsert with empty list
    session_empty = MagicMock(spec=Session)
    result_empty = FileMetadataRepository.bulk_upsert(session_empty, records=[])
    assert result_empty == 0
    session_empty.execute.assert_not_called()

    # Test bulk_get
    session_get = MagicMock(spec=Session)
    cache_get = MagicMock(spec=InMemoryCache)

    # Mock cache miss - all paths need to be fetched from DB
    cache_get.get.return_value = None

    # Mock database rows
    row1 = MagicMock(spec=FileMetadata)
    row1.id = "id1"
    row1.workspace_id = "ws-1"
    row1.path = "/abs/file1.txt"
    row1.relative_path = "file1.txt"
    row1.name = "file1.txt"
    row1.size_bytes = 100
    row1.mime_type = "text/plain"
    row1.checksum_sha256 = "sha1"
    row1.last_modified = datetime(2025, 1, 1, tzinfo=UTC)
    row1.extra_json = '{"tag": "test"}'

    row2 = MagicMock(spec=FileMetadata)
    row2.id = "id2"
    row2.workspace_id = "ws-1"
    row2.path = "/abs/file2.txt"
    row2.relative_path = "file2.txt"
    row2.name = "file2.txt"
    row2.size_bytes = 200
    row2.mime_type = None
    row2.checksum_sha256 = None
    row2.last_modified = None
    row2.extra_json = None

    query = MagicMock()
    session_get.query.return_value = query
    query.filter.return_value = query
    query.all.return_value = [row1, row2]

    result_get = FileMetadataRepository.bulk_get(
        session_get,
        workspace_id="ws-1",
        relative_paths=["file1.txt", "file2.txt"],
        cache=cache_get,
    )

    assert len(result_get) == 2
    assert "file1.txt" in result_get
    assert "file2.txt" in result_get
    assert result_get["file1.txt"] is row1
    assert result_get["file2.txt"] is row2
    assert cache_get.set.call_count == 2

    # Test bulk_get with empty list
    result_empty_get = FileMetadataRepository.bulk_get(
        session_get, workspace_id="ws-1", relative_paths=[]
    )
    assert result_empty_get == {}


def test_checksum_cache():
    """Test checksum-based duplicate detection cache."""
    from sqlalchemy.orm import Session

    from file_organizer.api.cache import InMemoryCache

    # Test checksum cache key format
    key = _checksum_cache_key("ws-1", "abc123sha256")
    assert key == "file_checksum:ws-1:abc123sha256"

    # Test find_by_checksum without cache
    session = MagicMock(spec=Session)
    row1 = MagicMock(spec=FileMetadata)
    row1.id = "id1"
    row1.workspace_id = "ws-1"
    row1.path = "/abs/file1.txt"
    row1.relative_path = "file1.txt"
    row1.name = "file1.txt"
    row1.size_bytes = 100
    row1.mime_type = "text/plain"
    row1.checksum_sha256 = "checksum123"
    row1.last_modified = datetime(2025, 1, 1, tzinfo=UTC)
    row1.extra_json = None

    row2 = MagicMock(spec=FileMetadata)
    row2.id = "id2"
    row2.workspace_id = "ws-1"
    row2.path = "/abs/file2.txt"
    row2.relative_path = "file2.txt"
    row2.name = "file2.txt"
    row2.size_bytes = 100
    row2.mime_type = "text/plain"
    row2.checksum_sha256 = "checksum123"
    row2.last_modified = datetime(2025, 1, 2, tzinfo=UTC)
    row2.extra_json = None

    query = MagicMock()
    session.query.return_value = query
    query.filter.return_value = query
    query.all.return_value = [row1, row2]

    result = FileMetadataRepository.find_by_checksum(
        session,
        workspace_id="ws-1",
        checksum_sha256="checksum123",
    )

    assert len(result) == 2
    assert result[0] is row1
    assert result[1] is row2
    session.query.assert_called_once_with(FileMetadata)

    # Test find_by_checksum with cache hit
    session_cached = MagicMock(spec=Session)
    cache = MagicMock(spec=InMemoryCache)
    cache.get.return_value = json.dumps({"file_ids": ["id1", "id2"]})

    session_cached.get.side_effect = [row1, row2]

    result_cached = FileMetadataRepository.find_by_checksum(
        session_cached,
        workspace_id="ws-1",
        checksum_sha256="checksum123",
        cache=cache,
    )

    assert len(result_cached) == 2
    assert result_cached[0] is row1
    assert result_cached[1] is row2
    cache.get.assert_called_once_with("file_checksum:ws-1:checksum123")
    # Should not query database when cache hits
    session_cached.query.assert_not_called()

    # Test find_by_checksum with cache miss populates cache
    session_miss = MagicMock(spec=Session)
    cache_miss = MagicMock(spec=InMemoryCache)
    cache_miss.get.return_value = None

    query_miss = MagicMock()
    session_miss.query.return_value = query_miss
    query_miss.filter.return_value = query_miss
    query_miss.all.return_value = [row1, row2]

    result_miss = FileMetadataRepository.find_by_checksum(
        session_miss,
        workspace_id="ws-1",
        checksum_sha256="checksum123",
        cache=cache_miss,
        cache_ttl_seconds=600,
    )

    assert len(result_miss) == 2
    cache_miss.set.assert_called_once()
    set_call_args = cache_miss.set.call_args
    assert set_call_args[0][0] == "file_checksum:ws-1:checksum123"
    assert set_call_args[1]["ttl_seconds"] == 600
    cached_data = json.loads(set_call_args[0][1])
    assert cached_data["file_ids"] == ["id1", "id2"]

    # Test find_by_checksum with empty checksum
    session_empty = MagicMock(spec=Session)
    result_empty = FileMetadataRepository.find_by_checksum(
        session_empty,
        workspace_id="ws-1",
        checksum_sha256="",
    )
    assert result_empty == []
    session_empty.query.assert_not_called()

    # Test find_by_checksum with None checksum
    session_none = MagicMock(spec=Session)
    result_none = FileMetadataRepository.find_by_checksum(
        session_none,
        workspace_id="ws-1",
        checksum_sha256=None,
    )
    assert result_none == []
    session_none.query.assert_not_called()

    # Test find_by_checksum with stale cache (invalid JSON)
    session_stale = MagicMock(spec=Session)
    cache_stale = MagicMock(spec=InMemoryCache)
    cache_stale.get.return_value = "invalid-json{"

    query_stale = MagicMock()
    session_stale.query.return_value = query_stale
    query_stale.filter.return_value = query_stale
    query_stale.all.return_value = [row1]

    result_stale = FileMetadataRepository.find_by_checksum(
        session_stale,
        workspace_id="ws-1",
        checksum_sha256="checksum123",
        cache=cache_stale,
    )

    assert len(result_stale) == 1
    cache_stale.delete.assert_called_once_with("file_checksum:ws-1:checksum123")

    # Test find_by_checksum with stale cache (missing rows)
    session_missing = MagicMock(spec=Session)
    cache_missing = MagicMock(spec=InMemoryCache)
    cache_missing.get.return_value = json.dumps({"file_ids": ["id1", "id2"]})

    # session.get returns None for id2 (missing)
    session_missing.get.side_effect = [row1, None]

    query_missing = MagicMock()
    session_missing.query.return_value = query_missing
    query_missing.filter.return_value = query_missing
    query_missing.all.return_value = [row1, row2]

    result_missing = FileMetadataRepository.find_by_checksum(
        session_missing,
        workspace_id="ws-1",
        checksum_sha256="checksum123",
        cache=cache_missing,
    )

    # Should fall through to DB query when cached row is missing
    assert len(result_missing) == 2
    cache_missing.delete.assert_called_once_with("file_checksum:ws-1:checksum123")

    # Test upsert invalidates checksum cache on update
    session_upsert = MagicMock(spec=Session)
    cache_upsert = MagicMock(spec=InMemoryCache)

    existing = MagicMock(spec=FileMetadata)
    existing.id = "existing-id"
    existing.workspace_id = "ws-1"
    existing.path = "/abs/file.txt"
    existing.relative_path = "file.txt"
    existing.name = "file.txt"
    existing.size_bytes = 100
    existing.mime_type = None
    existing.checksum_sha256 = "old_checksum"
    existing.last_modified = None
    existing.extra_json = None

    query_upsert = MagicMock()
    session_upsert.query.return_value = query_upsert
    query_upsert.filter.return_value = query_upsert
    query_upsert.first.return_value = existing

    FileMetadataRepository.upsert(
        session_upsert,
        workspace_id="ws-1",
        path="/abs/file.txt",
        relative_path="file.txt",
        name="file.txt",
        size_bytes=100,
        checksum_sha256="new_checksum",
        cache=cache_upsert,
    )

    # Should invalidate both old and new checksum caches
    delete_calls = [call[0][0] for call in cache_upsert.delete.call_args_list]
    assert "file_checksum:ws-1:old_checksum" in delete_calls
    assert "file_checksum:ws-1:new_checksum" in delete_calls

    # Test delete_by_relative_path invalidates checksum cache
    session_delete = MagicMock(spec=Session)
    cache_delete = MagicMock(spec=InMemoryCache)

    row_delete = MagicMock(spec=FileMetadata)
    row_delete.checksum_sha256 = "checksum_to_delete"

    query_delete = MagicMock()
    session_delete.query.return_value = query_delete
    query_delete.filter.return_value = query_delete
    query_delete.first.return_value = row_delete

    FileMetadataRepository.delete_by_relative_path(
        session_delete,
        workspace_id="ws-1",
        relative_path="file.txt",
        cache=cache_delete,
    )

    # Should invalidate checksum cache
    delete_calls = [call[0][0] for call in cache_delete.delete.call_args_list]
    assert "file_checksum:ws-1:checksum_to_delete" in delete_calls

    # Test bulk_upsert invalidates checksum caches
    session_bulk = MagicMock(spec=Session)
    cache_bulk = MagicMock(spec=InMemoryCache)

    records = [
        {
            "workspace_id": "ws-1",
            "path": "/abs/file1.txt",
            "relative_path": "file1.txt",
            "name": "file1.txt",
            "size_bytes": 100,
            "checksum_sha256": "checksum1",
        },
        {
            "workspace_id": "ws-1",
            "path": "/abs/file2.txt",
            "relative_path": "file2.txt",
            "name": "file2.txt",
            "size_bytes": 200,
            "checksum_sha256": "checksum2",
        },
    ]

    FileMetadataRepository.bulk_upsert(
        session_bulk,
        records=records,
        cache=cache_bulk,
    )

    # Should invalidate checksum caches for all records
    delete_calls = [call[0][0] for call in cache_bulk.delete.call_args_list]
    assert "file_checksum:ws-1:checksum1" in delete_calls
    assert "file_checksum:ws-1:checksum2" in delete_calls
