# Configuration Guide

This page focuses on deployment-time configuration for the web/API runtime.

For core app profile settings (`config.yaml`, `file-organizer config ...`, model defaults), see [Configuration Guide](../CONFIGURATION.md).

## Configuration surfaces

1. **Core app profile config** (`config.yaml` under platform config dir)
2. **Provider env vars** (`FO_PROVIDER`, `FO_OPENAI_*`, `FO_CLAUDE_*`, `FO_LLAMA_CPP_*`, `FO_MLX_*`)
3. **API runtime env vars** (`FO_API_*`, plus `FO_REDIS_URL` / `OLLAMA_HOST` compatibility)
4. **Optional API config file** via `FO_API_CONFIG_PATH` (YAML)

## API runtime environment variables (`FO_API_*`)

### Basic server settings

| Variable | Description | Default |
|---|---|---|
| `FO_API_APP_NAME` | API application name | `File Organizer API` |
| `FO_API_VERSION` | API version string | package `__version__` |
| `FO_API_ENVIRONMENT` | Runtime environment (`development`, `test`, `production`) | `development` |
| `FO_API_HOST` | Bind host | `0.0.0.0` |
| `FO_API_PORT` | Bind port | `8000` |
| `FO_API_LOG_LEVEL` | Log level | `INFO` |
| `FO_API_ENABLE_DOCS` | Enable `/docs` and OpenAPI pages | `true` |
| `FO_API_ALLOWED_PATHS` | JSON array or comma-separated allowed root paths | current user home directory |

### CORS and WebSocket

| Variable | Description |
|---|---|
| `FO_API_CORS_ORIGINS` | JSON array or comma-separated origins |
| `FO_API_CORS_ALLOW_METHODS` | Allowed methods |
| `FO_API_CORS_ALLOW_HEADERS` | Allowed headers |
| `FO_API_CORS_ALLOW_CREDENTIALS` | Allow credentials (`true`/`false`) |
| `FO_API_WS_PING_INTERVAL` | WebSocket ping interval seconds |
| `FO_API_WEBSOCKET_TOKEN` | Optional WebSocket token |

### Auth and API keys

| Variable | Description |
|---|---|
| `FO_API_AUTH_ENABLED` | Enable auth |
| `FO_API_AUTH_JWT_SECRET` | JWT secret (must be set outside development/test) |
| `FO_API_AUTH_JWT_ALGORITHM` | JWT algorithm |
| `FO_API_AUTH_ACCESS_MINUTES` | Access token lifetime |
| `FO_API_AUTH_REFRESH_DAYS` | Refresh token lifetime |
| `FO_API_API_KEY_ENABLED` | Enable API key auth |
| `FO_API_API_KEY_HEADER` | API key header name |
| `FO_API_API_KEYS` | Raw API keys (comma/JSON list; hashed at load time) |
| `FO_API_API_KEY_HASHES` | Pre-hashed API keys |

### Data/cache/rate limit/security

| Variable | Description |
|---|---|
| `FO_API_DATABASE_URL` | SQLAlchemy database URL |
| `FO_API_DB_POOL_SIZE` | DB pool size |
| `FO_API_CACHE_REDIS_URL` | Redis URL for cache |
| `FO_API_CACHE_TTL_SECONDS` | Cache TTL |
| `FO_API_RATE_LIMIT_ENABLED` | Enable rate limiting |
| `FO_API_RATE_LIMIT_DEFAULT_REQUESTS` | Default max requests |
| `FO_API_RATE_LIMIT_DEFAULT_WINDOW_SECONDS` | Default window size |
| `FO_API_RATE_LIMIT_RULES` | JSON object of per-route rules |
| `FO_API_SECURITY_HEADERS_ENABLED` | Enable security headers |
| `FO_API_SECURITY_CSP` | CSP header |

## Compatibility variables

- `FO_REDIS_URL` is used as fallback for auth/cache Redis URLs.
- `OLLAMA_HOST` is used as fallback for Ollama URL if `FO_OLLAMA_URL` is unset.

## Provider configuration in deployments

Use provider variables documented in [AI Provider Setup](../setup/ai-providers.md). Key points:

- `FO_PROVIDER` selects the provider mode.
- `FO_OPENAI_API_KEY` and `FO_CLAUDE_API_KEY` are preferred.
- SDK-native fallbacks are supported:
  - `OPENAI_API_KEY`
  - `ANTHROPIC_API_KEY`

## Example (production-style)

```bash
export FO_API_ENVIRONMENT=production
export FO_API_HOST=0.0.0.0
export FO_API_PORT=8000
export FO_API_AUTH_JWT_SECRET='replace-with-strong-secret'
export FO_API_CORS_ORIGINS='["https://app.example.com"]'
export FO_API_RATE_LIMIT_ENABLED=true
export FO_PROVIDER=openai
export FO_OPENAI_API_KEY=sk-...
export FO_OPENAI_MODEL=gpt-4o-mini
```

## See also

- [Core Configuration Guide](../CONFIGURATION.md)
- [AI Provider Setup](../setup/ai-providers.md)
- [Installation Guide](installation.md)
