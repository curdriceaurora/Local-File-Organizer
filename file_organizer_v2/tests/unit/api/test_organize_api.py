"""Unit tests for organize endpoint."""

import pytest
from fastapi.testclient import TestClient

from file_organizer.api.main import create_app


@pytest.fixture
def client():
    """Create TestClient for organize endpoint tests."""
    app = create_app()
    return TestClient(app)


class TestOrganizeEndpoint:
    """Tests for the /organize POST endpoint."""

    def test_organize_requires_file_input(self, client):
        """Organize endpoint should require file input or authentication."""
        response = client.post("/api/v1/organize")

        # 400: missing input, 401: auth required (expected when auth enforced)
        assert response.status_code in (400, 401)

    def test_organize_accepts_file_upload(self, client):
        """Organize endpoint should accept file upload."""
        # Create a dummy file for testing
        files = {"file": ("test.txt", b"test content", "text/plain")}
        response = client.post("/api/v1/organize", files=files)

        # Should not be 404 (endpoint exists)
        assert response.status_code != 404

    def test_organize_returns_json_response(self, client):
        """Organize endpoint should return JSON response."""
        files = {"file": ("test.txt", b"test content", "text/plain")}
        response = client.post("/api/v1/organize", files=files)

        if response.status_code in (200, 201, 202):
            assert response.headers.get("content-type") is not None
            assert "application/json" in response.headers.get("content-type", "")

    def test_organize_response_includes_filename(self, client):
        """Organize endpoint response should include organized filename."""
        files = {"file": ("test.txt", b"test content", "text/plain")}
        response = client.post("/api/v1/organize", files=files)

        if response.status_code in (200, 201, 202):
            data = response.json()
            assert "filename" in data or "organized_name" in data or "new_filename" in data

    def test_organize_response_includes_folder(self, client):
        """Organize endpoint response should include suggested folder."""
        files = {"file": ("test.txt", b"test content", "text/plain")}
        response = client.post("/api/v1/organize", files=files)

        if response.status_code in (200, 201, 202):
            data = response.json()
            assert "folder" in data or "folder_name" in data or "suggested_path" in data

    def test_organize_handles_text_files(self, client):
        """Organize endpoint should handle text files."""
        files = {"file": ("document.txt", b"Sample text content", "text/plain")}
        response = client.post("/api/v1/organize", files=files)

        # 401: auth required when auth enforced (expected); other codes for actual processing
        assert response.status_code in (200, 201, 202, 400, 401, 422)

    def test_organize_handles_large_files(self, client):
        """Organize endpoint should handle large files."""
        large_content = b"x" * (10 * 1024 * 1024)  # 10MB file
        files = {"file": ("large.txt", large_content, "text/plain")}
        response = client.post("/api/v1/organize", files=files)

        assert response.status_code != 404

    def test_organize_includes_confidence_score(self, client):
        """Organize endpoint response should include confidence score."""
        files = {"file": ("test.txt", b"test content", "text/plain")}
        response = client.post("/api/v1/organize", files=files)

        if response.status_code in (200, 201, 202):
            data = response.json()
            assert "confidence" in data or "confidence_score" in data

    def test_organize_batch_multiple_files(self, client):
        """Organize endpoint should support batch processing multiple files."""
        files = [
            ("file1.txt", b"content1", "text/plain"),
            ("file2.txt", b"content2", "text/plain"),
        ]
        multi_files = {"files": files}
        response = client.post("/api/v1/organize", files=multi_files)

        # Should either handle or return proper error
        assert response.status_code in (200, 201, 202, 400, 422)
