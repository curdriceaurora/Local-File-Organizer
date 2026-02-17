# WebSocket API

Real-time updates via WebSocket connections.

## Connecting to WebSocket

```javascript
const ws = new WebSocket('ws://localhost:8000/api/v1/ws?api_key=YOUR_KEY');

ws.onopen = () => {
  console.log('Connected');
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Received:', data);
};
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
