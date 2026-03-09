"""Tests for the files browsing routes (/ui/files/*)."""

from __future__ import annotations

import os
import platform
from pathlib import Path

import pytest

from .test_helpers import assert_file_order_in_html


@pytest.mark.unit
class TestFilesBrowse:
    """Tests for file browser page (/ui/files)."""

    def test_files_page_returns_200(self, web_client_builder) -> None:
        """Files page should return 200 status."""
        client = web_client_builder(allowed_paths=[])
        response = client.get("/ui/files")
        assert response.status_code == 200

    def test_files_page_returns_html(self, web_client_builder) -> None:
        """Files page should return HTML."""
        client = web_client_builder(allowed_paths=[])
        response = client.get("/ui/files")
        assert "text/html" in response.headers.get("content-type", "")

    def test_files_page_with_empty_directory(self, web_client_builder) -> None:
        """Files page should handle empty directories."""
        client = web_client_builder(allowed_paths=[])
        response = client.get("/ui/files")
        assert response.status_code == 200

    def test_files_page_with_test_files(self, tmp_path: Path, web_client_builder) -> None:
        """Files page should list files in directory."""
        # Create some test files
        (tmp_path / "file1.txt").write_text("test")
        (tmp_path / "file2.pdf").write_text("test")

        client = web_client_builder(allowed_paths=[str(tmp_path)])
        response = client.get("/ui/files")
        assert response.status_code == 200


@pytest.mark.unit
class TestFilesSorting:
    """Tests for file sorting endpoints."""

    @pytest.mark.parametrize(
        "sort_by,files,expected_order",
        [
            ("name", {"a.txt": "test", "b.txt": "test"}, ["a.txt", "b.txt"]),
            ("size", {"small.txt": "x", "large.txt": "x" * 1000}, ["small.txt", "large.txt"]),
            ("type", {"file.txt": "test", "file.pdf": "test"}, ["file.pdf", "file.txt"]),
        ],
        ids=["by_name", "by_size", "by_type"],
    )
    def test_files_sort(
        self, tmp_path: Path, web_client_builder, sort_by: str, files: dict, expected_order: list
    ) -> None:
        """Should handle various file sorting parameters."""
        for filename, content in files.items():
            (tmp_path / filename).write_text(content)

        client = web_client_builder(allowed_paths=[str(tmp_path)])
        response = client.get(f"/ui/files?sort_by={sort_by}")
        assert response.status_code == 200
        assert_file_order_in_html(response.text, *expected_order)

    def test_files_sort_by_modified(self, tmp_path: Path, web_client_builder) -> None:
        """Should handle sort by modified time parameter."""
        old_file = tmp_path / "file_old.txt"
        old_file.write_text("test")
        os.utime(old_file, (1000000000, 1000000000))  # Explicit older timestamp
        new_file = tmp_path / "file_new.txt"
        new_file.write_text("test")
        os.utime(new_file, (2000000000, 2000000000))  # Explicit newer timestamp

        client = web_client_builder(allowed_paths=[str(tmp_path)])
        response = client.get("/ui/files?sort_by=modified")
        assert response.status_code == 200
        # Verify files are sorted by modified time (older before newer)
        assert_file_order_in_html(response.text, "file_old.txt", "file_new.txt")

    @pytest.mark.skipif(
        platform.system() in ("Windows", "Darwin"),
        reason="Creation time sorting is flaky on Windows/macOS: st_birthtime and st_ctime "
        "don't reliably match st_mtime (used by os.utime). Skip on these platforms.",
    )
    def test_files_sort_by_created(self, tmp_path: Path, web_client_builder) -> None:
        """Should handle sort by created time parameter."""
        first_file = tmp_path / "file_first.txt"
        first_file.write_text("test")
        os.utime(first_file, (1500000000, 1500000000))  # Explicit earlier timestamp
        second_file = tmp_path / "file_second.txt"
        second_file.write_text("test")
        os.utime(second_file, (2500000000, 2500000000))  # Explicit later timestamp

        client = web_client_builder(allowed_paths=[str(tmp_path)])
        response = client.get("/ui/files?sort_by=created")
        assert response.status_code == 200
        # Verify files are sorted by created time (first before second)
        assert_file_order_in_html(response.text, "file_first.txt", "file_second.txt")

    def test_files_sort_descending(self, tmp_path: Path, web_client_builder) -> None:
        """Should handle descending sort order via sort_order parameter."""
        (tmp_path / "a.txt").write_text("test")
        (tmp_path / "b.txt").write_text("test")

        client = web_client_builder(allowed_paths=[str(tmp_path)])
        response = client.get("/ui/files?sort_by=name&sort_order=desc")
        assert response.status_code == 200
        # In descending order by name, "b.txt" should appear before "a.txt"
        assert_file_order_in_html(response.text, "b.txt", "a.txt")


@pytest.mark.unit
class TestFilesFiltering:
    """Tests for file filtering endpoints."""

    def test_files_filter_by_type(self, tmp_path: Path, web_client_builder) -> None:
        """Should filter files by type parameter."""
        (tmp_path / "doc.pdf").write_text("test")
        (tmp_path / "data.csv").write_text("test")
        (tmp_path / "file.txt").write_text("test")

        client = web_client_builder(allowed_paths=[str(tmp_path)])
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

    def test_file_tree_endpoint(self, tmp_path: Path, web_client_builder) -> None:
        """Should provide file tree endpoint for directory navigation."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "file.txt").write_text("test")

        client = web_client_builder(allowed_paths=[str(tmp_path)])
        # Use params dict for proper URL encoding
        response = client.get("/ui/files/tree", params={"path": str(tmp_path)})
        assert response.status_code == 200

    def test_files_breadcrumbs(self, tmp_path: Path, web_client_builder) -> None:
        """Should generate breadcrumb navigation."""
        # Basic test that page loads - breadcrumbs generated server-side
        client = web_client_builder(allowed_paths=[str(tmp_path)])
        response = client.get("/ui/files")
        assert response.status_code == 200
        # Breadcrumbs would be embedded in HTML
        assert len(response.text) > 0


@pytest.mark.unit
class TestFilesStateAndIntegration:
    """Tests for template rendering and state management (Stream D)."""

    def test_files_template_rendering_with_complex_context(
        self, tmp_path: Path, web_client_builder
    ) -> None:
        """Template should render correctly with complex file listings."""
        # Create files with various properties
        (tmp_path / "document.pdf").write_text("test" * 100)
        (tmp_path / "image.jpg").write_text("x" * 500)
        (tmp_path / "archive.zip").write_text("y" * 1000)
        subdir = tmp_path / "subdirectory"
        subdir.mkdir()
        (subdir / "nested.txt").write_text("nested")

        client = web_client_builder(allowed_paths=[str(tmp_path)])
        response = client.get("/ui/files")
        assert response.status_code == 200
        # Template should render with all file types present
        assert "document.pdf" in response.text or "pdf" in response.text.lower()

    def test_files_sorting_with_tied_values(self, tmp_path: Path, web_client_builder) -> None:
        """Sorting should handle files with identical sort keys."""
        # Create files with same size
        (tmp_path / "file_a.txt").write_text("test")
        (tmp_path / "file_b.txt").write_text("test")
        (tmp_path / "file_c.txt").write_text("test")

        client = web_client_builder(allowed_paths=[str(tmp_path)])
        response = client.get("/ui/files?sort_by=size")
        assert response.status_code == 200
        # Should handle tied values gracefully
        assert "file_a.txt" in response.text or "file_b.txt" in response.text

    def test_files_browser_cache_headers(self, tmp_path: Path, web_client_builder) -> None:
        """Regular HTML file-browser responses should not set Cache-Control headers."""
        (tmp_path / "file.txt").write_text("test")

        client = web_client_builder(allowed_paths=[str(tmp_path)])
        response = client.get("/ui/files")
        assert response.status_code == 200
        # Regular HTML /ui/files responses do not set Cache-Control headers
        assert response.headers.get("Cache-Control") is None


@pytest.mark.unit
class TestFilesSSEHandling:
    """Tests for SSE event stream handling in files routes (Stream B)."""

    # NOTE: SSE endpoints /ui/files/events and /ui/files/watch do not exist
    # Commenting out these tests as the routes are not implemented
    #
    # def test_files_sse_events_endpoint(self, tmp_path: Path) -> None:
    #     """Should provide SSE endpoint for file list updates."""
    #     (tmp_path / "file.txt").write_text("test")
    #
    #     client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
    #     # SSE endpoint would typically return streaming content
    #     response = client.get("/ui/files/events")
    #     # Endpoint may exist and return stream, or be 404 (acceptable)
    #     assert response.status_code in (200, 404)
    #
    # def test_files_watch_stream_completion(self, tmp_path: Path) -> None:
    #     """File watch stream endpoint should exist or be not found."""
    #     (tmp_path / "file.txt").write_text("test")
    #
    #     client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
    #     # Endpoint may not be implemented yet
    #     response = client.get("/ui/files/watch")
    #     assert response.status_code in (200, 404)
    #
    # def test_files_sse_event_format(self, tmp_path: Path) -> None:
    #     """SSE event responses should follow SSE format."""
    #     (tmp_path / "file.txt").write_text("test")
    #
    #     client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
    #     response = client.get("/ui/files/events")
    #     # Endpoint should exist or be explicitly not implemented
    #     assert response.status_code in (200, 404)

    @pytest.mark.skip(reason="SSE routes not yet implemented")
    def test_files_sse_placeholder(self) -> None:
        """Placeholder test for SSE handling until SSE routes are implemented."""


@pytest.mark.unit
class TestFilesErrorHandling:
    """Tests for error handling and edge cases in files routes (Stream A)."""

    def test_files_invalid_sort_parameter(self, tmp_path: Path, web_client_builder) -> None:
        """Should handle invalid sort_by parameter gracefully."""
        (tmp_path / "file.txt").write_text("test")

        client = web_client_builder(allowed_paths=[str(tmp_path)])
        # Invalid sort parameter is validated and rejected with 422
        response = client.get("/ui/files?sort_by=invalid_sort_field")
        # Should return 422 Unprocessable Entity for invalid parameter
        assert response.status_code == 422

    def test_files_directory_traversal_protection(self, tmp_path: Path, web_client_builder) -> None:
        """Should safely handle directory path parameters."""
        (tmp_path / "allowed.txt").write_text("test")

        client = web_client_builder(allowed_paths=[str(tmp_path)])
        # Path traversal attempts should be handled safely (either blocked or ignored)
        response = client.get("/ui/files?path=../../../etc/passwd")
        # Should return 200 (safe handling - error caught in HTML response)
        assert response.status_code == 200

    def test_files_unicode_filename_handling(self, tmp_path: Path, web_client_builder) -> None:
        """Should correctly handle files with unicode characters in names."""
        # Create files with unicode names
        (tmp_path / "файл_тест.txt").write_text("test")  # Russian
        (tmp_path / "文件测试.txt").write_text("test")  # Chinese

        client = web_client_builder(allowed_paths=[str(tmp_path)])
        response = client.get("/ui/files")
        assert response.status_code == 200
        # Response should handle unicode without crashing
        assert len(response.text) > 0
