"""Tests for integration base classes and data types."""

from __future__ import annotations

from typing import Any

import pytest

from file_organizer.integrations.base import (
    Integration,
    IntegrationConfig,
    IntegrationStatus,
    IntegrationType,
)

# ---------------------------------------------------------------------------
# IntegrationType enum tests
# ---------------------------------------------------------------------------


class TestIntegrationType:
    """Test suite for IntegrationType enum."""

    def test_all_members(self) -> None:
        """All expected integration types should exist."""
        assert IntegrationType.DESKTOP_APP == "desktop_app"
        assert IntegrationType.EDITOR == "editor"
        assert IntegrationType.WORKFLOW == "workflow"
        assert IntegrationType.BROWSER == "browser"
        assert IntegrationType.API == "api"

    def test_string_value(self) -> None:
        """IntegrationType members should behave as strings."""
        assert str(IntegrationType.BROWSER) == "browser"
        assert f"type={IntegrationType.API}" == "type=api"


# ---------------------------------------------------------------------------
# IntegrationConfig tests
# ---------------------------------------------------------------------------


class TestIntegrationConfig:
    """Test suite for IntegrationConfig dataclass."""

    def test_required_fields(self) -> None:
        """Config should store required fields."""
        config = IntegrationConfig(
            name="test-adapter",
            integration_type=IntegrationType.BROWSER,
        )
        assert config.name == "test-adapter"
        assert config.integration_type == IntegrationType.BROWSER

    def test_defaults(self) -> None:
        """Optional fields should have sensible defaults."""
        config = IntegrationConfig(
            name="test",
            integration_type=IntegrationType.EDITOR,
        )
        assert config.enabled is True
        assert config.auth_method == "none"
        assert config.settings == {}

    def test_custom_settings(self) -> None:
        """Custom settings dict should be stored."""
        config = IntegrationConfig(
            name="vscode",
            integration_type=IntegrationType.EDITOR,
            enabled=False,
            auth_method="token",
            settings={"workspace": "/tmp"},
        )
        assert config.enabled is False
        assert config.auth_method == "token"
        assert config.settings == {"workspace": "/tmp"}

    def test_merge_settings_adds_new_keys(self) -> None:
        """merge_settings should add new keys."""
        config = IntegrationConfig(
            name="test",
            integration_type=IntegrationType.API,
            settings={"a": 1},
        )
        config.merge_settings({"b": 2})
        assert config.settings == {"a": 1, "b": 2}

    def test_merge_settings_overwrites_existing_keys(self) -> None:
        """merge_settings should overwrite existing keys."""
        config = IntegrationConfig(
            name="test",
            integration_type=IntegrationType.API,
            settings={"a": 1, "b": 2},
        )
        config.merge_settings({"b": 99})
        assert config.settings == {"a": 1, "b": 99}

    def test_merge_settings_empty_update(self) -> None:
        """merge_settings with empty dict should be a no-op."""
        config = IntegrationConfig(
            name="test",
            integration_type=IntegrationType.API,
            settings={"a": 1},
        )
        config.merge_settings({})
        assert config.settings == {"a": 1}


# ---------------------------------------------------------------------------
# IntegrationStatus tests
# ---------------------------------------------------------------------------


class TestIntegrationStatus:
    """Test suite for IntegrationStatus dataclass."""

    def test_creation(self) -> None:
        """Status should store all fields."""
        status = IntegrationStatus(
            name="obsidian",
            integration_type=IntegrationType.DESKTOP_APP,
            enabled=True,
            connected=True,
            details={"vault": "/notes"},
        )
        assert status.name == "obsidian"
        assert status.integration_type == IntegrationType.DESKTOP_APP
        assert status.enabled is True
        assert status.connected is True
        assert status.details == {"vault": "/notes"}

    def test_defaults(self) -> None:
        """Details should default to empty dict."""
        status = IntegrationStatus(
            name="test",
            integration_type=IntegrationType.API,
            enabled=False,
            connected=False,
        )
        assert status.details == {}

    def test_frozen(self) -> None:
        """IntegrationStatus is frozen — fields should not be reassignable."""
        status = IntegrationStatus(
            name="test",
            integration_type=IntegrationType.API,
            enabled=True,
            connected=False,
        )
        with pytest.raises(AttributeError):
            status.name = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Integration ABC tests
# ---------------------------------------------------------------------------


class _StubIntegration(Integration):
    """Concrete stub for testing the abstract base class."""

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def disconnect(self) -> None:
        self.connected = False

    async def validate_auth(self) -> bool:
        return self.config.auth_method == "none"

    async def send_file(self, file_path: str, metadata: dict[str, Any] | None = None) -> bool:
        return True

    async def get_status(self) -> IntegrationStatus:
        return IntegrationStatus(
            name=self.config.name,
            integration_type=self.config.integration_type,
            enabled=self.config.enabled,
            connected=self.connected,
        )


class TestIntegrationABC:
    """Test suite for Integration abstract base class."""

    def test_init_stores_config_and_connected_flag(self) -> None:
        """__init__ should store config and set connected=False."""
        config = IntegrationConfig(
            name="stub",
            integration_type=IntegrationType.WORKFLOW,
        )
        integration = _StubIntegration(config)
        assert integration.config is config
        assert integration.connected is False

    @pytest.mark.asyncio
    async def test_connect(self) -> None:
        """connect() should set connected flag."""
        config = IntegrationConfig(name="stub", integration_type=IntegrationType.API)
        integration = _StubIntegration(config)
        result = await integration.connect()
        assert result is True
        assert integration.connected is True

    @pytest.mark.asyncio
    async def test_disconnect(self) -> None:
        """disconnect() should clear connected flag."""
        config = IntegrationConfig(name="stub", integration_type=IntegrationType.API)
        integration = _StubIntegration(config)
        integration.connected = True
        await integration.disconnect()
        assert integration.connected is False

    @pytest.mark.asyncio
    async def test_get_status(self) -> None:
        """get_status() should return IntegrationStatus."""
        config = IntegrationConfig(name="stub", integration_type=IntegrationType.API)
        integration = _StubIntegration(config)
        status = await integration.get_status()
        assert isinstance(status, IntegrationStatus)
        assert status.name == "stub"
        assert status.connected is False
