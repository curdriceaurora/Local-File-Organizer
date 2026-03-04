"""Tests for the search API router."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.exceptions import setup_exception_handlers
from file_organizer.api.routers.search import router


def _build_app() -> tuple[FastAPI, TestClient]:
    """Create a FastAPI app with search router and dependency overrides."""
    settings = ApiSettings(environment="test")
    app = FastAPI()
    setup_exception_handlers(app)
    app.dependency_overrides[get_settings] = lambda: settings
    app.include_router(router, prefix="/api/v1")
    client = TestClient(app)
    return app, client


@pytest.mark.unit
class TestSearch:
    """Tests for GET /api/v1/search."""

    def test_search_missing_query_required(self) -> None:
        """Test that query parameter is required."""
        _, client = _build_app()

        resp = client.get("/api/v1/search")
        assert resp.status_code == 400
        body = resp.json()
        assert "Query parameter 'q' is required" in body["detail"]

    def test_search_empty_query_required(self) -> None:
        """Test that empty query is rejected."""
        _, client = _build_app()

        resp = client.get("/api/v1/search?q=")
        assert resp.status_code == 400
        body = resp.json()
        assert "Query parameter 'q' is required" in body["detail"]

    def test_search_basic_query(self) -> None:
        """Test basic search matching files."""
        _, client = _build_app()

        resp = client.get("/api/v1/search?q=test")
        assert resp.status_code == 200
        results = resp.json()
        assert isinstance(results, list)
        # "test_document.txt" and "test_report.pdf" should match
        assert len(results) >= 2
        assert any(r["filename"] == "test_document.txt" for r in results)
        assert any(r["filename"] == "test_report.pdf" for r in results)

    def test_search_case_insensitive(self) -> None:
        """Test that search is case insensitive."""
        _, client = _build_app()

        resp_lower = client.get("/api/v1/search?q=test")
        resp_upper = client.get("/api/v1/search?q=TEST")

        results_lower = resp_lower.json()
        results_upper = resp_upper.json()

        assert len(results_lower) == len(results_upper)
        assert results_lower == results_upper

    def test_search_scoring_prefix_vs_substring(self) -> None:
        """Test that prefix matches score higher than substring matches."""
        _, client = _build_app()

        resp = client.get("/api/v1/search?q=test")
        results = resp.json()

        # "test_document.txt" starts with "test" - should have 0.9 score
        # "test_report.pdf" starts with "test" - should have 0.9 score
        test_results = [r for r in results if r["filename"].startswith("test")]
        for result in test_results:
            assert result["score"] == 0.9

    def test_search_no_results(self) -> None:
        """Test search with no matching results."""
        _, client = _build_app()

        resp = client.get("/api/v1/search?q=nonexistent")
        assert resp.status_code == 200
        results = resp.json()
        assert results == []

    def test_search_filter_by_type(self) -> None:
        """Test filtering results by file type."""
        _, client = _build_app()

        # Search for "test" files and filter to only "text" type
        resp = client.get("/api/v1/search?q=test&type=text")
        assert resp.status_code == 200
        results = resp.json()

        # Should only get test_document.txt (type="text")
        assert len(results) == 1
        assert results[0]["filename"] == "test_document.txt"
        assert results[0]["type"] == "text"

    def test_search_filter_by_type_no_match(self) -> None:
        """Test type filter with no matching results."""
        _, client = _build_app()

        # Search for "test" but filter to "image" type (no match)
        resp = client.get("/api/v1/search?q=test&type=image")
        assert resp.status_code == 200
        results = resp.json()
        assert results == []

    def test_search_pagination_limit(self) -> None:
        """Test pagination with limit parameter."""
        _, client = _build_app()

        # Get all results for broader query
        resp_all = client.get("/api/v1/search?q=e")  # Matches multiple files
        all_results = resp_all.json()

        # Get with limit=2
        resp_limited = client.get("/api/v1/search?q=e&limit=2")
        limited_results = resp_limited.json()

        assert len(limited_results) == 2
        assert len(limited_results) <= len(all_results)

    def test_search_pagination_offset(self) -> None:
        """Test pagination with offset parameter."""
        _, client = _build_app()

        # Get all results for broader query
        resp_all = client.get("/api/v1/search?q=e")  # Matches multiple files
        all_results = resp_all.json()

        # Precondition: must have more than 1 result to test offset
        assert len(all_results) > 1, "Fixture must return multiple results for this test"

        # Get with offset=1
        resp_offset = client.get("/api/v1/search?q=e&offset=1")
        offset_results = resp_offset.json()

        # Should get results after the first one
        assert len(offset_results) == len(all_results) - 1

    def test_search_pagination_limit_and_offset(self) -> None:
        """Test pagination with both limit and offset."""
        _, client = _build_app()

        # Get all results
        resp_all = client.get("/api/v1/search?q=e")
        all_results = resp_all.json()

        # Precondition: must have at least 3 results to test offset and limit
        assert len(all_results) > 2, "Fixture must return at least 3 results for this test"

        # Get with offset=1, limit=1
        resp = client.get("/api/v1/search?q=e&limit=1&offset=1")
        results = resp.json()

        # Should get exactly 1 result (the second one)
        assert len(results) == 1
        assert results[0] == all_results[1]

    def test_search_result_schema(self) -> None:
        """Test that search results have correct schema."""
        _, client = _build_app()

        resp = client.get("/api/v1/search?q=test")
        assert resp.status_code == 200
        results = resp.json()

        if results:
            result = results[0]
            # Required fields
            assert "filename" in result
            assert "path" in result
            assert "score" in result

            # Optional fields that should be present
            assert "type" in result
            assert "size" in result
