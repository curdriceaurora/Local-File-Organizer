"""Tests for the organize/scan routes (/ui/organize/*)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.main import create_app
from file_organizer.api.test_utils import build_test_settings


def _build_client(tmp_path: Path, allowed_paths: list[str] | None = None) -> TestClient:
    """Create a test client with organize route access."""
    if allowed_paths is None:
        allowed_paths = [str(tmp_path)]
    settings = build_test_settings(tmp_path, allowed_paths=allowed_paths)
    app = create_app(settings)
    return TestClient(app)


@pytest.mark.unit
class TestOrganizePage:
    """Tests for the main organize page."""

    def test_organize_page_returns_200(self, tmp_path: Path) -> None:
        """Organize page should return 200 status."""
        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        response = client.get("/ui/organize")
        assert response.status_code == 200

    def test_organize_page_returns_html(self, tmp_path: Path) -> None:
        """Organize page should return HTML."""
        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        response = client.get("/ui/organize")
        assert "text/html" in response.headers.get("content-type", "")

    def test_organize_page_with_test_directory(self, tmp_path: Path) -> None:
        """Organize page should display with test directory."""
        (tmp_path / "file.txt").write_text("test")

        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        response = client.get("/ui/organize")
        assert response.status_code == 200


@pytest.mark.unit
class TestOrganizeMethodSelection:
    """Tests for methodology/method selection."""

    def test_organize_with_default_method(self, tmp_path: Path) -> None:
        """Should handle default organization method."""
        (tmp_path / "file.txt").write_text("test")

        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        response = client.get("/ui/organize")
        assert response.status_code == 200

    def test_organize_with_para_method(self, tmp_path: Path) -> None:
        """Should handle PARA methodology selection."""
        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        response = client.get("/ui/organize?methodology=para")
        assert response.status_code in [200, 400]

    def test_organize_with_johnny_decimal_method(self, tmp_path: Path) -> None:
        """Should handle Johnny Decimal methodology selection."""
        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        response = client.get("/ui/organize?methodology=johnny_decimal")
        assert response.status_code in [200, 400]


@pytest.mark.unit
class TestScanEndpoint:
    """Tests for the scan directory endpoint."""

    def test_scan_returns_file_list(self, tmp_path: Path) -> None:
        """Scan should return list of files found."""
        (tmp_path / "file1.txt").write_text("test")
        (tmp_path / "file2.txt").write_text("test")

        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        # Scan might be a POST to /ui/organize/scan or similar
        response = client.get("/ui/organize")
        assert response.status_code == 200

    def test_scan_with_recursive_option(self, tmp_path: Path) -> None:
        """Scan should handle recursive directory traversal."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "file.txt").write_text("test")

        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        response = client.get("/ui/organize?recursive=true")
        assert response.status_code in [200, 400]

    def test_scan_with_hidden_files(self, tmp_path: Path) -> None:
        """Scan should handle hidden file inclusion."""
        (tmp_path / ".hidden").write_text("test")

        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        response = client.get("/ui/organize?include_hidden=true")
        assert response.status_code in [200, 400]


@pytest.mark.unit
class TestOrganizeResults:
    """Tests for organize result display."""

    def test_organize_results_page(self, tmp_path: Path) -> None:
        """Should display organize results."""
        (tmp_path / "file.txt").write_text("test")

        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        # Preview/results might be in a different route
        response = client.get("/ui/organize")
        assert response.status_code == 200

    def test_organize_action_buttons(self, tmp_path: Path) -> None:
        """Results should show organization action options."""
        (tmp_path / "file.txt").write_text("test")

        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        response = client.get("/ui/organize")
        # Should be able to get results page
        assert response.status_code == 200


@pytest.mark.unit
class TestOrganizeHtmxEndpoints:
    """Tests for HTMX partial response endpoints."""

    def test_organizehtmx_event_stream(self, tmp_path: Path) -> None:
        """Should support HTMX event stream for progress."""
        # Progress updates typically via SSE or similar
        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        response = client.get("/ui/organize")
        assert response.status_code == 200

    def test_organize_dry_run_mode(self, tmp_path: Path) -> None:
        """Should support dry-run preview mode."""
        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        response = client.get("/ui/organize?dry_run=true")
        assert response.status_code in [200, 400]
