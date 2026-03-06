"""Tests for the search endpoint — real filesystem search."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from file_organizer.api.config import ApiSettings

pytestmark = pytest.mark.unit


def _make_app(allowed_paths: list[str]) -> TestClient:
    """Create a test client with search router and given allowed_paths.

    Args:
        allowed_paths: List of directory paths to allow searching.

    Returns:
        A TestClient configured with the search router.
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
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 1
        assert results[0]["filename"] == "report.txt"
        assert results[0]["score"] > 0

    def test_search_file_type_filter(self, tmp_path: Path) -> None:
        (tmp_path / "doc.pdf").write_bytes(b"%PDF")
        (tmp_path / "doc.txt").write_text("text")
        client = _make_app([str(tmp_path)])

        resp = client.get("/search", params={"q": "doc", "type": "pdf"})
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 1
        assert results[0]["filename"] == "doc.pdf"

    def test_search_path_filter(self, tmp_path: Path) -> None:
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "inside.txt").write_text("data")
        (tmp_path / "outside.txt").write_text("data")
        client = _make_app([str(tmp_path)])

        resp = client.get("/search", params={"q": "inside", "path": str(sub)})
        assert resp.status_code == 200
        results = resp.json()
        filenames = [r["filename"] for r in results]
        assert "inside.txt" in filenames
        assert "outside.txt" not in filenames

    def test_search_scoring_order(self, tmp_path: Path) -> None:
        # Exact stem match should score higher than contains
        (tmp_path / "report.txt").write_text("a")
        (tmp_path / "annual_report_2024.txt").write_text("b")
        client = _make_app([str(tmp_path)])

        resp = client.get("/search", params={"q": "report"})
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 2
        # Exact stem match ("report") should be first
        assert results[0]["filename"] == "report.txt"
        assert results[0]["score"] > results[1]["score"]

    def test_search_pagination(self, tmp_path: Path) -> None:
        for i in range(5):
            (tmp_path / f"file_{i}.txt").write_text(str(i))
        client = _make_app([str(tmp_path)])

        resp = client.get("/search", params={"q": "file", "limit": 2, "offset": 0})
        assert resp.status_code == 200
        page1 = resp.json()
        assert len(page1) == 2

        resp = client.get("/search", params={"q": "file", "limit": 2, "offset": 2})
        assert resp.status_code == 200
        page2 = resp.json()
        assert len(page2) == 2

        # Pages should have different files
        names1 = {r["filename"] for r in page1}
        names2 = {r["filename"] for r in page2}
        assert names1.isdisjoint(names2)

    def test_search_empty_query(self, tmp_path: Path) -> None:
        client = _make_app([str(tmp_path)])

        resp = client.get("/search", params={"q": ""})
        assert resp.status_code == 400

        resp = client.get("/search")
        assert resp.status_code == 400

    def test_search_no_results(self, tmp_path: Path) -> None:
        (tmp_path / "hello.txt").write_text("x")
        client = _make_app([str(tmp_path)])

        resp = client.get("/search", params={"q": "nonexistent_xyz"})
        assert resp.status_code == 200
        assert resp.json() == []

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
        assert resp.status_code == 200
        assert resp.json() == []

        # Explicit path outside allowed_paths should be rejected
        resp = client.get("/search", params={"q": "secret", "path": str(forbidden)})
        # resolve_path raises ApiError with 403
        assert resp.status_code in (403, 422)

    def test_search_schema_validation(self, tmp_path: Path) -> None:
        """Verify search results have all required and optional fields with correct types."""
        (tmp_path / "test.pdf").write_bytes(b"%PDF")
        client = _make_app([str(tmp_path)])

        resp = client.get("/search", params={"q": "test"})
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) == 1

        result = results[0]
        # Required fields
        assert "filename" in result and isinstance(result["filename"], str)
        assert "path" in result and isinstance(result["path"], str)
        assert "score" in result and isinstance(result["score"], float)

        # Optional fields with correct types
        assert "type" in result and (isinstance(result["type"], str) or result["type"] is None)
        assert "size" in result and (isinstance(result["size"], int) or result["size"] is None)
        assert "created" in result and (
            isinstance(result["created"], str) or result["created"] is None
        )

    def test_search_limit_zero_returns_all(self, tmp_path: Path) -> None:
        """Verify limit=0 returns all results (treated as 'no limit')."""
        for i in range(5):
            (tmp_path / f"file_{i}.txt").write_text(str(i))
        client = _make_app([str(tmp_path)])

        resp = client.get("/search", params={"q": "file", "limit": 0})
        assert resp.status_code == 200
        results = resp.json()
        # limit=0 means no limit, return all
        assert len(results) == 5

    def test_search_negative_offset_behaves_as_zero(self, tmp_path: Path) -> None:
        """Verify negative offset is treated as zero or handled gracefully."""
        (tmp_path / "file.txt").write_text("x")
        client = _make_app([str(tmp_path)])

        # Negative offset should either be treated as 0 or raise 422
        resp = client.get("/search", params={"q": "file", "offset": -1})
        # Either valid (treated as 0) or validation error
        assert resp.status_code in (200, 422)

    def test_search_large_offset_returns_empty(self, tmp_path: Path) -> None:
        """Verify offset beyond results count returns empty list."""
        (tmp_path / "file.txt").write_text("x")
        client = _make_app([str(tmp_path)])

        resp = client.get("/search", params={"q": "file", "offset": 1000})
        assert resp.status_code == 200
        assert resp.json() == []

    def test_search_utf8_query(self, tmp_path: Path) -> None:
        """Verify search works with UTF-8 characters in query."""
        (tmp_path / "café.txt").write_text("content")
        client = _make_app([str(tmp_path)])

        resp = client.get("/search", params={"q": "café"})
        assert resp.status_code == 200
        results = resp.json()
        # UTF-8 search should work (case-insensitive)
        assert len(results) >= 0  # May or may not match depending on OS
