"""Tests for the search API router."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.exceptions import setup_exception_handlers
from file_organizer.api.routers.search import router


def _build_app(tmp_path: Path | None = None) -> tuple[FastAPI, TestClient]:
    """Create a FastAPI app with search router and dependency overrides."""
    # Use provided temp path or home directory
    allowed_path = str(tmp_path) if tmp_path else str(Path.home())
    settings = ApiSettings(environment="test", allowed_paths=[allowed_path])
    app = FastAPI()
    setup_exception_handlers(app)
    app.dependency_overrides[get_settings] = lambda: settings
    app.include_router(router, prefix="/api/v1")
    client = TestClient(app)
    return app, client


@pytest.mark.unit
class TestSearch:
    """Tests for GET /api/v1/search."""

    def test_search_missing_query_required(self, tmp_path: Path) -> None:
        """Test that query parameter is required."""
        _, client = _build_app(tmp_path)

        resp = client.get("/api/v1/search")
        assert resp.status_code == 400
        body = resp.json()
        assert "Query parameter 'q' is required" in body["detail"]

    def test_search_empty_query_required(self, tmp_path: Path) -> None:
        """Test that empty query is rejected."""
        _, client = _build_app(tmp_path)

        resp = client.get("/api/v1/search?q=")
        assert resp.status_code == 400
        body = resp.json()
        assert "Query parameter 'q' is required" in body["detail"]

    def test_search_basic_query(self, tmp_path: Path) -> None:
        """Test basic search matching files."""
        # Create test files
        (tmp_path / "test_document.txt").write_text("content")
        (tmp_path / "test_report.pdf").write_bytes(b"%PDF")
        _, client = _build_app(tmp_path)

        resp = client.get("/api/v1/search?q=test")
        assert resp.status_code == 200
        results = resp.json()
        assert isinstance(results, list)
        # "test_document.txt" and "test_report.pdf" should match
        assert len(results) >= 2
        assert any(r["filename"] == "test_document.txt" for r in results)
        assert any(r["filename"] == "test_report.pdf" for r in results)

    def test_search_case_insensitive(self, tmp_path: Path) -> None:
        """Test that search is case insensitive."""
        (tmp_path / "test_document.txt").write_text("content")
        _, client = _build_app(tmp_path)

        resp_lower = client.get("/api/v1/search?q=test")
        resp_upper = client.get("/api/v1/search?q=TEST")

        results_lower = resp_lower.json()
        results_upper = resp_upper.json()

        assert len(results_lower) == len(results_upper)
        assert results_lower == results_upper

    def test_search_scoring_prefix_vs_substring(self, tmp_path: Path) -> None:
        """Test that substring matches score correctly."""
        (tmp_path / "test_document.txt").write_text("content")
        (tmp_path / "document_test.txt").write_text("content")
        (tmp_path / "annual_test_report.txt").write_text("content")
        _, client = _build_app(tmp_path)

        resp = client.get("/api/v1/search?q=test")
        results = resp.json()

        # Results should be ordered by score (descending)
        scores = [r["score"] for r in results]
        # Verify scores are in descending order
        assert scores == sorted(scores, reverse=True)

    def test_search_no_results(self, tmp_path: Path) -> None:
        """Test search with no matching results."""
        (tmp_path / "file.txt").write_text("content")
        _, client = _build_app(tmp_path)

        resp = client.get("/api/v1/search?q=nonexistent")
        assert resp.status_code == 200
        results = resp.json()
        assert results == []

    def test_search_filter_by_type(self, tmp_path: Path) -> None:
        """Test filtering results by file type."""
        (tmp_path / "test_document.txt").write_text("content")
        (tmp_path / "test_report.pdf").write_bytes(b"%PDF")
        _, client = _build_app(tmp_path)

        # Search for "test" files and filter to only "txt" type
        resp = client.get("/api/v1/search?q=test&type=txt")
        assert resp.status_code == 200
        results = resp.json()

        # Should only get test_document.txt (type="txt")
        assert len(results) == 1
        assert results[0]["filename"] == "test_document.txt"
        assert results[0]["type"] == "txt"

    def test_search_filter_by_type_no_match(self, tmp_path: Path) -> None:
        """Test type filter with no matching results."""
        (tmp_path / "test_document.txt").write_text("content")
        _, client = _build_app(tmp_path)

        # Search for "test" but filter to "image" type (no match)
        resp = client.get("/api/v1/search?q=test&type=png")
        assert resp.status_code == 200
        results = resp.json()
        assert results == []

    def test_search_pagination_limit(self, tmp_path: Path) -> None:
        """Test pagination with limit parameter."""
        # Create multiple files that match query "e"
        for i in range(5):
            (tmp_path / f"file_{i}.txt").write_text(f"content {i}")
        _, client = _build_app(tmp_path)

        # Get all results for broader query
        resp_all = client.get("/api/v1/search?q=file")  # Matches all files
        all_results = resp_all.json()

        # Get with limit=2
        resp_limited = client.get("/api/v1/search?q=file&limit=2")
        limited_results = resp_limited.json()

        assert len(limited_results) == 2
        assert len(limited_results) <= len(all_results)

    def test_search_pagination_offset(self, tmp_path: Path) -> None:
        """Test pagination with offset parameter."""
        # Create multiple files
        for i in range(5):
            (tmp_path / f"file_{i}.txt").write_text(f"content {i}")
        _, client = _build_app(tmp_path)

        # Get all results for broader query
        resp_all = client.get("/api/v1/search?q=file")  # Matches all files
        all_results = resp_all.json()

        # Precondition: must have more than 1 result to test offset
        assert len(all_results) > 1, "Fixture must return multiple results for this test"

        # Get with offset=1
        resp_offset = client.get("/api/v1/search?q=file&offset=1")
        offset_results = resp_offset.json()

        # Should get results after the first one
        assert len(offset_results) == len(all_results) - 1

    def test_search_pagination_limit_and_offset(self, tmp_path: Path) -> None:
        """Test pagination with both limit and offset."""
        # Create multiple files
        for i in range(5):
            (tmp_path / f"file_{i}.txt").write_text(f"content {i}")
        _, client = _build_app(tmp_path)

        # Get all results
        resp_all = client.get("/api/v1/search?q=file")
        all_results = resp_all.json()

        # Precondition: must have at least 3 results to test offset and limit
        assert len(all_results) > 2, "Fixture must return at least 3 results for this test"

        # Get with offset=1, limit=1
        resp = client.get("/api/v1/search?q=file&limit=1&offset=1")
        results = resp.json()

        # Should get exactly 1 result (the second one)
        assert len(results) == 1
        assert results[0] == all_results[1]

    def test_search_result_schema(self, tmp_path: Path) -> None:
        """Test that search results have correct schema."""
        (tmp_path / "test_file.txt").write_text("content")
        _, client = _build_app(tmp_path)

        resp = client.get("/api/v1/search?q=test")
        assert resp.status_code == 200
        results = resp.json()

        assert len(results) > 0
        result = results[0]
        # Required fields
        assert "filename" in result
        assert "path" in result
        assert "score" in result

        # Optional fields that should be present
        assert "type" in result
        assert "size" in result
