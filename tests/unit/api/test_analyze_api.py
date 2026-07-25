"""Unit tests for analyze endpoint.

Note on transport: the endpoint takes ``content`` as a *query parameter*
(it is a bare scalar param alongside an ``UploadFile``), not as a JSON
body. Posting ``json={"content": ...}`` silently yields 400 because the
param never binds — earlier versions of these tests did exactly that and
passed only through hedged assertions (``!= 404``, conditional asserts).
"""

import pytest
from starlette.testclient import TestClient

from file_organizer.api.main import create_app

MOCKED_DESCRIPTION = "Mocked AI response"


@pytest.fixture
def client():
    """Create TestClient for analyze endpoint tests."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def mock_text_model(mocker):
    """Mock the text model for tests that reach the analysis path.

    Deliberately NOT autouse: tests that are rejected before the model is
    reached (e.g. input validation) must not carry idle patches.
    """
    mock_model = mocker.MagicMock()
    mock_model.generate.return_value = MOCKED_DESCRIPTION

    # Mock the get_text_model dependency and reset the module-level cache
    mocker.patch("file_organizer.api.routers.analyze.get_text_model", return_value=mock_model)
    mocker.patch("file_organizer.api.routers.analyze._text_model", None)
    return mock_model


def _assert_analysis_response(data: dict) -> None:
    """Assert the full AnalyzeResponse contract."""
    assert data["description"] == MOCKED_DESCRIPTION
    assert isinstance(data["category"], str) and data["category"]
    assert isinstance(data["confidence"], float)
    assert 0.0 <= data["confidence"] <= 1.0


@pytest.mark.unit
class TestAnalyzeEndpoint:
    """Tests for the /analyze endpoint."""

    def test_analyze_requires_input(self, client):
        """No content and no file is rejected with 400 before the model is reached."""
        response = client.post("/api/v1/analyze")

        assert response.status_code == 400
        data = response.json()
        assert data["message"] == "Either content or file must be provided"

    def test_analyze_accepts_text_input(self, client, mock_text_model):
        """Text content via query param reaches the model and returns an analysis."""
        response = client.post("/api/v1/analyze", params={"content": "Sample text to analyze"})

        assert response.status_code == 200
        _assert_analysis_response(response.json())
        assert mock_text_model.generate.called

    def test_analyze_json_body_is_not_a_supported_transport(self, client):
        """A JSON body does not bind to the content param — rejected as missing input."""
        response = client.post("/api/v1/analyze", json={"content": "Sample text"})

        assert response.status_code == 400

    def test_analyze_accepts_file_upload(self, client, mock_text_model):
        """File upload reaches the model and returns an analysis."""
        files = {"file": ("test.txt", b"content to analyze", "text/plain")}
        response = client.post("/api/v1/analyze", files=files)

        assert response.status_code == 200
        _assert_analysis_response(response.json())
        assert mock_text_model.generate.called

    def test_analyze_returns_description(self, client, mock_text_model):
        """The description field carries the model's generated text."""
        response = client.post(
            "/api/v1/analyze",
            params={"content": "This is a technical document about machine learning"},
        )

        assert response.status_code == 200
        assert response.json()["description"] == MOCKED_DESCRIPTION

    def test_analyze_returns_category(self, client, mock_text_model):
        """The category field is a non-empty string."""
        response = client.post(
            "/api/v1/analyze", params={"content": "Recipe for chocolate cake with frosting"}
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["category"], str) and data["category"]

    def test_analyze_handles_images(self, client, mock_text_model):
        """Image uploads are decoded permissively and analyzed."""
        # Minimal PNG file (1x1 pixel)
        png_data = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\r\x8b\x00\x00\x00\x00IEND\xaeB`\x82"
        files = {"file": ("image.png", png_data, "image/png")}
        response = client.post("/api/v1/analyze", files=files)

        assert response.status_code == 200
        _assert_analysis_response(response.json())

    def test_analyze_handles_pdfs(self, client, mock_text_model):
        """PDF uploads are decoded permissively and analyzed."""
        # Minimal PDF header
        pdf_data = b"%PDF-1.0\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        files = {"file": ("document.pdf", pdf_data, "application/pdf")}
        response = client.post("/api/v1/analyze", files=files)

        assert response.status_code == 200
        _assert_analysis_response(response.json())

    def test_analyze_returns_confidence(self, client, mock_text_model):
        """The confidence field is a float within [0, 1]."""
        response = client.post(
            "/api/v1/analyze", params={"content": "Clear, well-defined technical documentation"}
        )

        assert response.status_code == 200
        confidence = response.json()["confidence"]
        assert isinstance(confidence, float)
        assert 0.0 <= confidence <= 1.0

    def test_analyze_empty_content_handling(self, client, mock_text_model):
        """Empty (but present) content is analyzed, not rejected."""
        response = client.post("/api/v1/analyze", params={"content": ""})

        assert response.status_code == 200
        _assert_analysis_response(response.json())

    def test_analyze_large_content(self, client, mock_text_model):
        """Large uploads are truncated and analyzed (1MB exceeds URL limits, so use a file)."""
        files = {"file": ("big.txt", b"x" * (1024 * 1024), "text/plain")}
        response = client.post("/api/v1/analyze", files=files)

        assert response.status_code == 200
        _assert_analysis_response(response.json())

    def test_analyze_special_characters(self, client, mock_text_model):
        """Non-ASCII content is analyzed without error."""
        response = client.post(
            "/api/v1/analyze", params={"content": "Testing with émojis 🎉 and ñ special chars"}
        )

        assert response.status_code == 200
        _assert_analysis_response(response.json())
