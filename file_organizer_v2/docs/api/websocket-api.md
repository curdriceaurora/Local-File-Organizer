# WebSocket API

Real-time updates via WebSocket connections.

## Connecting to WebSocket

> **Security Note:** Do not pass API keys in URL. Use headers for authentication.

```javascript
// Node.js example using 'ws' library
const WebSocket = require('ws');

const ws = new WebSocket('ws://localhost:8000/api/v1/ws', {
  headers: {
    'X-API-Key': 'YOUR_API_KEY'
  }
});

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
