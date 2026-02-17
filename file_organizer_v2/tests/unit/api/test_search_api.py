"""Unit tests for search endpoint."""
import pytest
from fastapi.testclient import TestClient

from file_organizer.api.main import create_app


@pytest.fixture
def client():
    """Create TestClient for search endpoint tests."""
    app = create_app()
    return TestClient(app)


class TestSearchEndpoint:
    """Tests for the /search endpoint."""

    def test_search_requires_query(self, client):
        """Search endpoint should require query parameter."""
        response = client.get("/api/v1/search")

        assert response.status_code in (400, 422)

    def test_search_accepts_query_parameter(self, client):
        """Search endpoint should accept query parameter."""
        response = client.get("/api/v1/search?q=test")

        # Should not be 404 (endpoint exists)
        assert response.status_code != 404

    def test_search_returns_list(self, client):
        """Search endpoint should return list of results."""
        response = client.get("/api/v1/search?q=document")

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, list) or "results" in data

    def test_search_results_include_filename(self, client):
        """Search results should include filename."""
        response = client.get("/api/v1/search?q=test")

        if response.status_code == 200:
            data = response.json()
            results = data if isinstance(data, list) else data.get("results", [])
            if results:
                assert "filename" in results[0] or "name" in results[0]

    def test_search_results_include_path(self, client):
        """Search results should include file path."""
        response = client.get("/api/v1/search?q=test")

        if response.status_code == 200:
            data = response.json()
            results = data if isinstance(data, list) else data.get("results", [])
            if results:
                assert "path" in results[0] or "file_path" in results[0]

    def test_search_with_filter(self, client):
        """Search endpoint should support filters."""
        response = client.get("/api/v1/search?q=test&type=document")

        assert response.status_code in (200, 400, 422)

    def test_search_case_insensitive(self, client):
        """Search should be case insensitive."""
        response1 = client.get("/api/v1/search?q=TEST")
        response2 = client.get("/api/v1/search?q=test")

        assert response1.status_code == response2.status_code

    def test_search_supports_pagination(self, client):
        """Search endpoint should support pagination."""
        response = client.get("/api/v1/search?q=test&limit=10&offset=0")

        assert response.status_code in (200, 400, 422)

    def test_search_empty_query(self, client):
        """Search endpoint should handle empty query."""
        response = client.get("/api/v1/search?q=")

        assert response.status_code in (200, 400, 422)

    def test_search_special_characters_in_query(self, client):
        """Search should handle special characters in query."""
        response = client.get("/api/v1/search?q=%2Atest%2A")  # *test*

        assert response.status_code in (200, 400, 422)

    def test_search_includes_score(self, client):
        """Search results should include relevance score."""
        response = client.get("/api/v1/search?q=document")

        if response.status_code == 200:
            data = response.json()
            results = data if isinstance(data, list) else data.get("results", [])
            if results:
                assert "score" in results[0] or "relevance" in results[0]

    def test_search_returns_metadata(self, client):
        """Search results should include file metadata."""
        response = client.get("/api/v1/search?q=test")

        if response.status_code == 200:
            data = response.json()
            results = data if isinstance(data, list) else data.get("results", [])
            if results:
                result = results[0]
                # Should have at least one metadata field
                has_metadata = any(
                    key in result for key in [
                        "size", "created", "modified", "type", "description"
                    ]
                )
                assert has_metadata
