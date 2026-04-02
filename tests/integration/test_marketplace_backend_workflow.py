"""Integration coverage for marketplace backend workflows."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from file_organizer.api.dependencies import get_current_active_user
from file_organizer.api.exceptions import setup_exception_handlers
from file_organizer.api.routers.marketplace import router as marketplace_router
from file_organizer.plugins.marketplace.errors import (
    MarketplaceRepositoryError,
    MarketplaceSchemaError,
)
from file_organizer.plugins.marketplace.models import PluginPackage, PluginReview
from file_organizer.plugins.marketplace.repository import PluginRepository
from file_organizer.plugins.marketplace.service import MarketplaceService

pytestmark = pytest.mark.integration


def _package_payload(
    *,
    name: str,
    version: str,
    artifact: Path,
    description: str = "Useful plugin",
    tags: list[str] | None = None,
    category: str = "automation",
) -> dict[str, object]:
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    return {
        "name": name,
        "version": version,
        "author": "QA",
        "description": description,
        "homepage": "https://example.test/plugin",
        "download_url": artifact.name,
        "checksum_sha256": digest,
        "size_bytes": artifact.stat().st_size,
        "dependencies": [],
        "tags": tags or ["automation"],
        "category": category,
        "downloads": 7,
        "rating": 4.5,
        "reviews_count": 1,
        "min_organizer_version": "2.0.0",
        "max_organizer_version": None,
    }


def _write_plugin_archive(path: Path, plugin_name: str, version: str) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "plugin.py",
            (
                f"PLUGIN_NAME = {plugin_name!r}\n"
                f"PLUGIN_VERSION = {version!r}\n"
                "def register():\n"
                "    return 'ok'\n"
            ),
        )


@pytest.fixture()
def marketplace_service(tmp_path: Path) -> MarketplaceService:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    alpha_v1 = repo_dir / "alpha-1.0.0.zip"
    _write_plugin_archive(alpha_v1, "alpha-plugin", "1.0.0")
    alpha_v2 = repo_dir / "alpha-1.2.0.zip"
    _write_plugin_archive(alpha_v2, "alpha-plugin", "1.2.0")
    beta = repo_dir / "beta-1.0.0.zip"
    _write_plugin_archive(beta, "beta-plugin", "1.0.0")

    index = {
        "plugins": [
            _package_payload(
                name="alpha-plugin",
                version="1.0.0",
                artifact=alpha_v1,
                description="Alpha automation plugin",
                tags=["automation", "alpha"],
            ),
            _package_payload(
                name="alpha-plugin",
                version="1.2.0",
                artifact=alpha_v2,
                description="Alpha automation plugin improved",
                tags=["automation", "latest"],
            ),
            _package_payload(
                name="beta-plugin",
                version="1.0.0",
                artifact=beta,
                description="Beta search plugin",
                tags=["search"],
                category="search",
            ),
        ]
    }
    (repo_dir / "index.json").write_text(json.dumps(index), encoding="utf-8")
    return MarketplaceService(home_dir=tmp_path / "marketplace-home", repo_url=str(repo_dir))


@pytest.fixture()
def marketplace_client(
    monkeypatch: pytest.MonkeyPatch, marketplace_service: MarketplaceService
) -> TestClient:
    app = FastAPI()
    setup_exception_handlers(app)
    app.dependency_overrides[get_current_active_user] = lambda: type(
        "User",
        (),
        {"id": "reviewer-1", "username": "reviewer-1", "is_active": True},
    )()
    app.include_router(marketplace_router, prefix="/api/v1")
    monkeypatch.setattr(
        "file_organizer.api.routers.marketplace._service",
        lambda: marketplace_service,
    )
    return TestClient(app, raise_server_exceptions=False)


def test_marketplace_service_repository_and_routes(
    marketplace_service: MarketplaceService,
    marketplace_client: TestClient,
    tmp_path: Path,
) -> None:
    refreshed = marketplace_service.refresh_metadata()
    assert len(refreshed) == 3

    page = marketplace_service.list_plugins(page=1, per_page=2, query="alpha")
    assert len(page[0]) == 2
    assert page[1] == 2

    latest_alpha = marketplace_service.get_plugin("alpha-plugin")
    assert latest_alpha.version == "1.2.0"

    index_resp = marketplace_client.get("/api/v1/marketplace/plugins?q=alpha-plugin")
    assert index_resp.status_code == 200
    body = index_resp.json()
    assert body["total"] == 2
    assert {item["version"] for item in body["items"]} == {"1.0.0", "1.2.0"}

    details_resp = marketplace_client.get("/api/v1/marketplace/plugins/alpha-plugin")
    assert details_resp.status_code == 200
    assert details_resp.json()["version"] == "1.2.0"

    install_dir = tmp_path / "downloads"
    downloaded = marketplace_service.repository.download_plugin(latest_alpha, install_dir)
    assert downloaded.exists()
    assert marketplace_service.repository.verify_checksum(downloaded, latest_alpha.checksum_sha256)

    installed_v1 = marketplace_client.post(
        "/api/v1/marketplace/plugins/alpha-plugin/install",
        params={"version": "1.0.0"},
    )
    assert installed_v1.status_code == 200
    assert installed_v1.json()["version"] == "1.0.0"

    installed_list = marketplace_client.get("/api/v1/marketplace/installed")
    assert installed_list.status_code == 200
    assert [item["name"] for item in installed_list.json()] == ["alpha-plugin"]

    updates = marketplace_client.get("/api/v1/marketplace/updates")
    assert updates.status_code == 200
    assert updates.json() == ["alpha-plugin"]

    updated_resp = marketplace_client.post("/api/v1/marketplace/plugins/alpha-plugin/update")
    assert updated_resp.status_code == 200
    assert updated_resp.json()["updated"] is True
    assert updated_resp.json()["plugin"]["version"] == "1.2.0"

    updates_after = marketplace_client.get("/api/v1/marketplace/updates")
    assert updates_after.status_code == 200
    assert updates_after.json() == []

    review_resp = marketplace_client.post(
        "/api/v1/marketplace/plugins/alpha-plugin/reviews",
        json={"rating": 5, "title": "Great", "content": "Works well"},
    )
    assert review_resp.status_code == 200
    assert review_resp.json()["plugin_name"] == "alpha-plugin"

    review_list = marketplace_client.get("/api/v1/marketplace/plugins/alpha-plugin/reviews")
    assert review_list.status_code == 200
    assert len(review_list.json()) == 1

    average = marketplace_service.get_average_rating("alpha-plugin")
    assert average == 5.0

    uninstall_resp = marketplace_client.delete("/api/v1/marketplace/plugins/alpha-plugin")
    assert uninstall_resp.status_code == 200
    assert uninstall_resp.json() == {"uninstalled": True}

    installed_list_after = marketplace_client.get("/api/v1/marketplace/installed")
    assert installed_list_after.status_code == 200
    assert installed_list_after.json() == []


def test_marketplace_handles_invalid_repository_payload_and_network_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo_dir = tmp_path / "invalid-repo"
    repo_dir.mkdir()
    (repo_dir / "index.json").write_text(json.dumps({"plugins": [123]}), encoding="utf-8")
    invalid_repo = PluginRepository(str(repo_dir))
    with pytest.raises(MarketplaceSchemaError):
        invalid_repo.all_plugins()

    def raise_http_error(*args: object, **kwargs: object) -> object:
        request = httpx.Request("GET", "https://example.test/index.json")
        raise httpx.ConnectError("boom", request=request)

    class FailingClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def __enter__(self) -> FailingClient:
            return self

        def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
            return None

        get = raise_http_error

    monkeypatch.setattr("file_organizer.plugins.marketplace.repository.httpx.Client", FailingClient)
    http_repo = PluginRepository("https://example.test/repository")
    with pytest.raises(MarketplaceRepositoryError):
        http_repo.all_plugins()


def test_marketplace_routes_map_not_found_and_checksum_errors(
    marketplace_client: TestClient,
    marketplace_service: MarketplaceService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing_plugin(name: str, *, version: str | None = None) -> PluginPackage:
        raise MarketplaceRepositoryError(f"Plugin '{name}' not found.")

    monkeypatch.setattr(marketplace_service.repository, "get_plugin", missing_plugin)
    details_resp = marketplace_client.get("/api/v1/marketplace/plugins/missing-plugin")
    assert details_resp.status_code == 404
    assert details_resp.json()["error"] == "not_found"

    def checksum_failure(name: str, *, version: str | None = None) -> object:
        raise MarketplaceRepositoryError("Checksum verification failed for plugin 'alpha-plugin'.")

    monkeypatch.setattr(marketplace_service.installer, "install", checksum_failure)
    install_resp = marketplace_client.post("/api/v1/marketplace/plugins/alpha-plugin/install")
    assert install_resp.status_code == 422
    assert install_resp.json()["error"] == "checksum_failed"


def test_review_manager_roundtrip_and_helpful_counts(
    marketplace_service: MarketplaceService,
) -> None:
    review = PluginReview(
        plugin_name="beta-plugin",
        user_id="alice",
        rating=4,
        title="Solid",
        content="Search features work",
    )
    marketplace_service.add_review(review)
    marketplace_service.review_manager.mark_helpful("beta-plugin", "alice", "bob")

    stored = marketplace_service.get_reviews("beta-plugin", limit=5)
    assert len(stored) == 1
    assert stored[0].helpful_count == 1
    assert stored[0].rating == 4
