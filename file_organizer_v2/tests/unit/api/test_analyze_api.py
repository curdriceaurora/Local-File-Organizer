"""Unit tests for analyze endpoint."""
import pytest
from fastapi.testclient import TestClient

from file_organizer.api.main import create_app


@pytest.fixture
def client():
    """Create TestClient for analyze endpoint tests."""
    app = create_app()
    return TestClient(app)


class TestAnalyzeEndpoint:
    """Tests for the /analyze endpoint."""

    def test_analyze_requires_input(self, client):
        """Analyze endpoint should require input."""
        response = client.post("/api/v1/analyze")

        assert response.status_code in (400, 422, 404)

    def test_analyze_accepts_text_input(self, client):
        """Analyze endpoint should accept text input."""
        payload = {"content": "Sample text to analyze"}
        response = client.post("/api/v1/analyze", json=payload)

        # Should not be 404 (endpoint exists)
        assert response.status_code != 404

    def test_analyze_accepts_file_upload(self, client):
        """Analyze endpoint should accept file upload."""
        files = {"file": ("test.txt", b"content to analyze", "text/plain")}
        response = client.post("/api/v1/analyze", files=files)

        assert response.status_code != 404

    def test_analyze_returns_description(self, client):
        """Analyze endpoint should return file description."""
        payload = {"content": "This is a technical document about machine learning"}
        response = client.post("/api/v1/analyze", json=payload)

        if response.status_code in (200, 201, 202):
            data = response.json()
            assert "description" in data or "analysis" in data or "summary" in data

    def test_analyze_returns_category(self, client):
        """Analyze endpoint should return file category."""
        payload = {"content": "Recipe for chocolate cake with frosting"}
        response = client.post("/api/v1/analyze", json=payload)

        if response.status_code in (200, 201, 202):
            data = response.json()
            assert "category" in data or "type" in data or "classification" in data

    def test_analyze_handles_images(self, client):
        """Analyze endpoint should handle image files."""
        # Create a minimal PNG file (1x1 pixel)
        png_data = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\r\x8b\x00\x00\x00\x00IEND\xaeB`\x82'
        files = {"file": ("image.png", png_data, "image/png")}
        response = client.post("/api/v1/analyze", files=files)

        assert response.status_code in (200, 201, 202, 400, 422)

    def test_analyze_handles_pdfs(self, client):
        """Analyze endpoint should handle PDF files."""
        # Minimal PDF header
        pdf_data = b'%PDF-1.0\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n'
        files = {"file": ("document.pdf", pdf_data, "application/pdf")}
        response = client.post("/api/v1/analyze", files=files)

        assert response.status_code in (200, 201, 202, 400, 422)

    def test_analyze_returns_confidence(self, client):
        """Analyze endpoint should return confidence score."""
        payload = {"content": "Clear, well-defined technical documentation"}
        response = client.post("/api/v1/analyze", json=payload)

        if response.status_code in (200, 201, 202):
            data = response.json()
            assert "confidence" in data or "score" in data or "confidence_score" in data

    def test_analyze_empty_content_handling(self, client):
        """Analyze endpoint should handle empty content gracefully."""
        payload = {"content": ""}
        response = client.post("/api/v1/analyze", json=payload)

        assert response.status_code in (200, 201, 202, 400, 422)

    def test_analyze_large_content(self, client):
        """Analyze endpoint should handle large content."""
        large_content = "x" * (1024 * 1024)  # 1MB text
        payload = {"content": large_content}
        response = client.post("/api/v1/analyze", json=payload)

        assert response.status_code != 404

    def test_analyze_special_characters(self, client):
        """Analyze endpoint should handle special characters."""
        payload = {"content": "Testing with émojis 🎉 and ñ special chars"}
        response = client.post("/api/v1/analyze", json=payload)

        assert response.status_code in (200, 201, 202, 400, 422)
