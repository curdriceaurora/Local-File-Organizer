# API Reference

File Organizer provides a complete REST API for programmatic access to all features.

## Overview

The File Organizer API allows you to:

- Upload and manage files
- Organize files using various methodologies
- Search and analyze files
- Detect duplicates
- Generate analytics
- Manage workspaces and settings
- Monitor job progress in real-time via WebSocket

## API Features

### REST Endpoints

- File management (upload, list, delete)
- Organization (start jobs, monitor progress)
- Search and filtering
- Analysis (duplicates, storage)
- Settings and configuration

### Authentication

- API key-based authentication
- Bearer token in Authorization header
- Rate limiting and quotas

### Real-Time Updates

- WebSocket connections for live progress
- Job status streaming
- Event notifications

### Response Formats

- JSON responses
- OpenAPI examples for success and error payloads
- Proper HTTP status codes with route-level error documentation

## Quick Start

### 1. Generate API Key

1. Log in to web interface
1. Click **Settings** (gear icon)
1. Select **API Keys**
1. Click **Generate New Key**
1. Copy the token (shown only once)

### 2. Make Your First Request

```bash
curl -X GET "http://localhost:8000/api/v1/files?path=/" \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json"
```

### 3. Handle Response

```json
{
  "items": [
    {
      "path": "/Users/demo/Documents/report.pdf",
      "name": "report.pdf",
      "size": 102400,
      "created": "2026-04-01T12:00:00Z",
      "modified": "2026-04-04T09:30:00Z",
      "file_type": "pdf",
      "mime_type": "application/pdf"
    }
  ],
  "total": 1,
  "skip": 0,
  "limit": 100
}
```

## API Endpoints

### File Management

- `GET /api/v1/files` - List files

- `GET /api/v1/files/{id}` - Get file details

- `DELETE /api/v1/files/{id}` - Delete file

**Guide**: [File Management Endpoints](file-endpoints.md)

### Organization

- `POST /api/v1/organize/scan` - Scan files for organization
- `POST /api/v1/organize/preview` - Preview organization plan
- `POST /api/v1/organize/execute` - Execute organization
- `GET /api/v1/organize/status/{job_id}` - Get job status

**Guide**: [Organization Endpoints](organization-endpoints.md)

### Deduplication

- `POST /api/v1/dedupe/scan` - Scan for duplicate files
- `POST /api/v1/dedupe/preview` - Preview deduplication plan
- `POST /api/v1/dedupe/execute` - Execute deduplication

**Guide**: [Analysis Endpoints](analysis-endpoints.md)

### Search

- `GET /api/v1/search` - Search files

**Guide**: [Search Endpoints](search-endpoints.md)

### WebSocket

- `WS /api/v1/ws/{client_id}` - Real-time events
- Job progress updates
- File operation notifications

**Guide**: [WebSocket API](websocket-api.md)

## Authentication

### API Key Authentication

All API requests require authentication via API key:

```bash
curl -H "X-API-Key: YOUR_API_KEY" \
  "http://localhost:8000/api/v1/files?path=/"
```

### Rate Limiting

API requests are rate-limited:

- **Default**: 1000 requests/minute
- **Configurable**: Via app settings

Check rate limit in response headers:

```yaml
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1645026000
```

### Token Expiration

API keys have configurable expiration:

1. Generate key with expiration date
1. Expired keys return 401 Unauthorized
1. Generate new key if expired
1. Revoke old keys in Settings

## Response Format

The alpha3 API uses endpoint-specific response models for successful requests rather than a single `success/data/meta` envelope.

### Success response example

```json
{
  "items": [
    {
      "path": "/Users/demo/Documents/report.pdf",
      "name": "report.pdf",
      "size": 102400,
      "created": "2026-04-01T12:00:00Z",
      "modified": "2026-04-04T09:30:00Z",
      "file_type": "pdf",
      "mime_type": "application/pdf"
    }
  ],
  "total": 1,
  "skip": 0,
  "limit": 100
}
```

### `ApiError` response example

```json
{
  "error": "not_found",
  "message": "Path not found",
  "details": null
}
```

### `HTTPException` response example

```json
{
  "detail": "Incorrect username or password"
}
```

### Validation response example

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

**Guide**: [Endpoint Error Reference](error-reference.md)

## HTTP Status Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Bad request |
| 401 | Unauthorized (invalid API key) |
| 403 | Forbidden (no permission) |
| 404 | Not found |
| 429 | Too many requests (rate limit) |
| 500 | Server error |

## Common Response Fields

### File Object

```json
{
  "id": "file_123",
  "name": "document.pdf",
  "path": "/documents/",
  "size": 1024000,
  "type": "pdf",
  "created": "2024-02-01T10:30:00Z",
  "modified": "2024-02-15T14:20:00Z",
  "description": "AI-generated description",
  "tags": ["important", "project-x"]
}
```

### Job Object

```json
{
  "id": "job_456",
  "status": "in_progress",
  "methodology": "para",
  "fileCount": 42,
  "progress": 65,
  "startedAt": "2024-02-15T14:00:00Z",
  "estimatedCompletion": "2024-02-15T14:05:00Z"
}
```

## Using the API Programmatically

### Python (with `httpx`)

```python
import httpx

client = httpx.Client(
    base_url="http://localhost:8000/api/v1",
    headers={"X-API-Key": "your-api-key"},
)

response = client.get("/files", params={"path": "/documents"})
files = response.json()
```

### JavaScript/Node.js (with `fetch`)

```javascript
const response = await fetch(
  'http://localhost:8000/api/v1/files?path=/documents',
  {
    headers: { 'X-API-Key': 'your-api-key' },
  }
);
const files = await response.json();
```

See [Developer Guide](../developer/index.md) for more details.

## Interactive Documentation

Explore the API interactively:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`
- **OpenAPI Spec**: `http://localhost:8000/openapi.json`

## Example Use Cases

### 1. Organize Files Programmatically

```bash
# Start organization preview
curl -X POST http://localhost:8000/api/v1/organize/preview \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "path": "/documents",
    "methodology": "para"
  }'
```

### 2. Find Duplicate Files

```bash
# Scan for duplicates
curl -X POST http://localhost:8000/api/v1/dedupe/scan \
  -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "paths": ["/documents", "/downloads"]
  }'
```

### 3. Monitor Organization Job

```javascript
// Real-time job monitoring — replace CLIENT_ID with a unique identifier
const clientId = crypto.randomUUID();
// Browser WebSocket API: authentication via token query parameter
const ws = new WebSocket(
  `ws://localhost:8000/api/v1/ws/${clientId}?token=YOUR_API_KEY`
);

ws.onmessage = (event) => {
  const job = JSON.parse(event.data);
  console.log(`Progress: ${job.progress}%`);
};
```

## Getting Help

### Documentation

- This API Reference
- [Developer Guide](../developer/index.md)
- [API Clients Guide](../developer/api-clients.md)

### Support

- [GitHub Issues](https://github.com/curdriceaurora/Local-File-Organizer/issues)
- [GitHub Discussions](https://github.com/curdriceaurora/Local-File-Organizer/discussions)

### Troubleshooting

- Check [Troubleshooting Guide](../troubleshooting.md)
- Review error codes and messages
- Check server logs for details

## Next Steps

- [Authentication Details](authentication.md)
- [File Management API](file-endpoints.md)
- [Organization API](organization-endpoints.md)
- [Search API](search-endpoints.md)
- [WebSocket API](websocket-api.md)
