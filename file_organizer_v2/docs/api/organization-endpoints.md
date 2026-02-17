# Organization Endpoints

API endpoints for file organization operations.

## Scan for Organization

Analyze files to plan organization.

```
POST /api/v1/organize/scan
```

### Request Body

```json
{
  "path": "/uploads",
  "methodology": "para",
  "dry_run": true
}
```

### Response

```json
{
  "success": true,
  "data": {
    "job_id": "job_123",
    "status": "pending",
    "methodology": "para",
    "file_count": 100,
    "created_at": "2024-02-15T14:00:00Z"
  }
}
```

## Preview Organization

Preview what organization will do (dry run).

```
POST /api/v1/organize/preview
```

### Request Body

```json
{
  "job_id": "job_123"
}
```

### Response

```json
{
  "success": true,
  "data": {
    "changes": [
      {
        "file_id": "file_1",
        "original_path": "/uploads/document.pdf",
        "new_path": "/organized/Projects/document.pdf"
      }
    ]
  }
}
```

## Execute Organization

Apply the planned organization.

```
POST /api/v1/organize/execute
```

### Request Body

```json
{
  "job_id": "job_123"
}
```

### Response

```json
{
  "success": true,
  "data": {
    "job_id": "job_123",
    "status": "in_progress",
    "methodology": "para",
    "file_count": 100,
    "started_at": "2024-02-15T14:00:00Z"
  }
}
```

## Get Job Status

Get organization job status and progress.

```
GET /api/v1/organize/status/{job_id}
```

### Response

```json
{
  "success": true,
  "data": {
    "job_id": "job_123",
    "status": "in_progress",
    "methodology": "para",
    "progress": 65,
    "file_count": 100,
    "processed_count": 65,
    "error_count": 0,
    "started_at": "2024-02-15T14:00:00Z",
    "estimated_completion": "2024-02-15T14:05:00Z"
  }
}
```

______________________________________________________________________

See [API Reference](index.md) for more information.
