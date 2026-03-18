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


@pytest.mark.ci
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


@pytest.mark.ci
@pytest.mark.unit
class TestSemanticSearch:
    """Tests for GET /api/v1/search?semantic=true."""

    def test_semantic_false_is_default(self, tmp_path: Path) -> None:
        """Default search (no semantic param) uses keyword path — result set unchanged."""
        (tmp_path / "report.txt").write_text("quarterly finance report")
        _, client = _build_app(tmp_path)

        resp_default = client.get("/api/v1/search?q=report")
        resp_explicit = client.get("/api/v1/search?q=report&semantic=false")
        assert resp_default.status_code == 200
        assert resp_explicit.status_code == 200
        assert resp_default.json() == resp_explicit.json()

    def test_semantic_true_returns_200(self, tmp_path: Path) -> None:
        """semantic=true returns HTTP 200 and a list."""
        (tmp_path / "finance.txt").write_text("quarterly finance report summary")
        (tmp_path / "notes.txt").write_text("meeting notes agenda items")
        _, client = _build_app(tmp_path)

        resp = client.get("/api/v1/search?q=finance&semantic=true")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_semantic_true_empty_dir_returns_empty_list(self, tmp_path: Path) -> None:
        """Semantic search over an empty directory returns []."""
        _, client = _build_app(tmp_path)

        resp = client.get("/api/v1/search?q=anything&semantic=true")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_semantic_true_result_schema(self, tmp_path: Path) -> None:
        """Semantic results contain the same fields as keyword results."""
        (tmp_path / "doc.txt").write_text("finance budget quarterly report")
        (tmp_path / "other.txt").write_text(
            "meeting notes agenda items"
        )  # 2nd doc prevents TF-IDF ValueError
        _, client = _build_app(tmp_path)

        resp = client.get("/api/v1/search?q=finance&semantic=true")
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) >= 1, "single-file corpus with matching query must return ≥1 result"
        result = results[0]
        assert "filename" in result
        assert "path" in result
        assert isinstance(result["score"], float)
        assert "type" in result
        assert "size" in result

    def test_semantic_true_missing_query_returns_400(self, tmp_path: Path) -> None:
        """semantic=true still requires the q param."""
        _, client = _build_app(tmp_path)

        resp = client.get("/api/v1/search?semantic=true")
        assert resp.status_code == 400

    def test_semantic_true_keyword_path_unchanged(self, tmp_path: Path) -> None:
        """Existing keyword search path is unaffected when semantic=false."""
        (tmp_path / "myfile.txt").write_text("hello world")
        _, client = _build_app(tmp_path)

        resp = client.get("/api/v1/search?q=myfile&semantic=false")
        assert resp.status_code == 200
        results = resp.json()
        assert any(r["filename"] == "myfile.txt" for r in results)

    def test_semantic_true_with_type_filter(self, tmp_path: Path) -> None:
        """semantic=true respects the type filter parameter."""
        (tmp_path / "report.txt").write_text("finance quarterly report")
        (tmp_path / "data.csv").write_text("col1,col2\n1,2")
        _, client = _build_app(tmp_path)

        resp = client.get("/api/v1/search?q=report&semantic=true&type=txt")
        assert resp.status_code == 200
        results = resp.json()
        assert results, "expected at least one .txt result for query 'report'"
        # All returned files must be .txt
        for r in results:
            assert r["type"] == "txt"

    def test_semantic_true_limit_param_respected(self, tmp_path: Path) -> None:
        """semantic=true honours the limit query parameter."""
        for i in range(6):
            (tmp_path / f"file_{i}.txt").write_text(f"document {i} about finance")
        _, client = _build_app(tmp_path)

        resp = client.get("/api/v1/search?q=finance&semantic=true&limit=2")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_semantic_offset_beyond_max_returns_empty(self, tmp_path: Path) -> None:
        """semantic=true with offset >= _MAX_SEMANTIC returns [] immediately."""
        from file_organizer.api.routers.search import _MAX_SEMANTIC

        (tmp_path / "doc.txt").write_text("finance report content")
        _, client = _build_app(tmp_path)

        resp = client.get(f"/api/v1/search?q=finance&semantic=true&offset={_MAX_SEMANTIC}")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_semantic_offset_and_limit_within_max(self, tmp_path: Path) -> None:
        """semantic=true with offset+limit capped at _MAX_SEMANTIC returns results."""
        for i in range(4):
            (tmp_path / f"doc_{i}.txt").write_text(f"finance budget report document {i}")
        _, client = _build_app(tmp_path)

        resp = client.get("/api/v1/search?q=finance&semantic=true&offset=1&limit=2")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_semantic_no_limit_returns_all_within_max(self, tmp_path: Path) -> None:
        """semantic=true without limit returns all results up to _MAX_SEMANTIC."""
        for i in range(4):
            (tmp_path / f"doc_{i}.txt").write_text(f"finance budget quarterly {i}")
        _, client = _build_app(tmp_path)

        resp = client.get("/api/v1/search?q=finance&semantic=true")
        assert resp.status_code == 200
        results = resp.json()
        assert isinstance(results, list)
        assert len(results) >= 1


# ---------------------------------------------------------------------------
# Security: limit clamping, relative paths, constants
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.unit
class TestSearchSecurityBounds:
    """Verify input bounds and output sanitization in the search router."""

    def test_limit_clamped_to_max(self, tmp_path: Path) -> None:
        """Limit values above _MAX_LIMIT are silently clamped to _MAX_LIMIT."""
        from file_organizer.api.routers.search import _MAX_LIMIT

        for i in range(_MAX_LIMIT + 1):
            (tmp_path / f"file_{i}.txt").write_text(f"content {i}")
        _, client = _build_app(tmp_path)

        # Request a limit far above _MAX_LIMIT
        resp = client.get(f"/api/v1/search?q=file&limit={_MAX_LIMIT + 1000}")
        assert resp.status_code == 200
        results = resp.json()
        assert isinstance(results, list)
        assert len(results) == _MAX_LIMIT

    def test_limit_zero_treated_as_no_limit(self, tmp_path: Path) -> None:
        """limit=0 is treated as no explicit limit (returns all matches)."""
        for i in range(3):
            (tmp_path / f"file_{i}.txt").write_text(f"content {i}")
        _, client = _build_app(tmp_path)

        resp = client.get("/api/v1/search?q=file&limit=0")
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 3

    def test_result_paths_are_relative(self, tmp_path: Path) -> None:
        """Search results must use relative paths, not absolute."""
        (tmp_path / "report.txt").write_text("quarterly finance report")
        _, client = _build_app(tmp_path)

        resp = client.get("/api/v1/search?q=report")
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) >= 1
        for r in results:
            assert not Path(r["path"]).is_absolute(), (
                f"Path should be relative, got absolute: {r['path']}"
            )

    def test_max_semantic_constant_exists(self) -> None:
        """_MAX_SEMANTIC constant is defined as a defence-in-depth bound."""
        from file_organizer.api.routers.search import _MAX_SEMANTIC

        assert isinstance(_MAX_SEMANTIC, int)
        assert _MAX_SEMANTIC > 0

    def test_max_limit_constant_exists(self) -> None:
        """_MAX_LIMIT constant is defined for input clamping."""
        from file_organizer.api.routers.search import _MAX_LIMIT

        assert isinstance(_MAX_LIMIT, int)
        assert _MAX_LIMIT > 0


@pytest.mark.ci
@pytest.mark.unit
class TestRelativePathHelper:
    """Unit tests for the _relative_path helper."""

    def test_relative_to_matching_root(self, tmp_path: Path) -> None:
        from file_organizer.api.routers.search import _relative_path

        fp = tmp_path / "subdir" / "file.txt"
        result = _relative_path(fp, [tmp_path])
        assert result == str(Path("subdir") / "file.txt")

    def test_fallback_to_absolute_when_no_root_matches(self, tmp_path: Path) -> None:
        from file_organizer.api.routers.search import _relative_path

        fp = (tmp_path / "area_a" / "file.txt").resolve()
        roots = [(tmp_path / "area_b").resolve()]
        result = _relative_path(fp, roots)
        assert result == str(fp)

    def test_first_matching_root_wins(self, tmp_path: Path) -> None:
        from file_organizer.api.routers.search import _relative_path

        sub = tmp_path / "a" / "b"
        fp = sub / "file.txt"
        root_a = tmp_path / "a"
        root_b = tmp_path
        # root_a matches first and gives shorter relative path
        result = _relative_path(fp, [root_a, root_b])
        assert result == str(Path("b") / "file.txt")
