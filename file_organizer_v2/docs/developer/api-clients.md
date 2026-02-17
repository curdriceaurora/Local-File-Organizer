# API Clients Guide

## Python Client

### Installation

```bash
pip install file-organizer
```

### Basic Usage

```python
from file_organizer import FileOrganizerClient

client = FileOrganizerClient(
    base_url="http://localhost:8000",
    api_key="fo_abc123_token456"
)

# List files
files = client.files.list(path="/")

# Upload file
with open("document.pdf", "rb") as f:
    file = client.files.upload(f, path="/documents")

# Organize files
job = client.organize.start(
    path="/uploads",
    methodology="para"
)

# Check organization status
status = client.organize.get_status(job.job_id)

# Get results
results = client.organize.get_results(job.job_id)
```

### Authentication

```python
# Using API Key
client = FileOrganizerClient(
    base_url="http://localhost:8000",
    api_key="fo_abc123_token456"
)

# Using JWT Token
client = FileOrganizerClient(
    base_url="http://localhost:8000",
    access_token="eyJhbGc..."
)

# Login
client.auth.login(username="user", password="pass")
```

## JavaScript/Node.js Client

### Installation

```bash
npm install @file-organizer/client
```

### Basic Usage

```javascript
import FileOrganizerClient from "@file-organizer/client";

const client = new FileOrganizerClient({
    baseUrl: "http://localhost:8000",
    apiKey: "fo_abc123_token456"
});

// List files
const files = await client.files.list("/");

// Upload file
const formData = new FormData();
formData.append("file", fileInput.files[0]);
const file = await client.files.upload(formData, "/documents");

// Organize files
const job = await client.organize.start({
    path: "/uploads",
    methodology: "para"
});

// Check status
const status = await client.organize.getStatus(job.jobId);

// Get results
const results = await client.organize.getResults(job.jobId);
```

## cURL Examples

### Authentication

```bash
# API Key header
curl -H "X-API-Key: fo_abc123_token456" \
  http://localhost:8000/api/v1/files

# JWT Bearer token
curl -H "Authorization: Bearer eyJhbGc..." \
  http://localhost:8000/api/v1/files

# Login to get JWT
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "user", "password": "pass"}'
```

### File Operations

```bash
# List files
curl -H "X-API-Key: YOUR_API_KEY" \
  "http://localhost:8000/api/v1/files?path=/"

# Get file details
curl -H "X-API-Key: YOUR_API_KEY" \
  "http://localhost:8000/api/v1/files/file_id"

# Delete file
curl -X DELETE -H "X-API-Key: YOUR_API_KEY" \
  "http://localhost:8000/api/v1/files/file_id"
```

### Organization

```bash
# Start organization
curl -X POST -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "path": "/uploads",
    "methodology": "para",
    "dry_run": false
  }' \
  http://localhost:8000/api/v1/organize/scan

# Get organization status
curl -H "X-API-Key: YOUR_API_KEY" \
  "http://localhost:8000/api/v1/organize/status/job_id"

# Execute organization
curl -X POST -H "X-API-Key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"job_id": "job_id"}' \
  http://localhost:8000/api/v1/organize/execute
```

## Rate Limiting

### Limits by Endpoint

- **File Operations**: 100 requests/minute
- **Organization**: 10 jobs/minute
- **Search**: 100 requests/minute
- **Auth**: 10 attempts/minute

### Handling Rate Limits

```python
import time

try:
    response = client.files.list()
except RateLimitError as e:
    retry_after = e.retry_after
    time.sleep(retry_after)
    response = client.files.list()
```

### Rate Limit Headers

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1645000000
```

## Error Handling

### Common Errors

| Code | Error | Solution |
|------|-------|----------|
| 400 | Invalid request | Check request parameters |
| 401 | Unauthorized | Verify API key or token |
| 403 | Forbidden | Check user permissions |
| 404 | Not found | Verify resource ID/path |
| 429 | Rate limited | Wait and retry |
| 500 | Server error | Check server logs |

### Error Handling Example

```python
try:
    files = client.files.list("/")
except FileOrganizerError as e:
    print(f"Error: {e.code} - {e.message}")
    if e.code == 401:
        # Re-authenticate
        client.auth.login(username, password)
except RateLimitError as e:
    # Wait and retry
    time.sleep(e.retry_after)
```

## WebSocket Connection

### Real-Time Events

```javascript
const ws = new WebSocket(
    "ws://localhost:8000/api/v1/ws/my-client-id",
    {headers: {"X-API-Key": "YOUR_API_KEY"}}
);

ws.onopen = () => {
    console.log("Connected");
};

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log("Event:", data);
};

ws.onerror = (error) => {
    console.error("WebSocket error:", error);
};
```

### Event Types

- `file_uploaded` - File was uploaded
- `organize_progress` - Organization job progressing
- `organize_complete` - Organization finished
- `duplicate_detected` - Duplicates found
- `error` - An error occurred

## Best Practices

### API Key Security

```python
# DO: Use environment variables
import os
api_key = os.getenv("FILE_ORGANIZER_API_KEY")

# DON'T: Hardcode API keys
client = FileOrganizerClient(api_key="fo_abc123...")
```

### Timeout Handling

```python
# Set reasonable timeouts
client = FileOrganizerClient(
    base_url="http://localhost:8000",
    api_key="YOUR_API_KEY",
    timeout=30  # seconds
)
```

### Retry Logic

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
async def organize_with_retry(path):
    return await client.organize.start(path=path)
```

## See Also

- [API Reference](../api/index.md)
- [Architecture Guide](architecture.md)
