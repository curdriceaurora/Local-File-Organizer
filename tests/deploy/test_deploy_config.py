"""Tests for deployment configuration loading and validation.

Validates DeploymentConfig construction, environment variable loading,
default values, and edge cases for all configuration fields.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

import pytest

from file_organizer.deploy.config import (
    VALID_ENVIRONMENTS,
    VALID_LOG_LEVELS,
    DeploymentConfig,
)


@pytest.mark.unit
class TestDeploymentConfigDefaults:
    """Tests for DeploymentConfig default values."""

    def test_default_environment(self) -> None:
        """Verify default environment is 'dev'."""
        config = DeploymentConfig()
        assert config.environment == "dev"

    def test_default_redis_url(self) -> None:
        """Verify default Redis URL points to localhost."""
        config = DeploymentConfig()
        assert config.redis_url == "redis://localhost:6379/0"

    def test_default_data_directory(self) -> None:
        """Verify default data directory is /data."""
        config = DeploymentConfig()
        assert config.data_directory == Path("/data")

    def test_default_log_level(self) -> None:
        """Verify default log level is DEBUG."""
        config = DeploymentConfig()
        assert config.log_level == "DEBUG"

    def test_default_max_workers(self) -> None:
        """Verify default max_workers is 2."""
        config = DeploymentConfig()
        assert config.max_workers == 2

    def test_default_host(self) -> None:
        """Verify default host is 0.0.0.0."""
        config = DeploymentConfig()
        assert config.host == "0.0.0.0"

    def test_default_port(self) -> None:
        """Verify default port is 8000."""
        config = DeploymentConfig()
        assert config.port == 8000


@pytest.mark.unit
class TestDeploymentConfigValidation:
    """Tests for DeploymentConfig validation logic."""

    def test_invalid_environment_raises_error(self) -> None:
        """Verify ValueError for invalid environment."""
        with pytest.raises(ValueError, match="Invalid environment"):
            DeploymentConfig(environment="production")

    def test_invalid_log_level_raises_error(self) -> None:
        """Verify ValueError for invalid log level."""
        with pytest.raises(ValueError, match="Invalid log_level"):
            DeploymentConfig(log_level="VERBOSE")

    def test_log_level_normalized_to_uppercase(self) -> None:
        """Verify log level is normalized to uppercase."""
        config = DeploymentConfig(log_level="info")
        assert config.log_level == "INFO"

    def test_max_workers_zero_raises_error(self) -> None:
        """Verify ValueError for max_workers less than 1."""
        with pytest.raises(ValueError, match="max_workers must be at least 1"):
            DeploymentConfig(max_workers=0)

    def test_max_workers_negative_raises_error(self) -> None:
        """Verify ValueError for negative max_workers."""
        with pytest.raises(ValueError, match="max_workers must be at least 1"):
            DeploymentConfig(max_workers=-1)

    def test_invalid_port_zero_raises_error(self) -> None:
        """Verify ValueError for port 0."""
        with pytest.raises(ValueError, match="port must be between"):
            DeploymentConfig(port=0)

    def test_invalid_port_too_high_raises_error(self) -> None:
        """Verify ValueError for port above 65535."""
        with pytest.raises(ValueError, match="port must be between"):
            DeploymentConfig(port=70000)

    def test_string_data_directory_converted_to_path(self) -> None:
        """Verify string data_directory is converted to Path."""
        config = DeploymentConfig(data_directory="/tmp/test")  # type: ignore[arg-type]
        assert isinstance(config.data_directory, Path)
        assert config.data_directory == Path("/tmp/test")

    def test_all_valid_environments_accepted(self) -> None:
        """Verify all defined valid environments are accepted."""
        for env in VALID_ENVIRONMENTS:
            config = DeploymentConfig(environment=env)
            assert config.environment == env

    def test_all_valid_log_levels_accepted(self) -> None:
        """Verify all defined valid log levels are accepted."""
        for level in VALID_LOG_LEVELS:
            config = DeploymentConfig(log_level=level)
            assert config.log_level == level


@pytest.mark.unit
class TestDeploymentConfigFromEnv:
    """Tests for DeploymentConfig.from_env() class method."""

    def test_from_env_default_values(self) -> None:
        """Verify from_env returns dev defaults when no env vars set."""
        with mock.patch.dict(os.environ, {}, clear=True):
            config = DeploymentConfig.from_env()
            assert config.environment == "dev"
            assert config.log_level == "DEBUG"
            assert config.max_workers == 2

    def test_from_env_prod_environment(self) -> None:
        """Verify from_env returns prod defaults for prod environment."""
        env = {"FO_ENVIRONMENT": "prod"}
        with mock.patch.dict(os.environ, env, clear=True):
            config = DeploymentConfig.from_env()
            assert config.environment == "prod"
            assert config.log_level == "WARNING"
            assert config.max_workers == 8
            assert config.redis_url == "redis://redis:6379/0"

    def test_from_env_staging_environment(self) -> None:
        """Verify from_env returns staging defaults for staging environment."""
        env = {"FO_ENVIRONMENT": "staging"}
        with mock.patch.dict(os.environ, env, clear=True):
            config = DeploymentConfig.from_env()
            assert config.environment == "staging"
            assert config.log_level == "INFO"
            assert config.max_workers == 4

    def test_from_env_custom_redis_url(self) -> None:
        """Verify from_env picks up custom Redis URL."""
        env = {"FO_REDIS_URL": "redis://custom-host:6380/1"}
        with mock.patch.dict(os.environ, env, clear=True):
            config = DeploymentConfig.from_env()
            assert config.redis_url == "redis://custom-host:6380/1"

    def test_from_env_custom_data_dir(self) -> None:
        """Verify from_env picks up custom data directory."""
        env = {"FO_DATA_DIR": "/mnt/storage"}
        with mock.patch.dict(os.environ, env, clear=True):
            config = DeploymentConfig.from_env()
            assert config.data_directory == Path("/mnt/storage")

    def test_from_env_custom_log_level(self) -> None:
        """Verify from_env picks up custom log level."""
        env = {"FO_LOG_LEVEL": "ERROR"}
        with mock.patch.dict(os.environ, env, clear=True):
            config = DeploymentConfig.from_env()
            assert config.log_level == "ERROR"

    def test_from_env_custom_max_workers(self) -> None:
        """Verify from_env picks up custom max_workers."""
        env = {"FO_MAX_WORKERS": "16"}
        with mock.patch.dict(os.environ, env, clear=True):
            config = DeploymentConfig.from_env()
            assert config.max_workers == 16

    def test_from_env_custom_host_port(self) -> None:
        """Verify from_env picks up custom host and port."""
        env = {"FO_HOST": "127.0.0.1", "FO_PORT": "9000"}
        with mock.patch.dict(os.environ, env, clear=True):
            config = DeploymentConfig.from_env()
            assert config.host == "127.0.0.1"
            assert config.port == 9000

    def test_from_env_environment_case_insensitive(self) -> None:
        """Verify FO_ENVIRONMENT is case-insensitive."""
        env = {"FO_ENVIRONMENT": "PROD"}
        with mock.patch.dict(os.environ, env, clear=True):
            config = DeploymentConfig.from_env()
            assert config.environment == "prod"

    def test_from_env_overrides_env_defaults(self) -> None:
        """Verify explicit env vars override environment-specific defaults."""
        env = {
            "FO_ENVIRONMENT": "prod",
            "FO_LOG_LEVEL": "DEBUG",
            "FO_MAX_WORKERS": "1",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            config = DeploymentConfig.from_env()
            assert config.environment == "prod"
            assert config.log_level == "DEBUG"
            assert config.max_workers == 1


@pytest.mark.unit
class TestDeploymentConfigProperties:
    """Tests for DeploymentConfig computed properties."""

    def test_is_production_true(self) -> None:
        """Verify is_production returns True for prod."""
        config = DeploymentConfig(environment="prod")
        assert config.is_production is True

    def test_is_production_false(self) -> None:
        """Verify is_production returns False for dev."""
        config = DeploymentConfig(environment="dev")
        assert config.is_production is False

    def test_is_development_true(self) -> None:
        """Verify is_development returns True for dev."""
        config = DeploymentConfig(environment="dev")
        assert config.is_development is True

    def test_is_development_false(self) -> None:
        """Verify is_development returns False for prod."""
        config = DeploymentConfig(environment="prod")
        assert config.is_development is False

    def test_redis_host_extraction(self) -> None:
        """Verify redis_host extracts host from URL."""
        config = DeploymentConfig(redis_url="redis://myhost:6379/0")
        assert config.redis_host == "myhost"

    def test_redis_port_extraction(self) -> None:
        """Verify redis_port extracts port from URL."""
        config = DeploymentConfig(redis_url="redis://myhost:6380/0")
        assert config.redis_port == 6380

    def test_redis_port_default(self) -> None:
        """Verify redis_port defaults to 6379 when no port in URL."""
        config = DeploymentConfig(redis_url="redis://myhost/0")
        assert config.redis_port == 6379

    def test_redis_host_localhost(self) -> None:
        """Verify redis_host handles localhost URL."""
        config = DeploymentConfig(redis_url="redis://localhost:6379/0")
        assert config.redis_host == "localhost"
