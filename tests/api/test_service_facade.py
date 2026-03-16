"""Unit tests for ServiceFacade."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from file_organizer.api.config import ApiSettings
from file_organizer.api.service_facade import ServiceFacade
from file_organizer.version import __version__

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_SETTINGS: dict[str, object] = {
    "environment": "test",
    "auth_enabled": False,
    "auth_jwt_secret": "test-secret",
    "rate_limit_enabled": False,
}


def _make_facade(**overrides: object) -> ServiceFacade:
    """Return a ServiceFacade with test-friendly ApiSettings.

    ``overrides`` replace values from the base settings, so callers can pass
    e.g. ``environment="production"`` without hitting duplicate-keyword errors.
    """
    merged = {**_BASE_SETTINGS, **overrides}
    settings = ApiSettings(**merged)  # type: ignore[arg-type]
    return ServiceFacade(settings=settings)


# ---------------------------------------------------------------------------
# Instantiation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestServiceFacadeInstantiation:
    """Tests for ServiceFacade construction."""

    def test_default_construction(self) -> None:
        """ServiceFacade can be constructed without arguments."""
        facade = ServiceFacade()
        assert facade is not None

    def test_custom_settings(self) -> None:
        """ServiceFacade accepts an explicit ApiSettings instance."""
        settings = ApiSettings(environment="test", auth_jwt_secret="secret")
        facade = ServiceFacade(settings=settings)
        assert facade._settings is settings

    def test_importable_from_api_package(self) -> None:
        """ServiceFacade is importable directly from the api package."""
        from file_organizer.api import ServiceFacade as FacadeFromPackage

        assert FacadeFromPackage is ServiceFacade


# ---------------------------------------------------------------------------
# health_check
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestHealthCheck:
    """Tests for ServiceFacade.health_check()."""

    @pytest.mark.asyncio
    async def test_returns_required_keys(self) -> None:
        """health_check must return status, version and ollama keys."""
        facade = _make_facade()
        with patch.object(facade, "_check_ollama", new_callable=AsyncMock, return_value=True):
            result = await facade.health_check()

        assert "status" in result
        assert "version" in result
        assert "ollama" in result

    @pytest.mark.asyncio
    async def test_status_ok_when_ollama_reachable(self) -> None:
        """health_check.status is 'ok' when Ollama is reachable."""
        facade = _make_facade()
        with patch.object(facade, "_check_ollama", new_callable=AsyncMock, return_value=True):
            result = await facade.health_check()

        assert result["status"] == "ok"

    @pytest.mark.asyncio
    async def test_status_degraded_when_ollama_unreachable(self) -> None:
        """health_check.status is 'degraded' when Ollama is unreachable."""
        facade = _make_facade()
        with patch.object(facade, "_check_ollama", new_callable=AsyncMock, return_value=False):
            result = await facade.health_check()

        assert result["status"] == "degraded"

    @pytest.mark.asyncio
    async def test_version_matches_package(self) -> None:
        """health_check.version must match the installed package version."""
        facade = _make_facade()
        with patch.object(facade, "_check_ollama", new_callable=AsyncMock, return_value=True):
            result = await facade.health_check()

        assert result["version"] == __version__
        assert isinstance(result["version"], str)

    @pytest.mark.asyncio
    async def test_ollama_true_when_reachable(self) -> None:
        """health_check.ollama is True when _check_ollama returns True."""
        facade = _make_facade()
        with patch.object(facade, "_check_ollama", new_callable=AsyncMock, return_value=True):
            result = await facade.health_check()

        assert result["ollama"] is True

    @pytest.mark.asyncio
    async def test_ollama_false_when_unreachable(self) -> None:
        """health_check.ollama is False when _check_ollama returns False."""
        facade = _make_facade()
        with patch.object(facade, "_check_ollama", new_callable=AsyncMock, return_value=False):
            result = await facade.health_check()

        assert result["ollama"] is False

    @pytest.mark.asyncio
    async def test_status_unknown_when_llama_cpp_provider(self) -> None:
        """health_check.status is 'unknown' when provider is llama_cpp."""
        facade = _make_facade()
        with (
            patch(
                "file_organizer.api.service_facade.get_current_provider", return_value="llama_cpp"
            ),
            patch.object(
                facade, "_check_ollama", new_callable=AsyncMock, return_value=False
            ) as check,
        ):
            result = await facade.health_check()

        assert result["provider"] == "llama_cpp"
        assert result["status"] == "unknown"
        assert result["ollama"] is False
        check.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_status_unknown_when_mlx_provider(self) -> None:
        """health_check.status is 'unknown' when provider is mlx."""
        facade = _make_facade()
        with (
            patch("file_organizer.api.service_facade.get_current_provider", return_value="mlx"),
            patch.object(
                facade, "_check_ollama", new_callable=AsyncMock, return_value=False
            ) as check,
        ):
            result = await facade.health_check()

        assert result["provider"] == "mlx"
        assert result["status"] == "unknown"
        assert result["ollama"] is False
        check.assert_not_awaited()


# ---------------------------------------------------------------------------
# get_status
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetStatus:
    """Tests for ServiceFacade.get_status()."""

    @pytest.mark.asyncio
    async def test_returns_expected_keys(self) -> None:
        """get_status returns environment, version, auth_enabled and ollama."""
        facade = _make_facade()
        with patch.object(facade, "_check_ollama", new_callable=AsyncMock, return_value=False):
            result = await facade.get_status()

        for key in ("environment", "version", "auth_enabled", "ollama"):
            assert key in result, f"Missing key: {key}"

    @pytest.mark.asyncio
    async def test_environment_matches_settings(self) -> None:
        """get_status.environment reflects the configured environment."""
        facade = _make_facade(environment="test")
        with patch.object(facade, "_check_ollama", new_callable=AsyncMock, return_value=False):
            result = await facade.get_status()

        assert result["environment"] == "test"

    @pytest.mark.asyncio
    async def test_version_is_string(self) -> None:
        """get_status.version is the package version string."""
        facade = _make_facade()
        with patch.object(facade, "_check_ollama", new_callable=AsyncMock, return_value=False):
            result = await facade.get_status()

        assert result["version"] == __version__

    @pytest.mark.asyncio
    async def test_auth_enabled_true_reflects_settings(self) -> None:
        """get_status.auth_enabled is True when settings.auth_enabled is True."""
        facade = _make_facade(auth_enabled=True)
        with patch.object(facade, "_check_ollama", new_callable=AsyncMock, return_value=False):
            result = await facade.get_status()

        assert result["auth_enabled"] is True

    @pytest.mark.asyncio
    async def test_auth_enabled_false_reflects_settings(self) -> None:
        """get_status.auth_enabled is False when settings.auth_enabled is False."""
        facade = _make_facade(auth_enabled=False)
        with patch.object(facade, "_check_ollama", new_callable=AsyncMock, return_value=False):
            result = await facade.get_status()

        assert result["auth_enabled"] is False


# ---------------------------------------------------------------------------
# get_config
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetConfig:
    """Tests for ServiceFacade.get_config()."""

    @pytest.mark.asyncio
    async def test_returns_dict(self) -> None:
        """get_config returns a dict."""
        facade = _make_facade()
        result = await facade.get_config()
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_contains_expected_sections(self) -> None:
        """get_config dict contains ai, storage and organization keys."""
        facade = _make_facade()
        result = await facade.get_config()
        for section in ("ai", "storage", "organization"):
            assert section in result, f"Missing config section: {section}"

    @pytest.mark.asyncio
    async def test_contains_version(self) -> None:
        """get_config dict contains a version field."""
        facade = _make_facade()
        result = await facade.get_config()
        assert "version" in result


# ---------------------------------------------------------------------------
# _check_ollama (private helper)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCheckOllama:
    """Tests for ServiceFacade._check_ollama()."""

    @pytest.mark.asyncio
    async def test_returns_true_on_200(self) -> None:
        """_check_ollama returns True when HTTP 200 is received."""
        facade = _make_facade()
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = await facade._check_ollama()

        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_on_connection_error(self) -> None:
        """_check_ollama returns False when the connection is refused."""
        facade = _make_facade()
        with patch("urllib.request.urlopen", side_effect=ConnectionRefusedError("refused")):
            result = await facade._check_ollama()

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_timeout(self) -> None:
        """_check_ollama returns False on a timeout."""
        facade = _make_facade()
        with patch("urllib.request.urlopen", side_effect=TimeoutError("timed out")):
            result = await facade._check_ollama()

        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_on_non_200(self) -> None:
        """_check_ollama returns False when HTTP status is not 200."""
        facade = _make_facade()
        mock_response = MagicMock()
        mock_response.status = 503
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            result = await facade._check_ollama()

        assert result is False
