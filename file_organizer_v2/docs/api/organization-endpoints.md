# Organization Endpoints

API endpoints for file organization operations.

## Start Organization Job

Create and start an organization job.

```
POST /api/v1/organize
```

### Request Body

```json
{
  "file_ids": ["file_1", "file_2", "file_3"],
  "methodology": "para",
  "options": {
    "dryRun": false,
    "preserveOriginals": false,
    "createFolders": true,
    "applyMetadata": true
  }
}
```

### Response

```json
{
  "success": true,
  "data": {
    "jobId": "job_123",
    "status": "pending",
    "methodology": "para",
    "fileCount": 3,
    "createdAt": "2024-02-15T14:00:00Z"
  }
}
```

## List Organization Jobs

List all organization jobs.

```
GET /api/v1/organize/jobs
```

### Query Parameters

- `status` - Filter by status (pending, in_progress, completed, failed)
- `methodology` - Filter by methodology
- `limit` - Limit results (default: 50)

### Response

```json
{
  "success": true,
  "data": {
    "jobs": [
      {
        "jobId": "job_123",
        "status": "in_progress",
        "methodology": "para",
        "progress": 65,
        "createdAt": "2024-02-15T14:00:00Z"
      }
    ]
  }
}
```

## Get Job Status

Get detailed job information.

```
GET /api/v1/organize/jobs/{job_id}
```

### Response

```json
{
  "success": true,
  "data": {
    "jobId": "job_123",
    "status": "in_progress",
    "methodology": "para",
    "progress": 65,
    "fileCount": 100,
    "processedCount": 65,
    "errorCount": 0,
    "startedAt": "2024-02-15T14:00:00Z",
    "estimatedCompletion": "2024-02-15T14:05:00Z"
  }
}
```

## Get Job Results

Get detailed results of completed job.

```
GET /api/v1/organize/jobs/{job_id}/results
```

### Response

```json
{
  "success": true,
  "data": {
    "jobId": "job_123",
    "status": "completed",
    "results": {
      "organized": 100,
      "skipped": 0,
      "failed": 0,
      "changes": [
        {
          "fileId": "file_1",
          "originalPath": "/downloads/document.pdf",
          "newPath": "/organized/Projects/Website/document.pdf"
        }
      ]
    }
  }
}
```

## Cancel Job

Cancel a running job.

```
POST /api/v1/organize/jobs/{job_id}/cancel
```

### Response

```json
{
  "success": true,
  "message": "Job cancelled successfully"
}
```

______________________________________________________________________

See [API Reference](index.md) for more information.
