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
    _chunk_records,
)

pytestmark = [pytest.mark.unit, pytest.mark.ci]


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

    def test_chunk_records_splits_large_batches(self):
        records = [
            {
                "workspace_id": "ws",
                "relative_path": f"f{i}",
                "path": f"/f{i}",
                "name": f"f{i}",
                "size_bytes": i,
            }
            for i in range(450)
        ]
        chunks = _chunk_records(records)
        assert [len(chunk) for chunk in chunks] == [200, 200, 50]


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
        return session, items_query

    def test_pagination_returns_correct_structure(self):
        """Test that pagination returns all expected metadata fields."""
        rows = [MagicMock(spec=FileMetadata) for _ in range(10)]
        session, _ = self._make_session(total_count=50, items=rows)

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
        session, _ = self._make_session(total_count=50, items=rows)

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
        session, _ = self._make_session(total_count=50, items=rows)

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
        session, _ = self._make_session(total_count=45, items=rows)

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
        session, _ = self._make_session(total_count=0, items=[])

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
        session, items_query = self._make_session(total_count=5, items=rows)

        result = FileMetadataRepository.list_for_workspace_paginated(
            session,
            workspace_id="ws-1",
            limit=10,
            offset=0,
            sort_by="name",
            sort_order="asc",
        )

        assert result["items"] == rows
        items_query.order_by.assert_called_once()
        sort_args = items_query.order_by.call_args.args
        assert len(sort_args) == 2
        assert "name" in str(sort_args[0]).lower()
        assert "id" in str(sort_args[1]).lower()

    def test_pagination_sorts_by_size_desc(self):
        """Test sorting by size in descending order."""
        rows = [MagicMock(spec=FileMetadata) for _ in range(5)]
        session, items_query = self._make_session(total_count=5, items=rows)

        result = FileMetadataRepository.list_for_workspace_paginated(
            session,
            workspace_id="ws-1",
            limit=10,
            offset=0,
            sort_by="size_bytes",
            sort_order="desc",
        )

        assert result["items"] == rows
        items_query.order_by.assert_called_once()
        sort_args = items_query.order_by.call_args.args
        assert len(sort_args) == 2
        assert "size_bytes" in str(sort_args[0]).lower()
        assert "desc" in str(sort_args[0]).lower()
        assert "id" in str(sort_args[1]).lower()

    def test_pagination_clamps_negative_offset(self):
        """Test that negative offset is clamped to 0."""
        rows = [MagicMock(spec=FileMetadata) for _ in range(10)]
        session, _ = self._make_session(total_count=50, items=rows)

        result = FileMetadataRepository.list_for_workspace_paginated(
            session, workspace_id="ws-1", limit=10, offset=-5
        )

        assert result["offset"] == 0

    def test_pagination_clamps_zero_limit(self):
        """Test that zero limit is clamped to 1."""
        rows = [MagicMock(spec=FileMetadata)]
        session, _ = self._make_session(total_count=50, items=rows)

        result = FileMetadataRepository.list_for_workspace_paginated(
            session, workspace_id="ws-1", limit=0, offset=0
        )

        assert result["limit"] == 1

    def test_pagination_invalid_sort_field_falls_back_to_relative_path(self):
        """Invalid sort_by values fall back to deterministic relative_path ordering."""
        rows = [MagicMock(spec=FileMetadata) for _ in range(2)]
        session, items_query = self._make_session(total_count=2, items=rows)

        result = FileMetadataRepository.list_for_workspace_paginated(
            session,
            workspace_id="ws-1",
            sort_by="bogus",  # type: ignore[arg-type]
            sort_order="asc",
        )

        assert result["items"] == rows
        sort_args = items_query.order_by.call_args.args
        assert "relative_path" in str(sort_args[0]).lower()


class TestFileMetadataRepositoryBulkOperations:
    """Tests for bulk repository helpers."""

    def test_bulk_upsert_returns_zero_for_empty_records(self):
        session = MagicMock(spec=Session)

        assert FileMetadataRepository.bulk_upsert(session, records=[]) == 0
        session.execute.assert_not_called()

    def test_bulk_get_returns_empty_for_empty_paths(self):
        session = MagicMock(spec=Session)

        assert (
            FileMetadataRepository.bulk_get(session, workspace_id="ws-1", relative_paths=[]) == {}
        )
        session.query.assert_not_called()

    def test_find_by_checksum_returns_empty_for_none_checksum(self):
        session = MagicMock(spec=Session)

        assert (
            FileMetadataRepository.find_by_checksum(
                session, workspace_id="ws-1", checksum_sha256=None
            )
            == []
        )
        session.query.assert_not_called()

    def test_bulk_upsert_executes_large_batches_in_chunks(self):
        session = MagicMock(spec=Session)

        records = [
            {
                "workspace_id": "ws-1",
                "path": f"/abs/file-{index}.txt",
                "relative_path": f"file-{index}.txt",
                "name": f"file-{index}.txt",
                "size_bytes": index,
            }
            for index in range(450)
        ]

        count = FileMetadataRepository.bulk_upsert(session, records=records)

        assert count == 450
        assert session.execute.call_count == 3
        session.flush.assert_called_once()

    def test_find_by_checksum_returns_cached_empty_result_without_db_lookup(self):
        session = MagicMock(spec=Session)
        cache = MagicMock(spec=InMemoryCache)
        cache.get.return_value = json.dumps({"file_ids": []})

        result = FileMetadataRepository.find_by_checksum(
            session,
            workspace_id="ws-1",
            checksum_sha256="abc123",
            cache=cache,
        )

        assert result == []
        session.query.assert_not_called()


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

    # Test find_by_checksum with cache hit (batch IN query for validation)
    session_cached = MagicMock(spec=Session)
    cache = MagicMock(spec=InMemoryCache)
    cache.get.return_value = json.dumps({"file_ids": ["id1", "id2"]})

    # Mock the batch IN query used for cache validation
    query_cached = MagicMock()
    session_cached.query.return_value = query_cached
    query_cached.filter.return_value = query_cached
    query_cached.all.return_value = [row1, row2]

    result_cached = FileMetadataRepository.find_by_checksum(
        session_cached,
        workspace_id="ws-1",
        checksum_sha256="checksum123",
        cache=cache,
    )

    assert len(result_cached) == 2
    assert row1 in result_cached
    assert row2 in result_cached
    cache.get.assert_called_once_with("file_checksum:ws-1:checksum123")

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

    # Test find_by_checksum with stale cache (missing rows - batch query returns fewer)
    session_missing = MagicMock(spec=Session)
    cache_missing = MagicMock(spec=InMemoryCache)
    cache_missing.get.return_value = json.dumps({"file_ids": ["id1", "id2"]})

    # Batch IN query returns only 1 row (id2 missing), then fallthrough query returns both
    query_missing = MagicMock()
    session_missing.query.return_value = query_missing
    query_missing.filter.return_value = query_missing
    query_missing.all.side_effect = [[row1], [row1, row2]]  # cache validation, then fallthrough

    result_missing = FileMetadataRepository.find_by_checksum(
        session_missing,
        workspace_id="ws-1",
        checksum_sha256="checksum123",
        cache=cache_missing,
    )

    # Should fall through to DB query when cached rows count doesn't match
    assert len(result_missing) == 2
    cache_missing.delete.assert_any_call("file_checksum:ws-1:checksum123")

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


class TestChecksumCacheKeyHelper:
    """Tests for _checksum_cache_key helper (line 50)."""

    def test_checksum_cache_key_format(self) -> None:
        key = _checksum_cache_key("ws-abc", "deadbeef123")
        assert key == "file_checksum:ws-abc:deadbeef123"

    def test_checksum_cache_key_different_workspace(self) -> None:
        key1 = _checksum_cache_key("ws-1", "sha256abc")
        key2 = _checksum_cache_key("ws-2", "sha256abc")
        assert key1 != key2
        assert key1 == "file_checksum:ws-1:sha256abc"
        assert key2 == "file_checksum:ws-2:sha256abc"


class TestUpsertCacheInvalidation:
    """Tests for upsert cache invalidation paths (lines 97-99, 134-135, 138-139)."""

    def _make_session(self, existing_row: FileMetadata | None = None) -> MagicMock:
        session = MagicMock(spec=Session)
        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.first.return_value = existing_row
        return session

    def _make_existing_row(self, checksum: str | None = None) -> MagicMock:
        """Create a properly configured existing row mock for upsert tests."""
        existing = MagicMock(spec=FileMetadata)
        existing.id = "existing-id"
        existing.workspace_id = "ws-1"
        existing.path = "/p"
        existing.relative_path = "f.txt"
        existing.name = "f.txt"
        existing.size_bytes = 10
        existing.mime_type = None
        existing.checksum_sha256 = checksum
        existing.last_modified = None
        existing.extra_json = None
        return existing

    def test_upsert_update_invalidates_old_checksum_cache(self) -> None:
        """When checksum changes on update, old checksum cache is invalidated (lines 134-135)."""
        existing = self._make_existing_row(checksum="old_sha")
        session = self._make_session(existing_row=existing)
        cache = MagicMock(spec=InMemoryCache)

        FileMetadataRepository.upsert(
            session,
            workspace_id="ws-1",
            path="/p",
            relative_path="f.txt",
            name="f.txt",
            size_bytes=10,
            checksum_sha256="new_sha",
            cache=cache,
        )

        delete_keys = [c[0][0] for c in cache.delete.call_args_list]
        assert "file_checksum:ws-1:old_sha" in delete_keys
        assert "file_checksum:ws-1:new_sha" in delete_keys

    def test_upsert_update_same_checksum_no_old_invalidation(self) -> None:
        """When checksum unchanged on update, old checksum cache is NOT invalidated."""
        existing = self._make_existing_row(checksum="same_sha")
        session = self._make_session(existing_row=existing)
        cache = MagicMock(spec=InMemoryCache)

        FileMetadataRepository.upsert(
            session,
            workspace_id="ws-1",
            path="/p",
            relative_path="f.txt",
            name="f.txt",
            size_bytes=10,
            checksum_sha256="same_sha",
            cache=cache,
        )

        delete_keys = [c[0][0] for c in cache.delete.call_args_list]
        # old_checksum == new_checksum, so the condition on line 134 is False
        # Only the new checksum invalidation (line 138-139) fires
        assert delete_keys.count("file_checksum:ws-1:same_sha") == 1

    def test_upsert_update_none_to_checksum(self) -> None:
        """When old_checksum is None, only new checksum cache is invalidated (line 138-139)."""
        existing = self._make_existing_row(checksum=None)
        session = self._make_session(existing_row=existing)
        cache = MagicMock(spec=InMemoryCache)

        FileMetadataRepository.upsert(
            session,
            workspace_id="ws-1",
            path="/p",
            relative_path="f.txt",
            name="f.txt",
            size_bytes=10,
            checksum_sha256="new_sha",
            cache=cache,
        )

        delete_keys = [c[0][0] for c in cache.delete.call_args_list]
        # old_checksum is None so line 134 is False; only line 138-139 fires
        assert "file_checksum:ws-1:new_sha" in delete_keys
        assert len([k for k in delete_keys if k.startswith("file_checksum:")]) == 1

    def test_upsert_create_with_checksum_invalidates_new_cache(self) -> None:
        """When creating a new row with checksum, new checksum cache is invalidated (line 138)."""
        session = self._make_session(existing_row=None)
        cache = MagicMock(spec=InMemoryCache)

        FileMetadataRepository.upsert(
            session,
            workspace_id="ws-1",
            path="/p",
            relative_path="f.txt",
            name="f.txt",
            size_bytes=10,
            checksum_sha256="create_sha",
            cache=cache,
        )

        delete_keys = [c[0][0] for c in cache.delete.call_args_list]
        assert "file_checksum:ws-1:create_sha" in delete_keys

    def test_upsert_create_without_checksum_no_checksum_invalidation(self) -> None:
        """When creating without checksum, no checksum cache invalidation (line 138 is False)."""
        session = self._make_session(existing_row=None)
        cache = MagicMock(spec=InMemoryCache)

        FileMetadataRepository.upsert(
            session,
            workspace_id="ws-1",
            path="/p",
            relative_path="f.txt",
            name="f.txt",
            size_bytes=10,
            checksum_sha256=None,
            cache=cache,
        )

        delete_keys = [c[0][0] for c in cache.delete.call_args_list]
        # No checksum cache keys should be deleted
        assert not any(k.startswith("file_checksum:") for k in delete_keys)

    def test_upsert_captures_old_checksum_before_update(self) -> None:
        """Lines 97-99: old_checksum is captured from the existing row before update."""
        existing = self._make_existing_row(checksum="original_sha")
        session = self._make_session(existing_row=existing)
        cache = MagicMock(spec=InMemoryCache)

        FileMetadataRepository.upsert(
            session,
            workspace_id="ws-1",
            path="/p",
            relative_path="f.txt",
            name="f.txt",
            size_bytes=10,
            checksum_sha256="updated_sha",
            cache=cache,
        )

        # Verify the existing row's checksum was overwritten
        assert existing.checksum_sha256 == "updated_sha"
        # But old checksum cache was still invalidated (captured before overwrite)
        delete_keys = [c[0][0] for c in cache.delete.call_args_list]
        assert "file_checksum:ws-1:original_sha" in delete_keys


class TestListForWorkspacePaginatedSorting:
    """Tests for list_for_workspace_paginated sort columns and orders (lines 227-257)."""

    def _make_session(self, total_count: int, items: list[MagicMock]) -> MagicMock:
        session = MagicMock(spec=Session)
        count_query = MagicMock()
        count_query.filter.return_value = count_query
        count_query.scalar.return_value = total_count

        items_query = MagicMock()
        items_query.filter.return_value = items_query
        items_query.order_by.return_value = items_query
        items_query.offset.return_value = items_query
        items_query.limit.return_value = items_query
        items_query.all.return_value = items

        session.query.side_effect = [count_query, items_query]
        return session

    def test_sort_by_last_modified_asc(self) -> None:
        """Test sorting by last_modified ascending (line 237)."""
        rows = [MagicMock(spec=FileMetadata)]
        session = self._make_session(total_count=1, items=rows)

        result = FileMetadataRepository.list_for_workspace_paginated(
            session,
            workspace_id="ws-1",
            limit=10,
            offset=0,
            sort_by="last_modified",
            sort_order="asc",
        )

        assert result["items"] == rows
        assert result["total"] == 1

    def test_sort_by_relative_path_desc(self) -> None:
        """Test desc sort order (lines 240-241)."""
        rows = [MagicMock(spec=FileMetadata) for _ in range(3)]
        session = self._make_session(total_count=3, items=rows)

        result = FileMetadataRepository.list_for_workspace_paginated(
            session,
            workspace_id="ws-1",
            limit=10,
            offset=0,
            sort_by="relative_path",
            sort_order="desc",
        )

        assert result["items"] == rows
        assert result["total"] == 3

    def test_sort_by_name_desc(self) -> None:
        """Test sorting by name descending (lines 237, 240-241)."""
        rows = [MagicMock(spec=FileMetadata) for _ in range(2)]
        session = self._make_session(total_count=2, items=rows)

        result = FileMetadataRepository.list_for_workspace_paginated(
            session,
            workspace_id="ws-1",
            limit=5,
            offset=0,
            sort_by="name",
            sort_order="desc",
        )

        assert result["items"] == rows
        assert result["total"] == 2
        assert result["limit"] == 5
        assert result["offset"] == 0

    def test_pagination_has_next_and_has_prev_flags(self) -> None:
        """Test has_next and has_prev computation (lines 254-255, 257)."""
        rows = [MagicMock(spec=FileMetadata) for _ in range(5)]
        session = self._make_session(total_count=20, items=rows)

        result = FileMetadataRepository.list_for_workspace_paginated(
            session, workspace_id="ws-1", limit=5, offset=5
        )

        assert result["has_next"] is True  # 5 + 5 = 10 < 20
        assert result["has_prev"] is True  # offset 5 > 0
        assert result["total"] == 20

    def test_pagination_exact_boundary_no_next(self) -> None:
        """Test has_next is False when offset + limit == total (line 254)."""
        rows = [MagicMock(spec=FileMetadata) for _ in range(5)]
        session = self._make_session(total_count=10, items=rows)

        result = FileMetadataRepository.list_for_workspace_paginated(
            session, workspace_id="ws-1", limit=5, offset=5
        )

        assert result["has_next"] is False  # 5 + 5 = 10, not < 10
        assert result["has_prev"] is True

    def test_offset_and_limit_normalization(self) -> None:
        """Test that offset and limit are normalized (lines 227-228)."""
        rows: list[MagicMock] = []
        session = self._make_session(total_count=0, items=rows)

        result = FileMetadataRepository.list_for_workspace_paginated(
            session, workspace_id="ws-1", limit=-5, offset=-10
        )

        assert result["offset"] == 0
        assert result["limit"] == 1


class TestDeleteByRelativePathCacheHandling:
    """Tests for delete_by_relative_path cache handling (lines 286, 292-293)."""

    def test_delete_with_checksum_invalidates_checksum_cache(self) -> None:
        """Line 286, 292-293: deleting a row with a checksum invalidates checksum cache."""
        row = MagicMock(spec=FileMetadata)
        row.checksum_sha256 = "delete_me_sha"
        session = MagicMock(spec=Session)
        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.first.return_value = row
        cache = MagicMock(spec=InMemoryCache)

        result = FileMetadataRepository.delete_by_relative_path(
            session, workspace_id="ws-1", relative_path="file.txt", cache=cache
        )

        assert result is True
        delete_keys = [c[0][0] for c in cache.delete.call_args_list]
        assert "file_metadata:ws-1:file.txt" in delete_keys
        assert "file_checksum:ws-1:delete_me_sha" in delete_keys
        assert len(delete_keys) == 2

    def test_delete_without_checksum_no_checksum_cache_invalidation(self) -> None:
        """Line 292: when checksum is None, only path cache is invalidated."""
        row = MagicMock(spec=FileMetadata)
        row.checksum_sha256 = None
        session = MagicMock(spec=Session)
        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.first.return_value = row
        cache = MagicMock(spec=InMemoryCache)

        result = FileMetadataRepository.delete_by_relative_path(
            session, workspace_id="ws-1", relative_path="file.txt", cache=cache
        )

        assert result is True
        cache.delete.assert_called_once_with("file_metadata:ws-1:file.txt")


class TestBulkUpsert:
    """Tests for bulk_upsert (lines 319-366)."""

    def test_bulk_upsert_empty_records_returns_zero(self) -> None:
        """Lines 319-320: empty records list returns 0 immediately."""
        session = MagicMock(spec=Session)
        result = FileMetadataRepository.bulk_upsert(session, records=[])
        assert result == 0
        session.execute.assert_not_called()

    def test_bulk_upsert_constructs_insert_data(self) -> None:
        """Lines 322-339: records are transformed into insert_data with timestamps."""
        session = MagicMock(spec=Session)
        records = [
            {
                "workspace_id": "ws-1",
                "path": "/abs/file1.txt",
                "relative_path": "file1.txt",
                "name": "file1.txt",
                "size_bytes": 100,
                "mime_type": "text/plain",
                "checksum_sha256": "sha1",
            },
        ]

        result = FileMetadataRepository.bulk_upsert(session, records=records)

        assert result == 1
        session.execute.assert_called_once()
        session.flush.assert_called_once()

    def test_bulk_upsert_multiple_records_with_optional_fields(self) -> None:
        """Lines 325-326, 341-342: multiple records with and without optional fields."""
        session = MagicMock(spec=Session)
        records = [
            {
                "workspace_id": "ws-1",
                "path": "/abs/a.txt",
                "relative_path": "a.txt",
                "name": "a.txt",
                "size_bytes": 50,
            },
            {
                "workspace_id": "ws-1",
                "path": "/abs/b.txt",
                "relative_path": "b.txt",
                "name": "b.txt",
                "size_bytes": 75,
                "mime_type": "application/pdf",
                "checksum_sha256": "sha_b",
                "last_modified": datetime(2025, 6, 1, tzinfo=UTC),
                "extra_json": '{"key": "val"}',
            },
        ]

        result = FileMetadataRepository.bulk_upsert(session, records=records)

        assert result == 2
        session.execute.assert_called_once()
        session.flush.assert_called_once()

    def test_bulk_upsert_cache_invalidation(self) -> None:
        """Lines 359-364: cache entries are invalidated for all records."""
        session = MagicMock(spec=Session)
        cache = MagicMock(spec=InMemoryCache)
        records = [
            {
                "workspace_id": "ws-1",
                "path": "/abs/a.txt",
                "relative_path": "a.txt",
                "name": "a.txt",
                "size_bytes": 50,
                "checksum_sha256": "sha_a",
            },
            {
                "workspace_id": "ws-1",
                "path": "/abs/b.txt",
                "relative_path": "b.txt",
                "name": "b.txt",
                "size_bytes": 75,
            },
        ]

        FileMetadataRepository.bulk_upsert(session, records=records, cache=cache)

        delete_keys = [c[0][0] for c in cache.delete.call_args_list]
        assert "file_metadata:ws-1:a.txt" in delete_keys
        assert "file_metadata:ws-1:b.txt" in delete_keys
        assert "file_checksum:ws-1:sha_a" in delete_keys
        # b.txt has no checksum, so no checksum cache key
        assert "file_checksum:ws-1:None" not in delete_keys
        assert len(delete_keys) == 3  # 2 path keys + 1 checksum key

    def test_bulk_upsert_no_cache(self) -> None:
        """Line 359: when cache is None, no cache invalidation occurs."""
        session = MagicMock(spec=Session)
        records = [
            {
                "workspace_id": "ws-1",
                "path": "/abs/a.txt",
                "relative_path": "a.txt",
                "name": "a.txt",
                "size_bytes": 50,
            },
        ]

        result = FileMetadataRepository.bulk_upsert(session, records=records, cache=None)

        assert result == 1
        session.execute.assert_called_once()


class TestBulkGet:
    """Tests for bulk_get (lines 393-439)."""

    def _make_row(self, row_id: str, rel_path: str, workspace_id: str = "ws-1") -> MagicMock:
        row = MagicMock(spec=FileMetadata)
        row.id = row_id
        row.workspace_id = workspace_id
        row.path = f"/abs/{rel_path}"
        row.relative_path = rel_path
        row.name = rel_path
        row.size_bytes = 100
        row.mime_type = None
        row.checksum_sha256 = None
        row.last_modified = None
        row.extra_json = None
        return row

    def test_bulk_get_empty_paths_returns_empty_dict(self) -> None:
        """Lines 393-394: empty relative_paths returns {} immediately."""
        session = MagicMock(spec=Session)
        result = FileMetadataRepository.bulk_get(session, workspace_id="ws-1", relative_paths=[])
        assert result == {}

    def test_bulk_get_cache_hit_returns_from_cache(self) -> None:
        """Lines 399-412: cache hit path returns row from session.get()."""
        row1 = self._make_row("id1", "a.txt")
        session = MagicMock(spec=Session)
        session.get.return_value = row1
        cache = MagicMock(spec=InMemoryCache)
        cache.get.return_value = json.dumps({"id": "id1"})

        # Mock for the DB query (should not be called if all cache hits)
        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.all.return_value = []

        result = FileMetadataRepository.bulk_get(
            session, workspace_id="ws-1", relative_paths=["a.txt"], cache=cache
        )

        assert "a.txt" in result
        assert result["a.txt"] is row1

    def test_bulk_get_cache_miss_fetches_from_db(self) -> None:
        """Lines 414-437: cache miss triggers DB query and populates cache."""
        row1 = self._make_row("id1", "a.txt")
        session = MagicMock(spec=Session)
        cache = MagicMock(spec=InMemoryCache)
        cache.get.return_value = None  # cache miss

        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.all.return_value = [row1]

        result = FileMetadataRepository.bulk_get(
            session,
            workspace_id="ws-1",
            relative_paths=["a.txt"],
            cache=cache,
            cache_ttl_seconds=600,
        )

        assert "a.txt" in result
        assert result["a.txt"] is row1
        # Cache should be populated after DB fetch
        cache.set.assert_called_once()
        set_args = cache.set.call_args
        assert set_args[1]["ttl_seconds"] == 600

    def test_bulk_get_mixed_cache_hit_and_miss(self) -> None:
        """Lines 399-437: mix of cache hit and miss paths."""
        row_a = self._make_row("id-a", "a.txt")
        row_b = self._make_row("id-b", "b.txt")

        session = MagicMock(spec=Session)

        # Cache hit for a.txt, miss for b.txt
        def cache_get_side_effect(key: str) -> str | None:
            if "a.txt" in key:
                return json.dumps({"id": "id-a"})
            return None

        cache = MagicMock(spec=InMemoryCache)
        cache.get.side_effect = cache_get_side_effect

        # session.get returns the cached row
        session.get.return_value = row_a

        # DB query returns b.txt
        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.all.return_value = [row_b]

        result = FileMetadataRepository.bulk_get(
            session,
            workspace_id="ws-1",
            relative_paths=["a.txt", "b.txt"],
            cache=cache,
        )

        assert len(result) == 2
        assert result["a.txt"] is row_a
        assert result["b.txt"] is row_b

    def test_bulk_get_stale_cache_entry_falls_through_to_db(self) -> None:
        """Lines 406-413: invalid cached JSON falls through, deletes stale cache entry."""
        row_a = self._make_row("id-a", "a.txt")
        session = MagicMock(spec=Session)
        cache = MagicMock(spec=InMemoryCache)
        cache.get.return_value = "invalid-json{"

        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.all.return_value = [row_a]

        result = FileMetadataRepository.bulk_get(
            session,
            workspace_id="ws-1",
            relative_paths=["a.txt"],
            cache=cache,
        )

        assert result["a.txt"] is row_a
        # Stale entry should be deleted
        cache.delete.assert_called_once_with("file_metadata:ws-1:a.txt")

    def test_bulk_get_cache_hit_stale_id_falls_through(self) -> None:
        """Lines 408-413: cached ID points to deleted row, falls through to DB."""
        row_a = self._make_row("id-a-new", "a.txt")
        session = MagicMock(spec=Session)
        session.get.return_value = None  # row deleted

        cache = MagicMock(spec=InMemoryCache)
        cache.get.return_value = json.dumps({"id": "id-a-stale"})

        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.all.return_value = [row_a]

        result = FileMetadataRepository.bulk_get(
            session,
            workspace_id="ws-1",
            relative_paths=["a.txt"],
            cache=cache,
        )

        assert result["a.txt"] is row_a
        cache.delete.assert_called_once_with("file_metadata:ws-1:a.txt")

    def test_bulk_get_without_cache_fetches_all_from_db(self) -> None:
        """Lines 415-416: without cache, all paths go to DB."""
        row_a = self._make_row("id-a", "a.txt")
        row_b = self._make_row("id-b", "b.txt")
        session = MagicMock(spec=Session)

        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.all.return_value = [row_a, row_b]

        result = FileMetadataRepository.bulk_get(
            session,
            workspace_id="ws-1",
            relative_paths=["a.txt", "b.txt"],
            cache=None,
        )

        assert len(result) == 2
        assert result["a.txt"] is row_a
        assert result["b.txt"] is row_b

    def test_bulk_get_no_paths_to_fetch_skips_db_query(self) -> None:
        """Lines 418: if all paths are in cache, no DB query is made."""
        row_a = self._make_row("id-a", "a.txt")
        session = MagicMock(spec=Session)
        session.get.return_value = row_a

        cache = MagicMock(spec=InMemoryCache)
        cache.get.return_value = json.dumps({"id": "id-a"})

        result = FileMetadataRepository.bulk_get(
            session,
            workspace_id="ws-1",
            relative_paths=["a.txt"],
            cache=cache,
        )

        assert result["a.txt"] is row_a
        # session.query should not be called (all from cache)
        session.query.assert_not_called()


class TestFindByChecksum:
    """Tests for find_by_checksum (lines 466-505)."""

    def _make_row(self, row_id: str, rel_path: str) -> MagicMock:
        row = MagicMock(spec=FileMetadata)
        row.id = row_id
        row.workspace_id = "ws-1"
        row.path = f"/abs/{rel_path}"
        row.relative_path = rel_path
        row.name = rel_path
        row.size_bytes = 100
        row.mime_type = None
        row.checksum_sha256 = "chk123"
        row.last_modified = None
        row.extra_json = None
        return row

    def test_find_by_checksum_empty_string_returns_empty(self) -> None:
        """Lines 466-467: empty checksum returns [] immediately."""
        session = MagicMock(spec=Session)
        result = FileMetadataRepository.find_by_checksum(
            session, workspace_id="ws-1", checksum_sha256=""
        )
        assert result == []
        session.query.assert_not_called()

    def test_find_by_checksum_none_returns_empty(self) -> None:
        """Lines 466-467: None checksum returns [] immediately."""
        session = MagicMock(spec=Session)
        result = FileMetadataRepository.find_by_checksum(
            session, workspace_id="ws-1", checksum_sha256=None
        )
        assert result == []
        session.query.assert_not_called()

    def test_find_by_checksum_cache_hit_valid(self) -> None:
        """Lines 469-482: cache hit with valid file_ids returns rows via batch IN query."""
        row1 = self._make_row("id1", "a.txt")
        row2 = self._make_row("id2", "b.txt")
        session = MagicMock(spec=Session)

        # Mock the batch IN query path used for cache validation
        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.all.return_value = [row1, row2]

        cache = MagicMock(spec=InMemoryCache)
        cache.get.return_value = json.dumps({"file_ids": ["id1", "id2"]})

        result = FileMetadataRepository.find_by_checksum(
            session, workspace_id="ws-1", checksum_sha256="chk123", cache=cache
        )

        assert len(result) == 2
        assert row1 in result
        assert row2 in result

    def test_find_by_checksum_cache_hit_partial_missing_falls_through(self) -> None:
        """Lines 478-483: if cached rows count != file_ids count, invalidate and query."""
        row1 = self._make_row("id1", "a.txt")
        session = MagicMock(spec=Session)

        cache = MagicMock(spec=InMemoryCache)
        cache.get.return_value = json.dumps({"file_ids": ["id1", "id2"]})

        # First query call returns only 1 row (id2 missing) → cache miss
        # Second query call is the fallthrough DB query
        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.all.side_effect = [[row1], [row1]]  # cache validation, then fallthrough

        result = FileMetadataRepository.find_by_checksum(
            session, workspace_id="ws-1", checksum_sha256="chk123", cache=cache
        )

        assert len(result) == 1
        assert result[0] is row1
        cache.delete.assert_any_call("file_checksum:ws-1:chk123")

    def test_find_by_checksum_cache_hit_invalid_json_falls_through(self) -> None:
        """Lines 473-477: invalid JSON in cache falls through to DB."""
        row1 = self._make_row("id1", "a.txt")
        session = MagicMock(spec=Session)
        cache = MagicMock(spec=InMemoryCache)
        cache.get.return_value = "not-json{"

        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.all.return_value = [row1]

        result = FileMetadataRepository.find_by_checksum(
            session, workspace_id="ws-1", checksum_sha256="chk123", cache=cache
        )

        assert len(result) == 1
        cache.delete.assert_called_once_with("file_checksum:ws-1:chk123")

    def test_find_by_checksum_cache_miss_populates_cache(self) -> None:
        """Lines 485-505: cache miss queries DB and populates cache."""
        row1 = self._make_row("id1", "a.txt")
        session = MagicMock(spec=Session)
        cache = MagicMock(spec=InMemoryCache)
        cache.get.return_value = None

        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.all.return_value = [row1]

        result = FileMetadataRepository.find_by_checksum(
            session,
            workspace_id="ws-1",
            checksum_sha256="chk123",
            cache=cache,
            cache_ttl_seconds=500,
        )

        assert len(result) == 1
        assert result[0] is row1
        cache.set.assert_called_once()
        set_args = cache.set.call_args
        assert set_args[0][0] == "file_checksum:ws-1:chk123"
        cached_data = json.loads(set_args[0][1])
        assert cached_data["file_ids"] == ["id1"]
        assert set_args[1]["ttl_seconds"] == 500

    def test_find_by_checksum_without_cache_queries_db(self) -> None:
        """Lines 485-505: without cache, queries DB directly."""
        row1 = self._make_row("id1", "a.txt")
        session = MagicMock(spec=Session)

        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.all.return_value = [row1]

        result = FileMetadataRepository.find_by_checksum(
            session, workspace_id="ws-1", checksum_sha256="chk123"
        )

        assert len(result) == 1
        assert result[0] is row1

    def test_find_by_checksum_cache_hit_non_list_file_ids_falls_through(self) -> None:
        """Lines 478: if file_ids is not a list, invalidate cache and query DB."""
        row1 = self._make_row("id1", "a.txt")
        session = MagicMock(spec=Session)
        cache = MagicMock(spec=InMemoryCache)
        cache.get.return_value = json.dumps({"file_ids": "not-a-list"})

        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.all.return_value = [row1]

        result = FileMetadataRepository.find_by_checksum(
            session, workspace_id="ws-1", checksum_sha256="chk123", cache=cache
        )

        assert len(result) == 1
        cache.delete.assert_called_once_with("file_checksum:ws-1:chk123")
