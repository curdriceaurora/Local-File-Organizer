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
