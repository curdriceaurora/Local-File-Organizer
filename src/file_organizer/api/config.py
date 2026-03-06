"""API configuration and settings loader."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

import yaml
from loguru import logger
from pydantic import BaseModel, Field, SecretStr, field_validator

from file_organizer.api.api_keys import hash_api_key
from file_organizer.version import __version__

_DEFAULT_CORS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


def _default_auth_db_path() -> str:
    """Get default auth DB path via lazy import to avoid circular imports."""
    from file_organizer.config.path_manager import get_config_dir

    return str(get_config_dir() / "auth.db")


class ApiSettings(BaseModel):
    """Settings for the FastAPI backend."""

    app_name: str = "File Organizer API"
    version: str = __version__
    environment: str = "development"
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    cors_origins: list[str] = Field(default_factory=lambda: list(_DEFAULT_CORS))
    cors_allow_credentials: bool = True
    cors_allow_methods: list[str] = Field(default_factory=lambda: ["*"])
    cors_allow_headers: list[str] = Field(default_factory=lambda: ["*"])
    enable_docs: bool = True
    allowed_paths: list[str] = Field(default_factory=lambda: [str(Path.home())])
    websocket_ping_interval: int = Field(default=30, gt=0)
    websocket_token: Optional[str] = None
    auth_enabled: bool = True
    auth_db_path: str = Field(
        default_factory=_default_auth_db_path
    )
    auth_jwt_secret: SecretStr = SecretStr("change-me")
    auth_jwt_algorithm: str = "HS256"
    auth_access_token_minutes: int = Field(default=30, gt=0)
    auth_refresh_token_days: int = Field(default=7, gt=0)
    auth_redis_url: Optional[str] = None
    auth_login_rate_limit_enabled: bool = True
    auth_login_max_attempts: int = Field(default=5, gt=0)
    auth_login_window_seconds: int = Field(default=900, gt=0)
    auth_password_min_length: int = Field(default=12, gt=0)
    auth_password_require_number: bool = True
    auth_password_require_letter: bool = True
    auth_password_require_special: bool = True
    auth_password_require_uppercase: bool = True
    auth_bootstrap_admin: bool = False
    auth_bootstrap_admin_local_only: bool = True
    database_url: Optional[str] = None
    database_pool_size: int = Field(default=10, gt=0)
    database_max_overflow: int = Field(default=20, ge=0)
    database_pool_pre_ping: bool = True
    database_pool_recycle_seconds: int = Field(default=1800, gt=0)
    database_echo: bool = False
    cache_redis_url: Optional[str] = None
    cache_default_ttl_seconds: int = Field(default=900, gt=0)
    api_key_enabled: bool = True
    api_key_admin: bool = False
    api_key_header: str = "X-API-Key"
    api_key_hashes: list[str] = Field(default_factory=list)
    rate_limit_enabled: bool = True
    rate_limit_default_requests: int = Field(default=1000, gt=0)
    rate_limit_default_window_seconds: int = Field(default=60, gt=0)
    rate_limit_trust_proxy_headers: bool = False
    rate_limit_exempt_paths: list[str] = Field(
        default_factory=lambda: ["/", "/api/v1/health", "/docs", "/openapi.json", "/redoc"]
    )
    rate_limit_rules: dict[str, dict[str, int]] = Field(
        default_factory=lambda: {
            "/api/v1/auth/login": {"requests": 10, "window_seconds": 300},
            "/api/v1/auth/register": {"requests": 10, "window_seconds": 3600},
            "/api/v1/auth/refresh": {"requests": 30, "window_seconds": 300},
            "/api/v1/organize/execute": {"requests": 10, "window_seconds": 3600},
        }
    )
    security_headers_enabled: bool = True
    security_csp: str = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self' data:; "
        "connect-src 'self' ws: wss:;"
    )
    security_hsts_seconds: int = Field(default=31536000, ge=0)
    security_hsts_subdomains: bool = True
    security_referrer_policy: str = "strict-origin-when-cross-origin"
    ollama_url: str = "http://localhost:11434"

    @field_validator("ollama_url")
    @classmethod
    def _normalize_ollama_url(cls, v: str) -> str:
        """Prepend ``http://`` when *OLLAMA_HOST* is given as ``host:port``."""
        if v and not v.startswith(("http://", "https://")):
            return f"http://{v}"
        return v


def _parse_list(value: str) -> list[str]:
    """Parse list values from JSON or comma-separated strings."""
    value = value.strip()
    if not value:
        return []
    if value.startswith("["):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON list from env")
            value = value.strip("[]")
    return [v.strip() for v in value.split(",") if v.strip()]


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load YAML configuration from disk."""
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to read API config {}: {}", path, exc)
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def load_settings() -> ApiSettings:
    """Load API settings from a config file and environment variables.

    Environment variables override config file values when present.
    """
    config_path = os.environ.get("FO_API_CONFIG_PATH")
    data: dict[str, Any] = {}

    if config_path:
        # Config file path is provided by deployment configuration, not request data.
        path = Path(config_path).expanduser()  # codeql[py/path-injection]
        if path.exists():
            payload = _load_yaml(path)
            data.update(payload.get("api", payload))
        else:
            logger.warning("API config path does not exist: {}", path)

    env = os.environ
    if "FO_API_APP_NAME" in env:
        data["app_name"] = env["FO_API_APP_NAME"]
    if "FO_API_VERSION" in env:
        data["version"] = env["FO_API_VERSION"]
    if "FO_API_ENVIRONMENT" in env:
        data["environment"] = env["FO_API_ENVIRONMENT"]
    if "FO_API_HOST" in env:
        data["host"] = env["FO_API_HOST"]
    if "FO_API_PORT" in env:
        try:
            data["port"] = int(env["FO_API_PORT"])
        except ValueError:
            logger.warning("Invalid FO_API_PORT value: {}", env["FO_API_PORT"])
    if "FO_API_LOG_LEVEL" in env:
        data["log_level"] = env["FO_API_LOG_LEVEL"]
    if "FO_API_CORS_ORIGINS" in env:
        data["cors_origins"] = _parse_list(env["FO_API_CORS_ORIGINS"])
    if "FO_API_CORS_ALLOW_METHODS" in env:
        data["cors_allow_methods"] = _parse_list(env["FO_API_CORS_ALLOW_METHODS"])
    if "FO_API_CORS_ALLOW_HEADERS" in env:
        data["cors_allow_headers"] = _parse_list(env["FO_API_CORS_ALLOW_HEADERS"])
    if "FO_API_CORS_ALLOW_CREDENTIALS" in env:
        data["cors_allow_credentials"] = env["FO_API_CORS_ALLOW_CREDENTIALS"].lower() in (
            "1",
            "true",
            "yes",
        )
    if "FO_API_ENABLE_DOCS" in env:
        data["enable_docs"] = env["FO_API_ENABLE_DOCS"].lower() in ("1", "true", "yes")
    if "FO_API_ALLOWED_PATHS" in env:
        data["allowed_paths"] = _parse_list(env["FO_API_ALLOWED_PATHS"])
    if "FO_API_WS_PING_INTERVAL" in env:
        try:
            interval = int(env["FO_API_WS_PING_INTERVAL"])
            if interval > 0:
                data["websocket_ping_interval"] = interval
            else:
                logger.warning(
                    "Invalid FO_API_WS_PING_INTERVAL value (must be > 0): {}",
                    env["FO_API_WS_PING_INTERVAL"],
                )
        except ValueError:
            logger.warning(
                "Invalid FO_API_WS_PING_INTERVAL value: {}",
                env["FO_API_WS_PING_INTERVAL"],
            )
    if "FO_API_WEBSOCKET_TOKEN" in env:
        data["websocket_token"] = env["FO_API_WEBSOCKET_TOKEN"]
    if "FO_API_AUTH_ENABLED" in env:
        data["auth_enabled"] = env["FO_API_AUTH_ENABLED"].lower() in ("1", "true", "yes")
    if "FO_API_AUTH_DB_PATH" in env:
        data["auth_db_path"] = env["FO_API_AUTH_DB_PATH"]
    if "FO_API_AUTH_JWT_SECRET" in env:
        data["auth_jwt_secret"] = env["FO_API_AUTH_JWT_SECRET"]
    if "FO_API_AUTH_JWT_ALGORITHM" in env:
        data["auth_jwt_algorithm"] = env["FO_API_AUTH_JWT_ALGORITHM"]
    if "FO_API_AUTH_ACCESS_MINUTES" in env:
        try:
            data["auth_access_token_minutes"] = int(env["FO_API_AUTH_ACCESS_MINUTES"])
        except ValueError:
            logger.warning(
                "Invalid FO_API_AUTH_ACCESS_MINUTES value: {}",
                env["FO_API_AUTH_ACCESS_MINUTES"],
            )
    if "FO_API_AUTH_REFRESH_DAYS" in env:
        try:
            data["auth_refresh_token_days"] = int(env["FO_API_AUTH_REFRESH_DAYS"])
        except ValueError:
            logger.warning(
                "Invalid FO_API_AUTH_REFRESH_DAYS value: {}",
                env["FO_API_AUTH_REFRESH_DAYS"],
            )
    if "FO_API_AUTH_REDIS_URL" in env:
        data["auth_redis_url"] = env["FO_API_AUTH_REDIS_URL"]
    elif "FO_REDIS_URL" in env:
        data["auth_redis_url"] = env["FO_REDIS_URL"]

    if "FO_API_AUTH_LOGIN_RATE_LIMIT" in env:
        data["auth_login_rate_limit_enabled"] = env["FO_API_AUTH_LOGIN_RATE_LIMIT"].lower() in (
            "1",
            "true",
            "yes",
        )
    if "FO_API_AUTH_LOGIN_MAX_ATTEMPTS" in env:
        try:
            data["auth_login_max_attempts"] = int(env["FO_API_AUTH_LOGIN_MAX_ATTEMPTS"])
        except ValueError:
            logger.warning(
                "Invalid FO_API_AUTH_LOGIN_MAX_ATTEMPTS value: {}",
                env["FO_API_AUTH_LOGIN_MAX_ATTEMPTS"],
            )
    if "FO_API_AUTH_LOGIN_WINDOW_SECONDS" in env:
        try:
            data["auth_login_window_seconds"] = int(env["FO_API_AUTH_LOGIN_WINDOW_SECONDS"])
        except ValueError:
            logger.warning(
                "Invalid FO_API_AUTH_LOGIN_WINDOW_SECONDS value: {}",
                env["FO_API_AUTH_LOGIN_WINDOW_SECONDS"],
            )
    if "FO_API_AUTH_PASSWORD_MIN_LENGTH" in env:
        try:
            data["auth_password_min_length"] = int(env["FO_API_AUTH_PASSWORD_MIN_LENGTH"])
        except ValueError:
            logger.warning(
                "Invalid FO_API_AUTH_PASSWORD_MIN_LENGTH value: {}",
                env["FO_API_AUTH_PASSWORD_MIN_LENGTH"],
            )
    if "FO_API_AUTH_PASSWORD_REQUIRE_NUMBER" in env:
        data["auth_password_require_number"] = env[
            "FO_API_AUTH_PASSWORD_REQUIRE_NUMBER"
        ].lower() in ("1", "true", "yes")
    if "FO_API_AUTH_PASSWORD_REQUIRE_LETTER" in env:
        data["auth_password_require_letter"] = env[
            "FO_API_AUTH_PASSWORD_REQUIRE_LETTER"
        ].lower() in ("1", "true", "yes")
    if "FO_API_AUTH_PASSWORD_REQUIRE_SPECIAL" in env:
        data["auth_password_require_special"] = env[
            "FO_API_AUTH_PASSWORD_REQUIRE_SPECIAL"
        ].lower() in ("1", "true", "yes")
    if "FO_API_AUTH_PASSWORD_REQUIRE_UPPERCASE" in env:
        data["auth_password_require_uppercase"] = env[
            "FO_API_AUTH_PASSWORD_REQUIRE_UPPERCASE"
        ].lower() in ("1", "true", "yes")
    if "FO_API_AUTH_BOOTSTRAP_ADMIN" in env:
        data["auth_bootstrap_admin"] = env["FO_API_AUTH_BOOTSTRAP_ADMIN"].lower() in (
            "1",
            "true",
            "yes",
        )
    if "FO_API_AUTH_BOOTSTRAP_LOCAL_ONLY" in env:
        data["auth_bootstrap_admin_local_only"] = env[
            "FO_API_AUTH_BOOTSTRAP_LOCAL_ONLY"
        ].lower() in ("1", "true", "yes")
    if "FO_API_DATABASE_URL" in env:
        data["database_url"] = env["FO_API_DATABASE_URL"]
    if "FO_API_DB_POOL_SIZE" in env:
        try:
            data["database_pool_size"] = int(env["FO_API_DB_POOL_SIZE"])
        except ValueError:
            logger.warning("Invalid FO_API_DB_POOL_SIZE value: {}", env["FO_API_DB_POOL_SIZE"])
    if "FO_API_DB_MAX_OVERFLOW" in env:
        try:
            data["database_max_overflow"] = int(env["FO_API_DB_MAX_OVERFLOW"])
        except ValueError:
            logger.warning(
                "Invalid FO_API_DB_MAX_OVERFLOW value: {}",
                env["FO_API_DB_MAX_OVERFLOW"],
            )
    if "FO_API_DB_POOL_PRE_PING" in env:
        data["database_pool_pre_ping"] = env["FO_API_DB_POOL_PRE_PING"].lower() in (
            "1",
            "true",
            "yes",
        )
    if "FO_API_DB_POOL_RECYCLE_SECONDS" in env:
        try:
            data["database_pool_recycle_seconds"] = int(env["FO_API_DB_POOL_RECYCLE_SECONDS"])
        except ValueError:
            logger.warning(
                "Invalid FO_API_DB_POOL_RECYCLE_SECONDS value: {}",
                env["FO_API_DB_POOL_RECYCLE_SECONDS"],
            )
    if "FO_API_DB_ECHO" in env:
        data["database_echo"] = env["FO_API_DB_ECHO"].lower() in ("1", "true", "yes")
    if "FO_API_CACHE_REDIS_URL" in env:
        data["cache_redis_url"] = env["FO_API_CACHE_REDIS_URL"]
    elif "FO_REDIS_URL" in env:
        data["cache_redis_url"] = env["FO_REDIS_URL"]
    if "FO_API_CACHE_TTL_SECONDS" in env:
        try:
            data["cache_default_ttl_seconds"] = int(env["FO_API_CACHE_TTL_SECONDS"])
        except ValueError:
            logger.warning(
                "Invalid FO_API_CACHE_TTL_SECONDS value: {}",
                env["FO_API_CACHE_TTL_SECONDS"],
            )
    if "FO_API_API_KEY_ENABLED" in env:
        data["api_key_enabled"] = env["FO_API_API_KEY_ENABLED"].lower() in ("1", "true", "yes")
    if "FO_API_API_KEY_ADMIN" in env:
        data["api_key_admin"] = env["FO_API_API_KEY_ADMIN"].lower() in ("1", "true", "yes")
    if "FO_API_API_KEY_HEADER" in env:
        data["api_key_header"] = env["FO_API_API_KEY_HEADER"]
    if "FO_API_API_KEYS" in env:
        raw_keys = _parse_list(env["FO_API_API_KEYS"])
        data["api_key_hashes"] = [hash_api_key(key) for key in raw_keys]
    if "FO_API_API_KEY_HASHES" in env:
        data["api_key_hashes"] = _parse_list(env["FO_API_API_KEY_HASHES"])
    if "FO_API_RATE_LIMIT_ENABLED" in env:
        data["rate_limit_enabled"] = env["FO_API_RATE_LIMIT_ENABLED"].lower() in (
            "1",
            "true",
            "yes",
        )
    if "FO_API_RATE_LIMIT_DEFAULT_REQUESTS" in env:
        try:
            data["rate_limit_default_requests"] = int(env["FO_API_RATE_LIMIT_DEFAULT_REQUESTS"])
        except ValueError:
            logger.warning(
                "Invalid FO_API_RATE_LIMIT_DEFAULT_REQUESTS value: {}",
                env["FO_API_RATE_LIMIT_DEFAULT_REQUESTS"],
            )
    if "FO_API_RATE_LIMIT_DEFAULT_WINDOW_SECONDS" in env:
        try:
            data["rate_limit_default_window_seconds"] = int(
                env["FO_API_RATE_LIMIT_DEFAULT_WINDOW_SECONDS"]
            )
        except ValueError:
            logger.warning(
                "Invalid FO_API_RATE_LIMIT_DEFAULT_WINDOW_SECONDS value: {}",
                env["FO_API_RATE_LIMIT_DEFAULT_WINDOW_SECONDS"],
            )
    if "FO_API_RATE_LIMIT_TRUST_PROXY_HEADERS" in env:
        data["rate_limit_trust_proxy_headers"] = env[
            "FO_API_RATE_LIMIT_TRUST_PROXY_HEADERS"
        ].lower() in ("1", "true", "yes")
    if "FO_API_RATE_LIMIT_EXEMPT_PATHS" in env:
        data["rate_limit_exempt_paths"] = _parse_list(env["FO_API_RATE_LIMIT_EXEMPT_PATHS"])
    if "FO_API_RATE_LIMIT_RULES" in env:
        try:
            parsed_rules = json.loads(env["FO_API_RATE_LIMIT_RULES"])
            if isinstance(parsed_rules, dict):
                data["rate_limit_rules"] = parsed_rules
        except json.JSONDecodeError:
            logger.warning("Invalid FO_API_RATE_LIMIT_RULES JSON value")
    if "FO_API_SECURITY_HEADERS_ENABLED" in env:
        data["security_headers_enabled"] = env["FO_API_SECURITY_HEADERS_ENABLED"].lower() in (
            "1",
            "true",
            "yes",
        )
    if "FO_API_SECURITY_CSP" in env:
        data["security_csp"] = env["FO_API_SECURITY_CSP"]
    if "FO_API_SECURITY_HSTS_SECONDS" in env:
        try:
            data["security_hsts_seconds"] = int(env["FO_API_SECURITY_HSTS_SECONDS"])
        except ValueError:
            logger.warning(
                "Invalid FO_API_SECURITY_HSTS_SECONDS value: {}",
                env["FO_API_SECURITY_HSTS_SECONDS"],
            )
    if "FO_API_SECURITY_HSTS_SUBDOMAINS" in env:
        data["security_hsts_subdomains"] = env["FO_API_SECURITY_HSTS_SUBDOMAINS"].lower() in (
            "1",
            "true",
            "yes",
        )
    if "FO_API_SECURITY_REFERRER_POLICY" in env:
        data["security_referrer_policy"] = env["FO_API_SECURITY_REFERRER_POLICY"]
    if "FO_OLLAMA_URL" in env:
        data["ollama_url"] = env["FO_OLLAMA_URL"]
    elif "OLLAMA_HOST" in env:
        data["ollama_url"] = env["OLLAMA_HOST"]

    api_key_enabled_explicit = "api_key_enabled" in data
    settings = ApiSettings(**data)
    if settings.auth_enabled and settings.auth_jwt_secret.get_secret_value() == "change-me":
        if settings.environment.lower() in {"development", "test"}:
            logger.warning(
                "FO_API_AUTH_JWT_SECRET is using the default placeholder. "
                "Set FO_API_AUTH_JWT_SECRET before deploying."
            )
        else:
            raise ValueError(
                "FO_API_AUTH_JWT_SECRET must be set when auth is enabled outside development."
            )
    if settings.api_key_enabled and not settings.api_key_hashes and api_key_enabled_explicit:
        logger.warning("API key auth is enabled but no keys are configured.")
    if settings.environment.lower() not in {"development", "test"}:
        if "*" in settings.cors_origins:
            raise ValueError("CORS origins must be explicit in production.")
        if any("localhost" in origin or "127.0.0.1" in origin for origin in settings.cors_origins):
            raise ValueError("Localhost CORS origins must be removed in production.")
    return settings
