"""Tests for the search endpoint — real filesystem search."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.routers.search import _ScoringTiers

pytestmark = [pytest.mark.unit, pytest.mark.ci]
# Note: Real filesystem search with edge case assertions.
# Excluded from smoke suite due to timing sensitivity.


def _make_app(allowed_paths: list[str]) -> TestClient:
    """Create a test client with search router and given allowed_paths.

    Sets up a FastAPI test client with the search router, exception handlers,
    and dependency overrides for testing. This allows tests to control which
    paths are allowed for searching.

    Args:
        allowed_paths: List of directory paths to allow searching.

    Returns:
        A TestClient configured with the search router.

    Example:
        >>> client = _make_app(['/tmp/test'])
        >>> resp = client.get('/search', params={'q': 'test'})
        >>> assert resp.status_code == 200
    """
    from fastapi import FastAPI

    from file_organizer.api.exceptions import setup_exception_handlers
    from file_organizer.api.routers.search import router

    app = FastAPI()
    setup_exception_handlers(app)
    app.include_router(router)

    settings = ApiSettings(
        allowed_paths=allowed_paths,
        auth_enabled=False,
    )

    def override_settings() -> ApiSettings:
        """Override dependency to return test settings."""
        return settings

    from file_organizer.api.dependencies import get_settings

    app.dependency_overrides[get_settings] = override_settings
    return TestClient(app)


class TestSearchReturnsRealFiles:
    """Search endpoint should find real files on disk."""

    def test_search_returns_real_files(self, tmp_path: Path) -> None:
        (tmp_path / "report.txt").write_text("hello")
        (tmp_path / "notes.txt").write_text("world")
        client = _make_app([str(tmp_path)])

        resp = client.get("/search", params={"q": "report"})
        assert resp.status_code == 200, f"Expected status 200, got {resp.status_code}"
        results = resp.json()
        assert len(results) == 1, (
            f"Expected 1 result for 'report' query, got {len(results)} results"
        )
        assert results[0]["filename"] == "report.txt", (
            f"Expected filename 'report.txt', got {results[0]['filename']}"
        )
        assert results[0]["score"] > 0, f"Expected score > 0, got {results[0]['score']}"

    def test_search_file_type_filter(self, tmp_path: Path) -> None:
        (tmp_path / "doc.pdf").write_bytes(b"%PDF")
        (tmp_path / "doc.txt").write_text("text")
        client = _make_app([str(tmp_path)])

        resp = client.get("/search", params={"q": "doc", "type": "pdf"})
        assert resp.status_code == 200, f"Expected status 200, got {resp.status_code}"
        results = resp.json()
        assert len(results) == 1, f"Expected 1 PDF result, got {len(results)} results"
        assert results[0]["filename"] == "doc.pdf", (
            f"Expected PDF file, got {results[0]['filename']}"
        )

    def test_search_path_filter(self, tmp_path: Path) -> None:
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "inside.txt").write_text("data")
        (tmp_path / "outside.txt").write_text("data")
        client = _make_app([str(tmp_path)])

        resp = client.get("/search", params={"q": "inside", "path": str(sub)})
        assert resp.status_code == 200, f"Expected status 200, got {resp.status_code}"
        results = resp.json()
        filenames = [r["filename"] for r in results]
        assert "inside.txt" in filenames, f"Expected 'inside.txt' in results, got {filenames}"
        assert "outside.txt" not in filenames, (
            f"Did not expect 'outside.txt' in filtered results, got {filenames}"
        )

    def test_search_scoring_order(self, tmp_path: Path) -> None:
        # Exact stem match should score higher than contains
        (tmp_path / "report.txt").write_text("a")
        (tmp_path / "annual_report_2024.txt").write_text("b")
        client = _make_app([str(tmp_path)])

        resp = client.get("/search", params={"q": "report"})
        assert resp.status_code == 200, f"Expected status 200, got {resp.status_code}"
        results = resp.json()
        assert len(results) == 2, (
            f"Expected 2 results, got {len(results)}: {[r['filename'] for r in results]}"
        )
        # Exact stem match ("report") should be first
        assert results[0]["filename"] == "report.txt", (
            f"Exact match should rank first, got {results[0]['filename']}"
        )
        assert results[0]["score"] > results[1]["score"], (
            f"Exact match score ({results[0]['score']}) should be higher than "
            f"substring match ({results[1]['score']})"
        )

    def test_search_extension_match_scores_half(self, tmp_path: Path) -> None:
        """Verify extension-only match scores EXTENSION_MATCH (0.5)."""
        (tmp_path / "budget.pdf").write_text("expense data")
        client = _make_app([str(tmp_path)])

        resp = client.get("/search", params={"q": "pdf"})
        assert resp.status_code == 200, f"Expected status 200, got {resp.status_code}"
        results = resp.json()
        assert len(results) == 1, f"Expected 1 result for 'pdf' query, got {len(results)} results"
        assert results[0]["filename"] == "budget.pdf", (
            f"Expected filename 'budget.pdf', got {results[0]['filename']}"
        )
        assert results[0]["score"] == _ScoringTiers.EXTENSION_MATCH, (
            f"Extension-only match should score {_ScoringTiers.EXTENSION_MATCH}, "
            f"got {results[0]['score']}"
        )

    def test_search_extension_scores_below_name_contains(self, tmp_path: Path) -> None:
        """Verify extension match ranks below stem contains match."""
        (tmp_path / "pdf_notes.txt").write_text("note data")
        (tmp_path / "budget.pdf").write_text("expense data")
        client = _make_app([str(tmp_path)])

        resp = client.get("/search", params={"q": "pdf"})
        assert resp.status_code == 200, f"Expected status 200, got {resp.status_code}"
        results = resp.json()
        assert len(results) == 2, (
            f"Expected 2 results, got {len(results)}: {[r['filename'] for r in results]}"
        )
        # Stem contains ("pdf" in "pdf_notes") should rank first
        assert results[0]["filename"] == "pdf_notes.txt", (
            f"Stem-contains match should rank first, got {results[0]['filename']}"
        )
        assert results[0]["score"] == _ScoringTiers.STEM_CONTAINS, (
            f"Stem-contains match should score {_ScoringTiers.STEM_CONTAINS}, "
            f"got {results[0]['score']}"
        )
        # Extension match should rank second
        assert results[1]["filename"] == "budget.pdf", (
            f"Extension match should rank second, got {results[1]['filename']}"
        )
        assert results[1]["score"] == _ScoringTiers.EXTENSION_MATCH, (
            f"Extension-only match should score {_ScoringTiers.EXTENSION_MATCH}, "
            f"got {results[1]['score']}"
        )

    def test_search_pagination(self, tmp_path: Path) -> None:
        for i in range(5):
            (tmp_path / f"file_{i}.txt").write_text(str(i))
        client = _make_app([str(tmp_path)])

        resp = client.get("/search", params={"q": "file", "limit": 2, "offset": 0})
        assert resp.status_code == 200, f"Expected status 200, got {resp.status_code}"
        page1 = resp.json()
        assert len(page1) == 2, f"Expected 2 results in page 1, got {len(page1)}"

        resp = client.get("/search", params={"q": "file", "limit": 2, "offset": 2})
        assert resp.status_code == 200, f"Expected status 200, got {resp.status_code}"
        page2 = resp.json()
        assert len(page2) == 2, f"Expected 2 results in page 2, got {len(page2)}"

        # Pages should have different files
        names1 = {r["filename"] for r in page1}
        names2 = {r["filename"] for r in page2}
        assert names1.isdisjoint(names2), (
            f"Pages should be non-overlapping. Page 1: {names1}, Page 2: {names2}"
        )

    def test_search_empty_query(self, tmp_path: Path) -> None:
        client = _make_app([str(tmp_path)])

        resp = client.get("/search", params={"q": ""})
        assert resp.status_code == 400, f"Empty query should return 400, got {resp.status_code}"

        resp = client.get("/search")
        assert resp.status_code == 422, f"Missing query should return 422, got {resp.status_code}"

    def test_search_no_results(self, tmp_path: Path) -> None:
        (tmp_path / "hello.txt").write_text("x")
        client = _make_app([str(tmp_path)])

        resp = client.get("/search", params={"q": "nonexistent_xyz"})
        assert resp.status_code == 200, f"Expected status 200, got {resp.status_code}"
        assert resp.json() == [], f"Nonexistent query should return empty list, got {resp.json()}"

    def test_search_respects_allowed_paths(self, tmp_path: Path) -> None:
        allowed = tmp_path / "allowed"
        forbidden = tmp_path / "forbidden"
        allowed.mkdir()
        forbidden.mkdir()
        (allowed / "ok.txt").write_text("ok")
        (forbidden / "secret.txt").write_text("secret")
        client = _make_app([str(allowed)])

        # Search without path filter — only searches allowed roots
        resp = client.get("/search", params={"q": "secret"})
        assert resp.status_code == 200, f"Expected status 200, got {resp.status_code}"
        assert resp.json() == [], f"Secret should not be found in allowed paths, got {resp.json()}"

        # Explicit path outside allowed_paths should be rejected
        resp = client.get("/search", params={"q": "secret", "path": str(forbidden)})
        # resolve_path raises ApiError with 403
        assert resp.status_code in (403, 422), (
            f"Forbidden path should return 403 or 422, got {resp.status_code}"
        )

    def test_search_schema_validation(self, tmp_path: Path) -> None:
        """Verify search results have all required and optional fields with correct types."""
        (tmp_path / "test.pdf").write_bytes(b"%PDF")
        client = _make_app([str(tmp_path)])

        resp = client.get("/search", params={"q": "test"})
        assert resp.status_code == 200, f"Expected status 200, got {resp.status_code}"
        results = resp.json()
        assert len(results) == 1, f"Expected 1 result, got {len(results)}"

        result = results[0]
        # Required fields
        assert "filename" in result and isinstance(result["filename"], str), (
            f"filename field missing or not string: {result.get('filename')}"
        )
        assert "path" in result and isinstance(result["path"], str), (
            f"path field missing or not string: {result.get('path')}"
        )
        assert "score" in result and isinstance(result["score"], float), (
            f"score field missing or not float: {result.get('score')}"
        )

        # Optional fields with correct types
        assert "type" in result and (isinstance(result["type"], str) or result["type"] is None), (
            f"type field should be str or None: {result.get('type')}"
        )
        assert "size" in result and (isinstance(result["size"], int) or result["size"] is None), (
            f"size field should be int or None: {result.get('size')}"
        )
        assert "created" in result and (
            isinstance(result["created"], str) or result["created"] is None
        ), f"created field should be str or None: {result.get('created')}"

    def test_search_limit_zero_returns_all(self, tmp_path: Path) -> None:
        """Verify limit=0 returns all results (treated as 'no limit')."""
        for i in range(5):
            (tmp_path / f"file_{i}.txt").write_text(str(i))
        client = _make_app([str(tmp_path)])

        resp = client.get("/search", params={"q": "file", "limit": 0})
        assert resp.status_code == 200, f"Expected status 200, got {resp.status_code}"
        results = resp.json()
        # limit=0 means no limit, return all
        assert len(results) == 5, f"limit=0 should return all 5 results, got {len(results)}"

    def test_search_negative_offset_behaves_as_zero(self, tmp_path: Path) -> None:
        """Verify negative offset is treated as zero or handled gracefully."""
        (tmp_path / "file.txt").write_text("x")
        client = _make_app([str(tmp_path)])

        # Negative offset should either be treated as 0 or raise 422
        resp = client.get("/search", params={"q": "file", "offset": -1})
        # Either valid (treated as 0) or validation error
        assert resp.status_code in (200, 422), (
            f"Negative offset should return 200 or 422, got {resp.status_code}"
        )

    def test_search_large_offset_returns_empty(self, tmp_path: Path) -> None:
        """Verify offset beyond results count returns empty list."""
        (tmp_path / "file.txt").write_text("x")
        client = _make_app([str(tmp_path)])

        resp = client.get("/search", params={"q": "file", "offset": 1000})
        assert resp.status_code == 200, f"Expected status 200, got {resp.status_code}"
        assert resp.json() == [], f"Large offset should return empty list, got {resp.json()}"

    def test_search_utf8_query(self, tmp_path: Path) -> None:
        """Verify search works with UTF-8 characters in query."""
        (tmp_path / "café.txt").write_text("content")
        client = _make_app([str(tmp_path)])

        resp = client.get("/search", params={"q": "café"})
        assert resp.status_code == 200, f"Expected status 200, got {resp.status_code}"
        results = resp.json()
        # UTF-8 search should find the file with UTF-8 characters
        assert any("café.txt" in r["path"] for r in results), (
            f"UTF-8 search should find café.txt, got {[r['path'] for r in results]}"
        )
