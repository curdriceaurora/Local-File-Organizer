"""Integration tests for API files and organize routers.

Covers:
  - api/routers/files.py — GET /files, /files/info, /files/content,
    /files/{id}, POST /files/move, DELETE /files, /files/{id},
    POST /files/upload
  - api/routers/organize.py — POST /organize/scan, /organize/preview,
    /organize/execute, GET /organize/status/{job_id}, POST /organize
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.exceptions import setup_exception_handlers
from file_organizer.api.routers.files import router as files_router
from file_organizer.api.routers.organize import router as organize_router

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
def files_client(test_settings: ApiSettings) -> TestClient:
    app = FastAPI()
    app.dependency_overrides[get_settings] = lambda: test_settings
    setup_exception_handlers(app)
    app.include_router(files_router)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def organize_client(test_settings: ApiSettings) -> TestClient:
    app = FastAPI()
    app.dependency_overrides[get_settings] = lambda: test_settings
    setup_exception_handlers(app)
    app.include_router(organize_router)
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# files router — GET /files
# ---------------------------------------------------------------------------


class TestListFiles:
    def test_list_files_returns_200(self, files_client: TestClient, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("hello")
        r = files_client.get("/files", params={"path": str(tmp_path)})
        assert r.status_code == 200

    def test_list_files_response_shape(self, files_client: TestClient, tmp_path: Path) -> None:
        (tmp_path / "test.txt").write_text("x")
        r = files_client.get("/files", params={"path": str(tmp_path)})
        body = r.json()
        assert "items" in body
        assert "total" in body
        assert isinstance(body["items"], list)

    def test_list_files_nonexistent_path_returns_404(
        self, files_client: TestClient, tmp_path: Path
    ) -> None:
        r = files_client.get("/files", params={"path": str(tmp_path / "gone")})
        assert r.status_code == 404

    def test_list_files_type_filter_image(self, files_client: TestClient, tmp_path: Path) -> None:
        (tmp_path / "photo.jpg").write_bytes(b"\xff\xd8\xff")
        (tmp_path / "doc.txt").write_text("text")
        r = files_client.get("/files", params={"path": str(tmp_path), "file_type": "image"})
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) > 0
        assert all(".jpg" in item["path"] or item["path"].endswith(".jpg") for item in items)

    def test_list_files_sort_by_name(self, files_client: TestClient, tmp_path: Path) -> None:
        (tmp_path / "b.txt").write_text("x")
        (tmp_path / "a.txt").write_text("x")
        r = files_client.get("/files", params={"path": str(tmp_path), "sort_by": "name"})
        assert r.status_code == 200
        items = r.json()["items"]
        names = [i["path"].split("/")[-1] for i in items]
        assert names == sorted(names, key=str.lower)

    def test_list_files_sort_desc(self, files_client: TestClient, tmp_path: Path) -> None:
        for n in ["a.txt", "b.txt", "c.txt"]:
            (tmp_path / n).write_text("x")
        r = files_client.get(
            "/files", params={"path": str(tmp_path), "sort_by": "name", "sort_order": "desc"}
        )
        assert r.status_code == 200
        items = r.json()["items"]
        names = [i["path"].split("/")[-1] for i in items]
        assert names == sorted(names, key=str.lower, reverse=True)

    def test_list_files_pagination(self, files_client: TestClient, tmp_path: Path) -> None:
        page_dir = tmp_path / "page_dir"
        page_dir.mkdir()
        for i in range(5):
            (page_dir / f"f{i}.txt").write_text("x")
        r = files_client.get("/files", params={"path": str(page_dir), "skip": 0, "limit": 2})
        assert r.status_code == 200
        body = r.json()
        assert len(body["items"]) == 2
        assert body["total"] == 5

    def test_list_files_recursive(self, files_client: TestClient, tmp_path: Path) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "nested.txt").write_text("x")
        r = files_client.get("/files", params={"path": str(tmp_path), "recursive": "true"})
        assert r.status_code == 200
        paths = [item["path"] for item in r.json()["items"]]
        assert any("nested.txt" in p for p in paths)

    def test_list_files_sort_by_size(self, files_client: TestClient, tmp_path: Path) -> None:
        import os

        sub = tmp_path / "size_sort"
        sub.mkdir()
        (sub / "small.txt").write_text("x")
        (sub / "large.txt").write_text("x" * 1000)
        r = files_client.get(
            "/files", params={"path": str(sub), "sort_by": "size", "sort_order": "desc"}
        )
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 2
        names = [i["path"].split(os.sep)[-1] for i in items]
        assert names[0] == "large.txt"

    def test_list_files_sort_by_modified(self, files_client: TestClient, tmp_path: Path) -> None:
        import os
        import time

        sub = tmp_path / "modified_sort"
        sub.mkdir()
        old_file = sub / "old.txt"
        old_file.write_text("x")
        past = time.time() - 100
        os.utime(old_file, (past, past))
        (sub / "new.txt").write_text("x")
        r = files_client.get(
            "/files",
            params={"path": str(sub), "sort_by": "modified", "sort_order": "desc"},
        )
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 2
        names = [i["path"].split(os.sep)[-1] for i in items]
        assert names[0] == "new.txt"

    def test_list_files_sort_by_created(self, files_client: TestClient, tmp_path: Path) -> None:
        import os

        sub = tmp_path / "created_sort"
        sub.mkdir()
        (sub / "alpha.txt").write_text("x")
        (sub / "beta.txt").write_text("x")
        r = files_client.get(
            "/files",
            params={"path": str(sub), "sort_by": "created", "sort_order": "asc"},
        )
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 2
        names = [i["path"].split(os.sep)[-1] for i in items]
        assert set(names) == {"alpha.txt", "beta.txt"}


# ---------------------------------------------------------------------------
# files router — GET /files/info
# ---------------------------------------------------------------------------


class TestGetFileInfo:
    def test_file_info_returns_200(self, files_client: TestClient, tmp_path: Path) -> None:
        f = tmp_path / "info.txt"
        f.write_text("hello")
        r = files_client.get("/files/info", params={"path": str(f)})
        assert r.status_code == 200

    def test_file_info_nonexistent_returns_404(
        self, files_client: TestClient, tmp_path: Path
    ) -> None:
        r = files_client.get("/files/info", params={"path": str(tmp_path / "gone.txt")})
        assert r.status_code == 404

    def test_file_info_directory_returns_400(
        self, files_client: TestClient, tmp_path: Path
    ) -> None:
        r = files_client.get("/files/info", params={"path": str(tmp_path)})
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# files router — GET /files/content
# ---------------------------------------------------------------------------


class TestGetFileContent:
    def test_file_content_returns_text(self, files_client: TestClient, tmp_path: Path) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("hello world")
        r = files_client.get("/files/content", params={"path": str(f)})
        assert r.status_code == 200
        body = r.json()
        assert "hello world" in body["content"]
        assert body["truncated"] is False

    def test_file_content_nonexistent_returns_404(
        self, files_client: TestClient, tmp_path: Path
    ) -> None:
        r = files_client.get("/files/content", params={"path": str(tmp_path / "gone.txt")})
        assert r.status_code == 404

    def test_file_content_directory_returns_400(
        self, files_client: TestClient, tmp_path: Path
    ) -> None:
        r = files_client.get("/files/content", params={"path": str(tmp_path)})
        assert r.status_code == 400

    def test_file_content_truncated_when_max_bytes_exceeded(
        self, files_client: TestClient, tmp_path: Path
    ) -> None:
        f = tmp_path / "big.txt"
        f.write_text("A" * 200)
        r = files_client.get("/files/content", params={"path": str(f), "max_bytes": 10})
        assert r.status_code == 200
        body = r.json()
        assert body["truncated"] is True
        assert len(body["content"]) == 10


# ---------------------------------------------------------------------------
# files router — POST /files/move
# ---------------------------------------------------------------------------


class TestMoveFile:
    def test_move_file_succeeds(self, files_client: TestClient, tmp_path: Path) -> None:
        src = tmp_path / "src.txt"
        src.write_text("data")
        dst = tmp_path / "dst.txt"
        r = files_client.post(
            "/files/move",
            json={"source": str(src), "destination": str(dst)},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["moved"] is True
        assert dst.exists()

    def test_move_file_dry_run(self, files_client: TestClient, tmp_path: Path) -> None:
        src = tmp_path / "src.txt"
        src.write_text("data")
        dst = tmp_path / "dst.txt"
        r = files_client.post(
            "/files/move",
            json={"source": str(src), "destination": str(dst), "dry_run": True},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["moved"] is False
        assert body["dry_run"] is True
        assert src.exists()

    def test_move_nonexistent_source_returns_404(
        self, files_client: TestClient, tmp_path: Path
    ) -> None:
        r = files_client.post(
            "/files/move",
            json={"source": str(tmp_path / "gone.txt"), "destination": str(tmp_path / "dst.txt")},
        )
        assert r.status_code == 404

    def test_move_to_existing_without_overwrite_returns_409(
        self, files_client: TestClient, tmp_path: Path
    ) -> None:
        src = tmp_path / "src.txt"
        src.write_text("a")
        dst = tmp_path / "dst.txt"
        dst.write_text("b")
        r = files_client.post(
            "/files/move",
            json={"source": str(src), "destination": str(dst), "overwrite": False},
        )
        assert r.status_code == 409


# ---------------------------------------------------------------------------
# files router — DELETE /files
# ---------------------------------------------------------------------------


class TestDeleteFile:
    def test_delete_file_soft_delete_moves_to_trash(
        self, files_client: TestClient, tmp_path: Path
    ) -> None:
        f = tmp_path / "to_delete.txt"
        f.write_text("bye")
        with patch(
            "file_organizer.api.routers.files._trash_target",
            return_value=tmp_path / "trash" / "to_delete.txt",
        ):
            (tmp_path / "trash").mkdir(exist_ok=True)
            r = files_client.request(
                "DELETE",
                "/files",
                json={"path": str(f), "permanent": False},
            )
        assert r.status_code == 200
        body = r.json()
        assert body["deleted"] is True

    def test_delete_file_permanent(self, files_client: TestClient, tmp_path: Path) -> None:
        f = tmp_path / "perm_delete.txt"
        f.write_text("gone")
        r = files_client.request("DELETE", "/files", json={"path": str(f), "permanent": True})
        assert r.status_code == 200
        assert not f.exists()

    def test_delete_file_dry_run(self, files_client: TestClient, tmp_path: Path) -> None:
        f = tmp_path / "keep.txt"
        f.write_text("safe")
        r = files_client.request("DELETE", "/files", json={"path": str(f), "dry_run": True})
        assert r.status_code == 200
        body = r.json()
        assert body["deleted"] is False
        assert f.exists()

    def test_delete_nonexistent_returns_404(self, files_client: TestClient, tmp_path: Path) -> None:
        r = files_client.request("DELETE", "/files", json={"path": str(tmp_path / "gone.txt")})
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# files router — POST /files/upload
# ---------------------------------------------------------------------------


class TestUploadFiles:
    def test_upload_single_file(self, files_client: TestClient) -> None:
        r = files_client.post(
            "/files/upload",
            files={"file": ("test.txt", b"hello content", "text/plain")},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["filename"] == "test.txt"
        assert body["size"] == len(b"hello content")

    def test_upload_no_file_returns_400(self, files_client: TestClient) -> None:
        r = files_client.post("/files/upload")
        assert r.status_code == 400

    def test_upload_returns_file_id(self, files_client: TestClient) -> None:
        r = files_client.post(
            "/files/upload",
            files={"file": ("doc.pdf", b"pdf content", "application/pdf")},
        )
        assert r.status_code == 200
        assert "file_id" in r.json()


# ---------------------------------------------------------------------------
# organize router — POST /organize/scan
# ---------------------------------------------------------------------------


class TestOrganizeScan:
    def test_scan_returns_file_counts(self, organize_client: TestClient, tmp_path: Path) -> None:
        scan_dir = tmp_path / "scan_input"
        scan_dir.mkdir()
        (scan_dir / "report.txt").write_text("content")
        (scan_dir / "photo.jpg").write_bytes(b"\xff\xd8\xff")
        r = organize_client.post(
            "/organize/scan",
            json={"input_dir": str(scan_dir)},
        )
        assert r.status_code == 200
        body = r.json()
        assert "total_files" in body
        assert body["total_files"] == 2
        assert "counts" in body

    def test_scan_nonexistent_dir_returns_404(
        self, organize_client: TestClient, tmp_path: Path
    ) -> None:
        r = organize_client.post("/organize/scan", json={"input_dir": str(tmp_path / "gone")})
        assert r.status_code == 404

    def test_scan_recursive(self, organize_client: TestClient, tmp_path: Path) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "nested.txt").write_text("x")
        r = organize_client.post(
            "/organize/scan", json={"input_dir": str(tmp_path), "recursive": True}
        )
        assert r.status_code == 200
        assert r.json()["total_files"] >= 1


# ---------------------------------------------------------------------------
# organize router — POST /organize/preview
# ---------------------------------------------------------------------------


class TestOrganizePreview:
    def test_preview_dry_run(
        self,
        organize_client: TestClient,
        stub_all_models: None,
        stub_nltk: None,
        tmp_path: Path,
    ) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "report.txt").write_text("quarterly report content")
        out = tmp_path / "out"
        out.mkdir()
        r = organize_client.post(
            "/organize/preview",
            json={"input_dir": str(src), "output_dir": str(out)},
        )
        assert r.status_code == 200
        body = r.json()
        assert "total_files" in body
        assert "processed_files" in body

    def test_preview_nonexistent_input_returns_404(
        self, organize_client: TestClient, tmp_path: Path
    ) -> None:
        r = organize_client.post(
            "/organize/preview",
            json={"input_dir": str(tmp_path / "gone"), "output_dir": str(tmp_path)},
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# organize router — POST /organize/execute
# ---------------------------------------------------------------------------


class TestOrganizeExecute:
    def test_execute_background_returns_job_id(
        self, organize_client: TestClient, tmp_path: Path
    ) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "doc.txt").write_text("x")
        out = tmp_path / "out"
        out.mkdir()
        r = organize_client.post(
            "/organize/execute",
            json={"input_dir": str(src), "output_dir": str(out), "run_in_background": True},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "queued"
        assert "job_id" in body

    def test_execute_nonexistent_input_returns_404(
        self, organize_client: TestClient, tmp_path: Path
    ) -> None:
        r = organize_client.post(
            "/organize/execute",
            json={"input_dir": str(tmp_path / "gone"), "output_dir": str(tmp_path)},
        )
        assert r.status_code == 404

    def test_execute_sync_returns_result(
        self,
        organize_client: TestClient,
        stub_all_models: None,
        stub_nltk: None,
        tmp_path: Path,
    ) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "notes.txt").write_text("quarterly report content")
        out = tmp_path / "out"
        out.mkdir()
        r = organize_client.post(
            "/organize/execute",
            json={
                "input_dir": str(src),
                "output_dir": str(out),
                "run_in_background": False,
                "dry_run": True,
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["status"] in ("completed", "failed")


# ---------------------------------------------------------------------------
# organize router — GET /organize/status/{job_id}
# ---------------------------------------------------------------------------


class TestOrganizeJobStatus:
    def test_job_status_not_found_returns_404(self, organize_client: TestClient) -> None:
        r = organize_client.get("/organize/status/nonexistent-job-id")
        assert r.status_code == 404

    def test_job_status_after_background_submit(
        self, organize_client: TestClient, tmp_path: Path
    ) -> None:
        src = tmp_path / "src"
        src.mkdir()
        (src / "doc.txt").write_text("x")
        out = tmp_path / "out"
        out.mkdir()
        submit = organize_client.post(
            "/organize/execute",
            json={"input_dir": str(src), "output_dir": str(out), "run_in_background": True},
        )
        job_id = submit.json()["job_id"]
        r = organize_client.get(f"/organize/status/{job_id}")
        assert r.status_code == 200
        body = r.json()
        assert body["job_id"] == job_id
        assert "status" in body


# ---------------------------------------------------------------------------
# organize router — POST /organize (simple)
# ---------------------------------------------------------------------------


class TestSimpleOrganize:
    def test_organize_txt_file_returns_documents_folder(self, organize_client: TestClient) -> None:
        r = organize_client.post(
            "/organize",
            files={"file": ("quarterly_report.txt", b"content", "text/plain")},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["folder_name"] == "Documents"

    def test_organize_jpg_returns_images_folder(self, organize_client: TestClient) -> None:
        r = organize_client.post(
            "/organize",
            files={"file": ("vacation.jpg", b"\xff\xd8\xff", "image/jpeg")},
        )
        assert r.status_code == 200
        assert r.json()["folder_name"] == "Images"

    def test_organize_mp4_returns_videos_folder(self, organize_client: TestClient) -> None:
        r = organize_client.post(
            "/organize",
            files={"file": ("movie.mp4", b"content", "video/mp4")},
        )
        assert r.status_code == 200
        assert r.json()["folder_name"] == "Videos"

    def test_organize_mp3_returns_audio_folder(self, organize_client: TestClient) -> None:
        r = organize_client.post(
            "/organize",
            files={"file": ("song.mp3", b"content", "audio/mpeg")},
        )
        assert r.status_code == 200
        assert r.json()["folder_name"] == "Audio"

    def test_organize_unknown_ext_returns_other_folder(self, organize_client: TestClient) -> None:
        r = organize_client.post(
            "/organize",
            files={"file": ("data.xyz", b"content", "application/octet-stream")},
        )
        assert r.status_code == 200
        assert r.json()["folder_name"] == "Other"

    def test_organize_no_file_no_body_returns_400(self, organize_client: TestClient) -> None:
        r = organize_client.post("/organize")
        assert r.status_code in (400, 422)

    def test_organize_returns_confidence_score(self, organize_client: TestClient) -> None:
        r = organize_client.post(
            "/organize",
            files={"file": ("report.pdf", b"content", "application/pdf")},
        )
        assert r.status_code == 200
        body = r.json()
        assert "confidence" in body
        assert 0.0 <= body["confidence"] <= 1.0
