# WebSocket API

Real-time updates via WebSocket connections.

## Connecting to WebSocket

The WebSocket endpoint requires a unique `client_id` path parameter. Each client session must use a distinct `client_id`. Authentication is handled via the `token` query parameter. This approach works in both browser and Node.js environments.

**Endpoint**: `ws://localhost:8000/api/v1/ws/{client_id}?token=YOUR_API_KEY`

```javascript
// Browser example
const clientId = crypto.randomUUID();
const ws = new WebSocket(
  `ws://localhost:8000/api/v1/ws/${clientId}?token=YOUR_API_KEY`
);

ws.onopen = () => {
  console.log('Connected');
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Received:', data);
};
```

**Query Parameter Authentication**:

All WebSocket connections must use the `?token=` query parameter for authentication. This is the only method that works with browser WebSocket APIs.

```javascript
// Standard approach for both browser and Node.js
const WebSocket = require('ws');
const { randomUUID } = require('crypto');

const clientId = randomUUID();
const token = 'YOUR_API_KEY';

const ws = new WebSocket(
  `ws://localhost:8000/api/v1/ws/${clientId}?token=${token}`
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
