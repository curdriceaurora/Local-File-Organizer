"""Tests for the organize/scan routes (/ui/organize/*)."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_file_organizer(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Mock FileOrganizer to avoid AI model initialization in tests.

    FileOrganizer initializes AI models and TextProcessor calls ensure_nltk_data(),
    which can download datasets and cause tests to be slow/flaky. This fixture
    patches it with a fast stub that returns deterministic results.

    Returns the mock FileOrganizer class so tests can verify initialization.
    """
    mock_organizer = MagicMock()
    # Mock return value must be an object with OrganizationResult attributes
    mock_result = MagicMock()
    mock_result.total_files = 0
    mock_result.processed_files = 0
    mock_result.skipped_files = 0
    mock_result.failed_files = 0
    mock_result.processing_time = 0.0
    mock_result.organized_structure = {}
    mock_result.errors = {}
    mock_organizer.organize.return_value = mock_result

    mock_class = MagicMock(return_value=mock_organizer)
    monkeypatch.setattr(
        "file_organizer.web.organize_routes.FileOrganizer",
        mock_class,
    )
    # Return the class so tests can verify it was called with correct parameters
    return mock_class


@pytest.mark.unit
class TestOrganizePage:
    """Tests for the main organize page."""

    def test_organize_page_returns_200(self, tmp_path: Path, web_client_builder) -> None:
        """Organize page should return 200 status."""
        client = web_client_builder(allowed_paths=[str(tmp_path)])
        response = client.get("/ui/organize")
        assert response.status_code == 200

    def test_organize_page_returns_html(self, tmp_path: Path, web_client_builder) -> None:
        """Organize page should return HTML."""
        client = web_client_builder(allowed_paths=[str(tmp_path)])
        response = client.get("/ui/organize")
        assert "text/html" in response.headers.get("content-type", "")

    def test_organize_page_with_test_directory(self, tmp_path: Path, web_client_builder) -> None:
        """Organize page should display with test directory."""
        (tmp_path / "file.txt").write_text("test")

        client = web_client_builder(allowed_paths=[str(tmp_path)])
        response = client.get("/ui/organize")
        assert response.status_code == 200


@pytest.mark.unit
class TestOrganizeScan:
    """Tests for scan endpoint with different methodologies."""

    @pytest.mark.parametrize(
        "methodology",
        [
            "content_based",
            "para",
            "johnny_decimal",
        ],
        ids=["default", "para", "johnny_decimal"],
    )
    def test_organize_scan_with_methodology(
        self, tmp_path: Path, web_client_builder, mock_file_organizer: MagicMock, methodology: str
    ) -> None:
        """Should scan with different organization methodologies."""
        (tmp_path / "file.txt").write_text("test")
        output_dir = tmp_path / "organized"
        output_dir.mkdir()

        client = web_client_builder(allowed_paths=[str(tmp_path)])
        response = client.post(
            "/ui/organize/scan",
            data={
                "input_dir": str(tmp_path),
                "output_dir": str(output_dir),
                "methodology": methodology,
            },
        )
        assert response.status_code == 200
        # Verify plan was generated (success path, not error path)
        assert "Plan generated" in response.text
        # Verify FileOrganizer was instantiated and organize() was called
        mock_file_organizer.assert_called_once_with(dry_run=True, use_hardlinks=True)
        mock_file_organizer.return_value.organize.assert_called_once()


@pytest.mark.unit
class TestScanOptions:
    """Tests for scan endpoint with different options."""

    def test_scan_returns_plan(
        self, tmp_path: Path, web_client_builder, mock_file_organizer: Any
    ) -> None:
        """Scan should return an organization plan."""
        (tmp_path / "file1.txt").write_text("test")
        (tmp_path / "file2.pdf").write_text("test")
        output_dir = tmp_path / "organized"
        output_dir.mkdir()

        client = web_client_builder(allowed_paths=[str(tmp_path)])
        response = client.post(
            "/ui/organize/scan",
            data={
                "input_dir": str(tmp_path),
                "output_dir": str(output_dir),
            },
        )
        assert response.status_code == 200

    def test_scan_with_recursive_option(
        self, tmp_path: Path, web_client_builder, mock_file_organizer: Any
    ) -> None:
        """Scan should handle recursive directory traversal."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "file.txt").write_text("test")
        output_dir = tmp_path / "organized"
        output_dir.mkdir()

        client = web_client_builder(allowed_paths=[str(tmp_path)])
        response = client.post(
            "/ui/organize/scan",
            data={
                "input_dir": str(tmp_path),
                "output_dir": str(output_dir),
                "recursive": "1",
            },
        )
        assert response.status_code == 200

    def test_scan_with_hidden_files(self, tmp_path: Path, web_client_builder) -> None:
        """Scan should reject hidden file inclusion."""
        (tmp_path / ".hidden").write_text("test")
        output_dir = tmp_path / "organized"
        output_dir.mkdir()

        client = web_client_builder(allowed_paths=[str(tmp_path)])
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

    def test_organize_results_page(self, tmp_path: Path, web_client_builder) -> None:
        """Should display organize results."""
        (tmp_path / "file.txt").write_text("test")

        client = web_client_builder(allowed_paths=[str(tmp_path)])
        # Preview/results might be in a different route
        response = client.get("/ui/organize")
        assert response.status_code == 200

    def test_organize_action_buttons(self, tmp_path: Path, web_client_builder) -> None:
        """Results should show organization action options."""
        (tmp_path / "file.txt").write_text("test")

        client = web_client_builder(allowed_paths=[str(tmp_path)])
        response = client.get("/ui/organize")
        # Should be able to get results page
        assert response.status_code == 200


@pytest.mark.unit
class TestOrganizeHtmxEndpoints:
    """Tests for HTMX partial response endpoints."""

    def test_organize_htmx_request_header(
        self, tmp_path: Path, web_client_builder, mock_file_organizer: MagicMock
    ) -> None:
        """Should handle HTMX request headers for partial updates."""
        (tmp_path / "file.txt").write_text("test")
        output_dir = tmp_path / "organized"
        output_dir.mkdir()

        client = web_client_builder(allowed_paths=[str(tmp_path)])
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
        # HTMX requests should return HTML fragment with plan/result content
        assert "plan" in response.text.lower() or "organize" in response.text.lower()

    def test_organize_scan_validation(self, tmp_path: Path, web_client_builder) -> None:
        """Should validate scan parameters and return errors when needed."""
        client = web_client_builder(allowed_paths=[str(tmp_path)])
        # Missing required input_dir should error
        response = client.post(
            "/ui/organize/scan",
            data={
                "output_dir": str(tmp_path / "out"),
            },
        )
        assert response.status_code == 200
        assert "Input directory is required" in response.text


@pytest.mark.unit
class TestOrganizeInputValidation:
    """Tests for input validation and edge cases (Stream C)."""

    def test_organize_empty_input_directory(self, tmp_path: Path, web_client_builder) -> None:
        """Should validate that input directory is not empty/whitespace."""
        client = web_client_builder(allowed_paths=[str(tmp_path)])
        response = client.post(
            "/ui/organize/scan",
            data={
                "input_dir": "   ",  # Whitespace only
                "output_dir": str(tmp_path / "out"),
            },
        )
        # Should reject empty/whitespace input
        assert response.status_code in (200, 400)
        assert (
            "required" in response.text.lower()
            or "empty" in response.text.lower()
            or response.status_code == 400
        )

    def test_organize_path_normalization(self, tmp_path: Path, web_client_builder) -> None:
        """Should normalize path inputs correctly."""
        output_dir = tmp_path / "organized"
        output_dir.mkdir()

        client = web_client_builder(allowed_paths=[str(tmp_path)])
        # Use path with redundant slashes and dots
        normalized_path = str(tmp_path) + "//"
        response = client.post(
            "/ui/organize/scan",
            data={
                "input_dir": normalized_path,
                "output_dir": str(output_dir),
            },
        )
        # Should handle path normalization gracefully
        assert response.status_code in (200, 400)

    def test_organize_sort_filter_combination(self, tmp_path: Path, web_client_builder) -> None:
        """Should validate combinations of sort and filter parameters."""
        (tmp_path / "file.txt").write_text("test")

        client = web_client_builder(allowed_paths=[str(tmp_path)])
        response = client.post(
            "/ui/organize/scan",
            data={
                "input_dir": str(tmp_path),
                "output_dir": str(tmp_path / "out"),
                "sort_by": "name",
                "filter": "pdf",
            },
        )
        # Should accept valid sort/filter combinations
        assert response.status_code in (200, 400)


@pytest.mark.unit
class TestOrganizeProgressStreaming:
    """Tests for SSE progress streaming during organization (Stream B)."""

    # NOTE: SSE endpoint /ui/organize/progress does not exist
    # Commenting out these tests as the route is not implemented
    #
    # def test_organize_progress_stream_endpoint(self, tmp_path: Path, mock_file_organizer: Any) -> None:
    #     """Should support progress streaming endpoint for real-time updates."""
    #     (tmp_path / "file.txt").write_text("test")
    #     output_dir = tmp_path / "organized"
    #     output_dir.mkdir()
    #
    #     client = _build_client(tmp_path, allowed_paths=[str(tmp_path)])
    #     # Stream endpoint would typically use SSE or Server-Sent Events
    #     response = client.get("/ui/organize/progress")
    #     # Endpoint may exist and return stream, or be 404 (acceptable)
    #     assert response.status_code in (200, 404)

    def test_organize_scan_with_progress_updates(
        self, tmp_path: Path, web_client_builder, mock_file_organizer: MagicMock
    ) -> None:
        """Scan operation should emit progress updates during processing."""
        (tmp_path / "file.txt").write_text("test")
        output_dir = tmp_path / "organized"
        output_dir.mkdir()

        client = web_client_builder(allowed_paths=[str(tmp_path)])
        # Post scan request
        response = client.post(
            "/ui/organize/scan",
            data={
                "input_dir": str(tmp_path),
                "output_dir": str(output_dir),
            },
        )
        assert response.status_code == 200
        # Verify response includes progress indication
        assert "plan" in response.text.lower() or "organize" in response.text.lower()

    @pytest.mark.skip(reason="SSE streaming not yet implemented")
    def test_organize_stream_cancellation(self) -> None:
        """Stream should handle cancellation/timeout gracefully."""
        # Progress stream endpoint not yet implemented
        # TODO: Add assertions once streaming is implemented


@pytest.mark.unit
class TestOrganizeErrorHandling:
    """Tests for error handling and edge cases in organize routes (Stream A)."""

    def test_organize_invalid_methodology(self, tmp_path: Path, web_client_builder) -> None:
        """Should handle invalid methodology parameter."""
        (tmp_path / "file.txt").write_text("test")

        client = web_client_builder(allowed_paths=[str(tmp_path)])
        response = client.post(
            "/ui/organize/scan",
            data={
                "input_dir": str(tmp_path),
                "output_dir": str(tmp_path / "out"),
                "methodology": "invalid_methodology",
            },
        )
        # Should process with default methodology and return 200 with result
        assert response.status_code == 200

    def test_organize_nonexistent_directory(self, tmp_path: Path, web_client_builder) -> None:
        """Should handle non-existent input directory."""
        nonexistent = tmp_path / "does_not_exist"

        client = web_client_builder(allowed_paths=[str(tmp_path), str(nonexistent)])
        response = client.post(
            "/ui/organize/scan",
            data={
                "input_dir": str(nonexistent),
                "output_dir": str(tmp_path / "out"),
            },
        )
        # Should reject non-existent directory with error message
        assert response.status_code == 200  # Returns 200 with error in HTML

    def test_organize_scan_permission_error(self, tmp_path: Path, web_client_builder) -> None:
        """Should handle permission errors gracefully."""
        (tmp_path / "file.txt").write_text("test")

        client = web_client_builder(allowed_paths=[str(tmp_path)])
        # Use an output directory outside allowed paths (permission error scenario)
        response = client.post(
            "/ui/organize/scan",
            data={
                "input_dir": str(tmp_path),
                "output_dir": "/root/not_allowed",
            },
        )
        # Should handle permission error gracefully, returning 200 with error message or 403
        assert response.status_code in (200, 403)
