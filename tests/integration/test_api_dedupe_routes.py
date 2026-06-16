"""Integration tests for api/routers/dedupe.py.

Covers:
  - POST /dedupe/scan — 404 on missing path, 400 on file path, 200 on empty dir,
    duplicate detection
  - POST /dedupe/preview — 404/400 error handling, keep/remove shape
  - POST /dedupe/execute — 404/400 error handling, dry_run no-op, real deletion,
    response shape
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_current_active_user, get_settings
from file_organizer.api.exceptions import setup_exception_handlers
from file_organizer.api.models import DedupeGroup, DedupePreviewGroup
from file_organizer.api.routers.dedupe import _preview
from file_organizer.api.routers.dedupe import router as dedupe_router

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def test_settings(tmp_path: Path) -> ApiSettings:
    return ApiSettings(
        allowed_paths=[str(tmp_path)],
        auth_enabled=False,
        auth_db_path=str(tmp_path / "auth.db"),
    )


@pytest.fixture()
def dedupe_client(test_settings: ApiSettings) -> TestClient:
    app = FastAPI()
    app.dependency_overrides[get_settings] = lambda: test_settings
    app.dependency_overrides[get_current_active_user] = lambda: MagicMock(
        is_active=True,
        username="test-user",
    )
    setup_exception_handlers(app)
    app.include_router(dedupe_router)
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# POST /dedupe/scan
# ---------------------------------------------------------------------------


class TestDedupeScan:
    def test_scan_nonexistent_path_returns_404(
        self, dedupe_client: TestClient, tmp_path: Path
    ) -> None:
        missing = tmp_path / "does_not_exist"
        r = dedupe_client.post("/dedupe/scan", json={"path": str(missing)})
        assert r.status_code == 404
        body = r.json()
        assert body["error"] == "not_found"

    def test_scan_file_path_returns_400(self, dedupe_client: TestClient, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("hello")
        r = dedupe_client.post("/dedupe/scan", json={"path": str(f)})
        assert r.status_code == 400
        body = r.json()
        assert body["error"] == "invalid_path"

    def test_scan_empty_dir_returns_200(self, dedupe_client: TestClient, tmp_path: Path) -> None:
        scan_dir = tmp_path / "empty_dir"
        scan_dir.mkdir()
        r = dedupe_client.post("/dedupe/scan", json={"path": str(scan_dir)})
        assert r.status_code == 200
        body = r.json()
        assert "path" in body
        assert "duplicates" in body
        assert "stats" in body
        assert body["duplicates"] == []

    def test_scan_with_duplicate_files_finds_group(
        self, dedupe_client: TestClient, tmp_path: Path
    ) -> None:
        scan_dir = tmp_path / "with_dupes"
        scan_dir.mkdir()
        content = "identical content for dedup test"
        (scan_dir / "original.txt").write_text(content)
        (scan_dir / "copy.txt").write_text(content)

        r = dedupe_client.post("/dedupe/scan", json={"path": str(scan_dir)})
        assert r.status_code == 200
        body = r.json()
        assert len(body["duplicates"]) >= 1
        first_group = body["duplicates"][0]
        assert len(first_group["files"]) >= 2
        assert "hash_value" in first_group
        assert "wasted_space" in first_group


# ---------------------------------------------------------------------------
# POST /dedupe/preview
# ---------------------------------------------------------------------------


class TestDedupePreview:
    def test_preview_nonexistent_path_returns_404(
        self, dedupe_client: TestClient, tmp_path: Path
    ) -> None:
        missing = tmp_path / "ghost"
        r = dedupe_client.post("/dedupe/preview", json={"path": str(missing)})
        assert r.status_code == 404
        body = r.json()
        assert body["error"] == "not_found"

    def test_preview_file_path_returns_400(self, dedupe_client: TestClient, tmp_path: Path) -> None:
        f = tmp_path / "single.txt"
        f.write_text("data")
        r = dedupe_client.post("/dedupe/preview", json={"path": str(f)})
        assert r.status_code == 400
        body = r.json()
        assert body["error"] == "invalid_path"

    def test_preview_returns_keep_and_remove(
        self, dedupe_client: TestClient, tmp_path: Path
    ) -> None:
        preview_dir = tmp_path / "preview_dir"
        preview_dir.mkdir()
        content = "duplicate content abc"
        (preview_dir / "a.txt").write_text(content)
        (preview_dir / "b.txt").write_text(content)

        r = dedupe_client.post("/dedupe/preview", json={"path": str(preview_dir)})
        assert r.status_code == 200
        body = r.json()
        assert "preview" in body
        assert len(body["preview"]) >= 1
        group = body["preview"][0]
        assert "keep" in group
        assert "remove" in group
        assert isinstance(group["keep"], str)
        assert len(group["keep"]) > 0
        assert len(group["remove"]) >= 1


# ---------------------------------------------------------------------------
# POST /dedupe/execute
# ---------------------------------------------------------------------------


class TestDedupeExecute:
    def test_execute_nonexistent_path_returns_404(
        self, dedupe_client: TestClient, tmp_path: Path
    ) -> None:
        missing = tmp_path / "nowhere"
        r = dedupe_client.post(
            "/dedupe/execute",
            json={"path": str(missing), "dry_run": True, "trash": False},
        )
        assert r.status_code == 404
        body = r.json()
        assert body["error"] == "not_found"

    def test_execute_file_path_returns_400(self, dedupe_client: TestClient, tmp_path: Path) -> None:
        f = tmp_path / "notadir.txt"
        f.write_text("x")
        r = dedupe_client.post(
            "/dedupe/execute",
            json={"path": str(f), "dry_run": True, "trash": False},
        )
        assert r.status_code == 400
        body = r.json()
        assert body["error"] == "invalid_path"

    def test_execute_dry_run_does_not_delete(
        self, dedupe_client: TestClient, tmp_path: Path
    ) -> None:
        exec_dir = tmp_path / "dry_run_dir"
        exec_dir.mkdir()
        content = "dry run duplicate content"
        original = exec_dir / "orig.txt"
        duplicate = exec_dir / "dup.txt"
        original.write_text(content)
        duplicate.write_text(content)

        r = dedupe_client.post(
            "/dedupe/execute",
            json={"path": str(exec_dir), "dry_run": True, "trash": False},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["dry_run"] is True
        # Both files still exist — dry_run must not delete
        assert original.exists()
        assert duplicate.exists()

    def test_execute_removes_duplicates(self, dedupe_client: TestClient, tmp_path: Path) -> None:
        exec_dir = tmp_path / "real_delete_dir"
        exec_dir.mkdir()
        content = "content to be deduplicated for real"
        original = exec_dir / "keep.txt"
        duplicate = exec_dir / "remove_me.txt"
        original.write_text(content)
        duplicate.write_text(content)

        r = dedupe_client.post(
            "/dedupe/execute",
            json={"path": str(exec_dir), "dry_run": False, "trash": False},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["dry_run"] is False
        assert len(body["removed"]) == 1
        removed_path = Path(body["removed"][0])
        assert removed_path == duplicate
        assert not duplicate.exists()
        assert original.exists()
        assert len(list(exec_dir.iterdir())) == 1

    def test_execute_response_shape(self, dedupe_client: TestClient, tmp_path: Path) -> None:
        shape_dir = tmp_path / "shape_dir"
        shape_dir.mkdir()

        r = dedupe_client.post(
            "/dedupe/execute",
            json={"path": str(shape_dir), "dry_run": True, "trash": False},
        )
        assert r.status_code == 200
        body = r.json()
        assert "path" in body
        assert "removed" in body
        assert "dry_run" in body
        assert "stats" in body
        assert isinstance(body["removed"], list)

    def test_execute_trash_moves_duplicate_into_trash_dir(
        self, dedupe_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The handler calls `get_data_dir() / "trash"` from path_manager at
        # runtime; pin the data dir under tmp_path so the trash stays isolated.
        data_dir = tmp_path / "data"
        monkeypatch.setattr(
            "file_organizer.config.path_manager.get_data_dir",
            lambda: data_dir,
        )
        trash_dir = data_dir / "trash"

        exec_dir = tmp_path / "trash_dir_run"
        exec_dir.mkdir()
        content = "content moved to trash on dedupe"
        original = exec_dir / "keep.txt"
        duplicate = exec_dir / "remove_me.txt"
        original.write_text(content)
        duplicate.write_text(content)

        r = dedupe_client.post(
            "/dedupe/execute",
            json={"path": str(exec_dir), "dry_run": False, "trash": True},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["dry_run"] is False
        assert len(body["removed"]) == 1

        removed_path = Path(body["removed"][0])
        # The removed entry points into the trash dir, not the source dir.
        assert removed_path.parent == trash_dir
        assert removed_path.exists()
        # The original duplicate is gone from the source location.
        assert not duplicate.exists()
        # The kept copy stays put.
        assert original.exists()

    def test_execute_trash_rename_on_name_collision(
        self, dedupe_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Pin the trash dir and pre-seed it with a file whose name collides with
        # the duplicate about to be removed, forcing the `while destination.exists()`
        # rename loop to assign a `-1` suffix.
        data_dir = tmp_path / "data"
        monkeypatch.setattr(
            "file_organizer.config.path_manager.get_data_dir",
            lambda: data_dir,
        )
        trash_dir = data_dir / "trash"
        trash_dir.mkdir(parents=True, exist_ok=True)
        # Pre-existing trash entry colliding with the duplicate's name.
        (trash_dir / "remove_me.txt").write_text("a pre-existing unrelated trash file")

        exec_dir = tmp_path / "collision_run"
        exec_dir.mkdir()
        content = "collision content for dedupe trash rename"
        original = exec_dir / "keep.txt"
        duplicate = exec_dir / "remove_me.txt"
        original.write_text(content)
        duplicate.write_text(content)

        r = dedupe_client.post(
            "/dedupe/execute",
            json={"path": str(exec_dir), "dry_run": False, "trash": True},
        )
        assert r.status_code == 200
        body = r.json()
        assert len(body["removed"]) == 1

        removed_path = Path(body["removed"][0])
        # Collision avoided: the moved file got the `-1` suffix variant.
        assert removed_path == trash_dir / "remove_me-1.txt"
        assert removed_path.exists()
        # The pre-existing trash file was left untouched.
        assert (trash_dir / "remove_me.txt").read_text() == ("a pre-existing unrelated trash file")
        assert not duplicate.exists()

    def test_execute_skips_group_when_keep_missing(
        self, dedupe_client: TestClient, tmp_path: Path
    ) -> None:
        # Exercise the TOCTOU guard at the top of the removal loop: if the file
        # chosen to keep has vanished between scan and execute, the whole group
        # is skipped (`continue`). We inject a stale preview whose `keep` path
        # does not exist so the guard fires without racing the real filesystem.
        exec_dir = tmp_path / "keep_missing_dir"
        exec_dir.mkdir()
        missing_keep = exec_dir / "ghost_keep.txt"  # never created
        missing_remove = exec_dir / "ghost_remove.txt"  # never created
        stale = [
            DedupePreviewGroup(
                hash_value="deadbeef",
                keep=str(missing_keep),
                remove=[str(missing_remove)],
            )
        ]
        with patch("file_organizer.api.routers.dedupe._preview", return_value=stale):
            r = dedupe_client.post(
                "/dedupe/execute",
                json={"path": str(exec_dir), "dry_run": False, "trash": False},
            )
        assert r.status_code == 200
        body = r.json()
        # Group skipped entirely: nothing removed.
        assert body["removed"] == []

    def test_execute_skips_remove_target_when_missing(
        self, dedupe_client: TestClient, tmp_path: Path
    ) -> None:
        # Exercise the inner TOCTOU guard: the kept file exists, but a file
        # listed for removal has vanished, so that single entry is skipped
        # (`continue`) while the rest of the group proceeds.
        exec_dir = tmp_path / "remove_missing_dir"
        exec_dir.mkdir()
        keep_file = exec_dir / "real_keep.txt"
        keep_file.write_text("real keep content")
        missing_remove = exec_dir / "ghost_remove.txt"  # never created
        stale = [
            DedupePreviewGroup(
                hash_value="cafef00d",
                keep=str(keep_file),
                remove=[str(missing_remove)],
            )
        ]
        with patch("file_organizer.api.routers.dedupe._preview", return_value=stale):
            r = dedupe_client.post(
                "/dedupe/execute",
                json={"path": str(exec_dir), "dry_run": False, "trash": False},
            )
        assert r.status_code == 200
        body = r.json()
        # The missing remove target is skipped; nothing was deleted.
        assert body["removed"] == []
        assert keep_file.exists()


class TestPreviewHelper:
    def test_preview_skips_group_with_no_files(self) -> None:
        # _preview must drop a group that has no files (defensive `continue`),
        # so an empty group contributes nothing to the preview output.
        empty_group = DedupeGroup(
            hash_value="emptyhash",
            files=[],
            total_size=0,
            wasted_space=0,
        )
        result = _preview([empty_group])
        assert result == []
