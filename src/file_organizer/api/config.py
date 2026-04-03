"""API configuration and settings loader."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from loguru import logger
from pydantic import BaseModel, Field, NonNegativeInt, PositiveInt, SecretStr, field_validator

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
    websocket_ping_interval: PositiveInt = 30
    websocket_token: str | None = None
    auth_enabled: bool = True
    auth_db_path: str = Field(default_factory=_default_auth_db_path)
    auth_jwt_secret: SecretStr = SecretStr("change-me")
    auth_jwt_algorithm: str = "HS256"
    auth_access_token_minutes: PositiveInt = 30
    auth_refresh_token_days: PositiveInt = 7
    auth_redis_url: str | None = None
    auth_login_rate_limit_enabled: bool = True
    auth_login_max_attempts: PositiveInt = 5
    auth_login_window_seconds: PositiveInt = 900
    auth_password_min_length: PositiveInt = 12
    auth_password_require_number: bool = True
    auth_password_require_letter: bool = True
    auth_password_require_special: bool = True
    auth_password_require_uppercase: bool = True
    auth_bootstrap_admin: bool = False
    auth_bootstrap_admin_local_only: bool = True
    database_url: str | None = None
    database_pool_size: PositiveInt = 10
    database_max_overflow: NonNegativeInt = 20
    database_pool_pre_ping: bool = True
    database_pool_recycle_seconds: PositiveInt = 1800
    database_echo: bool = False
    cache_redis_url: str | None = None
    cache_default_ttl_seconds: PositiveInt = 900
    api_key_enabled: bool = True
    api_key_admin: bool = False
    api_key_header: str = "X-API-Key"
    api_key_hashes: list[str] = Field(default_factory=list)
    rate_limit_enabled: bool = True
    rate_limit_default_requests: PositiveInt = 1000
    rate_limit_default_window_seconds: PositiveInt = 60
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
    security_hsts_seconds: NonNegativeInt = 31536000
    security_hsts_subdomains: bool = True
    security_referrer_policy: str = "strict-origin-when-cross-origin"
    ollama_url: str = "http://localhost:11434"

    @field_validator("ollama_url")  # pyre-ignore[56]
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


def _parse_bool(value: str | None, name: str) -> bool | None:
    """Parse boolean from an environment variable string."""
    if value is None:
        return None

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes"}:
        return True
    if normalized in {"0", "false", "no"}:
        return False
    raise ValueError(f"Invalid {name} value: {value}")


def _load_bool(env: Mapping[str, str], env_name: str, data: dict[str, Any], key: str) -> None:
    """Load a boolean setting when the environment value parses cleanly."""
    if env_name not in env:
        return

    try:
        parsed = _parse_bool(env[env_name], env_name)
    except ValueError:
        logger.warning("Invalid {} value: {}", env_name, env[env_name])
    else:
        if parsed is not None:
            data[key] = parsed


def _parse_int(value: str, name: str) -> int | None:
    """Parse integer from environment variable with error logging.

    Args:
        value: The string value to parse.
        name: The environment variable name for logging.

    Returns:
        Parsed integer, or ``None`` on failure.
    """
    try:
        return int(value)
    except ValueError:
        logger.warning("Invalid {} value: {}", name, value)
        return None


def _load_file_config(env: Mapping[str, str]) -> dict[str, Any]:
    """Load configuration from YAML file if path is specified."""
    config_path = env.get("FO_API_CONFIG_PATH")
    if not config_path:
        return {}

    # Config file path is provided by deployment configuration, not request data.
    path = Path(config_path).expanduser()  # codeql[py/path-injection]
    if not path.exists():
        logger.warning("API config path does not exist: {}", path)
        return {}

    payload = _load_yaml(path)
    return payload.get("api", payload)


def _load_basic_settings(env: Mapping[str, str], data: dict[str, Any]) -> None:
    """Load basic application settings from environment."""
    if "FO_API_APP_NAME" in env:
        data["app_name"] = env["FO_API_APP_NAME"]
    if "FO_API_VERSION" in env:
        data["version"] = env["FO_API_VERSION"]
    if "FO_API_ENVIRONMENT" in env:
        data["environment"] = env["FO_API_ENVIRONMENT"]
    if "FO_API_HOST" in env:
        data["host"] = env["FO_API_HOST"]
    if "FO_API_PORT" in env:
        port = _parse_int(env["FO_API_PORT"], "FO_API_PORT")
        if port is not None:
            data["port"] = port
    if "FO_API_LOG_LEVEL" in env:
        data["log_level"] = env["FO_API_LOG_LEVEL"]
    _load_bool(env, "FO_API_ENABLE_DOCS", data, "enable_docs")
    if "FO_API_ALLOWED_PATHS" in env:
        data["allowed_paths"] = _parse_list(env["FO_API_ALLOWED_PATHS"])


def _load_cors_settings(env: Mapping[str, str], data: dict[str, Any]) -> None:
    """Load CORS configuration from environment."""
    if "FO_API_CORS_ORIGINS" in env:
        data["cors_origins"] = _parse_list(env["FO_API_CORS_ORIGINS"])
    if "FO_API_CORS_ALLOW_METHODS" in env:
        data["cors_allow_methods"] = _parse_list(env["FO_API_CORS_ALLOW_METHODS"])
    if "FO_API_CORS_ALLOW_HEADERS" in env:
        data["cors_allow_headers"] = _parse_list(env["FO_API_CORS_ALLOW_HEADERS"])
    _load_bool(env, "FO_API_CORS_ALLOW_CREDENTIALS", data, "cors_allow_credentials")


def _load_websocket_settings(env: Mapping[str, str], data: dict[str, Any]) -> None:
    """Load WebSocket configuration from environment."""
    if "FO_API_WS_PING_INTERVAL" in env:
        interval = _parse_int(env["FO_API_WS_PING_INTERVAL"], "FO_API_WS_PING_INTERVAL")
        if interval is not None and interval > 0:
            data["websocket_ping_interval"] = interval
        elif interval is not None:
            logger.warning(
                "Invalid FO_API_WS_PING_INTERVAL value (must be > 0): {}",
                env["FO_API_WS_PING_INTERVAL"],
            )
    if "FO_API_WEBSOCKET_TOKEN" in env:
        data["websocket_token"] = env["FO_API_WEBSOCKET_TOKEN"]


def _load_auth_settings(env: Mapping[str, str], data: dict[str, Any]) -> None:
    """Load authentication configuration from environment."""
    _load_bool(env, "FO_API_AUTH_ENABLED", data, "auth_enabled")
    if "FO_API_AUTH_DB_PATH" in env:
        data["auth_db_path"] = env["FO_API_AUTH_DB_PATH"]
    if "FO_API_AUTH_JWT_SECRET" in env:
        data["auth_jwt_secret"] = env["FO_API_AUTH_JWT_SECRET"]
    if "FO_API_AUTH_JWT_ALGORITHM" in env:
        data["auth_jwt_algorithm"] = env["FO_API_AUTH_JWT_ALGORITHM"]
    if "FO_API_AUTH_ACCESS_MINUTES" in env:
        minutes = _parse_int(env["FO_API_AUTH_ACCESS_MINUTES"], "FO_API_AUTH_ACCESS_MINUTES")
        if minutes is not None:
            data["auth_access_token_minutes"] = minutes
    if "FO_API_AUTH_REFRESH_DAYS" in env:
        days = _parse_int(env["FO_API_AUTH_REFRESH_DAYS"], "FO_API_AUTH_REFRESH_DAYS")
        if days is not None:
            data["auth_refresh_token_days"] = days
    if "FO_API_AUTH_REDIS_URL" in env:
        data["auth_redis_url"] = env["FO_API_AUTH_REDIS_URL"]
    elif "FO_REDIS_URL" in env:
        data["auth_redis_url"] = env["FO_REDIS_URL"]
    _load_bool(env, "FO_API_AUTH_BOOTSTRAP_ADMIN", data, "auth_bootstrap_admin")
    _load_bool(env, "FO_API_AUTH_BOOTSTRAP_LOCAL_ONLY", data, "auth_bootstrap_admin_local_only")


def _load_auth_rate_limit_settings(env: Mapping[str, str], data: dict[str, Any]) -> None:
    """Load authentication rate limiting configuration from environment."""
    _load_bool(env, "FO_API_AUTH_LOGIN_RATE_LIMIT", data, "auth_login_rate_limit_enabled")
    if "FO_API_AUTH_LOGIN_MAX_ATTEMPTS" in env:
        attempts = _parse_int(
            env["FO_API_AUTH_LOGIN_MAX_ATTEMPTS"], "FO_API_AUTH_LOGIN_MAX_ATTEMPTS"
        )
        if attempts is not None:
            data["auth_login_max_attempts"] = attempts
    if "FO_API_AUTH_LOGIN_WINDOW_SECONDS" in env:
        window = _parse_int(
            env["FO_API_AUTH_LOGIN_WINDOW_SECONDS"], "FO_API_AUTH_LOGIN_WINDOW_SECONDS"
        )
        if window is not None:
            data["auth_login_window_seconds"] = window


def _load_password_policy_settings(env: Mapping[str, str], data: dict[str, Any]) -> None:
    """Load password policy configuration from environment."""
    if "FO_API_AUTH_PASSWORD_MIN_LENGTH" in env:
        min_len = _parse_int(
            env["FO_API_AUTH_PASSWORD_MIN_LENGTH"], "FO_API_AUTH_PASSWORD_MIN_LENGTH"
        )
        if min_len is not None:
            data["auth_password_min_length"] = min_len
    _load_bool(env, "FO_API_AUTH_PASSWORD_REQUIRE_NUMBER", data, "auth_password_require_number")
    _load_bool(env, "FO_API_AUTH_PASSWORD_REQUIRE_LETTER", data, "auth_password_require_letter")
    _load_bool(env, "FO_API_AUTH_PASSWORD_REQUIRE_SPECIAL", data, "auth_password_require_special")
    _load_bool(
        env,
        "FO_API_AUTH_PASSWORD_REQUIRE_UPPERCASE",
        data,
        "auth_password_require_uppercase",
    )


def _load_database_settings(env: Mapping[str, str], data: dict[str, Any]) -> None:
    """Load database configuration from environment."""
    if "FO_API_DATABASE_URL" in env:
        data["database_url"] = env["FO_API_DATABASE_URL"]
    if "FO_API_DB_POOL_SIZE" in env:
        size = _parse_int(env["FO_API_DB_POOL_SIZE"], "FO_API_DB_POOL_SIZE")
        if size is not None:
            data["database_pool_size"] = size
    if "FO_API_DB_MAX_OVERFLOW" in env:
        overflow = _parse_int(env["FO_API_DB_MAX_OVERFLOW"], "FO_API_DB_MAX_OVERFLOW")
        if overflow is not None:
            data["database_max_overflow"] = overflow
    _load_bool(env, "FO_API_DB_POOL_PRE_PING", data, "database_pool_pre_ping")
    if "FO_API_DB_POOL_RECYCLE_SECONDS" in env:
        recycle = _parse_int(
            env["FO_API_DB_POOL_RECYCLE_SECONDS"], "FO_API_DB_POOL_RECYCLE_SECONDS"
        )
        if recycle is not None:
            data["database_pool_recycle_seconds"] = recycle
    _load_bool(env, "FO_API_DB_ECHO", data, "database_echo")


def _load_cache_settings(env: Mapping[str, str], data: dict[str, Any]) -> None:
    """Load cache configuration from environment."""
    if "FO_API_CACHE_REDIS_URL" in env:
        data["cache_redis_url"] = env["FO_API_CACHE_REDIS_URL"]
    elif "FO_REDIS_URL" in env:
        data["cache_redis_url"] = env["FO_REDIS_URL"]
    if "FO_API_CACHE_TTL_SECONDS" in env:
        ttl = _parse_int(env["FO_API_CACHE_TTL_SECONDS"], "FO_API_CACHE_TTL_SECONDS")
        if ttl is not None:
            data["cache_default_ttl_seconds"] = ttl


def _load_api_key_settings(env: Mapping[str, str], data: dict[str, Any]) -> None:
    """Load API key configuration from environment."""
    _load_bool(env, "FO_API_API_KEY_ENABLED", data, "api_key_enabled")
    _load_bool(env, "FO_API_API_KEY_ADMIN", data, "api_key_admin")
    if "FO_API_API_KEY_HEADER" in env:
        data["api_key_header"] = env["FO_API_API_KEY_HEADER"]
    if "FO_API_API_KEYS" in env:
        raw_keys = _parse_list(env["FO_API_API_KEYS"])
        data["api_key_hashes"] = [hash_api_key(key) for key in raw_keys]
    if "FO_API_API_KEY_HASHES" in env:
        data["api_key_hashes"] = _parse_list(env["FO_API_API_KEY_HASHES"])


def _load_rate_limit_settings(env: Mapping[str, str], data: dict[str, Any]) -> None:
    """Load rate limiting configuration from environment."""
    _load_bool(env, "FO_API_RATE_LIMIT_ENABLED", data, "rate_limit_enabled")
    if "FO_API_RATE_LIMIT_DEFAULT_REQUESTS" in env:
        requests = _parse_int(
            env["FO_API_RATE_LIMIT_DEFAULT_REQUESTS"], "FO_API_RATE_LIMIT_DEFAULT_REQUESTS"
        )
        if requests is not None:
            data["rate_limit_default_requests"] = requests
    if "FO_API_RATE_LIMIT_DEFAULT_WINDOW_SECONDS" in env:
        window = _parse_int(
            env["FO_API_RATE_LIMIT_DEFAULT_WINDOW_SECONDS"],
            "FO_API_RATE_LIMIT_DEFAULT_WINDOW_SECONDS",
        )
        if window is not None:
            data["rate_limit_default_window_seconds"] = window
    _load_bool(
        env,
        "FO_API_RATE_LIMIT_TRUST_PROXY_HEADERS",
        data,
        "rate_limit_trust_proxy_headers",
    )
    if "FO_API_RATE_LIMIT_EXEMPT_PATHS" in env:
        data["rate_limit_exempt_paths"] = _parse_list(env["FO_API_RATE_LIMIT_EXEMPT_PATHS"])
    if "FO_API_RATE_LIMIT_RULES" in env:
        try:
            parsed_rules = json.loads(env["FO_API_RATE_LIMIT_RULES"])
            if isinstance(parsed_rules, dict):
                data["rate_limit_rules"] = parsed_rules
        except json.JSONDecodeError:
            logger.warning("Invalid FO_API_RATE_LIMIT_RULES JSON value")


def _load_security_settings(env: Mapping[str, str], data: dict[str, Any]) -> None:
    """Load security headers configuration from environment."""
    _load_bool(env, "FO_API_SECURITY_HEADERS_ENABLED", data, "security_headers_enabled")
    if "FO_API_SECURITY_CSP" in env:
        data["security_csp"] = env["FO_API_SECURITY_CSP"]
    if "FO_API_SECURITY_HSTS_SECONDS" in env:
        seconds = _parse_int(env["FO_API_SECURITY_HSTS_SECONDS"], "FO_API_SECURITY_HSTS_SECONDS")
        if seconds is not None:
            data["security_hsts_seconds"] = seconds
    _load_bool(env, "FO_API_SECURITY_HSTS_SUBDOMAINS", data, "security_hsts_subdomains")
    if "FO_API_SECURITY_REFERRER_POLICY" in env:
        data["security_referrer_policy"] = env["FO_API_SECURITY_REFERRER_POLICY"]


def _load_ollama_settings(env: Mapping[str, str], data: dict[str, Any]) -> None:
    """Load Ollama configuration from environment."""
    if "FO_OLLAMA_URL" in env:
        data["ollama_url"] = env["FO_OLLAMA_URL"]
    elif "OLLAMA_HOST" in env:
        data["ollama_url"] = env["OLLAMA_HOST"]


def _validate_settings(settings: ApiSettings, api_key_enabled_explicit: bool) -> None:
    """Validate settings and log warnings or raise errors for misconfiguration.

    Args:
        settings: The loaded API settings to validate.
        api_key_enabled_explicit: Whether API key was explicitly configured.

    Raises:
        ValueError: On critical production misconfigurations.
    """
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


def load_settings() -> ApiSettings:
    """Load API settings from a config file and environment variables.

    Environment variables override config file values when present.
    Delegates to specialized loaders for each configuration category
    to keep complexity manageable.

    Returns:
        Validated ``ApiSettings`` instance.

    Raises:
        ValueError: On critical production misconfigurations.
    """
    env = os.environ
    data = _load_file_config(env)

    _load_basic_settings(env, data)
    _load_cors_settings(env, data)
    _load_websocket_settings(env, data)
    _load_auth_settings(env, data)
    _load_auth_rate_limit_settings(env, data)
    _load_password_policy_settings(env, data)
    _load_database_settings(env, data)
    _load_cache_settings(env, data)
    _load_api_key_settings(env, data)
    _load_rate_limit_settings(env, data)
    _load_security_settings(env, data)
    _load_ollama_settings(env, data)

    api_key_enabled_explicit = "api_key_enabled" in data
    settings = ApiSettings(**data)
    _validate_settings(settings, api_key_enabled_explicit)
    return settings
