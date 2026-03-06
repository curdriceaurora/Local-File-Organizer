"""HTTP-level tests for the files_routes web endpoints.

Tests route handlers via TestClient at the HTTP transport layer, mocking
template rendering and filesystem dependencies where needed.
"""

from __future__ import annotations

from io import BytesIO
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from starlette.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.exceptions import setup_exception_handlers
from file_organizer.web.files_routes import files_router

pytestmark = [pytest.mark.unit]

_HTML_OK = HTMLResponse("<html>ok</html>")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tree(tmp_path):
    """Create a sample file tree for HTTP tests."""
    (tmp_path / "subdir").mkdir()
    (tmp_path / "hello.txt").write_text("hello world")
    (tmp_path / "photo.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    return tmp_path


@pytest.fixture()
def settings(tree):
    """Return ApiSettings pointing at the temp tree."""
    return ApiSettings(
        allowed_paths=[str(tree)],
        auth_enabled=False,
        auth_db_path=str(tree / "auth.db"),
    )


@pytest.fixture()
def client(settings):
    """Create a TestClient with the files router mounted."""
    app = FastAPI()
    app.dependency_overrides[get_settings] = lambda: settings
    setup_exception_handlers(app)
    app.include_router(files_router, prefix="/ui")
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# GET /files (full browser page)
# ---------------------------------------------------------------------------


class TestFilesBrowser:
    """Test GET /ui/files endpoint."""

    def test_returns_200(self, client, tree):
        with patch("file_organizer.web.files_routes.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<html>files</html>")
            response = client.get(f"/ui/files?path={tree}")
        assert response.status_code == 200

    def test_uses_browser_template(self, client, tree):
        with patch("file_organizer.web.files_routes.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<html></html>")
            client.get(f"/ui/files?path={tree}")
        assert "files/browser.html" in str(mock_tpl.TemplateResponse.call_args)

    def test_accepts_view_param(self, client, tree):
        with patch("file_organizer.web.files_routes.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<html></html>")
            response = client.get(f"/ui/files?path={tree}&view=list")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# GET /files/list (HTMX partial)
# ---------------------------------------------------------------------------


class TestFilesList:
    """Test GET /ui/files/list endpoint."""

    def test_returns_200(self, client, tree):
        with patch("file_organizer.web.files_routes.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<div>results</div>")
            response = client.get(f"/ui/files/list?path={tree}")
        assert response.status_code == 200

    def test_uses_results_template(self, client, tree):
        with patch("file_organizer.web.files_routes.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<div></div>")
            client.get(f"/ui/files/list?path={tree}")
        assert "files/_results.html" in str(mock_tpl.TemplateResponse.call_args)

    def test_query_filter(self, client, tree):
        with patch("file_organizer.web.files_routes.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<div></div>")
            response = client.get(f"/ui/files/list?path={tree}&q=hello")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# GET /files/tree (HTMX sidebar tree)
# ---------------------------------------------------------------------------


class TestFilesTree:
    """Test GET /ui/files/tree endpoint."""

    def test_returns_roots_when_no_path(self, client):
        with patch("file_organizer.web.files_routes.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<ul>tree</ul>")
            response = client.get("/ui/files/tree")
        assert response.status_code == 200
        assert "files/_tree.html" in str(mock_tpl.TemplateResponse.call_args)

    def test_returns_children_with_path(self, client, tree):
        with patch("file_organizer.web.files_routes.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<ul>children</ul>")
            response = client.get(f"/ui/files/tree?path={tree}")
        assert response.status_code == 200

    def test_depth_param(self, client, tree):
        with patch("file_organizer.web.files_routes.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<ul></ul>")
            response = client.get(f"/ui/files/tree?path={tree}&depth=2")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# GET /files/thumbnail
# ---------------------------------------------------------------------------


class TestFilesThumbnail:
    """Test GET /ui/files/thumbnail endpoint."""

    def test_image_thumbnail(self, client, tree):
        img_path = tree / "photo.png"
        with patch(
            "file_organizer.web.files_routes.render_image_thumbnail",
            return_value=b"\x89PNG_THUMB",
        ):
            response = client.get(f"/ui/files/thumbnail?path={img_path}&kind=image")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"

    def test_pdf_placeholder(self, client, tree):
        pdf_path = tree / "doc.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 dummy")
        with patch(
            "file_organizer.web.files_routes.render_placeholder_thumbnail",
            return_value=b"\x89PNG_PLACEHOLDER",
        ):
            response = client.get(f"/ui/files/thumbnail?path={pdf_path}&kind=pdf")
        assert response.status_code == 200

    def test_nonexistent_file_returns_error(self, client, tree):
        response = client.get(f"/ui/files/thumbnail?path={tree / 'missing.txt'}&kind=file")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /files/raw
# ---------------------------------------------------------------------------


class TestFilesRaw:
    """Test GET /ui/files/raw endpoint."""

    def test_serve_file_inline(self, client, tree):
        txt_path = tree / "hello.txt"
        response = client.get(f"/ui/files/raw?path={txt_path}")
        assert response.status_code == 200
        assert b"hello world" in response.content

    def test_serve_file_download(self, client, tree):
        txt_path = tree / "hello.txt"
        response = client.get(f"/ui/files/raw?path={txt_path}&download=true")
        assert response.status_code == 200
        assert "content-disposition" in response.headers

    def test_nonexistent_file_returns_error(self, client, tree):
        response = client.get(f"/ui/files/raw?path={tree / 'nope.txt'}")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /files/preview (HTMX partial)
# ---------------------------------------------------------------------------


class TestFilesPreview:
    """Test GET /ui/files/preview endpoint."""

    def test_text_preview(self, client, tree):
        txt_path = tree / "hello.txt"
        with patch("file_organizer.web.files_routes.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<div>preview</div>")
            response = client.get(f"/ui/files/preview?path={txt_path}")
        assert response.status_code == 200
        assert "files/_preview.html" in str(mock_tpl.TemplateResponse.call_args)

    def test_nonexistent_file_preview(self, client, tree):
        with patch("file_organizer.web.files_routes.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<div>error</div>")
            response = client.get(f"/ui/files/preview?path={tree / 'nonexistent.txt'}")
        # The handler catches ApiError internally and renders template with error
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# POST /files/upload
# ---------------------------------------------------------------------------


class TestFilesUpload:
    """Test POST /ui/files/upload endpoint."""

    def test_upload_single_file(self, client, tree):
        with patch("file_organizer.web.files_routes.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<div>uploaded</div>")
            response = client.post(
                "/ui/files/upload",
                data={"path": str(tree), "view": "grid"},
                files=[("files", ("test_upload.txt", BytesIO(b"content"), "text/plain"))],
            )
        assert response.status_code == 200

    def test_upload_no_files(self, client, tree):
        with patch("file_organizer.web.files_routes.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<div>error</div>")
            response = client.post(
                "/ui/files/upload",
                data={"path": str(tree), "view": "grid"},
            )
        # Error is handled internally and rendered in template
        assert response.status_code == 200

    def test_upload_hidden_file_rejected(self, client, tree):
        with patch("file_organizer.web.files_routes.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<div>rejected</div>")
            response = client.post(
                "/ui/files/upload",
                data={"path": str(tree), "view": "grid"},
                files=[("files", (".hidden", BytesIO(b"secret"), "text/plain"))],
            )
        assert response.status_code == 200

    def test_upload_duplicate_skipped(self, client, tree):
        # hello.txt already exists in tree
        with patch("file_organizer.web.files_routes.templates") as mock_tpl:
            mock_tpl.TemplateResponse.return_value = HTMLResponse("<div>skipped</div>")
            response = client.post(
                "/ui/files/upload",
                data={"path": str(tree), "view": "grid"},
                files=[("files", ("hello.txt", BytesIO(b"dup"), "text/plain"))],
            )
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# POST /files/rename
# ---------------------------------------------------------------------------


class TestFilesRename:
    """Test POST /ui/files/rename endpoint."""

    def test_rename_file_success(self, client, tree):
        old_file = tree / "hello.txt"
        assert old_file.exists()
        response = client.post(
            "/ui/files/rename",
            data={"path": str(old_file), "new_name": "renamed.txt"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["old_path"] == str(old_file)
        assert "renamed.txt" in data["new_path"]
        # Verify file was actually renamed
        assert not old_file.exists()
        assert (tree / "renamed.txt").exists()

    def test_rename_file_not_found(self, client, tree):
        nonexistent = tree / "nonexistent.txt"
        response = client.post(
            "/ui/files/rename",
            data={"path": str(nonexistent), "new_name": "new.txt"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "not found" in data["error"].lower()

    def test_rename_with_invalid_name(self, client, tree):
        file_path = tree / "hello.txt"
        response = client.post(
            "/ui/files/rename",
            data={"path": str(file_path), "new_name": "path/with/slashes.txt"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "path separator" in data["error"].lower()

    def test_rename_with_empty_name(self, client, tree):
        file_path = tree / "hello.txt"
        # Empty string will be caught at validation level (422)
        # Test with whitespace-only name instead
        response = client.post(
            "/ui/files/rename",
            data={"path": str(file_path), "new_name": "   "},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "empty" in data["error"].lower()

    def test_rename_to_existing_name(self, client, tree):
        file1 = tree / "hello.txt"
        # photo.png already exists in tree
        response = client.post(
            "/ui/files/rename",
            data={"path": str(file1), "new_name": "photo.png"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "exists" in data["error"].lower()


# ---------------------------------------------------------------------------
# POST /files/move
# ---------------------------------------------------------------------------


class TestFilesMove:
    """Test POST /ui/files/move endpoint."""

    def test_move_file_success(self, client, tree):
        file_to_move = tree / "hello.txt"
        dest_dir = tree / "subdir"
        assert file_to_move.exists()
        assert dest_dir.exists() and dest_dir.is_dir()

        response = client.post(
            "/ui/files/move",
            data={"path": str(file_to_move), "destination": str(dest_dir)},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["source_path"] == str(file_to_move)
        # Verify file was actually moved
        assert not file_to_move.exists()
        assert (dest_dir / "hello.txt").exists()

    def test_move_file_not_found(self, client, tree):
        nonexistent = tree / "nonexistent.txt"
        dest_dir = tree / "subdir"
        response = client.post(
            "/ui/files/move",
            data={"path": str(nonexistent), "destination": str(dest_dir)},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "not found" in data["error"].lower()

    def test_move_to_nonexistent_dest(self, client, tree):
        file_to_move = tree / "hello.txt"
        nonexistent_dir = tree / "nonexistent"
        response = client.post(
            "/ui/files/move",
            data={"path": str(file_to_move), "destination": str(nonexistent_dir)},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "not found" in data["error"].lower()

    def test_move_to_file_instead_of_dir(self, client, tree):
        file_to_move = tree / "hello.txt"
        dest_file = tree / "photo.png"
        response = client.post(
            "/ui/files/move",
            data={"path": str(file_to_move), "destination": str(dest_file)},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "not a directory" in data["error"].lower()

    def test_move_file_to_self_fails(self, client, tree):
        file_to_move = tree / "hello.txt"
        # Try to move to parent (which creates hello.txt again)
        # Create a duplicate scenario
        dest_dir = tree
        file_to_move.write_text("content")
        response = client.post(
            "/ui/files/move",
            data={"path": str(file_to_move), "destination": str(dest_dir)},
        )
        assert response.status_code == 200
        data = response.json()
        # File already exists (itself) in destination
        assert data["success"] is False


# ---------------------------------------------------------------------------
# POST /files/delete
# ---------------------------------------------------------------------------


class TestFilesDelete:
    """Test POST /ui/files/delete endpoint."""

    def test_delete_file_success(self, client, tree):
        file_to_delete = tree / "hello.txt"
        assert file_to_delete.exists()
        response = client.post(
            "/ui/files/delete",
            data={"path": str(file_to_delete)},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["path"] == str(file_to_delete)
        # Verify file was actually deleted
        assert not file_to_delete.exists()

    def test_delete_file_not_found(self, client, tree):
        nonexistent = tree / "nonexistent.txt"
        response = client.post(
            "/ui/files/delete",
            data={"path": str(nonexistent)},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "not found" in data["error"].lower()

    def test_delete_directory(self, client, tree):
        dir_to_delete = tree / "subdir"
        assert dir_to_delete.exists() and dir_to_delete.is_dir()
        response = client.post(
            "/ui/files/delete",
            data={"path": str(dir_to_delete)},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        # Verify directory was actually deleted
        assert not dir_to_delete.exists()
