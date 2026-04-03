"""Comprehensive tests for the marketplace API router."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import (
    get_current_active_user,
    get_settings,
)
from file_organizer.api.exceptions import setup_exception_handlers
from file_organizer.api.routers.marketplace import MarketplaceReviewRequest, router
from file_organizer.plugins.marketplace import (
    InstalledPlugin,
    MarketplaceError,
    PluginPackage,
    PluginReview,
)

pytestmark = pytest.mark.ci


def _build_app(
    mock_service: MagicMock | None = None,
) -> tuple[FastAPI, TestClient]:
    """Create a FastAPI app with marketplace router and optional service mock."""
    settings = ApiSettings(environment="test", auth_enabled=False)
    app = FastAPI()
    setup_exception_handlers(app)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_current_active_user] = lambda: MagicMock(
        is_active=True, is_admin=True, id="test-user-id"
    )

    if mock_service:
        # Override the _service function in marketplace router
        import file_organizer.api.routers.marketplace as mp

        mp._service = lambda: mock_service

    app.include_router(router, prefix="/api/v1")
    client = TestClient(app)
    return app, client


# Sample plugin data for use in tests
def _sample_plugin() -> PluginPackage:
    """Create a sample plugin package for testing."""
    return PluginPackage(
        name="test-plugin",
        version="1.0.0",
        author="Test Author",
        description="A test plugin",
        download_url="https://example.com/test-plugin.zip",
        checksum_sha256="abc123def456",
        size_bytes=1024,
        homepage="https://example.com",
        category="organization",
        tags=("test", "demo"),
        dependencies=("plugin-base>=1.0",),
        downloads=100,
        rating=4.5,
        reviews_count=10,
        min_organizer_version="1.0.0",
        max_organizer_version="2.0.0",
    )


def _sample_installed() -> InstalledPlugin:
    """Create a sample installed plugin for testing."""
    return InstalledPlugin(
        name="test-plugin",
        version="1.0.0",
        source_url="https://example.com/test-plugin.zip",
        installed_at=datetime.now(UTC).isoformat(),
    )


def _sample_review() -> PluginReview:
    """Create a sample review for testing."""
    return PluginReview(
        plugin_name="test-plugin",
        user_id="test-user-id",
        rating=5,
        title="Great plugin!",
        content="This plugin is awesome.",
        created_at=datetime.now(UTC).isoformat(),
        updated_at=datetime.now(UTC).isoformat(),
        helpful_count=42,
    )


@pytest.mark.unit
class TestListPlugins:
    """Tests for GET /api/v1/marketplace/plugins."""

    def test_list_plugins_success(self) -> None:
        """Test listing available plugins."""
        mock_service = MagicMock()
        mock_service.list_plugins.return_value = (
            [_sample_plugin()],
            1,  # total
        )
        _, client = _build_app(mock_service)

        resp = client.get("/api/v1/marketplace/plugins")
        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert "page" in body
        assert "per_page" in body
        assert "total" in body
        assert len(body["items"]) == 1
        assert body["items"][0]["name"] == "test-plugin"
        assert body["page"] == 1
        assert body["total"] == 1

    def test_list_plugins_with_filters(self) -> None:
        """Test listing plugins with query and category filter."""
        mock_service = MagicMock()
        mock_service.list_plugins.return_value = ([], 0)
        _, client = _build_app(mock_service)

        resp = client.get(
            "/api/v1/marketplace/plugins",
            params={"q": "test", "category": "organization", "page": 1, "per_page": 10},
        )
        assert resp.status_code == 200
        mock_service.list_plugins.assert_called_once_with(
            page=1,
            per_page=10,
            query="test",
            tags=None,
            category="organization",
        )

    def test_list_plugins_pagination(self) -> None:
        """Test listing plugins with custom pagination."""
        mock_service = MagicMock()
        mock_service.list_plugins.return_value = ([_sample_plugin()], 50)
        _, client = _build_app(mock_service)

        resp = client.get("/api/v1/marketplace/plugins", params={"page": 2, "per_page": 25})
        assert resp.status_code == 200
        body = resp.json()
        assert body["page"] == 2
        assert body["per_page"] == 25
        assert body["total"] == 50

    def test_list_plugins_with_tags_filter(self) -> None:
        """Test listing plugins filtered by tags."""
        mock_service = MagicMock()
        mock_service.list_plugins.return_value = ([], 0)
        _, client = _build_app(mock_service)

        resp = client.get("/api/v1/marketplace/plugins", params={"tags": ["test", "demo"]})
        assert resp.status_code == 200
        mock_service.list_plugins.assert_called_once()
        call_kwargs = mock_service.list_plugins.call_args[1]
        assert call_kwargs["tags"] == ["test", "demo"]

    def test_list_plugins_marketplace_error(self) -> None:
        """Test listing plugins when marketplace service errors."""
        mock_service = MagicMock()
        mock_service.list_plugins.side_effect = MarketplaceError("Service unavailable")
        _, client = _build_app(mock_service)

        resp = client.get("/api/v1/marketplace/plugins")
        assert resp.status_code == 400
        body = resp.json()
        assert "error" in body


@pytest.mark.unit
class TestGetPlugin:
    """Tests for GET /api/v1/marketplace/plugins/{name}."""

    def test_get_plugin_success(self) -> None:
        """Test getting a single plugin by name."""
        mock_service = MagicMock()
        mock_service.get_plugin.return_value = _sample_plugin()
        _, client = _build_app(mock_service)

        resp = client.get("/api/v1/marketplace/plugins/test-plugin")
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "test-plugin"
        assert body["version"] == "1.0.0"
        assert body["author"] == "Test Author"
        assert body["category"] == "organization"
        mock_service.get_plugin.assert_called_once_with("test-plugin")

    def test_get_plugin_not_found(self) -> None:
        """Test getting nonexistent plugin."""
        mock_service = MagicMock()
        mock_service.get_plugin.side_effect = MarketplaceError("Plugin not found")
        _, client = _build_app(mock_service)

        resp = client.get("/api/v1/marketplace/plugins/nonexistent")
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"] == "not_found"


@pytest.mark.unit
class TestListInstalledPlugins:
    """Tests for GET /api/v1/marketplace/installed."""

    def test_list_installed_success(self) -> None:
        """Test listing installed plugins."""
        mock_service = MagicMock()
        mock_service.list_installed.return_value = [_sample_installed()]
        _, client = _build_app(mock_service)

        resp = client.get("/api/v1/marketplace/installed")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) == 1
        assert body[0]["name"] == "test-plugin"
        assert body[0]["version"] == "1.0.0"

    def test_list_installed_empty(self) -> None:
        """Test listing installed plugins when none are installed."""
        mock_service = MagicMock()
        mock_service.list_installed.return_value = []
        _, client = _build_app(mock_service)

        resp = client.get("/api/v1/marketplace/installed")
        assert resp.status_code == 200
        body = resp.json()
        assert body == []

    def test_list_installed_error(self) -> None:
        """Test listing installed plugins when service errors."""
        mock_service = MagicMock()
        mock_service.list_installed.side_effect = MarketplaceError("Service error")
        _, client = _build_app(mock_service)

        resp = client.get("/api/v1/marketplace/installed")
        assert resp.status_code == 400


@pytest.mark.unit
class TestListAvailableUpdates:
    """Tests for GET /api/v1/marketplace/updates."""

    def test_list_updates_available(self) -> None:
        """Test listing plugins with available updates."""
        mock_service = MagicMock()
        mock_service.check_updates.return_value = ["plugin1", "plugin2"]
        _, client = _build_app(mock_service)

        resp = client.get("/api/v1/marketplace/updates")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) == 2
        assert "plugin1" in body

    def test_list_updates_none_available(self) -> None:
        """Test when no updates are available."""
        mock_service = MagicMock()
        mock_service.check_updates.return_value = []
        _, client = _build_app(mock_service)

        resp = client.get("/api/v1/marketplace/updates")
        assert resp.status_code == 200
        body = resp.json()
        assert body == []

    def test_list_updates_error(self) -> None:
        """Test listing updates when service errors."""
        mock_service = MagicMock()
        mock_service.check_updates.side_effect = MarketplaceError("Check failed")
        _, client = _build_app(mock_service)

        resp = client.get("/api/v1/marketplace/updates")
        assert resp.status_code == 400


@pytest.mark.unit
class TestInstallPlugin:
    """Tests for POST /api/v1/marketplace/plugins/{name}/install."""

    def test_install_plugin_success(self) -> None:
        """Test installing a plugin."""
        mock_service = MagicMock()
        mock_service.install.return_value = _sample_installed()
        _, client = _build_app(mock_service)

        resp = client.post("/api/v1/marketplace/plugins/test-plugin/install")
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "test-plugin"
        assert body["version"] == "1.0.0"
        mock_service.install.assert_called_once_with("test-plugin", version=None)

    def test_install_plugin_with_version(self) -> None:
        """Test installing a specific version."""
        mock_service = MagicMock()
        mock_service.install.return_value = _sample_installed()
        _, client = _build_app(mock_service)

        resp = client.post(
            "/api/v1/marketplace/plugins/test-plugin/install", params={"version": "1.5.0"}
        )
        assert resp.status_code == 200
        mock_service.install.assert_called_once_with("test-plugin", version="1.5.0")

    def test_install_plugin_not_found(self) -> None:
        """Test installing nonexistent plugin."""
        mock_service = MagicMock()
        mock_service.install.side_effect = MarketplaceError("Plugin not found")
        _, client = _build_app(mock_service)

        resp = client.post("/api/v1/marketplace/plugins/nonexistent/install")
        assert resp.status_code == 404

    def test_install_plugin_checksum_error(self) -> None:
        """Test install with checksum failure."""
        mock_service = MagicMock()
        mock_service.install.side_effect = MarketplaceError("Checksum verification failed")
        _, client = _build_app(mock_service)

        resp = client.post("/api/v1/marketplace/plugins/test-plugin/install")
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"] == "checksum_failed"


@pytest.mark.unit
class TestUninstallPlugin:
    """Tests for DELETE /api/v1/marketplace/plugins/{name}."""

    def test_uninstall_plugin_success(self) -> None:
        """Test uninstalling a plugin."""
        mock_service = MagicMock()
        mock_service.uninstall.return_value = None
        _, client = _build_app(mock_service)

        resp = client.delete("/api/v1/marketplace/plugins/test-plugin")
        assert resp.status_code == 200
        body = resp.json()
        assert body["uninstalled"] is True
        mock_service.uninstall.assert_called_once_with("test-plugin")

    def test_uninstall_nonexistent_plugin(self) -> None:
        """Test uninstalling plugin that isn't installed."""
        mock_service = MagicMock()
        mock_service.uninstall.side_effect = MarketplaceError("Plugin not found")
        _, client = _build_app(mock_service)

        resp = client.delete("/api/v1/marketplace/plugins/nonexistent")
        assert resp.status_code == 404

    def test_uninstall_plugin_error(self) -> None:
        """Test uninstall when service encounters error."""
        mock_service = MagicMock()
        mock_service.uninstall.side_effect = MarketplaceError("Uninstall failed")
        _, client = _build_app(mock_service)

        resp = client.delete("/api/v1/marketplace/plugins/test-plugin")
        assert resp.status_code == 400


@pytest.mark.unit
class TestUpdatePlugin:
    """Tests for POST /api/v1/marketplace/plugins/{name}/update."""

    def test_update_plugin_success(self) -> None:
        """Test updating an installed plugin."""
        mock_service = MagicMock()
        mock_service.update.return_value = _sample_installed()
        _, client = _build_app(mock_service)

        resp = client.post("/api/v1/marketplace/plugins/test-plugin/update")
        assert resp.status_code == 200
        body = resp.json()
        assert body["updated"] is True
        assert body["plugin"]["name"] == "test-plugin"
        assert body["plugin"]["version"] == "1.0.0"
        mock_service.update.assert_called_once_with("test-plugin")

    def test_update_plugin_no_update_available(self) -> None:
        """Test update when no update is available."""
        mock_service = MagicMock()
        mock_service.update.return_value = None
        _, client = _build_app(mock_service)

        resp = client.post("/api/v1/marketplace/plugins/test-plugin/update")
        assert resp.status_code == 200
        body = resp.json()
        assert body["updated"] is False
        assert body["plugin"] is None

    def test_update_nonexistent_plugin(self) -> None:
        """Test updating plugin that isn't installed."""
        mock_service = MagicMock()
        mock_service.update.side_effect = MarketplaceError("Plugin not found")
        _, client = _build_app(mock_service)

        resp = client.post("/api/v1/marketplace/plugins/nonexistent/update")
        assert resp.status_code == 404


@pytest.mark.unit
class TestListReviews:
    """Tests for GET /api/v1/marketplace/plugins/{name}/reviews."""

    def test_list_reviews_success(self) -> None:
        """Test listing reviews for a plugin."""
        mock_service = MagicMock()
        mock_service.get_reviews.return_value = [_sample_review()]
        _, client = _build_app(mock_service)

        resp = client.get("/api/v1/marketplace/plugins/test-plugin/reviews")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) == 1
        assert body[0]["plugin_name"] == "test-plugin"
        assert body[0]["rating"] == 5
        mock_service.get_reviews.assert_called_once_with("test-plugin", limit=10)

    def test_list_reviews_custom_limit(self) -> None:
        """Test listing reviews with custom limit."""
        mock_service = MagicMock()
        mock_service.get_reviews.return_value = []
        _, client = _build_app(mock_service)

        resp = client.get("/api/v1/marketplace/plugins/test-plugin/reviews", params={"limit": 50})
        assert resp.status_code == 200
        mock_service.get_reviews.assert_called_once_with("test-plugin", limit=50)

    def test_list_reviews_no_reviews(self) -> None:
        """Test listing reviews when none exist."""
        mock_service = MagicMock()
        mock_service.get_reviews.return_value = []
        _, client = _build_app(mock_service)

        resp = client.get("/api/v1/marketplace/plugins/test-plugin/reviews")
        assert resp.status_code == 200
        body = resp.json()
        assert body == []

    def test_list_reviews_plugin_not_found(self) -> None:
        """Test listing reviews for nonexistent plugin."""
        mock_service = MagicMock()
        mock_service.get_reviews.side_effect = MarketplaceError("Plugin not found")
        _, client = _build_app(mock_service)

        resp = client.get("/api/v1/marketplace/plugins/nonexistent/reviews")
        assert resp.status_code == 404


@pytest.mark.unit
class TestAddReview:
    """Tests for POST /api/v1/marketplace/plugins/{name}/reviews."""

    def test_add_review_success(self) -> None:
        """Test submitting a review for a plugin."""
        mock_service = MagicMock()
        mock_service.add_review.return_value = None
        mock_service.get_reviews.return_value = [_sample_review()]
        _, client = _build_app(mock_service)

        payload = {
            "rating": 5,
            "title": "Great plugin!",
            "content": "This plugin is awesome.",
        }
        resp = client.post("/api/v1/marketplace/plugins/test-plugin/reviews", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["plugin_name"] == "test-plugin"
        assert body["rating"] == 5
        assert body["title"] == "Great plugin!"
        assert body["user_id"] == "test-user-id"

    def test_add_review_invalid_rating(self) -> None:
        """Test adding review with invalid rating."""
        mock_service = MagicMock()
        _, client = _build_app(mock_service)

        payload = {
            "rating": 10,  # Invalid: must be 1-5
            "title": "Great!",
            "content": "Good plugin.",
        }
        resp = client.post("/api/v1/marketplace/plugins/test-plugin/reviews", json=payload)
        assert resp.status_code == 422  # Validation error

    def test_add_review_empty_title(self) -> None:
        """Test adding review with empty title."""
        mock_service = MagicMock()
        _, client = _build_app(mock_service)

        payload = {
            "rating": 5,
            "title": "",  # Invalid: min_length=1
            "content": "Good plugin.",
        }
        resp = client.post("/api/v1/marketplace/plugins/test-plugin/reviews", json=payload)
        assert resp.status_code == 422

    def test_add_review_whitespace_only_title(self) -> None:
        """Test adding review rejects titles that become empty after stripping."""
        mock_service = MagicMock()
        _, client = _build_app(mock_service)

        payload = {
            "rating": 5,
            "title": "   ",
            "content": "Good plugin.",
        }
        resp = client.post("/api/v1/marketplace/plugins/test-plugin/reviews", json=payload)
        assert resp.status_code == 422

    def test_add_review_whitespace_content_is_normalized(self) -> None:
        """Test adding review strips leading and trailing whitespace from content fields."""
        mock_service = MagicMock()
        mock_service.add_review.return_value = None
        mock_service.get_reviews.return_value = [_sample_review()]
        _, client = _build_app(mock_service)

        payload = {
            "rating": 5,
            "title": "  Great plugin!  ",
            "content": "  This plugin is awesome.  ",
        }
        resp = client.post("/api/v1/marketplace/plugins/test-plugin/reviews", json=payload)

        assert resp.status_code == 200
        review = mock_service.add_review.call_args.args[0]
        assert review.title == "Great plugin!"
        assert review.content == "This plugin is awesome."

    def test_add_review_plugin_not_found(self) -> None:
        """Test adding review for nonexistent plugin."""
        mock_service = MagicMock()
        mock_service.add_review.return_value = None
        mock_service.get_reviews.side_effect = MarketplaceError("Plugin not found")
        _, client = _build_app(mock_service)

        payload = {
            "rating": 5,
            "title": "Great!",
            "content": "Good plugin.",
        }
        resp = client.post("/api/v1/marketplace/plugins/nonexistent/reviews", json=payload)
        assert resp.status_code == 404

    def test_add_review_write_failed(self) -> None:
        """Test when review save fails."""
        mock_service = MagicMock()
        mock_service.add_review.return_value = None
        mock_service.get_reviews.return_value = []  # Empty list means save failed
        _, client = _build_app(mock_service)

        payload = {
            "rating": 5,
            "title": "Great!",
            "content": "Good plugin.",
        }
        resp = client.post("/api/v1/marketplace/plugins/test-plugin/reviews", json=payload)
        assert resp.status_code == 500
        body = resp.json()
        assert body["error"] == "review_write_failed"

    def test_add_review_minimum_content(self) -> None:
        """Test adding review with minimum valid content."""
        mock_service = MagicMock()
        mock_service.add_review.return_value = None
        mock_service.get_reviews.return_value = [_sample_review()]
        _, client = _build_app(mock_service)

        payload = {
            "rating": 1,  # Minimum valid rating
            "title": "OK",  # Minimum title length
            "content": "Acceptable.",
        }
        resp = client.post("/api/v1/marketplace/plugins/test-plugin/reviews", json=payload)
        assert resp.status_code == 200

    def test_add_review_maximum_content(self) -> None:
        """Test adding review with maximum valid content."""
        mock_service = MagicMock()
        mock_service.add_review.return_value = None
        mock_service.get_reviews.return_value = [_sample_review()]
        _, client = _build_app(mock_service)

        payload = {
            "rating": 5,  # Maximum valid rating
            "title": "x" * 120,  # Maximum title length
            "content": "y" * 2000,  # Maximum content length
        }
        resp = client.post("/api/v1/marketplace/plugins/test-plugin/reviews", json=payload)
        assert resp.status_code == 200


@pytest.mark.unit
class TestMarketplaceReviewSchema:
    """Tests for MarketplaceReviewRequest schema metadata."""

    def test_schema_preserves_rating_and_text_constraints(self) -> None:
        schema = MarketplaceReviewRequest.model_json_schema()
        properties = schema["properties"]

        assert properties["rating"]["minimum"] == 1
        assert properties["rating"]["maximum"] == 5
        assert properties["title"]["minLength"] == 1
        assert properties["title"]["maxLength"] == 120
        assert properties["content"]["minLength"] == 1
        assert properties["content"]["maxLength"] == 2000
