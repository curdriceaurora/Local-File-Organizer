"""Repository for :class:`file_organizer.api.db_models.FileMetadata`."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TypedDict

from sqlalchemy import and_
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from file_organizer.api.cache import CacheBackend
from file_organizer.api.db_models import FileMetadata

_CACHE_PREFIX = "file_metadata"


class FileMetadataDict(TypedDict, total=False):
    """Type-safe dictionary for bulk file metadata operations."""

    workspace_id: str
    path: str
    relative_path: str
    name: str
    size_bytes: int
    mime_type: str | None
    checksum_sha256: str | None
    last_modified: datetime | None
    extra_json: str | None


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
            row = FileMetadata(
                workspace_id=workspace_id,
                path=path,
                relative_path=relative_path,
                name=name,
                size_bytes=size_bytes,
                mime_type=mime_type,
                checksum_sha256=checksum_sha256,
                last_modified=last_modified,
                extra_json=extra_json,
            )
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

    @staticmethod
    def bulk_upsert(
        session: Session,
        *,
        records: list[FileMetadataDict],
        cache: CacheBackend | None = None,
        cache_ttl_seconds: int = 900,
    ) -> int:
        """Bulk upsert file metadata records for improved performance.

        Uses SQLite's INSERT OR REPLACE to efficiently handle large batches
        of file metadata. This is significantly faster than individual upserts
        for scanning large directories.

        Args:
            session: Active SQLAlchemy session.
            records: List of file metadata dictionaries to upsert.
            cache: Optional cache backend to invalidate entries.
            cache_ttl_seconds: TTL for cached entries (default 900s).

        Returns:
            Number of records processed.
        """
        if not records:
            return 0

        now = datetime.now(UTC)
        insert_data = []

        for rec in records:
            insert_data.append({
                "workspace_id": rec["workspace_id"],
                "path": rec["path"],
                "relative_path": rec["relative_path"],
                "name": rec["name"],
                "size_bytes": rec["size_bytes"],
                "mime_type": rec.get("mime_type"),
                "checksum_sha256": rec.get("checksum_sha256"),
                "last_modified": rec.get("last_modified"),
                "extra_json": rec.get("extra_json"),
                "updated_at": now,
            })

        stmt = insert(FileMetadata).values(insert_data)
        stmt = stmt.on_conflict_do_update(
            index_elements=["workspace_id", "relative_path"],
            set_={
                "path": stmt.excluded.path,
                "name": stmt.excluded.name,
                "size_bytes": stmt.excluded.size_bytes,
                "mime_type": stmt.excluded.mime_type,
                "checksum_sha256": stmt.excluded.checksum_sha256,
                "last_modified": stmt.excluded.last_modified,
                "extra_json": stmt.excluded.extra_json,
                "updated_at": now,
            },
        )

        session.execute(stmt)
        session.flush()

        if cache is not None:
            for rec in records:
                cache.delete(_cache_key(rec["workspace_id"], rec["relative_path"]))

        return len(records)

    @staticmethod
    def bulk_get(
        session: Session,
        *,
        workspace_id: str,
        relative_paths: list[str],
        cache: CacheBackend | None = None,
    ) -> dict[str, FileMetadata]:
        """Bulk fetch metadata by relative paths for improved performance.

        Retrieves multiple file metadata records in a single query, which is
        much more efficient than individual lookups when processing large
        file sets.

        Args:
            session: Active SQLAlchemy session.
            workspace_id: Workspace identifier.
            relative_paths: List of relative paths to fetch.
            cache: Optional cache backend (currently not used for bulk ops).

        Returns:
            Dictionary mapping relative_path -> FileMetadata.
        """
        if not relative_paths:
            return {}

        rows = (
            session.query(FileMetadata)
            .filter(
                and_(
                    FileMetadata.workspace_id == workspace_id,
                    FileMetadata.relative_path.in_(relative_paths),
                )
            )
            .all()
        )

        return {row.relative_path: row for row in rows}
