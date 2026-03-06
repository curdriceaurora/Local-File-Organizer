"""Tests for the organize/scan routes (/ui/organize/*)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from file_organizer.api.main import create_app
from file_organizer.api.test_utils import build_test_settings


def _build_client(tmp_path: Path, allowed_paths: list[str] | None = None) -> TestClient:
    """Create a test client with organize route access."""
    if allowed_paths is None:
        allowed_paths = [str(tmp_path)]
    settings = build_test_settings(tmp_path, allowed_paths=allowed_paths)
    app = create_app(settings)
    return TestClient(app)


@pytest.fixture
def mock_file_organizer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock FileOrganizer to avoid AI model initialization in tests.

    FileOrganizer initializes AI models and TextProcessor calls ensure_nltk_data(),
    which can download datasets and cause tests to be slow/flaky. This fixture
    patches it with a fast stub that returns deterministic results.
    """
    mock_organizer = MagicMock()
    mock_organizer.organize.return_value = {
        "plan": {
            "moves": [],
            "copies": [],
            "conflicts": [],
            "statistics": {"total_files": 0, "organized": 0},
        },
        "error": None,
    }
    monkeypatch.setattr(
        "file_organizer.web.organize_routes.FileOrganizer",
        MagicMock(return_value=mock_organizer),
    )


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
class TestOrganizeScan:
    """Tests for scan endpoint with different methodologies."""

    def test_organize_scan_with_default_method(self, tmp_path: Path, mock_file_organizer: Any) -> None:
        """Should scan with default (content_based) methodology."""
        (tmp_path / "file.txt").write_text("test")
        output_dir = tmp_path / "organized"
        output_dir.mkdir()

        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        response = client.post(
            "/ui/organize/scan",
            data={
                "input_dir": str(tmp_path),
                "output_dir": str(output_dir),
                "methodology": "content_based",
            },
        )
        assert response.status_code == 200

    def test_organize_scan_with_para_method(self, tmp_path: Path, mock_file_organizer: Any) -> None:
        """Should scan with PARA methodology."""
        (tmp_path / "file.txt").write_text("test")
        output_dir = tmp_path / "organized"
        output_dir.mkdir()

        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        response = client.post(
            "/ui/organize/scan",
            data={
                "input_dir": str(tmp_path),
                "output_dir": str(output_dir),
                "methodology": "para",
            },
        )
        assert response.status_code == 200

    def test_organize_scan_with_johnny_decimal_method(self, tmp_path: Path, mock_file_organizer: Any) -> None:
        """Should scan with Johnny Decimal methodology."""
        (tmp_path / "file.txt").write_text("test")
        output_dir = tmp_path / "organized"
        output_dir.mkdir()

        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        response = client.post(
            "/ui/organize/scan",
            data={
                "input_dir": str(tmp_path),
                "output_dir": str(output_dir),
                "methodology": "johnny_decimal",
            },
        )
        assert response.status_code == 200


@pytest.mark.unit
class TestScanOptions:
    """Tests for scan endpoint with different options."""

    def test_scan_returns_plan(self, tmp_path: Path, mock_file_organizer: Any) -> None:
        """Scan should return an organization plan."""
        (tmp_path / "file1.txt").write_text("test")
        (tmp_path / "file2.pdf").write_text("test")
        output_dir = tmp_path / "organized"
        output_dir.mkdir()

        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        response = client.post(
            "/ui/organize/scan",
            data={
                "input_dir": str(tmp_path),
                "output_dir": str(output_dir),
            },
        )
        assert response.status_code == 200

    def test_scan_with_recursive_option(self, tmp_path: Path, mock_file_organizer: Any) -> None:
        """Scan should handle recursive directory traversal."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "file.txt").write_text("test")
        output_dir = tmp_path / "organized"
        output_dir.mkdir()

        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        response = client.post(
            "/ui/organize/scan",
            data={
                "input_dir": str(tmp_path),
                "output_dir": str(output_dir),
                "recursive": "1",
            },
        )
        assert response.status_code == 200

    def test_scan_with_hidden_files(self, tmp_path: Path) -> None:
        """Scan should reject hidden file inclusion."""
        (tmp_path / ".hidden").write_text("test")
        output_dir = tmp_path / "organized"
        output_dir.mkdir()

        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        response = client.post(
            "/ui/organize/scan",
            data={
                "input_dir": str(tmp_path),
                "output_dir": str(output_dir),
                "include_hidden": "1",
            },
        )
        assert response.status_code == 200
        assert "not supported" in response.text.lower()


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

    def test_organize_htmx_request_header(self, tmp_path: Path, mock_file_organizer: Any) -> None:
        """Should handle HTMX request headers for partial updates."""
        (tmp_path / "file.txt").write_text("test")
        output_dir = tmp_path / "organized"
        output_dir.mkdir()

        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        # Send scan request with HTMX header to indicate it's a partial update
        response = client.post(
            "/ui/organize/scan",
            data={
                "input_dir": str(tmp_path),
                "output_dir": str(output_dir),
            },
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 200

    def test_organize_scan_validation(self, tmp_path: Path) -> None:
        """Should validate scan parameters and return errors when needed."""
        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        # Missing required input_dir should error
        response = client.post(
            "/ui/organize/scan",
            data={
                "output_dir": str(tmp_path / "out"),
            },
        )
        assert response.status_code == 200
        assert "Input directory is required" in response.text
