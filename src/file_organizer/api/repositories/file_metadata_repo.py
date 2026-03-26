"""Repository for :class:`file_organizer.api.db_models.FileMetadata`."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Literal, TypedDict

from sqlalchemy import and_, desc, func
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from file_organizer.api.cache import CacheBackend
from file_organizer.api.db_models import FileMetadata

_CACHE_PREFIX = "file_metadata"
_CHECKSUM_CACHE_PREFIX = "file_checksum"
_SQLITE_BULK_BATCH_SIZE = 200
_SORT_COLUMNS = {
    "relative_path": FileMetadata.relative_path,
    "name": FileMetadata.name,
    "size_bytes": FileMetadata.size_bytes,
    "last_modified": FileMetadata.last_modified,
}


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


class PaginatedFileMetadata(TypedDict):
    """Paginated file metadata result with metadata."""

    items: list[FileMetadata]
    total: int
    limit: int
    offset: int
    has_next: bool
    has_prev: bool


def _cache_key(workspace_id: str, relative_path: str) -> str:
    return f"{_CACHE_PREFIX}:{workspace_id}:{relative_path}"


def _checksum_cache_key(workspace_id: str, checksum: str) -> str:
    return f"{_CHECKSUM_CACHE_PREFIX}:{workspace_id}:{checksum}"


def _chunk_records(
    records: list[FileMetadataDict], chunk_size: int = _SQLITE_BULK_BATCH_SIZE
) -> list[list[FileMetadataDict]]:
    """Split bulk-upsert records into SQLite-safe chunks."""
    return [records[index : index + chunk_size] for index in range(0, len(records), chunk_size)]


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

        old_checksum = None
        if row is not None:
            old_checksum = row.checksum_sha256

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

            # Invalidate old checksum cache if checksum changed
            if old_checksum is not None and old_checksum != checksum_sha256:
                cache.delete(_checksum_cache_key(workspace_id, old_checksum))

            # Invalidate new checksum cache to ensure consistency
            if checksum_sha256 is not None:
                cache.delete(_checksum_cache_key(workspace_id, checksum_sha256))

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
    def list_for_workspace_paginated(
        session: Session,
        *,
        workspace_id: str,
        limit: int = 200,
        offset: int = 0,
        sort_by: Literal["relative_path", "name", "size_bytes", "last_modified"] = "relative_path",
        sort_order: Literal["asc", "desc"] = "asc",
    ) -> PaginatedFileMetadata:
        """List metadata entries with pagination metadata and sort options.

        Provides efficient pagination with total count and navigation metadata.
        Supports sorting by multiple fields in ascending or descending order.

        Args:
            session: Active SQLAlchemy session.
            workspace_id: Workspace identifier.
            limit: Maximum number of records to return (default 200).
            offset: Number of records to skip (default 0).
            sort_by: Field to sort by (default "relative_path").
            sort_order: Sort direction "asc" or "desc" (default "asc").

        Returns:
            PaginatedFileMetadata with items and pagination metadata.
        """
        # Normalize offset and limit
        offset = max(0, offset)
        limit = max(1, limit)

        # Build base query
        base_filter = FileMetadata.workspace_id == workspace_id

        # Get total count for pagination metadata
        total = session.query(func.count(FileMetadata.id)).filter(base_filter).scalar() or 0

        # Determine sort column with secondary tiebreaker for deterministic pagination
        primary_col = _SORT_COLUMNS.get(sort_by, FileMetadata.relative_path)
        if sort_order == "desc":
            sort_column = desc(primary_col)
            id_tiebreaker = desc(FileMetadata.id)
        else:
            sort_column = primary_col
            id_tiebreaker = FileMetadata.id

        # Execute paginated query
        items = (
            session.query(FileMetadata)
            .filter(base_filter)
            .order_by(sort_column, id_tiebreaker)
            .offset(offset)
            .limit(limit)
            .all()
        )

        # Calculate pagination flags
        has_next = (offset + limit) < total
        has_prev = offset > 0

        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_next": has_next,
            "has_prev": has_prev,
        }

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

        checksum = row.checksum_sha256

        session.delete(row)
        session.flush()
        if cache is not None:
            cache.delete(_cache_key(workspace_id, relative_path))
            if checksum is not None:
                cache.delete(_checksum_cache_key(workspace_id, checksum))
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
        for batch in _chunk_records(records):
            insert_data = []
            for rec in batch:
                insert_data.append(
                    {
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
                    }
                )

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

            # Prefetch old checksums before upsert so we can invalidate stale cache keys
            old_checksums: dict[tuple[str, str], str | None] = {}
            if cache is not None:
                ws_paths = [(rec["workspace_id"], rec["relative_path"]) for rec in batch]
                existing_rows = (
                    session.query(
                        FileMetadata.workspace_id,
                        FileMetadata.relative_path,
                        FileMetadata.checksum_sha256,
                    )
                    .filter(
                        and_(
                            FileMetadata.workspace_id.in_({wp[0] for wp in ws_paths}),
                            FileMetadata.relative_path.in_({wp[1] for wp in ws_paths}),
                        )
                    )
                    .all()
                )
                for row in existing_rows:
                    old_checksums[(row.workspace_id, row.relative_path)] = row.checksum_sha256

            session.execute(stmt)

            if cache is not None:
                for rec in batch:
                    cache.delete(_cache_key(rec["workspace_id"], rec["relative_path"]))
                    new_checksum = rec.get("checksum_sha256")
                    old_checksum = old_checksums.get((rec["workspace_id"], rec["relative_path"]))
                    # Invalidate old checksum cache if it changed
                    if old_checksum is not None and old_checksum != new_checksum:
                        cache.delete(_checksum_cache_key(rec["workspace_id"], old_checksum))
                    # Invalidate new checksum cache to ensure consistency
                    if new_checksum is not None:
                        cache.delete(_checksum_cache_key(rec["workspace_id"], new_checksum))

        session.flush()

        return len(records)

    @staticmethod
    def bulk_get(
        session: Session,
        *,
        workspace_id: str,
        relative_paths: list[str],
        cache: CacheBackend | None = None,
        cache_ttl_seconds: int = 900,
    ) -> dict[str, FileMetadata]:
        """Bulk fetch metadata by relative paths for improved performance.

        Retrieves multiple file metadata records in a single query, which is
        much more efficient than individual lookups when processing large
        file sets. Uses cache when available to reduce database queries.

        Args:
            session: Active SQLAlchemy session.
            workspace_id: Workspace identifier.
            relative_paths: List of relative paths to fetch.
            cache: Optional cache backend for improved performance.
            cache_ttl_seconds: TTL for cached entries (default 900s).

        Returns:
            Dictionary mapping relative_path -> FileMetadata.
        """
        if not relative_paths:
            return {}

        result = {}
        paths_to_fetch = []

        if cache is not None:
            for rel_path in relative_paths:
                cached = cache.get(_cache_key(workspace_id, rel_path))
                if cached:
                    try:
                        data = json.loads(cached)
                        cached_id = data.get("id")
                    except (TypeError, ValueError, AttributeError):
                        cached_id = None
                    if isinstance(cached_id, str):
                        row = session.get(FileMetadata, cached_id)
                        if row is not None:
                            result[rel_path] = row
                            continue
                    cache.delete(_cache_key(workspace_id, rel_path))
                paths_to_fetch.append(rel_path)
        else:
            paths_to_fetch = list(relative_paths)

        if paths_to_fetch:
            rows = (
                session.query(FileMetadata)
                .filter(
                    and_(
                        FileMetadata.workspace_id == workspace_id,
                        FileMetadata.relative_path.in_(paths_to_fetch),
                    )
                )
                .all()
            )

            for row in rows:
                result[row.relative_path] = row
                if cache is not None:
                    cache.set(
                        _cache_key(workspace_id, row.relative_path),
                        json.dumps(_cache_payload(row)),
                        ttl_seconds=cache_ttl_seconds,
                    )

        return result

    @staticmethod
    def find_by_checksum(
        session: Session,
        *,
        workspace_id: str,
        checksum_sha256: str | None,
        cache: CacheBackend | None = None,
        cache_ttl_seconds: int = 900,
    ) -> list[FileMetadata]:
        """Find all files with the given checksum for duplicate detection.

        Retrieves all file metadata records matching a specific checksum within
        a workspace. Uses cache to avoid repeated queries during duplicate
        detection operations. Returns empty list if checksum is None or empty.

        Args:
            session: Active SQLAlchemy session.
            workspace_id: Workspace identifier.
            checksum_sha256: SHA256 checksum to search for.
            cache: Optional cache backend for improved performance.
            cache_ttl_seconds: TTL for cached entries (default 900s).

        Returns:
            List of FileMetadata records with matching checksum.
        """
        if not checksum_sha256:
            return []

        if cache is not None:
            cache_key = _checksum_cache_key(workspace_id, checksum_sha256)
            cached = cache.get(cache_key)
            if cached:
                try:
                    data = json.loads(cached)
                    file_ids = data.get("file_ids")
                except (TypeError, ValueError, AttributeError):
                    file_ids = None
                if isinstance(file_ids, list):
                    if not file_ids:
                        return []
                    rows = session.query(FileMetadata).filter(FileMetadata.id.in_(file_ids)).all()
                    if len(rows) == len(file_ids):
                        return rows
                cache.delete(cache_key)

        rows = (
            session.query(FileMetadata)
            .filter(
                and_(
                    FileMetadata.workspace_id == workspace_id,
                    FileMetadata.checksum_sha256 == checksum_sha256,
                )
            )
            .all()
        )

        if cache is not None:
            cache_key = _checksum_cache_key(workspace_id, checksum_sha256)
            file_ids = [row.id for row in rows]
            cache.set(
                cache_key,
                json.dumps({"file_ids": file_ids}),
                ttl_seconds=cache_ttl_seconds,
            )

        return rows
