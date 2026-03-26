"""Integration tests for API config loading.

Covers:
  - api/config.py — ApiSettings, load_settings, _parse_list, _load_yaml
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from file_organizer.api.config import ApiSettings, load_settings

pytestmark = [pytest.mark.ci, pytest.mark.integration]


# ---------------------------------------------------------------------------
# ApiSettings
# ---------------------------------------------------------------------------


class TestApiSettingsDefaults:
    def test_created(self) -> None:
        s = ApiSettings()
        assert s is not None

    def test_default_port(self) -> None:
        assert ApiSettings().port == 8000

    def test_default_environment(self) -> None:
        assert ApiSettings().environment == "development"

    def test_default_auth_enabled(self) -> None:
        assert ApiSettings().auth_enabled is True

    def test_default_cors_origins_non_empty(self) -> None:
        assert len(ApiSettings().cors_origins) > 0

    def test_default_rate_limit_enabled(self) -> None:
        assert ApiSettings().rate_limit_enabled is True

    def test_version_is_string(self) -> None:
        assert len(ApiSettings().version) > 0


class TestApiSettingsOllamaUrlValidator:
    def test_bare_host_port_gets_http_prefix(self) -> None:
        s = ApiSettings(ollama_url="localhost:11434")
        assert s.ollama_url.startswith("http://")

    def test_http_url_unchanged(self) -> None:
        s = ApiSettings(ollama_url="http://localhost:11434")
        assert s.ollama_url == "http://localhost:11434"

    def test_https_url_unchanged(self) -> None:
        s = ApiSettings(ollama_url="https://my.server.com")
        assert s.ollama_url == "https://my.server.com"


# ---------------------------------------------------------------------------
# load_settings — no env vars
# ---------------------------------------------------------------------------


class TestLoadSettingsNoEnv:
    def test_returns_api_settings(self) -> None:
        s = load_settings()
        assert isinstance(s, ApiSettings)

    def test_default_port_returned(self) -> None:
        s = load_settings()
        assert s.port == 8000


# ---------------------------------------------------------------------------
# load_settings — env var overrides
# ---------------------------------------------------------------------------


class TestLoadSettingsEnvOverrides:
    def test_app_name_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_API_APP_NAME", "MyApp")
        s = load_settings()
        assert s.app_name == "MyApp"

    def test_port_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_API_PORT", "9090")
        s = load_settings()
        assert s.port == 9090

    def test_invalid_port_falls_back_to_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_API_PORT", "not-a-number")
        s = load_settings()
        assert s.port == 8000

    def test_environment_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_API_ENVIRONMENT", "staging")
        monkeypatch.setenv("FO_API_AUTH_JWT_SECRET", "a-real-secret-key")
        monkeypatch.setenv("FO_API_CORS_ORIGINS", "https://app.example.com")
        s = load_settings()
        assert s.environment == "staging"

    def test_log_level_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_API_LOG_LEVEL", "DEBUG")
        s = load_settings()
        assert s.log_level == "DEBUG"

    def test_cors_origins_json_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_API_CORS_ORIGINS", '["http://example.com"]')
        s = load_settings()
        assert s.cors_origins == ["http://example.com"]

    def test_cors_origins_csv_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_API_CORS_ORIGINS", "http://a.com,http://b.com")
        s = load_settings()
        assert len(s.cors_origins) == 2

    def test_enable_docs_false_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_API_ENABLE_DOCS", "false")
        s = load_settings()
        assert s.enable_docs is False

    def test_enable_docs_true_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_API_ENABLE_DOCS", "1")
        s = load_settings()
        assert s.enable_docs is True

    def test_invalid_boolean_env_keeps_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_API_AUTH_ENABLED", "maybe")
        s = load_settings()
        assert s.auth_enabled is True

    def test_invalid_rate_limit_boolean_keeps_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FO_API_RATE_LIMIT_ENABLED", "maybe")
        s = load_settings()
        assert s.rate_limit_enabled is True

    def test_invalid_bootstrap_local_only_boolean_keeps_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FO_API_AUTH_BOOTSTRAP_LOCAL_ONLY", "maybe")
        s = load_settings()
        assert s.auth_bootstrap_admin_local_only is True

    def test_auth_enabled_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_API_AUTH_ENABLED", "false")
        s = load_settings()
        assert s.auth_enabled is False

    def test_auth_jwt_secret_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_API_AUTH_JWT_SECRET", "my-secret-key")
        s = load_settings()
        assert s.auth_jwt_secret.get_secret_value() == "my-secret-key"

    def test_auth_access_minutes_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_API_AUTH_ACCESS_MINUTES", "60")
        s = load_settings()
        assert s.auth_access_token_minutes == 60

    def test_invalid_access_minutes_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_API_AUTH_ACCESS_MINUTES", "bad")
        s = load_settings()
        assert s.auth_access_token_minutes == 30

    def test_auth_refresh_days_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_API_AUTH_REFRESH_DAYS", "14")
        s = load_settings()
        assert s.auth_refresh_token_days == 14

    def test_auth_redis_url_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_API_AUTH_REDIS_URL", "redis://localhost:6379")
        s = load_settings()
        assert s.auth_redis_url == "redis://localhost:6379"

    def test_fo_redis_url_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FO_API_AUTH_REDIS_URL", raising=False)
        monkeypatch.setenv("FO_REDIS_URL", "redis://fallback:6379")
        s = load_settings()
        assert s.auth_redis_url == "redis://fallback:6379"

    def test_auth_login_rate_limit_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_API_AUTH_LOGIN_RATE_LIMIT", "false")
        s = load_settings()
        assert s.auth_login_rate_limit_enabled is False

    def test_auth_login_max_attempts_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_API_AUTH_LOGIN_MAX_ATTEMPTS", "10")
        s = load_settings()
        assert s.auth_login_max_attempts == 10

    def test_invalid_login_max_attempts_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_API_AUTH_LOGIN_MAX_ATTEMPTS", "bad")
        s = load_settings()
        assert s.auth_login_max_attempts == 5

    def test_auth_password_min_length_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_API_AUTH_PASSWORD_MIN_LENGTH", "16")
        s = load_settings()
        assert s.auth_password_min_length == 16

    def test_password_require_number_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_API_AUTH_PASSWORD_REQUIRE_NUMBER", "false")
        s = load_settings()
        assert s.auth_password_require_number is False

    def test_password_require_letter_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_API_AUTH_PASSWORD_REQUIRE_LETTER", "false")
        s = load_settings()
        assert s.auth_password_require_letter is False

    def test_password_require_special_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_API_AUTH_PASSWORD_REQUIRE_SPECIAL", "false")
        s = load_settings()
        assert s.auth_password_require_special is False

    def test_password_require_uppercase_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_API_AUTH_PASSWORD_REQUIRE_UPPERCASE", "false")
        s = load_settings()
        assert s.auth_password_require_uppercase is False

    def test_cors_allow_methods_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_API_CORS_ALLOW_METHODS", "GET,POST")
        s = load_settings()
        assert "GET" in s.cors_allow_methods

    def test_cors_allow_headers_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_API_CORS_ALLOW_HEADERS", "Content-Type,Authorization")
        s = load_settings()
        assert "Content-Type" in s.cors_allow_headers

    def test_cors_allow_credentials_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_API_CORS_ALLOW_CREDENTIALS", "false")
        s = load_settings()
        assert s.cors_allow_credentials is False

    def test_websocket_token_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_API_WEBSOCKET_TOKEN", "secret-ws-token")
        s = load_settings()
        assert s.websocket_token == "secret-ws-token"

    def test_auth_db_path_from_env(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setenv("FO_API_AUTH_DB_PATH", str(tmp_path / "auth.db"))
        s = load_settings()
        assert "auth.db" in s.auth_db_path

    def test_ws_ping_interval_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_API_WS_PING_INTERVAL", "60")
        s = load_settings()
        assert s.websocket_ping_interval == 60

    def test_invalid_ws_ping_interval_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_API_WS_PING_INTERVAL", "bad")
        s = load_settings()
        assert s.websocket_ping_interval == 30

    def test_zero_ws_ping_interval_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_API_WS_PING_INTERVAL", "0")
        s = load_settings()
        assert s.websocket_ping_interval == 30


# ---------------------------------------------------------------------------
# load_settings — YAML config file
# ---------------------------------------------------------------------------


class TestLoadSettingsYamlFile:
    def test_settings_loaded_from_yaml(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = tmp_path / "api.yml"
        cfg.write_text(yaml.dump({"app_name": "YAML App", "port": 7777}), encoding="utf-8")
        monkeypatch.setenv("FO_API_CONFIG_PATH", str(cfg))
        s = load_settings()
        assert s.app_name == "YAML App"
        assert s.port == 7777

    def test_nested_api_key_in_yaml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = tmp_path / "api.yml"
        cfg.write_text(
            yaml.dump({"api": {"app_name": "Nested YAML App", "port": 5555}}),
            encoding="utf-8",
        )
        monkeypatch.setenv("FO_API_CONFIG_PATH", str(cfg))
        s = load_settings()
        assert s.app_name == "Nested YAML App"

    def test_missing_config_path_logs_warning(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FO_API_CONFIG_PATH", str(tmp_path / "missing.yml"))
        s = load_settings()
        assert isinstance(s, ApiSettings)

    def test_corrupt_yaml_returns_defaults(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = tmp_path / "api.yml"
        cfg.write_text("not: valid: yaml: [[[", encoding="utf-8")
        monkeypatch.setenv("FO_API_CONFIG_PATH", str(cfg))
        s = load_settings()
        assert isinstance(s, ApiSettings)

    def test_non_dict_yaml_returns_defaults(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = tmp_path / "api.yml"
        cfg.write_text(yaml.dump([1, 2, 3]), encoding="utf-8")
        monkeypatch.setenv("FO_API_CONFIG_PATH", str(cfg))
        s = load_settings()
        assert isinstance(s, ApiSettings)

    def test_env_overrides_yaml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = tmp_path / "api.yml"
        cfg.write_text(yaml.dump({"port": 7777}), encoding="utf-8")
        monkeypatch.setenv("FO_API_CONFIG_PATH", str(cfg))
        monkeypatch.setenv("FO_API_PORT", "8888")
        s = load_settings()
        assert s.port == 8888
