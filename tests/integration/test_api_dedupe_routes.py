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
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_current_active_user, get_settings
from file_organizer.api.exceptions import setup_exception_handlers
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
