"""Repository for :class:`file_organizer.api.db_models.FileMetadata`."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from file_organizer.api.cache import CacheBackend
from file_organizer.api.db_models import FileMetadata

_CACHE_PREFIX = "file_metadata"


def _cache_key(workspace_id: str, relative_path: str) -> str:
    return f"{_CACHE_PREFIX}:{workspace_id}:{relative_path}"


def _cache_payload(row: FileMetadata) -> dict[str, object]:
    return {
        "id": row.id,
        "workspace_id": row.workspace_id,
        "path": row.path,
        "relative_path": row.relative_path,
        "name": row.name,
        "size_bytes": row.size_bytes,
        "mime_type": row.mime_type,
        "checksum_sha256": row.checksum_sha256,
        "last_modified": row.last_modified.isoformat() if row.last_modified is not None else None,
        "extra_json": row.extra_json,
    }


class FileMetadataRepository:
    """CRUD access for file metadata records."""

    @staticmethod
    def upsert(
        session: Session,
        *,
        workspace_id: str,
        path: str,
        relative_path: str,
        name: str,
        size_bytes: int,
        mime_type: str | None = None,
        checksum_sha256: str | None = None,
        last_modified: datetime | None = None,
        extra_json: str | None = None,
        cache: CacheBackend | None = None,
        cache_ttl_seconds: int = 900,
    ) -> FileMetadata:
        """Create or update a metadata row identified by workspace/path."""
        row = (
            session.query(FileMetadata)
            .filter(
                FileMetadata.workspace_id == workspace_id,
                FileMetadata.relative_path == relative_path,
            )
            .first()
        )
        if row is None:
            row = FileMetadata()
            row.workspace_id = workspace_id
            row.path = path
            row.relative_path = relative_path
            row.name = name
            row.size_bytes = size_bytes
            row.mime_type = mime_type
            row.checksum_sha256 = checksum_sha256
            row.last_modified = last_modified
            row.extra_json = extra_json
            session.add(row)
        else:
            row.path = path
            row.name = name
            row.size_bytes = size_bytes
            row.mime_type = mime_type
            row.checksum_sha256 = checksum_sha256
            row.last_modified = last_modified
            row.extra_json = extra_json
            row.updated_at = datetime.now(UTC)

        session.flush()

        if cache is not None:
            cache.set(
                _cache_key(workspace_id, relative_path),
                json.dumps(_cache_payload(row)),
                ttl_seconds=cache_ttl_seconds,
            )

        return row

    @staticmethod
    def get_by_relative_path(
        session: Session,
        *,
        workspace_id: str,
        relative_path: str,
        cache: CacheBackend | None = None,
    ) -> FileMetadata | None:
        """Fetch a metadata row by workspace/relative path."""
        if cache is not None:
            cached = cache.get(_cache_key(workspace_id, relative_path))
            if cached:
                try:
                    data = json.loads(cached)
                    cached_id = data.get("id")
                except (TypeError, ValueError, AttributeError):
                    cached_id = None
                if isinstance(cached_id, str):
                    row = session.get(FileMetadata, cached_id)
                    if row is not None:
                        return row
                cache.delete(_cache_key(workspace_id, relative_path))

        row = (
            session.query(FileMetadata)
            .filter(
                FileMetadata.workspace_id == workspace_id,
                FileMetadata.relative_path == relative_path,
            )
            .first()
        )
        if row is not None and cache is not None:
            cache.set(
                _cache_key(workspace_id, relative_path),
                json.dumps(_cache_payload(row)),
                ttl_seconds=900,
            )
        return row

    @staticmethod
    def list_for_workspace(
        session: Session,
        *,
        workspace_id: str,
        limit: int = 200,
        offset: int = 0,
    ) -> list[FileMetadata]:
        """List metadata entries for a workspace ordered by relative path."""
        return (
            session.query(FileMetadata)
            .filter(FileMetadata.workspace_id == workspace_id)
            .order_by(FileMetadata.relative_path)
            .offset(max(0, offset))
            .limit(max(1, limit))
            .all()
        )

    @staticmethod
    def delete_by_relative_path(
        session: Session,
        *,
        workspace_id: str,
        relative_path: str,
        cache: CacheBackend | None = None,
    ) -> bool:
        """Delete a metadata row by workspace/relative path."""
        row = (
            session.query(FileMetadata)
            .filter(
                FileMetadata.workspace_id == workspace_id,
                FileMetadata.relative_path == relative_path,
            )
            .first()
        )
        if row is None:
            return False
        session.delete(row)
        session.flush()
        if cache is not None:
            cache.delete(_cache_key(workspace_id, relative_path))
        return True
