"""Tests for the files browsing routes (/ui/files/*)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from file_organizer.api.main import create_app
from file_organizer.api.test_utils import build_test_settings


def _build_client(tmp_path: Path, allowed_paths: list[str] | None = None) -> TestClient:
    """Create a test client with files route access."""
    if allowed_paths is None:
        allowed_paths = [str(tmp_path)]
    settings = build_test_settings(tmp_path, allowed_paths=allowed_paths)
    app = create_app(settings)
    return TestClient(app)


@pytest.mark.unit
class TestFilesBrowse:
    """Tests for file browser page (/ui/files)."""

    def test_files_page_returns_200(self, tmp_path: Path) -> None:
        """Files page should return 200 status."""
        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        response = client.get("/ui/files")
        assert response.status_code == 200

    def test_files_page_returns_html(self, tmp_path: Path) -> None:
        """Files page should return HTML."""
        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        response = client.get("/ui/files")
        assert "text/html" in response.headers.get("content-type", "")

    def test_files_page_with_empty_directory(self, tmp_path: Path) -> None:
        """Files page should handle empty directories."""
        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        response = client.get("/ui/files")
        assert response.status_code == 200

    def test_files_page_with_test_files(self, tmp_path: Path) -> None:
        """Files page should list files in directory."""
        # Create some test files
        (tmp_path / "file1.txt").write_text("test")
        (tmp_path / "file2.pdf").write_text("test")

        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        response = client.get("/ui/files")
        assert response.status_code == 200


@pytest.mark.unit
class TestFilesSorting:
    """Tests for file sorting endpoints."""

    def test_files_sort_by_name(self, tmp_path: Path) -> None:
        """Should handle sort by name parameter."""
        (tmp_path / "b.txt").write_text("test")
        (tmp_path / "a.txt").write_text("test")

        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        response = client.get("/ui/files?sort_by=name")
        assert response.status_code == 200

    def test_files_sort_by_size(self, tmp_path: Path) -> None:
        """Should handle sort by size parameter."""
        (tmp_path / "large.txt").write_text("x" * 1000)
        (tmp_path / "small.txt").write_text("x")

        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        response = client.get("/ui/files?sort_by=size")
        assert response.status_code == 200

    def test_files_sort_by_modified(self, tmp_path: Path) -> None:
        """Should handle sort by modified time parameter."""
        (tmp_path / "file.txt").write_text("test")

        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        response = client.get("/ui/files?sort_by=modified")
        assert response.status_code == 200

    def test_files_sort_by_created(self, tmp_path: Path) -> None:
        """Should handle sort by created time parameter."""
        (tmp_path / "file.txt").write_text("test")

        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        response = client.get("/ui/files?sort_by=created")
        assert response.status_code == 200

    def test_files_sort_by_type(self, tmp_path: Path) -> None:
        """Should handle sort by type parameter."""
        (tmp_path / "file.txt").write_text("test")
        (tmp_path / "file.pdf").write_text("test")

        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        response = client.get("/ui/files?sort_by=type")
        assert response.status_code == 200

    def test_files_sort_descending(self, tmp_path: Path) -> None:
        """Should handle descending sort order via sort_order parameter."""
        (tmp_path / "a.txt").write_text("test")
        (tmp_path / "b.txt").write_text("test")

        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        response = client.get("/ui/files?sort_by=name&sort_order=desc")
        assert response.status_code == 200
        content = response.text
        assert "a.txt" in content
        assert "b.txt" in content
        # In descending order by name, "b.txt" should appear before "a.txt"
        assert content.index("b.txt") < content.index("a.txt")


@pytest.mark.unit
class TestFilesFiltering:
    """Tests for file filtering endpoints."""

    def test_files_filter_by_type(self, tmp_path: Path) -> None:
        """Should filter files by type parameter."""
        (tmp_path / "doc.pdf").write_text("test")
        (tmp_path / "data.csv").write_text("test")
        (tmp_path / "file.txt").write_text("test")

        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        # Filter to show only .txt files
        response = client.get("/ui/files?type=.txt")
        assert response.status_code == 200
        # Should include the .txt file
        assert "file.txt" in response.text


@pytest.mark.unit
class TestFilesApi:
    """Tests for file API endpoints (HTMX and JSON)."""

    def test_file_tree_endpoint(self, tmp_path: Path) -> None:
        """Should provide file tree endpoint for directory navigation."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "file.txt").write_text("test")

        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        # Use params dict for proper URL encoding
        response = client.get("/ui/files/tree", params={"path": str(tmp_path)})
        assert response.status_code == 200

    def test_files_breadcrumbs(self, tmp_path: Path) -> None:
        """Should generate breadcrumb navigation."""
        # Basic test that page loads - breadcrumbs generated server-side
        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        response = client.get("/ui/files")
        assert response.status_code == 200
        # Breadcrumbs would be embedded in HTML
        assert len(response.text) > 0
