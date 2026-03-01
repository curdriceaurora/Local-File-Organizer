# Python API Reference

This page provides an auto-generated reference for the public Python modules in
`file_organizer.api`.  Use it when writing plugins, integration tests, or when
extending the API layer.

---

## Core Application

### `main` — FastAPI application factory

::: file_organizer.api.main
    options:
      show_root_heading: true
      show_source: false
      members:
        - create_app
        - configure_logging

### `config` — Settings and configuration loader

::: file_organizer.api.config
    options:
      show_root_heading: true
      show_source: false
      members:
        - ApiSettings
        - load_settings

### `models` — Pydantic request/response models

::: file_organizer.api.models
    options:
      show_root_heading: true
      show_source: false

---

## Authentication

### `auth` — JWT helpers and password utilities

::: file_organizer.api.auth
    options:
      show_root_heading: true
      show_source: false
      members:
        - TokenBundle
        - TokenError
        - create_token_bundle
        - decode_token
        - hash_password
        - verify_password
        - validate_password
        - is_access_token
        - is_refresh_token

### `auth_store` — Token storage backends

::: file_organizer.api.auth_store
    options:
      show_root_heading: true
      show_source: false
      members:
        - TokenStore
        - InMemoryTokenStore
        - RedisTokenStore
        - build_token_store

### `auth_rate_limit` — Login rate limiting

::: file_organizer.api.auth_rate_limit
    options:
      show_root_heading: true
      show_source: false
      members:
        - LoginRateLimiter
        - InMemoryLoginRateLimiter
        - RedisLoginRateLimiter
        - build_login_rate_limiter

### `auth_models` — SQLAlchemy auth models

::: file_organizer.api.auth_models
    options:
      show_root_heading: true
      show_source: false

### `dependencies` — FastAPI dependency providers

::: file_organizer.api.dependencies
    options:
      show_root_heading: true
      show_source: false
      members:
        - AnonymousUser
        - ApiKeyIdentity
        - UserLike
        - get_settings
        - get_db
        - get_token_store
        - get_login_rate_limiter
        - get_current_user
        - get_current_active_user
        - require_admin_user

### `api_keys` — API key management

::: file_organizer.api.api_keys
    options:
      show_root_heading: true
      show_source: false

---

## Middleware and Rate Limiting

### `middleware` — Request middleware

::: file_organizer.api.middleware
    options:
      show_root_heading: true
      show_source: false
      members:
        - RateLimitMiddleware
        - SecurityHeadersMiddleware
        - setup_middleware

### `rate_limit` — General-purpose rate limiter

::: file_organizer.api.rate_limit
    options:
      show_root_heading: true
      show_source: false
      members:
        - RateLimitResult
        - RateLimiter
        - InMemoryRateLimiter
        - RedisRateLimiter
        - build_rate_limiter

---

## Routers

### `routers.auth` — Authentication endpoints

::: file_organizer.api.routers.auth
    options:
      show_root_heading: true
      show_source: false

### `routers.files` — File management endpoints

::: file_organizer.api.routers.files
    options:
      show_root_heading: true
      show_source: false

### `routers.organize` — Organization endpoints

::: file_organizer.api.routers.organize
    options:
      show_root_heading: true
      show_source: false

### `routers.search` — Search endpoints

::: file_organizer.api.routers.search
    options:
      show_root_heading: true
      show_source: false

### `routers.analyze` — Analysis endpoints

::: file_organizer.api.routers.analyze
    options:
      show_root_heading: true
      show_source: false

### `routers.dedupe` — Deduplication endpoints

::: file_organizer.api.routers.dedupe
    options:
      show_root_heading: true
      show_source: false

### `routers.health` — Health check endpoint

::: file_organizer.api.routers.health
    options:
      show_root_heading: true
      show_source: false

### `routers.config` — Configuration endpoints

::: file_organizer.api.routers.config
    options:
      show_root_heading: true
      show_source: false

### `routers.system` — System status endpoints

::: file_organizer.api.routers.system
    options:
      show_root_heading: true
      show_source: false

### `routers.realtime` — WebSocket / real-time endpoints

::: file_organizer.api.routers.realtime
    options:
      show_root_heading: true
      show_source: false

---

## Supporting Modules

### `exceptions` — Exception handlers

::: file_organizer.api.exceptions
    options:
      show_root_heading: true
      show_source: false

### `cache` — Response caching helpers

::: file_organizer.api.cache
    options:
      show_root_heading: true
      show_source: false

### `jobs` — Background job management

::: file_organizer.api.jobs
    options:
      show_root_heading: true
      show_source: false

### `repositories` — Data access layer

::: file_organizer.api.repositories
    options:
      show_root_heading: true
      show_source: false

### `utils` — Shared API utilities

::: file_organizer.api.utils
    options:
      show_root_heading: true
      show_source: false

### `realtime` — Real-time connection manager

::: file_organizer.api.realtime
    options:
      show_root_heading: true
      show_source: false
