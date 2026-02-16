"""API tests for marketplace routes."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from file_organizer.api.test_utils import create_auth_client
from file_organizer.plugins.marketplace import compute_sha256

pytestmark = pytest.mark.ci


def _plugin_archive(repo_dir: Path, *, name: str, version: str) -> dict[str, object]:
    archive_name = f"{name}-{version}.zip"
    archive_path = repo_dir / archive_name
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "plugin.py",
            "\n".join(
                [
                    "from file_organizer.plugins import Plugin, PluginMetadata",
                    "",
                    "class ApiMarketplacePlugin(Plugin):",
                    "    def get_metadata(self):",
                    f"        return PluginMetadata(name='{name}', version='{version}', author='tests', description='api plugin')",
                    "    def on_load(self): pass",
                    "    def on_enable(self): pass",
                    "    def on_disable(self): pass",
                    "    def on_unload(self): pass",
                ]
            ),
        )
    return {
        "name": name,
        "version": version,
        "author": "tests",
        "description": f"{name} plugin",
        "download_url": archive_name,
        "checksum_sha256": compute_sha256(archive_path),
        "size_bytes": archive_path.stat().st_size,
        "dependencies": [],
        "tags": ["utility"],
        "category": "utility",
        "license": "MIT",
        "min_organizer_version": "2.0.0",
        "max_organizer_version": None,
        "downloads": 10,
        "rating": 4.5,
        "reviews_count": 2,
    }


def _write_repo(repo_dir: Path, plugins: list[dict[str, object]]) -> None:
    (repo_dir / "index.json").write_text(json.dumps({"plugins": plugins}, indent=2), encoding="utf-8")


def _build_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    alpha_v1 = _plugin_archive(repo_dir, name="alpha", version="1.0.0")
    alpha_v2 = _plugin_archive(repo_dir, name="alpha", version="1.1.0")
    beta = _plugin_archive(repo_dir, name="beta", version="2.0.0")
    _write_repo(repo_dir, [alpha_v1, alpha_v2, beta])

    monkeypatch.setenv("FO_MARKETPLACE_HOME", str(tmp_path / "marketplace-home"))
    monkeypatch.setenv("FO_MARKETPLACE_REPO_URL", str(repo_dir))
    client, headers, _ = create_auth_client(tmp_path, allowed_paths=[str(tmp_path)])
    return client, headers


def test_marketplace_list_and_get(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client, headers = _build_client(tmp_path, monkeypatch)

    listing = client.get("/api/v1/marketplace/plugins", headers=headers)
    assert listing.status_code == 200
    payload = listing.json()
    assert payload["total"] == 3
    names = {item["name"] for item in payload["items"]}
    assert {"alpha", "beta"}.issubset(names)

    details = client.get("/api/v1/marketplace/plugins/alpha", headers=headers)
    assert details.status_code == 200
    assert details.json()["name"] == "alpha"


def test_marketplace_install_updates_and_reviews(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, headers = _build_client(tmp_path, monkeypatch)

    install = client.post(
        "/api/v1/marketplace/plugins/alpha/install",
        params={"version": "1.0.0"},
        headers=headers,
    )
    assert install.status_code == 200
    assert install.json()["version"] == "1.0.0"

    installed = client.get("/api/v1/marketplace/installed", headers=headers)
    assert installed.status_code == 200
    assert installed.json()[0]["name"] == "alpha"

    updates = client.get("/api/v1/marketplace/updates", headers=headers)
    assert updates.status_code == 200
    assert "alpha" in updates.json()

    update = client.post("/api/v1/marketplace/plugins/alpha/update", headers=headers)
    assert update.status_code == 200
    assert update.json()["updated"] is True
    assert update.json()["plugin"]["version"] == "1.1.0"

    review = client.post(
        "/api/v1/marketplace/plugins/alpha/reviews",
        json={"rating": 5, "title": "Great", "content": "Very useful"},
        headers=headers,
    )
    assert review.status_code == 200
    assert review.json()["rating"] == 5

    reviews = client.get("/api/v1/marketplace/plugins/alpha/reviews", headers=headers)
    assert reviews.status_code == 200
    assert len(reviews.json()) >= 1

    uninstall = client.delete("/api/v1/marketplace/plugins/alpha", headers=headers)
    assert uninstall.status_code == 200
    assert uninstall.json()["uninstalled"] is True

