"""Tests for health check endpoint functionality.

Validates health status reporting, individual component checks,
and edge cases for Redis, disk, and model availability checks.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest import mock

import pytest

from file_organizer.deploy.config import DeploymentConfig
from file_organizer.deploy.health import ComponentStatus, HealthEndpoint


@pytest.fixture
def dev_config() -> DeploymentConfig:
    """Create a dev environment config for testing."""
    return DeploymentConfig(
        environment="dev",
        redis_url="redis://localhost:6379/0",
        data_directory=Path("/tmp/fo-test-data"),
    )


@pytest.fixture
def health_endpoint(dev_config: DeploymentConfig) -> HealthEndpoint:
    """Create a health endpoint for testing."""
    return HealthEndpoint(
        config=dev_config,
        start_time=time.time() - 60,  # Started 60 seconds ago
    )


@pytest.mark.unit
class TestComponentStatus:
    """Tests for the ComponentStatus dataclass."""

    def test_component_status_defaults(self) -> None:
        """Verify ComponentStatus default values."""
        status = ComponentStatus(name="test", healthy=True)
        assert status.name == "test"
        assert status.healthy is True
        assert status.message == ""
        assert status.response_time_ms == 0.0

    def test_component_status_with_message(self) -> None:
        """Verify ComponentStatus stores message correctly."""
        status = ComponentStatus(name="redis", healthy=False, message="Connection refused")
        assert status.message == "Connection refused"

    def test_component_status_with_response_time(self) -> None:
        """Verify ComponentStatus stores response time correctly."""
        status = ComponentStatus(name="disk", healthy=True, response_time_ms=1.5)
        assert status.response_time_ms == 1.5


@pytest.mark.unit
class TestHealthEndpointGetHealth:
    """Tests for HealthEndpoint.get_health() method."""

    def test_get_health_returns_required_keys(self, health_endpoint: HealthEndpoint) -> None:
        """Verify get_health returns all required keys."""
        with (
            mock.patch.object(
                health_endpoint,
                "_check_redis",
                return_value=ComponentStatus(name="redis", healthy=True),
            ),
            mock.patch.object(
                health_endpoint,
                "_check_disk_space",
                return_value=ComponentStatus(name="disk", healthy=True),
            ),
            mock.patch.object(
                health_endpoint,
                "_check_model_availability",
                return_value=ComponentStatus(name="model", healthy=True),
            ),
        ):
            result = health_endpoint.get_health()
            assert "status" in result
            assert "version" in result
            assert "uptime_seconds" in result
            assert "environment" in result
            assert "components" in result

    def test_get_health_all_healthy(self, health_endpoint: HealthEndpoint) -> None:
        """Verify status is 'healthy' when all components are healthy."""
        with (
            mock.patch.object(
                health_endpoint,
                "_check_redis",
                return_value=ComponentStatus(name="redis", healthy=True),
            ),
            mock.patch.object(
                health_endpoint,
                "_check_disk_space",
                return_value=ComponentStatus(name="disk", healthy=True),
            ),
            mock.patch.object(
                health_endpoint,
                "_check_model_availability",
                return_value=ComponentStatus(name="model", healthy=True),
            ),
        ):
            result = health_endpoint.get_health()
            assert result["status"] == "healthy"

    def test_get_health_unhealthy_when_redis_down(self, health_endpoint: HealthEndpoint) -> None:
        """Verify status is 'unhealthy' when Redis is down."""
        with (
            mock.patch.object(
                health_endpoint,
                "_check_redis",
                return_value=ComponentStatus(name="redis", healthy=False),
            ),
            mock.patch.object(
                health_endpoint,
                "_check_disk_space",
                return_value=ComponentStatus(name="disk", healthy=True),
            ),
            mock.patch.object(
                health_endpoint,
                "_check_model_availability",
                return_value=ComponentStatus(name="model", healthy=True),
            ),
        ):
            result = health_endpoint.get_health()
            assert result["status"] == "unhealthy"

    def test_get_health_unhealthy_when_disk_low(self, health_endpoint: HealthEndpoint) -> None:
        """Verify status is 'unhealthy' when disk space is low."""
        with (
            mock.patch.object(
                health_endpoint,
                "_check_redis",
                return_value=ComponentStatus(name="redis", healthy=True),
            ),
            mock.patch.object(
                health_endpoint,
                "_check_disk_space",
                return_value=ComponentStatus(name="disk", healthy=False),
            ),
            mock.patch.object(
                health_endpoint,
                "_check_model_availability",
                return_value=ComponentStatus(name="model", healthy=True),
            ),
        ):
            result = health_endpoint.get_health()
            assert result["status"] == "unhealthy"

    def test_get_health_unhealthy_when_model_unavailable(
        self, health_endpoint: HealthEndpoint
    ) -> None:
        """Verify status is 'unhealthy' when model service is unavailable."""
        with (
            mock.patch.object(
                health_endpoint,
                "_check_redis",
                return_value=ComponentStatus(name="redis", healthy=True),
            ),
            mock.patch.object(
                health_endpoint,
                "_check_disk_space",
                return_value=ComponentStatus(name="disk", healthy=True),
            ),
            mock.patch.object(
                health_endpoint,
                "_check_model_availability",
                return_value=ComponentStatus(name="model", healthy=False),
            ),
        ):
            result = health_endpoint.get_health()
            assert result["status"] == "unhealthy"

    def test_get_health_includes_version(self, health_endpoint: HealthEndpoint) -> None:
        """Verify get_health includes the application version."""
        with (
            mock.patch.object(
                health_endpoint,
                "_check_redis",
                return_value=ComponentStatus(name="redis", healthy=True),
            ),
            mock.patch.object(
                health_endpoint,
                "_check_disk_space",
                return_value=ComponentStatus(name="disk", healthy=True),
            ),
            mock.patch.object(
                health_endpoint,
                "_check_model_availability",
                return_value=ComponentStatus(name="model", healthy=True),
            ),
        ):
            result = health_endpoint.get_health()
            assert isinstance(result["version"], str)
            assert len(str(result["version"])) > 0

    def test_get_health_uptime_positive(self, health_endpoint: HealthEndpoint) -> None:
        """Verify uptime_seconds is positive when start_time is in the past."""
        with (
            mock.patch.object(
                health_endpoint,
                "_check_redis",
                return_value=ComponentStatus(name="redis", healthy=True),
            ),
            mock.patch.object(
                health_endpoint,
                "_check_disk_space",
                return_value=ComponentStatus(name="disk", healthy=True),
            ),
            mock.patch.object(
                health_endpoint,
                "_check_model_availability",
                return_value=ComponentStatus(name="model", healthy=True),
            ),
        ):
            result = health_endpoint.get_health()
            assert result["uptime_seconds"] > 0  # type: ignore[operator]

    def test_get_health_includes_environment(self, health_endpoint: HealthEndpoint) -> None:
        """Verify get_health includes the deployment environment."""
        with (
            mock.patch.object(
                health_endpoint,
                "_check_redis",
                return_value=ComponentStatus(name="redis", healthy=True),
            ),
            mock.patch.object(
                health_endpoint,
                "_check_disk_space",
                return_value=ComponentStatus(name="disk", healthy=True),
            ),
            mock.patch.object(
                health_endpoint,
                "_check_model_availability",
                return_value=ComponentStatus(name="model", healthy=True),
            ),
        ):
            result = health_endpoint.get_health()
            assert result["environment"] == "dev"

    def test_get_health_components_have_required_keys(
        self, health_endpoint: HealthEndpoint
    ) -> None:
        """Verify each component in the health response has required keys."""
        with (
            mock.patch.object(
                health_endpoint,
                "_check_redis",
                return_value=ComponentStatus(
                    name="redis", healthy=True, message="ok", response_time_ms=1.0
                ),
            ),
            mock.patch.object(
                health_endpoint,
                "_check_disk_space",
                return_value=ComponentStatus(
                    name="disk", healthy=True, message="ok", response_time_ms=0.5
                ),
            ),
            mock.patch.object(
                health_endpoint,
                "_check_model_availability",
                return_value=ComponentStatus(
                    name="model", healthy=True, message="ok", response_time_ms=2.0
                ),
            ),
        ):
            result = health_endpoint.get_health()
            components = result["components"]
            assert isinstance(components, dict)
            for name in ("redis", "disk", "model"):
                assert name in components  # type: ignore[operator]
                comp = components[name]  # type: ignore[index]
                assert "healthy" in comp  # type: ignore[operator]
                assert "message" in comp  # type: ignore[operator]
                assert "response_time_ms" in comp  # type: ignore[operator]


@pytest.mark.unit
class TestHealthEndpointRedisCheck:
    """Tests for Redis health check."""

    def test_check_redis_returns_bool(self, health_endpoint: HealthEndpoint) -> None:
        """Verify check_redis returns a boolean (True or False)."""
        result = health_endpoint.check_redis()
        assert result is True or result is False

    def test_check_redis_connection_refused(self, health_endpoint: HealthEndpoint) -> None:
        """Verify check_redis returns False when connection is refused."""
        # Use a port that's unlikely to be listening
        health_endpoint.config = DeploymentConfig(redis_url="redis://localhost:59999/0")
        assert health_endpoint.check_redis() is False

    def test_check_redis_socket_error(self, health_endpoint: HealthEndpoint) -> None:
        """Verify check_redis handles socket errors gracefully."""
        with mock.patch("socket.socket") as mock_socket:
            mock_sock_instance = mock.MagicMock()
            mock_sock_instance.connect_ex.side_effect = OSError("Network error")
            mock_socket.return_value = mock_sock_instance

            result = health_endpoint.check_redis()
            assert result is False

    def test_internal_check_redis_has_response_time(self, health_endpoint: HealthEndpoint) -> None:
        """Verify _check_redis records response time."""
        status = health_endpoint._check_redis()
        assert status.response_time_ms >= 0


@pytest.mark.unit
class TestHealthEndpointDiskCheck:
    """Tests for disk space health check."""

    def test_check_disk_space_returns_bool(self, health_endpoint: HealthEndpoint) -> None:
        """Verify check_disk_space returns a boolean (True or False)."""
        result = health_endpoint.check_disk_space()
        assert result is True or result is False

    def test_check_disk_space_healthy_with_sufficient_space(
        self, health_endpoint: HealthEndpoint
    ) -> None:
        """Verify disk check passes when there is enough space."""
        health_endpoint.min_disk_space_mb = 1  # 1MB minimum
        assert health_endpoint.check_disk_space() is True

    def test_check_disk_space_unhealthy_with_extreme_threshold(
        self, health_endpoint: HealthEndpoint
    ) -> None:
        """Verify disk check fails with an impossibly high threshold."""
        health_endpoint.min_disk_space_mb = 999_999_999  # ~1PB
        assert health_endpoint.check_disk_space() is False

    def test_check_disk_space_uses_fallback_path(self, dev_config: DeploymentConfig) -> None:
        """Verify disk check uses fallback path when data dir doesn't exist."""
        dev_config.data_directory = Path("/nonexistent/path/fo-test")
        endpoint = HealthEndpoint(config=dev_config, min_disk_space_mb=1)
        # Should not raise; falls back to /
        result = endpoint.check_disk_space()
        assert result is True or result is False

    def test_internal_check_disk_space_includes_message(
        self, health_endpoint: HealthEndpoint
    ) -> None:
        """Verify _check_disk_space status includes a message."""
        health_endpoint.min_disk_space_mb = 1
        status = health_endpoint._check_disk_space()
        assert "MB" in status.message


@pytest.mark.unit
class TestHealthEndpointModelCheck:
    """Tests for model availability health check."""

    def test_check_model_availability_returns_bool(self, health_endpoint: HealthEndpoint) -> None:
        """Verify check_model_availability returns a boolean (True or False)."""
        result = health_endpoint.check_model_availability()
        assert result is True or result is False

    def test_check_model_unavailable_on_closed_port(self, health_endpoint: HealthEndpoint) -> None:
        """Verify model check returns False when port is closed."""
        health_endpoint.model_host = "localhost"
        health_endpoint.model_port = 59998  # Unlikely to be open
        assert health_endpoint.check_model_availability() is False

    def test_check_model_socket_error(self, health_endpoint: HealthEndpoint) -> None:
        """Verify model check handles socket errors gracefully."""
        with mock.patch("socket.socket") as mock_socket:
            mock_sock_instance = mock.MagicMock()
            mock_sock_instance.connect_ex.side_effect = OSError("Timeout")
            mock_socket.return_value = mock_sock_instance

            result = health_endpoint.check_model_availability()
            assert result is False

    def test_internal_check_model_has_response_time(self, health_endpoint: HealthEndpoint) -> None:
        """Verify _check_model_availability records response time."""
        status = health_endpoint._check_model_availability()
        assert status.response_time_ms >= 0
