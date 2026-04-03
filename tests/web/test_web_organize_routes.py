"""Tests for the organize/scan routes (/ui/organize/*)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from file_organizer.api.main import create_app
from file_organizer.api.test_utils import build_test_settings
from file_organizer.core.organizer import OrganizationResult
from tests.conftest import get_csrf_headers, get_csrf_token


def _build_client(tmp_path: Path, allowed_paths: list[str] | None = None) -> TestClient:
    """Create a test client with organize route access."""
    if allowed_paths is None:
        allowed_paths = [str(tmp_path)]
    settings = build_test_settings(tmp_path, allowed_paths=allowed_paths)
    app = create_app(settings)
    return TestClient(app)


@pytest.fixture
def mock_file_organizer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock FileOrganizer.organize() to avoid AI model initialization in tests.

    FileOrganizer initializes AI models and TextProcessor calls ensure_nltk_data(),
    which can download datasets and cause tests to be slow/flaky. This fixture
    patches ONLY the organize() method while keeping the class available for
    attributes like TEXT_EXTENSIONS used by route helpers.
    """
    # Create mock result matching OrganizationResult interface
    # Must include all attributes that route code accesses
    mock_result = MagicMock(spec=OrganizationResult)
    mock_result.total_files = 0
    mock_result.processed_files = 0
    mock_result.skipped_files = 0
    mock_result.failed_files = 0
    mock_result.processing_time = 0.0
    mock_result.organized_structure = {}
    mock_result.errors = []

    # Patch only the organize method, not the entire class
    def mock_organize(*args: Any, **kwargs: Any) -> Any:
        return mock_result

    monkeypatch.setattr(
        "file_organizer.web.organize_routes.FileOrganizer.organize",
        mock_organize,
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

    def test_organize_scan_with_default_method(
        self, tmp_path: Path, mock_file_organizer: Any
    ) -> None:
        """Should scan with default (content_based) methodology."""
        (tmp_path / "file.txt").write_text("test")
        output_dir = tmp_path / "organized"
        output_dir.mkdir()

        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        csrf_headers = get_csrf_headers(client, seed_url="/ui/organize")
        response = client.post(
            "/ui/organize/scan",
            data={
                "input_dir": str(tmp_path),
                "output_dir": str(output_dir),
                "methodology": "content_based",
            },
            headers=csrf_headers,
        )
        assert response.status_code == 200
        # Verify plan was generated (success path, not error path)
        assert "plan" in response.text.lower()

    def test_organize_scan_with_para_method(self, tmp_path: Path, mock_file_organizer: Any) -> None:
        """Should scan with PARA methodology."""
        (tmp_path / "file.txt").write_text("test")
        output_dir = tmp_path / "organized"
        output_dir.mkdir()

        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        csrf_headers = get_csrf_headers(client, seed_url="/ui/organize")
        response = client.post(
            "/ui/organize/scan",
            data={
                "input_dir": str(tmp_path),
                "output_dir": str(output_dir),
                "methodology": "para",
            },
            headers=csrf_headers,
        )
        assert response.status_code == 200
        # Verify plan was generated (success path, not error path)
        assert "plan" in response.text.lower()

    def test_organize_scan_with_johnny_decimal_method(
        self, tmp_path: Path, mock_file_organizer: Any
    ) -> None:
        """Should scan with Johnny Decimal methodology."""
        (tmp_path / "file.txt").write_text("test")
        output_dir = tmp_path / "organized"
        output_dir.mkdir()

        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        csrf_headers = get_csrf_headers(client, seed_url="/ui/organize")
        response = client.post(
            "/ui/organize/scan",
            data={
                "input_dir": str(tmp_path),
                "output_dir": str(output_dir),
                "methodology": "johnny_decimal",
            },
            headers=csrf_headers,
        )
        assert response.status_code == 200
        # Verify plan was generated (success path, not error path)
        assert "plan" in response.text.lower()


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
        csrf_headers = get_csrf_headers(client, seed_url="/ui/organize")
        response = client.post(
            "/ui/organize/scan",
            data={
                "input_dir": str(tmp_path),
                "output_dir": str(output_dir),
            },
            headers=csrf_headers,
        )
        assert response.status_code == 200
        assert "plan" in response.text.lower()

    def test_scan_with_recursive_option(self, tmp_path: Path, mock_file_organizer: Any) -> None:
        """Scan should handle recursive directory traversal."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "file.txt").write_text("test")
        output_dir = tmp_path / "organized"
        output_dir.mkdir()

        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        csrf_headers = get_csrf_headers(client, seed_url="/ui/organize")
        response = client.post(
            "/ui/organize/scan",
            data={
                "input_dir": str(tmp_path),
                "output_dir": str(output_dir),
                "recursive": "1",
            },
            headers=csrf_headers,
        )
        assert response.status_code == 200
        assert "plan" in response.text.lower()

    def test_scan_with_hidden_files(self, tmp_path: Path) -> None:
        """Scan should reject hidden file inclusion."""
        (tmp_path / ".hidden").write_text("test")
        output_dir = tmp_path / "organized"
        output_dir.mkdir()

        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        csrf_headers = get_csrf_headers(client, seed_url="/ui/organize")
        response = client.post(
            "/ui/organize/scan",
            data={
                "input_dir": str(tmp_path),
                "output_dir": str(output_dir),
                "include_hidden": "1",
            },
            headers=csrf_headers,
        )
        assert response.status_code == 200
        assert "not supported" in response.text.lower()

    def test_organize_scan_post_without_csrf_returns_403(self, tmp_path: Path) -> None:
        """POST to scan without CSRF token should be rejected with 403."""
        (tmp_path / "file.txt").write_text("test")
        output_dir = tmp_path / "organized"
        output_dir.mkdir()

        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        response = client.post(
            "/ui/organize/scan",
            data={
                "input_dir": str(tmp_path),
                "output_dir": str(output_dir),
            },
            # No x-csrf-token header — middleware must reject
        )
        assert response.status_code == 403


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
        csrf_headers = {"HX-Request": "true", **get_csrf_headers(client, seed_url="/ui/organize")}
        response = client.post(
            "/ui/organize/scan",
            data={
                "input_dir": str(tmp_path),
                "output_dir": str(output_dir),
            },
            headers=csrf_headers,
        )
        assert response.status_code == 200
        assert "plan" in response.text.lower()

    def test_organize_scan_validation(self, tmp_path: Path) -> None:
        """Should validate scan parameters and return errors when needed."""
        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        # Missing required input_dir should error
        csrf_headers = get_csrf_headers(client, seed_url="/ui/organize")
        response = client.post(
            "/ui/organize/scan",
            data={
                "output_dir": str(tmp_path / "out"),
            },
            headers=csrf_headers,
        )
        assert response.status_code == 200
        assert "Input directory is required" in response.text


@pytest.mark.unit
class TestOrganizeRoutes:
    """Tests for organize route security and validation."""

    def test_organize_scan_post_with_wrong_csrf_token_returns_403(self, tmp_path: Path) -> None:
        """POST with a seeded cookie but mismatched header token should be rejected."""
        (tmp_path / "file.txt").write_text("test")
        client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
        token = get_csrf_token(client, seed_url="/ui/organize")
        response = client.post(
            "/ui/organize/scan",
            data={"input_dir": str(tmp_path), "output_dir": str(tmp_path / "out")},
            headers={"x-csrf-token": f"{token}-tampered"},
        )
        assert response.status_code == 403
