"""Integration tests for ServiceFacade.

External HTTP (Ollama probe) is mocked at the urllib boundary.
Filesystem operations use real tmp_path.
AI/model inference is mocked at the FileOrganizer boundary.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.api.config import ApiSettings
from file_organizer.api.service_facade import ServiceFacade


@pytest.mark.integration
class TestServiceFacadeHealthCheck:
    """health_check() with real settings, mocked Ollama HTTP probe."""

    @pytest.mark.ci
    def test_health_returns_required_keys(self):
        settings = ApiSettings(auth_enabled=False)
        facade = ServiceFacade(settings=settings)
        with patch("file_organizer.api.service_facade.urllib.request.urlopen") as mock_open:
            mock_open.return_value.__enter__ = lambda s: s
            mock_open.return_value.__exit__ = MagicMock(return_value=False)
            result = asyncio.get_event_loop().run_until_complete(facade.health_check())
        assert "status" in result
        assert "version" in result
        assert "provider" in result

    @pytest.mark.ci
    def test_health_degraded_when_ollama_unreachable(self):
        settings = ApiSettings(auth_enabled=False)
        facade = ServiceFacade(settings=settings)
        with patch(
            "file_organizer.api.service_facade.urllib.request.urlopen",
            side_effect=Exception("connection refused"),
        ):
            result = asyncio.get_event_loop().run_until_complete(facade.health_check())
        assert result["status"] in ("degraded", "unknown")

    def test_health_returns_correct_version(self):
        from file_organizer.version import __version__

        settings = ApiSettings(auth_enabled=False)
        facade = ServiceFacade(settings=settings)
        with patch("file_organizer.api.service_facade.urllib.request.urlopen") as mock_open:
            mock_open.return_value.__enter__ = lambda s: s
            mock_open.return_value.__exit__ = MagicMock(return_value=False)
            result = asyncio.get_event_loop().run_until_complete(facade.health_check())
        assert result["version"] == __version__


@pytest.mark.integration
class TestServiceFacadeOrganizeFiles:
    """organize_files() with real filesystem, mocked AI model."""

    @pytest.mark.ci
    def test_organize_returns_error_dict_for_missing_source(self, tmp_path):
        settings = ApiSettings(
            auth_enabled=False,
            allowed_paths=[str(tmp_path)],
        )
        facade = ServiceFacade(settings=settings)
        result = asyncio.get_event_loop().run_until_complete(
            facade.organize_files(str(tmp_path / "nonexistent"))
        )
        assert isinstance(result, dict)


@pytest.mark.integration
class TestServiceFacadeGetConfig:
    """get_config() with real ApiSettings."""

    @pytest.mark.ci
    def test_get_config_returns_expected_keys(self):
        settings = ApiSettings(auth_enabled=False, environment="test")
        facade = ServiceFacade(settings=settings)
        result = asyncio.get_event_loop().run_until_complete(facade.get_config())
        assert isinstance(result, dict)
        assert "version" in result

    def test_get_config_returns_dict_with_ai_key(self):
        settings = ApiSettings(auth_enabled=False, environment="staging")
        facade = ServiceFacade(settings=settings)
        result = asyncio.get_event_loop().run_until_complete(facade.get_config())
        # ConfigResponse has version, ai, storage, organization, app_version keys
        assert isinstance(result, dict)
        assert "ai" in result
