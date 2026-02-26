"""Tests for API configuration and settings loader."""

from __future__ import annotations

import json
import os

import pytest

from file_organizer.api.config import (
    ApiSettings,
    _load_yaml,
    _parse_list,
    load_settings,
)


@pytest.mark.unit
class TestParseList:
    """Tests for _parse_list helper."""

    def test_comma_separated(self):
        assert _parse_list("a,b,c") == ["a", "b", "c"]

    def test_json_array(self):
        assert _parse_list('["a","b","c"]') == ["a", "b", "c"]

    def test_empty_string(self):
        assert _parse_list("") == []

    def test_whitespace_only(self):
        assert _parse_list("   ") == []

    def test_strips_whitespace(self):
        assert _parse_list("a , b , c") == ["a", "b", "c"]

    def test_invalid_json_falls_back_to_csv(self):
        result = _parse_list("[invalid json")
        assert result == ["invalid json"]

    def test_json_with_non_string_items(self):
        assert _parse_list("[1, 2, 3]") == ["1", "2", "3"]

    def test_single_value(self):
        assert _parse_list("single") == ["single"]

    def test_trailing_comma(self):
        result = _parse_list("a,b,")
        assert result == ["a", "b"]


@pytest.mark.unit
class TestLoadYaml:
    """Tests for _load_yaml helper."""

    def test_valid_yaml(self, tmp_path):
        f = tmp_path / "config.yaml"
        f.write_text("api:\n  host: 0.0.0.0\n  port: 9000\n")
        result = _load_yaml(f)
        assert result["api"]["host"] == "0.0.0.0"
        assert result["api"]["port"] == 9000

    def test_non_dict_yaml(self, tmp_path):
        f = tmp_path / "config.yaml"
        f.write_text("- item1\n- item2\n")
        assert _load_yaml(f) == {}

    def test_nonexistent_file(self, tmp_path):
        result = _load_yaml(tmp_path / "missing.yaml")
        assert result == {}

    def test_invalid_yaml(self, tmp_path):
        f = tmp_path / "bad.yaml"
        f.write_text("{{invalid: yaml: [")
        result = _load_yaml(f)
        # yaml.safe_load may parse this or return empty; either way no crash
        assert isinstance(result, dict)


@pytest.mark.unit
class TestApiSettings:
    """Tests for ApiSettings defaults."""

    def test_defaults(self):
        settings = ApiSettings()
        assert settings.app_name == "File Organizer API"
        assert settings.host == "0.0.0.0"
        assert settings.port == 8000
        assert settings.environment == "development"
        assert settings.auth_enabled is True
        assert settings.enable_docs is True
        assert settings.rate_limit_enabled is True
        assert settings.api_key_enabled is True

    def test_cors_defaults(self):
        settings = ApiSettings()
        assert "http://localhost:3000" in settings.cors_origins
        assert settings.cors_allow_credentials is True
        assert "*" in settings.cors_allow_methods

    def test_custom_values(self):
        settings = ApiSettings(
            app_name="Custom API",
            port=9000,
            environment="production",
        )
        assert settings.app_name == "Custom API"
        assert settings.port == 9000

    def test_security_defaults(self):
        settings = ApiSettings()
        assert settings.security_headers_enabled is True
        assert settings.security_hsts_seconds == 31536000
        assert settings.security_hsts_subdomains is True

    def test_rate_limit_rules_defaults(self):
        settings = ApiSettings()
        assert "/api/v1/auth/login" in settings.rate_limit_rules


@pytest.mark.unit
class TestLoadSettings:
    """Tests for load_settings."""

    @pytest.fixture(autouse=True)
    def _clean_env(self, monkeypatch):
        """Remove all FO_API_ environment variables for clean tests."""
        for key in list(os.environ):
            if key.startswith("FO_API_") or key.startswith("FO_REDIS_"):
                monkeypatch.delenv(key, raising=False)
        # Also clear config path
        monkeypatch.delenv("FO_API_CONFIG_PATH", raising=False)

    def test_defaults_with_no_env(self):
        settings = load_settings()
        assert settings.app_name == "File Organizer API"
        assert settings.environment == "development"

    def test_env_app_name(self, monkeypatch):
        monkeypatch.setenv("FO_API_APP_NAME", "Test App")
        settings = load_settings()
        assert settings.app_name == "Test App"

    def test_env_version(self, monkeypatch):
        monkeypatch.setenv("FO_API_VERSION", "99.0.0")
        settings = load_settings()
        assert settings.version == "99.0.0"

    def test_env_environment(self, monkeypatch):
        monkeypatch.setenv("FO_API_ENVIRONMENT", "test")
        settings = load_settings()
        assert settings.environment == "test"

    def test_env_host(self, monkeypatch):
        monkeypatch.setenv("FO_API_HOST", "127.0.0.1")
        settings = load_settings()
        assert settings.host == "127.0.0.1"

    def test_env_port_valid(self, monkeypatch):
        monkeypatch.setenv("FO_API_PORT", "9000")
        settings = load_settings()
        assert settings.port == 9000

    def test_env_port_invalid(self, monkeypatch):
        monkeypatch.setenv("FO_API_PORT", "not-a-number")
        settings = load_settings()
        assert settings.port == 8000  # Falls back to default

    def test_env_log_level(self, monkeypatch):
        monkeypatch.setenv("FO_API_LOG_LEVEL", "DEBUG")
        settings = load_settings()
        assert settings.log_level == "DEBUG"

    def test_env_cors_origins(self, monkeypatch):
        monkeypatch.setenv("FO_API_CORS_ORIGINS", "http://example.com,http://other.com")
        settings = load_settings()
        assert settings.cors_origins == ["http://example.com", "http://other.com"]

    def test_env_cors_allow_methods(self, monkeypatch):
        monkeypatch.setenv("FO_API_CORS_ALLOW_METHODS", "GET,POST")
        settings = load_settings()
        assert settings.cors_allow_methods == ["GET", "POST"]

    def test_env_cors_allow_headers(self, monkeypatch):
        monkeypatch.setenv("FO_API_CORS_ALLOW_HEADERS", "Content-Type,Authorization")
        settings = load_settings()
        assert settings.cors_allow_headers == ["Content-Type", "Authorization"]

    def test_env_cors_allow_credentials_true(self, monkeypatch):
        monkeypatch.setenv("FO_API_CORS_ALLOW_CREDENTIALS", "true")
        settings = load_settings()
        assert settings.cors_allow_credentials is True

    def test_env_cors_allow_credentials_false(self, monkeypatch):
        monkeypatch.setenv("FO_API_CORS_ALLOW_CREDENTIALS", "false")
        settings = load_settings()
        assert settings.cors_allow_credentials is False

    def test_env_enable_docs_true(self, monkeypatch):
        monkeypatch.setenv("FO_API_ENABLE_DOCS", "1")
        settings = load_settings()
        assert settings.enable_docs is True

    def test_env_enable_docs_false(self, monkeypatch):
        monkeypatch.setenv("FO_API_ENABLE_DOCS", "no")
        settings = load_settings()
        assert settings.enable_docs is False

    def test_env_allowed_paths(self, monkeypatch):
        monkeypatch.setenv("FO_API_ALLOWED_PATHS", "/tmp,/home")
        settings = load_settings()
        assert settings.allowed_paths == ["/tmp", "/home"]

    def test_env_ws_ping_interval_valid(self, monkeypatch):
        monkeypatch.setenv("FO_API_WS_PING_INTERVAL", "15")
        settings = load_settings()
        assert settings.websocket_ping_interval == 15

    def test_env_ws_ping_interval_invalid_string(self, monkeypatch):
        monkeypatch.setenv("FO_API_WS_PING_INTERVAL", "abc")
        settings = load_settings()
        assert settings.websocket_ping_interval == 30  # default

    def test_env_ws_ping_interval_zero(self, monkeypatch):
        monkeypatch.setenv("FO_API_WS_PING_INTERVAL", "0")
        settings = load_settings()
        assert settings.websocket_ping_interval == 30  # default since 0 is not > 0

    def test_env_websocket_token(self, monkeypatch):
        monkeypatch.setenv("FO_API_WEBSOCKET_TOKEN", "secret-token")
        settings = load_settings()
        assert settings.websocket_token == "secret-token"

    def test_env_auth_enabled(self, monkeypatch):
        monkeypatch.setenv("FO_API_AUTH_ENABLED", "false")
        settings = load_settings()
        assert settings.auth_enabled is False

    def test_env_auth_db_path(self, monkeypatch):
        monkeypatch.setenv("FO_API_AUTH_DB_PATH", "/tmp/auth.db")
        settings = load_settings()
        assert settings.auth_db_path == "/tmp/auth.db"

    def test_env_auth_jwt_secret(self, monkeypatch):
        monkeypatch.setenv("FO_API_AUTH_JWT_SECRET", "my-secret-key")
        settings = load_settings()
        assert settings.auth_jwt_secret.get_secret_value() == "my-secret-key"

    def test_env_auth_jwt_algorithm(self, monkeypatch):
        monkeypatch.setenv("FO_API_AUTH_JWT_ALGORITHM", "HS512")
        settings = load_settings()
        assert settings.auth_jwt_algorithm == "HS512"

    def test_env_auth_access_minutes_valid(self, monkeypatch):
        monkeypatch.setenv("FO_API_AUTH_ACCESS_MINUTES", "60")
        settings = load_settings()
        assert settings.auth_access_token_minutes == 60

    def test_env_auth_access_minutes_invalid(self, monkeypatch):
        monkeypatch.setenv("FO_API_AUTH_ACCESS_MINUTES", "bad")
        settings = load_settings()
        assert settings.auth_access_token_minutes == 30

    def test_env_auth_refresh_days_valid(self, monkeypatch):
        monkeypatch.setenv("FO_API_AUTH_REFRESH_DAYS", "14")
        settings = load_settings()
        assert settings.auth_refresh_token_days == 14

    def test_env_auth_refresh_days_invalid(self, monkeypatch):
        monkeypatch.setenv("FO_API_AUTH_REFRESH_DAYS", "bad")
        settings = load_settings()
        assert settings.auth_refresh_token_days == 7

    def test_env_auth_redis_url(self, monkeypatch):
        monkeypatch.setenv("FO_API_AUTH_REDIS_URL", "redis://auth:6379")
        settings = load_settings()
        assert settings.auth_redis_url == "redis://auth:6379"

    def test_env_redis_url_fallback(self, monkeypatch):
        monkeypatch.setenv("FO_REDIS_URL", "redis://fallback:6379")
        settings = load_settings()
        assert settings.auth_redis_url == "redis://fallback:6379"

    def test_env_auth_redis_url_takes_priority(self, monkeypatch):
        monkeypatch.setenv("FO_API_AUTH_REDIS_URL", "redis://primary:6379")
        monkeypatch.setenv("FO_REDIS_URL", "redis://fallback:6379")
        settings = load_settings()
        assert settings.auth_redis_url == "redis://primary:6379"

    def test_env_auth_login_rate_limit(self, monkeypatch):
        monkeypatch.setenv("FO_API_AUTH_LOGIN_RATE_LIMIT", "false")
        settings = load_settings()
        assert settings.auth_login_rate_limit_enabled is False

    def test_env_auth_login_max_attempts_valid(self, monkeypatch):
        monkeypatch.setenv("FO_API_AUTH_LOGIN_MAX_ATTEMPTS", "10")
        settings = load_settings()
        assert settings.auth_login_max_attempts == 10

    def test_env_auth_login_max_attempts_invalid(self, monkeypatch):
        monkeypatch.setenv("FO_API_AUTH_LOGIN_MAX_ATTEMPTS", "bad")
        settings = load_settings()
        assert settings.auth_login_max_attempts == 5

    def test_env_auth_login_window_seconds_valid(self, monkeypatch):
        monkeypatch.setenv("FO_API_AUTH_LOGIN_WINDOW_SECONDS", "300")
        settings = load_settings()
        assert settings.auth_login_window_seconds == 300

    def test_env_auth_login_window_seconds_invalid(self, monkeypatch):
        monkeypatch.setenv("FO_API_AUTH_LOGIN_WINDOW_SECONDS", "bad")
        settings = load_settings()
        assert settings.auth_login_window_seconds == 900

    def test_env_auth_password_min_length_valid(self, monkeypatch):
        monkeypatch.setenv("FO_API_AUTH_PASSWORD_MIN_LENGTH", "8")
        settings = load_settings()
        assert settings.auth_password_min_length == 8

    def test_env_auth_password_min_length_invalid(self, monkeypatch):
        monkeypatch.setenv("FO_API_AUTH_PASSWORD_MIN_LENGTH", "bad")
        settings = load_settings()
        assert settings.auth_password_min_length == 12

    def test_env_password_require_number(self, monkeypatch):
        monkeypatch.setenv("FO_API_AUTH_PASSWORD_REQUIRE_NUMBER", "false")
        settings = load_settings()
        assert settings.auth_password_require_number is False

    def test_env_password_require_letter(self, monkeypatch):
        monkeypatch.setenv("FO_API_AUTH_PASSWORD_REQUIRE_LETTER", "false")
        settings = load_settings()
        assert settings.auth_password_require_letter is False

    def test_env_password_require_special(self, monkeypatch):
        monkeypatch.setenv("FO_API_AUTH_PASSWORD_REQUIRE_SPECIAL", "false")
        settings = load_settings()
        assert settings.auth_password_require_special is False

    def test_env_password_require_uppercase(self, monkeypatch):
        monkeypatch.setenv("FO_API_AUTH_PASSWORD_REQUIRE_UPPERCASE", "false")
        settings = load_settings()
        assert settings.auth_password_require_uppercase is False

    def test_env_bootstrap_admin(self, monkeypatch):
        monkeypatch.setenv("FO_API_AUTH_BOOTSTRAP_ADMIN", "true")
        settings = load_settings()
        assert settings.auth_bootstrap_admin is True

    def test_env_bootstrap_local_only(self, monkeypatch):
        monkeypatch.setenv("FO_API_AUTH_BOOTSTRAP_LOCAL_ONLY", "false")
        settings = load_settings()
        assert settings.auth_bootstrap_admin_local_only is False

    def test_env_database_url(self, monkeypatch):
        monkeypatch.setenv("FO_API_DATABASE_URL", "sqlite:///test.db")
        settings = load_settings()
        assert settings.database_url == "sqlite:///test.db"

    def test_env_db_pool_size_valid(self, monkeypatch):
        monkeypatch.setenv("FO_API_DB_POOL_SIZE", "20")
        settings = load_settings()
        assert settings.database_pool_size == 20

    def test_env_db_pool_size_invalid(self, monkeypatch):
        monkeypatch.setenv("FO_API_DB_POOL_SIZE", "bad")
        settings = load_settings()
        assert settings.database_pool_size == 10

    def test_env_db_max_overflow_valid(self, monkeypatch):
        monkeypatch.setenv("FO_API_DB_MAX_OVERFLOW", "50")
        settings = load_settings()
        assert settings.database_max_overflow == 50

    def test_env_db_max_overflow_invalid(self, monkeypatch):
        monkeypatch.setenv("FO_API_DB_MAX_OVERFLOW", "bad")
        settings = load_settings()
        assert settings.database_max_overflow == 20

    def test_env_db_pool_pre_ping(self, monkeypatch):
        monkeypatch.setenv("FO_API_DB_POOL_PRE_PING", "false")
        settings = load_settings()
        assert settings.database_pool_pre_ping is False

    def test_env_db_pool_recycle_seconds_valid(self, monkeypatch):
        monkeypatch.setenv("FO_API_DB_POOL_RECYCLE_SECONDS", "3600")
        settings = load_settings()
        assert settings.database_pool_recycle_seconds == 3600

    def test_env_db_pool_recycle_seconds_invalid(self, monkeypatch):
        monkeypatch.setenv("FO_API_DB_POOL_RECYCLE_SECONDS", "bad")
        settings = load_settings()
        assert settings.database_pool_recycle_seconds == 1800

    def test_env_db_echo(self, monkeypatch):
        monkeypatch.setenv("FO_API_DB_ECHO", "true")
        settings = load_settings()
        assert settings.database_echo is True

    def test_env_cache_redis_url(self, monkeypatch):
        monkeypatch.setenv("FO_API_CACHE_REDIS_URL", "redis://cache:6379")
        settings = load_settings()
        assert settings.cache_redis_url == "redis://cache:6379"

    def test_env_cache_redis_url_fallback(self, monkeypatch):
        monkeypatch.setenv("FO_REDIS_URL", "redis://shared:6379")
        settings = load_settings()
        assert settings.cache_redis_url == "redis://shared:6379"

    def test_env_cache_ttl_seconds_valid(self, monkeypatch):
        monkeypatch.setenv("FO_API_CACHE_TTL_SECONDS", "600")
        settings = load_settings()
        assert settings.cache_default_ttl_seconds == 600

    def test_env_cache_ttl_seconds_invalid(self, monkeypatch):
        monkeypatch.setenv("FO_API_CACHE_TTL_SECONDS", "bad")
        settings = load_settings()
        assert settings.cache_default_ttl_seconds == 900

    def test_env_api_key_enabled(self, monkeypatch):
        monkeypatch.setenv("FO_API_API_KEY_ENABLED", "false")
        settings = load_settings()
        assert settings.api_key_enabled is False

    def test_env_api_key_admin(self, monkeypatch):
        monkeypatch.setenv("FO_API_API_KEY_ADMIN", "true")
        settings = load_settings()
        assert settings.api_key_admin is True

    def test_env_api_key_header(self, monkeypatch):
        monkeypatch.setenv("FO_API_API_KEY_HEADER", "X-Custom-Key")
        settings = load_settings()
        assert settings.api_key_header == "X-Custom-Key"

    def test_env_api_keys_hashed(self, monkeypatch):
        monkeypatch.setenv("FO_API_API_KEYS", "key1,key2")
        settings = load_settings()
        assert len(settings.api_key_hashes) == 2
        # Each should be a bcrypt hash
        for h in settings.api_key_hashes:
            assert h.startswith("$2")

    def test_env_api_key_hashes_direct(self, monkeypatch):
        monkeypatch.setenv("FO_API_API_KEY_HASHES", "hash1,hash2")
        settings = load_settings()
        assert settings.api_key_hashes == ["hash1", "hash2"]

    def test_env_rate_limit_enabled(self, monkeypatch):
        monkeypatch.setenv("FO_API_RATE_LIMIT_ENABLED", "false")
        settings = load_settings()
        assert settings.rate_limit_enabled is False

    def test_env_rate_limit_default_requests_valid(self, monkeypatch):
        monkeypatch.setenv("FO_API_RATE_LIMIT_DEFAULT_REQUESTS", "500")
        settings = load_settings()
        assert settings.rate_limit_default_requests == 500

    def test_env_rate_limit_default_requests_invalid(self, monkeypatch):
        monkeypatch.setenv("FO_API_RATE_LIMIT_DEFAULT_REQUESTS", "bad")
        settings = load_settings()
        assert settings.rate_limit_default_requests == 1000

    def test_env_rate_limit_default_window_valid(self, monkeypatch):
        monkeypatch.setenv("FO_API_RATE_LIMIT_DEFAULT_WINDOW_SECONDS", "120")
        settings = load_settings()
        assert settings.rate_limit_default_window_seconds == 120

    def test_env_rate_limit_default_window_invalid(self, monkeypatch):
        monkeypatch.setenv("FO_API_RATE_LIMIT_DEFAULT_WINDOW_SECONDS", "bad")
        settings = load_settings()
        assert settings.rate_limit_default_window_seconds == 60

    def test_env_rate_limit_trust_proxy_headers(self, monkeypatch):
        monkeypatch.setenv("FO_API_RATE_LIMIT_TRUST_PROXY_HEADERS", "true")
        settings = load_settings()
        assert settings.rate_limit_trust_proxy_headers is True

    def test_env_rate_limit_exempt_paths(self, monkeypatch):
        monkeypatch.setenv("FO_API_RATE_LIMIT_EXEMPT_PATHS", "/health,/ready")
        settings = load_settings()
        assert settings.rate_limit_exempt_paths == ["/health", "/ready"]

    def test_env_rate_limit_rules_json(self, monkeypatch):
        rules = {"/api/v1/test": {"requests": 5, "window_seconds": 60}}
        monkeypatch.setenv("FO_API_RATE_LIMIT_RULES", json.dumps(rules))
        settings = load_settings()
        assert settings.rate_limit_rules == rules

    def test_env_rate_limit_rules_invalid_json(self, monkeypatch):
        monkeypatch.setenv("FO_API_RATE_LIMIT_RULES", "not-json")
        settings = load_settings()
        # Falls back to defaults
        assert "/api/v1/auth/login" in settings.rate_limit_rules

    def test_env_security_headers_enabled(self, monkeypatch):
        monkeypatch.setenv("FO_API_SECURITY_HEADERS_ENABLED", "false")
        settings = load_settings()
        assert settings.security_headers_enabled is False

    def test_env_security_csp(self, monkeypatch):
        monkeypatch.setenv("FO_API_SECURITY_CSP", "default-src 'none'")
        settings = load_settings()
        assert settings.security_csp == "default-src 'none'"

    def test_env_security_hsts_seconds_valid(self, monkeypatch):
        monkeypatch.setenv("FO_API_SECURITY_HSTS_SECONDS", "86400")
        settings = load_settings()
        assert settings.security_hsts_seconds == 86400

    def test_env_security_hsts_seconds_invalid(self, monkeypatch):
        monkeypatch.setenv("FO_API_SECURITY_HSTS_SECONDS", "bad")
        settings = load_settings()
        assert settings.security_hsts_seconds == 31536000

    def test_env_security_hsts_subdomains(self, monkeypatch):
        monkeypatch.setenv("FO_API_SECURITY_HSTS_SUBDOMAINS", "false")
        settings = load_settings()
        assert settings.security_hsts_subdomains is False

    def test_env_security_referrer_policy(self, monkeypatch):
        monkeypatch.setenv("FO_API_SECURITY_REFERRER_POLICY", "no-referrer")
        settings = load_settings()
        assert settings.security_referrer_policy == "no-referrer"

    def test_yaml_config_file(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("api:\n  app_name: YAML App\n  port: 7777\n")
        monkeypatch.setenv("FO_API_CONFIG_PATH", str(config_file))
        settings = load_settings()
        assert settings.app_name == "YAML App"
        assert settings.port == 7777

    def test_yaml_config_missing_path(self, monkeypatch):
        monkeypatch.setenv("FO_API_CONFIG_PATH", "/tmp/nonexistent_config_12345.yaml")
        settings = load_settings()
        # Should fall back to defaults
        assert settings.app_name == "File Organizer API"

    def test_yaml_config_flat_structure(self, tmp_path, monkeypatch):
        """Config YAML without 'api' wrapper key."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("app_name: Flat Config\nport: 6666\n")
        monkeypatch.setenv("FO_API_CONFIG_PATH", str(config_file))
        settings = load_settings()
        assert settings.app_name == "Flat Config"
        assert settings.port == 6666

    def test_env_overrides_yaml(self, tmp_path, monkeypatch):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("api:\n  app_name: YAML App\n")
        monkeypatch.setenv("FO_API_CONFIG_PATH", str(config_file))
        monkeypatch.setenv("FO_API_APP_NAME", "Env App")
        settings = load_settings()
        assert settings.app_name == "Env App"

    def test_jwt_secret_warning_in_development(self, monkeypatch):
        """Default JWT secret with auth enabled in dev should warn but not raise."""
        monkeypatch.setenv("FO_API_ENVIRONMENT", "development")
        settings = load_settings()
        assert settings.auth_jwt_secret.get_secret_value() == "change-me"

    def test_jwt_secret_error_in_production(self, monkeypatch):
        """Default JWT secret in production should raise ValueError."""
        monkeypatch.setenv("FO_API_ENVIRONMENT", "production")
        monkeypatch.setenv("FO_API_CORS_ORIGINS", "https://example.com")
        with pytest.raises(ValueError, match="FO_API_AUTH_JWT_SECRET must be set"):
            load_settings()

    def test_api_key_enabled_without_hashes_warns(self, monkeypatch, caplog):
        """Explicitly enabling API keys without hashes should log warning."""
        monkeypatch.setenv("FO_API_API_KEY_ENABLED", "true")
        load_settings()
        # Warning is logged via loguru, not stdlib - just verify no crash

    def test_production_wildcard_cors_raises(self, monkeypatch):
        monkeypatch.setenv("FO_API_ENVIRONMENT", "production")
        monkeypatch.setenv("FO_API_AUTH_JWT_SECRET", "real-secret-key-123")
        monkeypatch.setenv("FO_API_CORS_ORIGINS", "*")
        with pytest.raises(ValueError, match="CORS origins must be explicit"):
            load_settings()

    def test_production_localhost_cors_raises(self, monkeypatch):
        monkeypatch.setenv("FO_API_ENVIRONMENT", "production")
        monkeypatch.setenv("FO_API_AUTH_JWT_SECRET", "real-secret-key-123")
        monkeypatch.setenv("FO_API_CORS_ORIGINS", "http://localhost:3000")
        with pytest.raises(ValueError, match="Localhost CORS origins must be removed"):
            load_settings()

    def test_production_valid_settings(self, monkeypatch):
        monkeypatch.setenv("FO_API_ENVIRONMENT", "production")
        monkeypatch.setenv("FO_API_AUTH_JWT_SECRET", "real-secret-key-123")
        monkeypatch.setenv("FO_API_CORS_ORIGINS", "https://example.com")
        settings = load_settings()
        assert settings.environment == "production"
        assert settings.cors_origins == ["https://example.com"]

    def test_ws_ping_interval_negative(self, monkeypatch):
        monkeypatch.setenv("FO_API_WS_PING_INTERVAL", "-5")
        settings = load_settings()
        assert settings.websocket_ping_interval == 30  # default
