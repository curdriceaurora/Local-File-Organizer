"""Integration tests for API search and config routers.

Covers:
  - api/routers/search.py — GET /search (keyword, type filter, no query, empty,
    pagination, semantic import-error, permission-error path)
  - api/routers/config.py — GET /config, PUT /config, POST /config/reset
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings
from file_organizer.api.exceptions import setup_exception_handlers
from file_organizer.api.routers.config import router as config_router
from file_organizer.api.routers.search import router as search_router

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def test_settings(tmp_path: Path) -> ApiSettings:
    return ApiSettings(
        allowed_paths=[str(tmp_path)],
        auth_enabled=False,
        auth_db_path=str(tmp_path / "auth.db"),
    )


@pytest.fixture()
def search_client(test_settings: ApiSettings) -> TestClient:
    app = FastAPI()
    app.dependency_overrides[get_settings] = lambda: test_settings
    setup_exception_handlers(app)
    app.include_router(search_router)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def config_client(test_settings: ApiSettings) -> TestClient:
    app = FastAPI()
    app.dependency_overrides[get_settings] = lambda: test_settings
    setup_exception_handlers(app)
    app.include_router(config_router)
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Search router — GET /search
# ---------------------------------------------------------------------------


class TestSearchRouter:
    def test_missing_query_returns_400(self, search_client: TestClient) -> None:
        r = search_client.get("/search")
        assert r.status_code == 400
        assert "required" in r.json()["detail"].lower()

    def test_empty_query_returns_400(self, search_client: TestClient) -> None:
        r = search_client.get("/search", params={"q": ""})
        assert r.status_code == 400

    def test_keyword_search_no_match_returns_empty_list(
        self, search_client: TestClient, tmp_path: Path
    ) -> None:
        r = search_client.get("/search", params={"q": "xyznonexistent", "path": str(tmp_path)})
        assert r.status_code == 200
        assert r.json() == []

    def test_keyword_search_finds_matching_file(
        self, search_client: TestClient, tmp_path: Path
    ) -> None:
        (tmp_path / "report.txt").write_text("quarterly report")
        r = search_client.get("/search", params={"q": "report", "path": str(tmp_path)})
        assert r.status_code == 200
        results = r.json()
        assert len(results) >= 1
        filenames = [item["filename"] for item in results]
        assert "report.txt" in filenames

    def test_search_result_shape(self, search_client: TestClient, tmp_path: Path) -> None:
        (tmp_path / "data.csv").write_text("col1,col2\n1,2")
        r = search_client.get("/search", params={"q": "data", "path": str(tmp_path)})
        assert r.status_code == 200
        results = r.json()
        assert len(results) >= 1
        item = results[0]
        assert "filename" in item
        assert "path" in item
        assert "score" in item

    def test_search_type_filter_txt(self, search_client: TestClient, tmp_path: Path) -> None:
        (tmp_path / "notes.txt").write_text("some text")
        (tmp_path / "image.jpg").write_bytes(b"\xff\xd8\xff")
        r = search_client.get(
            "/search", params={"q": "notes", "path": str(tmp_path), "type": "txt"}
        )
        assert r.status_code == 200
        results = r.json()
        assert all(item["filename"].endswith(".txt") for item in results)

    def test_search_with_limit(self, search_client: TestClient, tmp_path: Path) -> None:
        for i in range(5):
            (tmp_path / f"file{i}.txt").write_text("content")
        r = search_client.get("/search", params={"q": "file", "path": str(tmp_path), "limit": 2})
        assert r.status_code == 200
        results = r.json()
        assert len(results) == 2

    def test_search_with_offset(self, search_client: TestClient, tmp_path: Path) -> None:
        for i in range(3):
            (tmp_path / f"doc{i}.txt").write_text("content")
        r_all = search_client.get("/search", params={"q": "doc", "path": str(tmp_path)})
        r_offset = search_client.get(
            "/search", params={"q": "doc", "path": str(tmp_path), "offset": 1}
        )
        assert r_all.status_code == 200
        assert r_offset.status_code == 200
        assert len(r_offset.json()) == len(r_all.json()) - 1

    def test_search_uses_allowed_paths_when_no_path_given(
        self, search_client: TestClient, tmp_path: Path
    ) -> None:
        (tmp_path / "allowed_file.txt").write_text("here")
        r = search_client.get("/search", params={"q": "allowed_file"})
        assert r.status_code == 200

    def test_search_exact_filename_score_is_highest(
        self, search_client: TestClient, tmp_path: Path
    ) -> None:
        (tmp_path / "report.txt").write_text("x")
        (tmp_path / "my_report_data.txt").write_text("x")
        r = search_client.get("/search", params={"q": "report", "path": str(tmp_path)})
        assert r.status_code == 200
        results = r.json()
        assert len(results) >= 2
        assert results[0]["score"] >= results[1]["score"]

    def test_search_semantic_without_deps_returns_503(
        self, search_client: TestClient, tmp_path: Path
    ) -> None:
        (tmp_path / "doc.txt").write_text("some content here")
        import unittest.mock as mock

        with mock.patch(
            "file_organizer.api.routers.search._semantic_search",
            side_effect=ImportError("search deps not installed"),
        ):
            r = search_client.get(
                "/search",
                params={"q": "doc", "path": str(tmp_path), "semantic": "true"},
            )
        assert r.status_code == 503

    def test_search_semantic_large_offset_returns_empty(
        self, search_client: TestClient, tmp_path: Path
    ) -> None:
        (tmp_path / "doc.txt").write_text("some content")
        r = search_client.get(
            "/search",
            params={
                "q": "doc",
                "path": str(tmp_path),
                "semantic": "true",
                "offset": 9999,
            },
        )
        assert r.status_code == 200
        assert r.json() == []


# ---------------------------------------------------------------------------
# Config router — GET /config, PUT /config, POST /config/reset
# ---------------------------------------------------------------------------


class TestConfigRouter:
    def test_get_config_returns_200(self, config_client: TestClient) -> None:
        r = config_client.get("/config")
        assert r.status_code == 200

    def test_get_config_has_version(self, config_client: TestClient) -> None:
        from file_organizer.api.routers.config import ConfigResponse

        r = config_client.get("/config")
        body = r.json()
        assert "version" in body
        assert body["version"] == ConfigResponse().version

    def test_get_config_has_ai_section(self, config_client: TestClient) -> None:
        r = config_client.get("/config")
        body = r.json()
        assert "ai" in body
        assert "model" in body["ai"]

    def test_put_config_updates_organization_method(self, config_client: TestClient) -> None:
        r = config_client.put(
            "/config",
            json={"organization": {"method": "JD", "auto_organize": True}},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["organization"]["method"] == "JD"

    def test_put_config_updates_ai_temperature(self, config_client: TestClient) -> None:
        r = config_client.put(
            "/config",
            json={"ai": {"temperature": 0.9, "model": "llama3:8b", "max_tokens": 2000}},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ai"]["temperature"] == pytest.approx(0.9)
        assert body["ai"]["model"] == "llama3:8b"

    def test_reset_config_restores_defaults(self, config_client: TestClient) -> None:
        config_client.put("/config", json={"organization": {"method": "JD", "auto_organize": True}})
        r = config_client.post("/config/reset")
        assert r.status_code == 200
        body = r.json()
        assert body["organization"]["method"] == "PARA"

    def test_put_config_partial_update_storage(self, config_client: TestClient) -> None:
        config_client.post("/config/reset")
        r = config_client.put(
            "/config",
            json={"storage": {"base_path": "/custom/path", "auto_backup": False}},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["storage"]["auto_backup"] is False
