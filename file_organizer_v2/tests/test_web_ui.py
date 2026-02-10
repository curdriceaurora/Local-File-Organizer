"""Tests for the web UI routing and template rendering."""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Optional

from fastapi.testclient import TestClient

from file_organizer.api.main import create_app
from file_organizer.api.test_utils import build_test_settings

_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8"
    "/w8AAn8B9p4n9QAAAABJRU5ErkJggg=="
)


def _build_client(tmp_path: Path, allowed_root: Optional[Path] = None) -> TestClient:
    allowed_paths = [str(allowed_root)] if allowed_root else []
    settings = build_test_settings(
        tmp_path,
        allowed_paths=allowed_paths,
        auth_overrides={"auth_enabled": False},
    )
    app = create_app(settings)
    return TestClient(app)


def test_ui_routes_render(tmp_path: Path) -> None:
    client = _build_client(tmp_path)
    response = client.get("/ui/")
    assert response.status_code == 200
    assert "hx-boost" in response.text

    for path in ("/ui/files", "/ui/organize", "/ui/settings", "/ui/profile"):
        page = client.get(path)
        assert page.status_code == 200


def test_ui_static_assets(tmp_path: Path) -> None:
    client = _build_client(tmp_path)
    css = client.get("/static/css/styles.css")
    assert css.status_code == 200
    htmx = client.get("/static/js/htmx.min.js")
    assert htmx.status_code == 200


def test_file_browser_endpoints(tmp_path: Path) -> None:
    root = tmp_path / "library"
    root.mkdir()
    (root / "Photos").mkdir()
    (root / "note.txt").write_text("hello", encoding="utf-8")
    (root / "preview.png").write_bytes(_PNG_BYTES)
    (root / "report.pdf").write_bytes(b"%PDF-1.4\n%")

    client = _build_client(tmp_path, allowed_root=root)

    tree = client.get("/ui/files/tree")
    assert tree.status_code == 200
    assert root.name in tree.text

    listing = client.get("/ui/files/list", params={"path": str(root)})
    assert listing.status_code == 200
    assert "note.txt" in listing.text

    page = client.get("/ui/files", params={"path": str(root)})
    assert page.status_code == 200
    assert "data-file-browser" in page.text

    thumb = client.get(
        "/ui/files/thumbnail",
        params={"path": str(root / "preview.png"), "kind": "image"},
    )
    assert thumb.status_code == 200

    preview = client.get("/ui/files/preview", params={"path": str(root / "note.txt")})
    assert preview.status_code == 200
    assert "note.txt" in preview.text

    upload = client.post(
        "/ui/files/upload",
        data={"path": str(root)},
        files={"files": ("upload.txt", b"data")},
    )
    assert upload.status_code == 200
    assert (root / "upload.txt").exists()


def test_upload_rejects_hidden_files(tmp_path: Path) -> None:
    root = tmp_path / "library"
    root.mkdir()

    client = _build_client(tmp_path, allowed_root=root)
    response = client.post(
        "/ui/files/upload",
        data={"path": str(root)},
        files={"files": (".secret", b"data")},
    )
    assert response.status_code == 200
    assert "hidden files are not allowed" in response.text.lower()
    assert not (root / ".secret").exists()
