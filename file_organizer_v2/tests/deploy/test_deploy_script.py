"""Tests for deployment automation script.

Validates build_image, push_image, validate_deployment, and rollback
functions with mocked subprocess and network calls.
"""

from __future__ import annotations

import subprocess
import sys
import urllib.error
from pathlib import Path
from unittest import mock

# Add scripts directory to path for import
SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from deploy import (  # noqa: E402
    DeployConfig,
    HealthCheckResult,
    build_image,
    push_image,
    rollback,
    validate_deployment,
)


class TestDeployConfig:
    """Tests for the DeployConfig dataclass."""

    def test_deploy_config_creation(self) -> None:
        """Verify DeployConfig can be created with all fields."""
        config = DeployConfig(
            registry="docker.io/myuser",
            image_name="file-organizer",
            tag="v2.0.0",
            env_file=".env.prod",
        )
        assert config.registry == "docker.io/myuser"
        assert config.image_name == "file-organizer"
        assert config.tag == "v2.0.0"
        assert config.env_file == ".env.prod"

    def test_deploy_config_full_image_name(self) -> None:
        """Verify full_image_name property returns correct format."""
        config = DeployConfig(
            registry="ghcr.io/org",
            image_name="file-organizer",
            tag="latest",
        )
        assert config.full_image_name == "ghcr.io/org/file-organizer:latest"

    def test_deploy_config_env_file_optional(self) -> None:
        """Verify env_file defaults to None."""
        config = DeployConfig(
            registry="docker.io/user",
            image_name="app",
            tag="v1",
        )
        assert config.env_file is None


class TestHealthCheckResult:
    """Tests for the HealthCheckResult dataclass."""

    def test_health_check_result_healthy(self) -> None:
        """Verify HealthCheckResult for a healthy deployment."""
        result = HealthCheckResult(
            healthy=True,
            status_code=200,
            response_time_ms=15.5,
        )
        assert result.healthy is True
        assert result.status_code == 200
        assert result.response_time_ms == 15.5
        assert result.details is None

    def test_health_check_result_unhealthy(self) -> None:
        """Verify HealthCheckResult for an unhealthy deployment."""
        result = HealthCheckResult(
            healthy=False,
            status_code=503,
            response_time_ms=100.0,
            details={"error": "Service unavailable"},
        )
        assert result.healthy is False
        assert result.status_code == 503
        assert result.details == {"error": "Service unavailable"}


class TestBuildImage:
    """Tests for the build_image function."""

    @mock.patch("deploy.subprocess.run")
    def test_build_image_success(self, mock_run: mock.MagicMock) -> None:
        """Verify build_image returns True on success."""
        mock_run.return_value = mock.MagicMock(returncode=0)
        result = build_image("file-organizer:v2.0.0")
        assert result is True
        mock_run.assert_called_once()

    @mock.patch("deploy.subprocess.run")
    def test_build_image_failure(self, mock_run: mock.MagicMock) -> None:
        """Verify build_image returns False on failure."""
        mock_run.return_value = mock.MagicMock(returncode=1)
        result = build_image("file-organizer:v2.0.0")
        assert result is False

    @mock.patch("deploy.subprocess.run")
    def test_build_image_custom_dockerfile(self, mock_run: mock.MagicMock) -> None:
        """Verify build_image uses custom Dockerfile."""
        mock_run.return_value = mock.MagicMock(returncode=0)
        result = build_image("app:latest", dockerfile="Dockerfile.prod")
        assert result is True
        call_args = mock_run.call_args[0][0]
        assert "Dockerfile.prod" in call_args

    @mock.patch("deploy.subprocess.run")
    def test_build_image_timeout(self, mock_run: mock.MagicMock) -> None:
        """Verify build_image handles timeout gracefully."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="docker", timeout=600)
        result = build_image("file-organizer:v2.0.0")
        assert result is False

    @mock.patch("deploy.subprocess.run")
    def test_build_image_docker_not_found(self, mock_run: mock.MagicMock) -> None:
        """Verify build_image handles missing docker CLI."""
        mock_run.side_effect = FileNotFoundError("docker not found")
        result = build_image("file-organizer:v2.0.0")
        assert result is False


class TestPushImage:
    """Tests for the push_image function."""

    @mock.patch("deploy.subprocess.run")
    def test_push_image_success(self, mock_run: mock.MagicMock) -> None:
        """Verify push_image returns True on success."""
        mock_run.return_value = mock.MagicMock(returncode=0)
        result = push_image("file-organizer:v2.0.0", "docker.io/myuser")
        assert result is True
        assert mock_run.call_count == 2  # tag + push

    @mock.patch("deploy.subprocess.run")
    def test_push_image_tag_failure(self, mock_run: mock.MagicMock) -> None:
        """Verify push_image returns False when tagging fails."""
        mock_run.return_value = mock.MagicMock(returncode=1)
        result = push_image("file-organizer:v2.0.0", "docker.io/myuser")
        assert result is False

    @mock.patch("deploy.subprocess.run")
    def test_push_image_push_failure(self, mock_run: mock.MagicMock) -> None:
        """Verify push_image returns False when push fails."""
        mock_run.side_effect = [
            mock.MagicMock(returncode=0),  # tag succeeds
            mock.MagicMock(returncode=1),  # push fails
        ]
        result = push_image("file-organizer:v2.0.0", "docker.io/myuser")
        assert result is False

    @mock.patch("deploy.subprocess.run")
    def test_push_image_timeout(self, mock_run: mock.MagicMock) -> None:
        """Verify push_image handles timeout gracefully."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="docker", timeout=300)
        result = push_image("file-organizer:v2.0.0", "docker.io/myuser")
        assert result is False


class TestValidateDeployment:
    """Tests for the validate_deployment function."""

    @mock.patch("deploy.urllib.request.urlopen")
    def test_validate_deployment_healthy(self, mock_urlopen: mock.MagicMock) -> None:
        """Verify validate_deployment returns healthy for 200 OK."""
        mock_response = mock.MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b'{"status": "healthy"}'
        mock_response.__enter__ = mock.MagicMock(return_value=mock_response)
        mock_response.__exit__ = mock.MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = validate_deployment("http://localhost:8000/health")
        assert result.healthy is True
        assert result.status_code == 200
        assert result.response_time_ms >= 0

    @mock.patch("deploy.urllib.request.urlopen")
    def test_validate_deployment_unhealthy_status(self, mock_urlopen: mock.MagicMock) -> None:
        """Verify validate_deployment returns unhealthy for unhealthy status."""
        mock_response = mock.MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b'{"status": "unhealthy"}'
        mock_response.__enter__ = mock.MagicMock(return_value=mock_response)
        mock_response.__exit__ = mock.MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = validate_deployment("http://localhost:8000/health")
        assert result.healthy is False

    @mock.patch("deploy.urllib.request.urlopen")
    def test_validate_deployment_connection_error(self, mock_urlopen: mock.MagicMock) -> None:
        """Verify validate_deployment handles connection errors."""
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")
        result = validate_deployment("http://localhost:8000/health")
        assert result.healthy is False
        assert result.status_code == 0

    @mock.patch("deploy.urllib.request.urlopen")
    def test_validate_deployment_http_error(self, mock_urlopen: mock.MagicMock) -> None:
        """Verify validate_deployment handles HTTP errors."""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="http://localhost:8000/health",
            code=503,
            msg="Service Unavailable",
            hdrs=None,  # type: ignore[arg-type]
            fp=None,
        )
        result = validate_deployment("http://localhost:8000/health")
        assert result.healthy is False
        assert result.status_code == 503


class TestRollback:
    """Tests for the rollback function."""

    @mock.patch("deploy.subprocess.run")
    def test_rollback_success(self, mock_run: mock.MagicMock) -> None:
        """Verify rollback returns True on success."""
        mock_run.return_value = mock.MagicMock(returncode=0)
        result = rollback("v1.9.0")
        assert result is True
        assert mock_run.call_count == 2  # down + up

    @mock.patch("deploy.subprocess.run")
    def test_rollback_stop_failure(self, mock_run: mock.MagicMock) -> None:
        """Verify rollback returns False when stop fails."""
        mock_run.return_value = mock.MagicMock(returncode=1)
        result = rollback("v1.9.0")
        assert result is False

    @mock.patch("deploy.subprocess.run")
    def test_rollback_start_failure(self, mock_run: mock.MagicMock) -> None:
        """Verify rollback returns False when start fails."""
        mock_run.side_effect = [
            mock.MagicMock(returncode=0),  # stop succeeds
            mock.MagicMock(returncode=1),  # start fails
        ]
        result = rollback("v1.9.0")
        assert result is False

    @mock.patch("deploy.subprocess.run")
    def test_rollback_timeout(self, mock_run: mock.MagicMock) -> None:
        """Verify rollback handles timeout gracefully."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="docker-compose", timeout=120)
        result = rollback("v1.9.0")
        assert result is False
