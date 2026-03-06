"""Tests for the dedupe API router."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_current_active_user, get_settings
from file_organizer.api.exceptions import setup_exception_handlers
from file_organizer.api.routers.dedupe import router


def _build_app(tmp_path: Path) -> tuple[FastAPI, TestClient, ApiSettings]:
    """Create a minimal FastAPI app with the dedupe router."""
    settings = ApiSettings(
        environment="test",
        auth_enabled=False,
        allowed_paths=[str(tmp_path)],
        auth_jwt_secret="test-secret",
        rate_limit_enabled=False,
    )
    app = FastAPI()
    setup_exception_handlers(app)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_current_active_user] = lambda: MagicMock(
        is_active=True, is_admin=True
    )
    app.include_router(router, prefix="/api/v1")
    client = TestClient(app)
    return app, client, settings


def _make_mock_index(groups: dict | None = None, stats: dict | None = None):
    """Create a mock DuplicateIndex with given groups and stats."""
    from file_organizer.services.deduplication.index import (
        DuplicateGroup,
        FileMetadata,
    )

    mock_index = MagicMock()

    if groups is None:
        # Default: one group with 2 duplicate files
        now = datetime(2025, 1, 1, tzinfo=UTC)
        fm1 = FileMetadata(
            path=Path("/tmp/a.txt"),
            size=100,
            modified_time=now,
            accessed_time=now,
            hash_value="abc123",
        )
        fm2 = FileMetadata(
            path=Path("/tmp/b.txt"),
            size=100,
            modified_time=now,
            accessed_time=now,
            hash_value="abc123",
        )
        group = DuplicateGroup(hash_value="abc123", files=[fm1, fm2])
        groups = {"abc123": group}

    mock_index.get_duplicates.return_value = groups
    mock_index.get_statistics.return_value = stats or {
        "total_files": 10,
        "unique_files": 9,
        "duplicate_groups": 1,
    }
    return mock_index


# ---------------------------------------------------------------------------
# scan_duplicates endpoint
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestScanDuplicates:
    """Tests for POST /api/v1/dedupe/scan."""

    @patch("file_organizer.api.routers.dedupe.DuplicateDetector")
    def test_scan_success(self, mock_detector_cls, tmp_path: Path) -> None:
        scan_dir = tmp_path / "data"
        scan_dir.mkdir()
        mock_instance = MagicMock()
        mock_instance.scan_directory.return_value = _make_mock_index()
        mock_detector_cls.return_value = mock_instance
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/dedupe/scan",
            json={"path": str(scan_dir)},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["duplicates"]) == 1
        assert body["duplicates"][0]["hash_value"] == "abc123"
        assert len(body["duplicates"][0]["files"]) == 2
        assert "stats" in body

    def test_scan_path_not_found(self, tmp_path: Path) -> None:
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/dedupe/scan",
            json={"path": str(tmp_path / "missing")},
        )
        assert resp.status_code == 404

    def test_scan_path_is_file(self, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("not a dir")
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/dedupe/scan",
            json={"path": str(f)},
        )
        assert resp.status_code == 400

    @patch("file_organizer.api.routers.dedupe.DuplicateDetector")
    def test_scan_no_duplicates(self, mock_detector_cls, tmp_path: Path) -> None:
        scan_dir = tmp_path / "data"
        scan_dir.mkdir()
        mock_instance = MagicMock()
        mock_instance.scan_directory.return_value = _make_mock_index(groups={})
        mock_detector_cls.return_value = mock_instance
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/dedupe/scan",
            json={"path": str(scan_dir)},
        )
        assert resp.status_code == 200
        assert resp.json()["duplicates"] == []

    @patch("file_organizer.api.routers.dedupe.DuplicateDetector")
    def test_scan_with_options(self, mock_detector_cls, tmp_path: Path) -> None:
        scan_dir = tmp_path / "data"
        scan_dir.mkdir()
        mock_instance = MagicMock()
        mock_instance.scan_directory.return_value = _make_mock_index()
        mock_detector_cls.return_value = mock_instance
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/dedupe/scan",
            json={
                "path": str(scan_dir),
                "algorithm": "md5",
                "recursive": False,
                "min_file_size": 100,
                "max_file_size": 10000,
                "include_patterns": ["*.txt"],
                "exclude_patterns": ["*.log"],
            },
        )
        assert resp.status_code == 200
        # Verify the options were passed through
        call_args = mock_instance.scan_directory.call_args
        options = call_args[0][1]
        assert options.algorithm == "md5"
        assert options.recursive is False
        assert options.min_file_size == 100


# ---------------------------------------------------------------------------
# preview_duplicates endpoint
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPreviewDuplicates:
    """Tests for POST /api/v1/dedupe/preview."""

    @patch("file_organizer.api.routers.dedupe.DuplicateDetector")
    def test_preview_success(self, mock_detector_cls, tmp_path: Path) -> None:
        scan_dir = tmp_path / "data"
        scan_dir.mkdir()
        mock_instance = MagicMock()
        mock_instance.scan_directory.return_value = _make_mock_index()
        mock_detector_cls.return_value = mock_instance
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/dedupe/preview",
            json={"path": str(scan_dir)},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["preview"]) == 1
        preview_group = body["preview"][0]
        assert preview_group["hash_value"] == "abc123"
        assert preview_group["keep"] is not None
        assert len(preview_group["remove"]) == 1

    def test_preview_path_not_found(self, tmp_path: Path) -> None:
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/dedupe/preview",
            json={"path": str(tmp_path / "missing")},
        )
        assert resp.status_code == 404

    def test_preview_path_is_file(self, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("not a dir")
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/dedupe/preview",
            json={"path": str(f)},
        )
        assert resp.status_code == 400

    @patch("file_organizer.api.routers.dedupe.DuplicateDetector")
    def test_preview_empty_group_skipped(self, mock_detector_cls, tmp_path: Path) -> None:
        """Groups with no files should be skipped in preview."""
        from file_organizer.services.deduplication.index import DuplicateGroup

        scan_dir = tmp_path / "data"
        scan_dir.mkdir()
        empty_group = DuplicateGroup(hash_value="empty", files=[])
        mock_instance = MagicMock()
        mock_instance.scan_directory.return_value = _make_mock_index(groups={"empty": empty_group})
        mock_detector_cls.return_value = mock_instance
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/dedupe/preview",
            json={"path": str(scan_dir)},
        )
        assert resp.status_code == 200
        assert resp.json()["preview"] == []


# ---------------------------------------------------------------------------
# execute_deduplication endpoint
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExecuteDeduplication:
    """Tests for POST /api/v1/dedupe/execute."""

    @patch("file_organizer.api.routers.dedupe.DuplicateDetector")
    def test_execute_dry_run(self, mock_detector_cls, tmp_path: Path) -> None:
        scan_dir = tmp_path / "data"
        scan_dir.mkdir()
        mock_instance = MagicMock()
        mock_instance.scan_directory.return_value = _make_mock_index()
        mock_detector_cls.return_value = mock_instance
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/dedupe/execute",
            json={"path": str(scan_dir), "dry_run": True},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["dry_run"] is True
        assert len(body["removed"]) >= 1

    @patch("file_organizer.api.routers.dedupe.DuplicateDetector")
    def test_execute_permanent_delete(self, mock_detector_cls, tmp_path: Path) -> None:
        scan_dir = tmp_path / "data"
        scan_dir.mkdir()
        # Create actual duplicate files
        dup1 = scan_dir / "dup1.txt"
        dup2 = scan_dir / "dup2.txt"
        dup1.write_text("same content")
        dup2.write_text("same content")

        now = datetime(2025, 1, 1, tzinfo=UTC)
        from file_organizer.services.deduplication.index import (
            DuplicateGroup,
            FileMetadata,
        )

        fm1 = FileMetadata(
            path=dup1, size=12, modified_time=now, accessed_time=now, hash_value="h1"
        )
        fm2 = FileMetadata(
            path=dup2, size=12, modified_time=now, accessed_time=now, hash_value="h1"
        )
        group = DuplicateGroup(hash_value="h1", files=[fm1, fm2])

        mock_instance = MagicMock()
        mock_instance.scan_directory.return_value = _make_mock_index(groups={"h1": group})
        mock_detector_cls.return_value = mock_instance
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/dedupe/execute",
            json={
                "path": str(scan_dir),
                "dry_run": False,
                "trash": False,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["dry_run"] is False
        assert len(body["removed"]) == 1
        # dup2 should be deleted (it's the second in the group)
        assert not dup2.exists()
        # dup1 should still exist (it's kept)
        assert dup1.exists()

    @patch("file_organizer.api.routers.dedupe.DuplicateDetector")
    def test_execute_trash(self, mock_detector_cls, tmp_path: Path) -> None:
        scan_dir = tmp_path / "data"
        scan_dir.mkdir()
        dup1 = scan_dir / "keep.txt"
        dup2 = scan_dir / "trash.txt"
        dup1.write_text("same")
        dup2.write_text("same")

        now = datetime(2025, 1, 1, tzinfo=UTC)
        from file_organizer.services.deduplication.index import (
            DuplicateGroup,
            FileMetadata,
        )

        fm1 = FileMetadata(path=dup1, size=4, modified_time=now, accessed_time=now, hash_value="h2")
        fm2 = FileMetadata(path=dup2, size=4, modified_time=now, accessed_time=now, hash_value="h2")
        group = DuplicateGroup(hash_value="h2", files=[fm1, fm2])

        mock_instance = MagicMock()
        mock_instance.scan_directory.return_value = _make_mock_index(groups={"h2": group})
        mock_detector_cls.return_value = mock_instance
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/dedupe/execute",
            json={
                "path": str(scan_dir),
                "dry_run": False,
                "trash": True,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["dry_run"] is False
        assert len(body["removed"]) == 1
        # File should have been moved, not deleted
        assert not dup2.exists()
        assert dup1.exists()

    @patch("file_organizer.api.routers.dedupe.DuplicateDetector")
    def test_execute_trash_collision(self, mock_detector_cls, tmp_path: Path) -> None:
        """When trash already has a file with the same name, increment counter."""
        scan_dir = tmp_path / "data"
        scan_dir.mkdir()
        dup1 = scan_dir / "keep.txt"
        dup2 = scan_dir / "remove.txt"
        dup1.write_text("same")
        dup2.write_text("same")

        # Pre-create a file in trash with the same name
        trash_dir = Path.home() / ".config" / "file-organizer" / "trash"
        trash_dir.mkdir(parents=True, exist_ok=True)
        existing_trash = trash_dir / "remove.txt"
        existing_trash.write_text("already here")

        now = datetime(2025, 1, 1, tzinfo=UTC)
        from file_organizer.services.deduplication.index import (
            DuplicateGroup,
            FileMetadata,
        )

        fm1 = FileMetadata(path=dup1, size=4, modified_time=now, accessed_time=now, hash_value="h3")
        fm2 = FileMetadata(path=dup2, size=4, modified_time=now, accessed_time=now, hash_value="h3")
        group = DuplicateGroup(hash_value="h3", files=[fm1, fm2])

        mock_instance = MagicMock()
        mock_instance.scan_directory.return_value = _make_mock_index(groups={"h3": group})
        mock_detector_cls.return_value = mock_instance
        _, client, _ = _build_app(tmp_path)

        try:
            resp = client.post(
                "/api/v1/dedupe/execute",
                json={
                    "path": str(scan_dir),
                    "dry_run": False,
                    "trash": True,
                },
            )
            assert resp.status_code == 200
            body = resp.json()
            assert len(body["removed"]) == 1
            # Should have been renamed to remove-1.txt in trash
            assert "remove" in body["removed"][0]
        finally:
            existing_trash.unlink(missing_ok=True)
            # Clean up any numbered files
            for f in trash_dir.glob("remove*"):
                f.unlink(missing_ok=True)

    @patch("file_organizer.api.routers.dedupe.DuplicateDetector")
    def test_execute_nonexistent_file_skipped(self, mock_detector_cls, tmp_path: Path) -> None:
        """Files that don't exist at execution time are silently skipped."""
        scan_dir = tmp_path / "data"
        scan_dir.mkdir()
        keep = scan_dir / "keep.txt"
        keep.write_text("content")
        # Ghost file is in the index but doesn't exist on disk
        ghost = scan_dir / "ghost.txt"

        now = datetime(2025, 1, 1, tzinfo=UTC)
        from file_organizer.services.deduplication.index import (
            DuplicateGroup,
            FileMetadata,
        )

        fm1 = FileMetadata(path=keep, size=7, modified_time=now, accessed_time=now, hash_value="h4")
        fm2 = FileMetadata(
            path=ghost, size=7, modified_time=now, accessed_time=now, hash_value="h4"
        )
        group = DuplicateGroup(hash_value="h4", files=[fm1, fm2])

        mock_instance = MagicMock()
        mock_instance.scan_directory.return_value = _make_mock_index(groups={"h4": group})
        mock_detector_cls.return_value = mock_instance
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/dedupe/execute",
            json={
                "path": str(scan_dir),
                "dry_run": False,
                "trash": False,
            },
        )
        assert resp.status_code == 200
        # Ghost file is not on disk, so nothing removed
        assert len(resp.json()["removed"]) == 0

    def test_execute_path_not_found(self, tmp_path: Path) -> None:
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/dedupe/execute",
            json={"path": str(tmp_path / "missing")},
        )
        assert resp.status_code == 404

    def test_execute_path_is_file(self, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("not a dir")
        _, client, _ = _build_app(tmp_path)

        resp = client.post(
            "/api/v1/dedupe/execute",
            json={"path": str(f)},
        )
        assert resp.status_code == 400
