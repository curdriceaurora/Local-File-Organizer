"""Coverage tests for integrations.manager module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from file_organizer.integrations.base import (
    Integration,
    IntegrationConfig,
    IntegrationStatus,
    IntegrationType,
)
from file_organizer.integrations.manager import IntegrationManager

pytestmark = pytest.mark.unit


def _make_integration(
    name: str = "test",
    enabled: bool = True,
    connected: bool = False,
) -> Integration:
    config = IntegrationConfig(
        name=name,
        integration_type=IntegrationType.API,
        enabled=enabled,
    )
    mock = MagicMock(spec=Integration)
    mock.config = config
    mock.connected = connected
    mock.connect = AsyncMock(return_value=True)
    mock.disconnect = AsyncMock()
    mock.send_file = AsyncMock(return_value=True)
    mock.get_status = AsyncMock(
        return_value=IntegrationStatus(
            name=name,
            integration_type=IntegrationType.API,
            enabled=enabled,
            connected=connected,
        )
    )
    return mock


class TestIntegrationManagerRegistration:
    def test_register_and_get(self):
        mgr = IntegrationManager()
        intg = _make_integration("demo")
        mgr.register(intg)
        assert mgr.get("demo") is intg

    def test_unregister(self):
        mgr = IntegrationManager()
        intg = _make_integration("demo")
        mgr.register(intg)
        mgr.unregister("demo")
        assert mgr.get("demo") is None

    def test_unregister_nonexistent(self):
        mgr = IntegrationManager()
        mgr.unregister("nonexistent")

    def test_names_sorted(self):
        mgr = IntegrationManager()
        mgr.register(_make_integration("beta"))
        mgr.register(_make_integration("alpha"))
        assert mgr.names() == ["alpha", "beta"]

    def test_get_missing_returns_none(self):
        mgr = IntegrationManager()
        assert mgr.get("missing") is None


class TestIntegrationManagerListConfigs:
    def test_list_configs(self):
        mgr = IntegrationManager()
        mgr.register(_make_integration("a"))
        mgr.register(_make_integration("b"))
        configs = mgr.list_configs()
        assert len(configs) == 2
        assert configs[0].name == "a"
        assert configs[1].name == "b"


class TestIntegrationManagerAsync:
    @pytest.mark.asyncio
    async def test_list_statuses(self):
        mgr = IntegrationManager()
        mgr.register(_make_integration("s1"))
        mgr.register(_make_integration("s2"))
        statuses = await mgr.list_statuses()
        assert len(statuses) == 2

    @pytest.mark.asyncio
    async def test_connect(self):
        mgr = IntegrationManager()
        intg = _make_integration("demo")
        mgr.register(intg)
        result = await mgr.connect("demo")
        assert result is True
        intg.connect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_connect_missing_returns_false(self):
        mgr = IntegrationManager()
        result = await mgr.connect("missing")
        assert result is False

    @pytest.mark.asyncio
    async def test_disconnect(self):
        mgr = IntegrationManager()
        intg = _make_integration("demo")
        mgr.register(intg)
        result = await mgr.disconnect("demo")
        assert result is True
        intg.disconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disconnect_missing_returns_false(self):
        mgr = IntegrationManager()
        result = await mgr.disconnect("missing")
        assert result is False

    @pytest.mark.asyncio
    async def test_connect_all_skips_disabled(self):
        mgr = IntegrationManager()
        enabled = _make_integration("enabled", enabled=True)
        disabled = _make_integration("disabled", enabled=False)
        mgr.register(enabled)
        mgr.register(disabled)

        results = await mgr.connect_all()
        assert results["enabled"] is True
        assert results["disabled"] is False
        disabled.connect.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_disconnect_all(self):
        mgr = IntegrationManager()
        i1 = _make_integration("a")
        i2 = _make_integration("b")
        mgr.register(i1)
        mgr.register(i2)

        await mgr.disconnect_all()
        i1.disconnect.assert_awaited_once()
        i2.disconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_send_file_success(self):
        mgr = IntegrationManager()
        intg = _make_integration("demo", connected=True)
        mgr.register(intg)

        result = await mgr.send_file("demo", "/file.txt", metadata={"key": "val"})
        assert result is True
        intg.send_file.assert_awaited_once_with("/file.txt", metadata={"key": "val"})

    @pytest.mark.asyncio
    async def test_send_file_missing_returns_false(self):
        mgr = IntegrationManager()
        result = await mgr.send_file("missing", "/file.txt")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_file_reconnects(self):
        mgr = IntegrationManager()
        intg = _make_integration("demo", connected=False)
        mgr.register(intg)

        result = await mgr.send_file("demo", "/file.txt")
        assert result is True
        intg.connect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_send_file_connect_fails(self):
        mgr = IntegrationManager()
        intg = _make_integration("demo", connected=False)
        intg.connect = AsyncMock(return_value=False)
        mgr.register(intg)

        result = await mgr.send_file("demo", "/file.txt")
        assert result is False


class TestIntegrationManagerUpdateSettings:
    def test_update_settings_success(self):
        mgr = IntegrationManager()
        intg = _make_integration("demo")
        intg.config = MagicMock()
        intg.config.name = "demo"
        mgr.register(intg)

        result = mgr.update_settings("demo", {"key": "val"})
        assert result is True
        intg.config.merge_settings.assert_called_once_with({"key": "val"})

    def test_update_settings_missing(self):
        mgr = IntegrationManager()
        result = mgr.update_settings("missing", {"key": "val"})
        assert result is False
