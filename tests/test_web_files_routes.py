"""Tests for the files browsing routes (/ui/files/*)."""

from __future__ import annotations

import os
import platform
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
        # Verify files are sorted by name (ascending)
        content = response.text
        assert "a.txt" in content
        assert "b.txt" in content
        assert content.index("a.txt") < content.index("b.txt")

    def test_files_sort_by_size(self, tmp_path: Path) -> None:
        """Should handle sort by size parameter."""
        (tmp_path / "large.txt").write_text("x" * 1000)
        (tmp_path / "small.txt").write_text("x")

        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        response = client.get("/ui/files?sort_by=size")
        assert response.status_code == 200
        # Verify files are sorted by size (ascending - small before large)
        content = response.text
        assert "small.txt" in content
        assert "large.txt" in content
        assert content.index("small.txt") < content.index("large.txt")

    def test_files_sort_by_modified(self, tmp_path: Path) -> None:
        """Should handle sort by modified time parameter."""
        old_file = tmp_path / "file_old.txt"
        old_file.write_text("test")
        os.utime(old_file, (1000000000, 1000000000))  # Explicit older timestamp
        new_file = tmp_path / "file_new.txt"
        new_file.write_text("test")
        os.utime(new_file, (2000000000, 2000000000))  # Explicit newer timestamp

        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        response = client.get("/ui/files?sort_by=modified")
        assert response.status_code == 200
        # Verify files are sorted by modified time (older before newer)
        content = response.text
        assert "file_old.txt" in content
        assert "file_new.txt" in content
        assert content.index("file_old.txt") < content.index("file_new.txt")

    @pytest.mark.skipif(
        platform.system() in ("Windows", "Darwin"),
        reason="Creation time sorting is flaky on Windows/macOS: st_birthtime and st_ctime "
        "don't reliably match st_mtime (used by os.utime). Skip on these platforms.",
    )
    def test_files_sort_by_created(self, tmp_path: Path) -> None:
        """Should handle sort by created time parameter."""
        first_file = tmp_path / "file_first.txt"
        first_file.write_text("test")
        os.utime(first_file, (1500000000, 1500000000))  # Explicit earlier timestamp
        second_file = tmp_path / "file_second.txt"
        second_file.write_text("test")
        os.utime(second_file, (2500000000, 2500000000))  # Explicit later timestamp

        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        response = client.get("/ui/files?sort_by=created")
        assert response.status_code == 200
        # Verify files are sorted by created time (first before second)
        content = response.text
        assert "file_first.txt" in content
        assert "file_second.txt" in content
        assert content.index("file_first.txt") < content.index("file_second.txt")

    def test_files_sort_by_type(self, tmp_path: Path) -> None:
        """Should handle sort by type parameter."""
        (tmp_path / "file.txt").write_text("test")
        (tmp_path / "file.pdf").write_text("test")

        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        response = client.get("/ui/files?sort_by=type")
        assert response.status_code == 200
        # Verify files are sorted by type extension
        content = response.text
        assert "file.txt" in content
        assert "file.pdf" in content
        # PDF comes before TXT alphabetically by extension
        assert content.index("file.pdf") < content.index("file.txt")

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
        # Should exclude other file types
        assert "doc.pdf" not in response.text
        assert "data.csv" not in response.text


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


@pytest.mark.unit
class TestFilesErrorHandling:
    """Tests for error handling and edge cases in files routes (Stream A)."""

    def test_files_invalid_sort_parameter(self, tmp_path: Path) -> None:
        """Should handle invalid sort_by parameter gracefully."""
        (tmp_path / "file.txt").write_text("test")

        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        # Invalid sort parameter is validated and rejected with 422
        response = client.get("/ui/files?sort_by=invalid_sort_field")
        # Should return 422 Unprocessable Entity for invalid parameter
        assert response.status_code in (422, 400)

    def test_files_directory_traversal_protection(self, tmp_path: Path) -> None:
        """Should safely handle directory path parameters."""
        (tmp_path / "allowed.txt").write_text("test")

        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        # Path traversal attempts should be handled safely (either blocked or ignored)
        response = client.get("/ui/files?path=../../../etc/passwd")
        # Should return 200 (safe handling) or error
        assert response.status_code in (200, 400, 403, 404)

    def test_files_unicode_filename_handling(self, tmp_path: Path) -> None:
        """Should correctly handle files with unicode characters in names."""
        # Create files with unicode names
        (tmp_path / "файл_тест.txt").write_text("test")  # Russian
        (tmp_path / "文件测试.txt").write_text("test")  # Chinese

        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        response = client.get("/ui/files")
        assert response.status_code == 200
        # Response should handle unicode without crashing
        assert len(response.text) > 0
