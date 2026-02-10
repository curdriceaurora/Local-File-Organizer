"""Tests for API configuration loading."""
from __future__ import annotations

import pytest

from file_organizer.api.config import ApiSettings, load_settings

pytestmark = pytest.mark.ci


def test_load_settings_ignores_invalid_ws_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    default_interval = ApiSettings().websocket_ping_interval
    monkeypatch.delenv("FO_API_CONFIG_PATH", raising=False)
    monkeypatch.setenv("FO_API_WS_PING_INTERVAL", "0")
    settings = load_settings()
    assert settings.websocket_ping_interval == default_interval


def test_load_settings_accepts_valid_ws_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FO_API_CONFIG_PATH", raising=False)
    monkeypatch.setenv("FO_API_WS_PING_INTERVAL", "12")
    settings = load_settings()
    assert settings.websocket_ping_interval == 12
