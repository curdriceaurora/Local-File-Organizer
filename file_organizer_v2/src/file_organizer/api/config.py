"""API configuration and settings loader."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

import yaml
from loguru import logger
from pydantic import BaseModel, Field

from file_organizer.version import __version__

_DEFAULT_CORS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


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
        default_factory=lambda: str(Path.home() / ".config" / "file-organizer" / "auth.db")
    )
    auth_jwt_secret: str = "change-me"
    auth_jwt_algorithm: str = "HS256"
    auth_access_token_minutes: int = Field(default=30, gt=0)
    auth_refresh_token_days: int = Field(default=7, gt=0)
    auth_redis_url: Optional[str] = None


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
        path = Path(config_path).expanduser()
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

    return ApiSettings(**data)
