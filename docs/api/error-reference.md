# API Error Reference

This reference matches the alpha3 OpenAPI schema exposed at `/openapi.json`. Route decorators now include concrete `responses={...}` metadata for success payloads and the documented error cases below.

## Error Response Shapes

### `ApiError` responses

These are raised by `file_organizer.api.exceptions.ApiError` and share a stable JSON shape:

```json
{
  "error": "not_found",
  "message": "Path not found",
  "details": null
}
```

### `HTTPException` responses

Some endpoints still use FastAPI's built-in `HTTPException` shape:

```json
{
  "detail": "Incorrect username or password"
}
```

### Validation responses

Request parsing and schema validation failures return:

```json
{
  "error": "validation_error",
  "message": "Invalid request payload.",
  "details": [
    {
      "loc": ["body", "path"],
      "msg": "Path must not be empty"
    }
  ]
}
```

## Global status codes

| Code | Meaning |
|------|---------|
| `400` | Invalid request, malformed identifier, unsupported state, or a FastAPI `detail` error |
| `401` | Authentication required or token invalid |
| `403` | Authenticated but not allowed to perform the operation |
| `404` | Requested file, path, job, integration, plugin, or config key was not found |
| `409` | Conflict, usually destination already exists |
| `422` | Validation error or explicit semantic validation failure |
| `429` | Rate-limited authentication flow |
| `500` | Unexpected server error |
| `503` | Optional dependency or backend service unavailable |

## Endpoint error codes

### Health and daemon

| Endpoint | Error codes |
|----------|-------------|
| `GET /api/v1/health` | `500 internal_server_error` if the probe itself fails unexpectedly |
| `GET /api/v1/daemon/status` | `500 internal_server_error` if daemon status lookup fails |
| `POST /api/v1/daemon/start` | `500 internal_server_error` if daemon start fails |
| `POST /api/v1/daemon/stop` | `500 internal_server_error` if daemon stop fails |
| `POST /api/v1/daemon/toggle` | `500 internal_server_error` if status lookup or transition fails |

### Authentication

| Endpoint | Error codes |
|----------|-------------|
| `POST /api/v1/auth/register` | `400` invalid password, username taken, or email already registered; `422 validation_error` |
| `POST /api/v1/auth/login` | `400` inactive user; `401` incorrect username or password; `429` too many attempts |
| `POST /api/v1/auth/refresh` | `401` invalid refresh token, revoked refresh token, or inactive user; `422 validation_error` |
| `POST /api/v1/auth/logout` | `401` missing or invalid access token, invalid refresh token, or refresh token for another user; `422 validation_error` |
| `GET /api/v1/auth/me` | `401` unauthenticated; `403` inactive or forbidden principal |

### Files

| Endpoint | Error codes |
|----------|-------------|
| `GET /api/v1/files` | `401` unauthenticated; `404 not_found`; `422 validation_error` |
| `GET /api/v1/files/info` | `400 invalid_path`; `401`; `404 not_found`; `422 validation_error` |
| `GET /api/v1/files/content` | `400 invalid_path`; `401`; `404 not_found`; `422 validation_error` |
| `GET /api/v1/files/{file_id}` | `400 invalid_id`; `401`; `404 not_found`; `422 invalid_id` |
| `POST /api/v1/files/move` | `400 invalid_request`; `401`; `404 not_found`; `409 conflict`; `422 validation_error` |
| `DELETE /api/v1/files` | `401`; `404 not_found`; `422 validation_error` |
| `DELETE /api/v1/files/{file_id}` | `400 invalid_id`; `401`; `404 not_found`; `422 invalid_id` |

### Organization and deduplication

| Endpoint | Error codes |
|----------|-------------|
| `POST /api/v1/organize/scan` | `401`; `404 not_found`; `422 validation_error` |
| `POST /api/v1/organize/preview` | `401`; `404 not_found`; `422 validation_error` |
| `POST /api/v1/organize/execute` | `401`; `404 not_found`; `422 validation_error` |
| `GET /api/v1/organize/status/{job_id}` | `401`; `404 not_found` |
| `POST /api/v1/organize` | `400 detail` when neither multipart file nor JSON payload is supplied; `401` |
| `POST /api/v1/dedupe/scan` | `400 invalid_path`; `401`; `404 not_found`; `422 validation_error` |
| `POST /api/v1/dedupe/preview` | `400 invalid_path`; `401`; `404 not_found`; `422 validation_error` |
| `POST /api/v1/dedupe/execute` | `400 invalid_path`; `401`; `404 not_found`; `422 validation_error` |

### Search and analyze

| Endpoint | Error codes |
|----------|-------------|
| `GET /api/v1/search` | `400 detail` when `q` is empty; `422 validation_error`; `503` semantic search dependencies unavailable |
| `POST /api/v1/analyze` | `400 detail` when neither `content` nor `file` is supplied; `503` AI backend unavailable; `500 detail` for analysis failures |

### Setup and configuration

| Endpoint | Error codes |
|----------|-------------|
| `GET /api/v1/setup/status` | `500 internal_server_error` on unexpected config load failure |
| `GET /api/v1/setup/capabilities` | `500 internal_server_error` on hardware detection failure |
| `POST /api/v1/setup/complete` | `422 validation_error`; `500 internal_server_error` on persistence failure |
| `GET /api/v1/setup/browse-folder` | Returns availability state in-band instead of raising most runtime failures |
| `GET /api/v1/config` | `500 internal_server_error` |
| `PUT /api/v1/config` | `403 forbidden`; `422 validation_error`; `500 internal_server_error` |
| `POST /api/v1/config/reset` | `403 forbidden`; `500 internal_server_error` |
| `GET /api/v1/system/status` | `400 invalid_path`; `401`; `404 not_found`; `422 validation_error` |
| `GET /api/v1/system/config` | `401`; `422 validation_error`; `500 internal_server_error` |
| `PATCH /api/v1/system/config` | `401`; `403 forbidden`; `422 validation_error`; `500 internal_server_error` |
| `GET /api/v1/system/stats` | `400 invalid_path`; `401`; `404 not_found`; `422 validation_error` |

### Integrations, marketplace, and plugin API

| Endpoint group | Error codes |
|----------------|-------------|
| `/api/v1/integrations*` | `401`; `404 not_found` for unknown integrations; `400 invalid_filename` or other invalid-path errors; `422 validation_error`; `500 internal_server_error` |
| `/api/v1/marketplace*` | `401`; `400 marketplace_error`; `404 not_found`; `422 checksum_failed` or validation error; `500 internal_server_error` |
| `/api/v1/plugins*` | `401`; `400 invalid_key`, `invalid_path`, or invalid callback URL; `404 not_found` or `config_key_not_found`; `409 conflict`; `422 validation_error`; `500 internal_server_error` |

## OpenAPI examples

The generated OpenAPI schema now includes concrete examples for both successful and error responses on the highest-traffic REST routes:

- `auth`
- `files`
- `organize`
- `dedupe`
- `search`
- `analyze`
- `system`
- `config`
- `setup`

That gives API consumers one place to inspect machine-readable examples in `/openapi.json` and one place to review the error-code contract in prose.
