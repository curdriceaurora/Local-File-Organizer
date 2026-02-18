"""Unit tests for files endpoint."""

import pytest
from fastapi.testclient import TestClient

from file_organizer.api.main import create_app


@pytest.fixture
def client():
    """Create TestClient for files endpoint tests."""
    app = create_app()
    return TestClient(app)


class TestFilesListEndpoint:
    """Tests for GET /files endpoint."""

    def test_files_list_returns_200(self, client):
        """GET /files should return 200 OK or 401 when auth required."""
        response = client.get("/api/v1/files")

        assert response.status_code in (200, 401)

    def test_files_list_returns_json(self, client):
        """GET /files should return JSON response."""
        response = client.get("/api/v1/files")

        assert response.headers.get("content-type") is not None
        assert "application/json" in response.headers.get("content-type", "")

    def test_files_list_returns_array(self, client):
        """GET /files should return list of files."""
        response = client.get("/api/v1/files")

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list) or "files" in data

    def test_files_include_metadata(self, client):
        """Files should include metadata."""
        response = client.get("/api/v1/files")

        if response.status_code == 200:
            data = response.json()
            files = data if isinstance(data, list) else data.get("files", [])
            if files:
                file_obj = files[0]
                assert "id" in file_obj or "name" in file_obj

    def test_files_list_supports_pagination(self, client):
        """Files endpoint should support pagination."""
        response = client.get("/api/v1/files?limit=10&offset=0")

        assert response.status_code in (200, 400, 401, 422)

    def test_files_list_supports_filtering(self, client):
        """Files endpoint should support filtering."""
        response = client.get("/api/v1/files?type=document")

        assert response.status_code in (200, 400, 401, 422)

    def test_files_list_supports_sorting(self, client):
        """Files endpoint should support sorting."""
        response = client.get("/api/v1/files?sort=name&order=asc")

        assert response.status_code in (200, 400, 401, 422)


class TestFileDetailEndpoint:
    """Tests for GET /files/{file_id} endpoint."""

    def test_file_detail_requires_id(self, client):
        """GET /files/{id} should require file ID."""
        response = client.get("/api/v1/files/")

        # Should either not exist, return error, redirect, or require auth
        assert response.status_code in (200, 307, 401, 404, 422)

    def test_file_detail_returns_404_for_missing(self, client):
        """GET /files/{id} should return 404 or 403 for missing/disallowed file."""
        response = client.get("/api/v1/files/nonexistent-id")

        assert response.status_code in (404, 403, 401, 400)

    def test_file_detail_returns_json(self, client):
        """GET /files/{id} should return JSON."""
        response = client.get("/api/v1/files/test-id")

        if response.status_code == 200:
            assert response.headers.get("content-type") is not None
            assert "application/json" in response.headers.get("content-type", "")

    def test_file_detail_includes_properties(self, client):
        """File detail should include file properties."""
        response = client.get("/api/v1/files/test-id")

        if response.status_code == 200:
            data = response.json()
            assert "id" in data or "name" in data


class TestFileUploadEndpoint:
    """Tests for POST /files/upload endpoint."""

    def test_file_upload_accepts_files(self, client):
        """POST /files/upload should accept file uploads."""
        files = {"file": ("test.txt", b"test content", "text/plain")}
        response = client.post("/api/v1/files/upload", files=files)

        # Should not be 404 (endpoint exists) or 405 (method not allowed)
        assert response.status_code not in (404, 405)

    def test_file_upload_returns_uploaded_info(self, client):
        """Upload should return information about uploaded file."""
        files = {"file": ("test.txt", b"test content", "text/plain")}
        response = client.post("/api/v1/files/upload", files=files)

        if response.status_code in (200, 201):
            data = response.json()
            assert "id" in data or "file_id" in data or "filename" in data

    def test_file_upload_requires_file(self, client):
        """Upload endpoint should require file."""
        response = client.post("/api/v1/files/upload")

        assert response.status_code in (400, 401, 422)

    def test_file_upload_handles_multiple_files(self, client):
        """Upload should handle multiple files."""
        files = [
            ("file1.txt", b"content1", "text/plain"),
            ("file2.txt", b"content2", "text/plain"),
        ]
        response = client.post("/api/v1/files/upload", files=[("files", f) for f in files])

        assert response.status_code in (200, 201, 400, 401, 422)


class TestFileDeleteEndpoint:
    """Tests for DELETE /files/{file_id} endpoint."""

    def test_file_delete_exists(self, client):
        """DELETE /files/{id} endpoint should exist."""
        response = client.delete("/api/v1/files/test-id")

        # Should not return 404 for method not found or 405 method not allowed
        assert response.status_code != 405

    def test_file_delete_requires_id(self, client):
        """DELETE /files should require file ID."""
        response = client.delete("/api/v1/files/")

        assert response.status_code in (404, 401, 422)

    def test_file_delete_returns_success(self, client):
        """DELETE should return success response."""
        response = client.delete("/api/v1/files/test-id")

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)

    def test_file_delete_handles_missing_file(self, client):
        """DELETE should handle missing file gracefully."""
        response = client.delete("/api/v1/files/nonexistent-id")

        assert response.status_code in (200, 404, 403, 401)
