# WebSocket API

Real-time updates via WebSocket connections.

## Connecting to WebSocket

The WebSocket endpoint requires a unique `client_id` path parameter and an API token
passed as a query parameter. Each client session must use a distinct `client_id`.

**Endpoint**: `ws://localhost:8000/api/v1/ws/{client_id}?token=YOUR_API_KEY`

```javascript
// Node.js example using 'ws' library
const WebSocket = require('ws');
const { randomUUID } = require('crypto');

// Generate a unique client ID for this session
const clientId = randomUUID();

const ws = new WebSocket(
  `ws://localhost:8000/api/v1/ws/${clientId}?token=YOUR_API_KEY`
);

ws.on('open', () => {
  console.log('Connected');
});

ws.on('message', (data) => {
  const event = JSON.parse(data);
  console.log('Received:', event);
});
```

## Events

### Job Progress

Updates on organization job progress.

```json
{
  "type": "job_progress",
  "jobId": "job_123",
  "progress": 65,
  "processedCount": 65,
  "totalCount": 100,
  "currentFile": "document.pdf"
}
```

### Job Complete

Job has finished.

```json
{
  "type": "job_complete",
  "jobId": "job_123",
  "status": "completed",
  "organized": 100,
  "failed": 0
}
```

### File Uploaded

New file uploaded.

```json
{
  "type": "file_uploaded",
  "fileId": "file_456",
  "name": "newfile.pdf",
  "size": 512000
}
```

### Error

Error occurred during operation.

```json
{
  "type": "error",
  "jobId": "job_123",
  "error": "Permission denied",
  "code": "PERMISSION_ERROR"
}
```

______________________________________________________________________

See [API Reference](index.md) for more information.
