# Analysis Endpoints

API endpoints for file analysis operations.

## Detect Duplicates

Analyze and find duplicate files.

```
POST /api/v1/analyze/duplicates
```

### Request Body

```json
{
  "paths": ["/documents", "/downloads"],
  "method": "smart",
  "minSize": 1000000
}
```

### Response

```json
{
  "success": true,
  "data": {
    "jobId": "job_234",
    "status": "completed",
    "groups": [
      {
        "similarity": 1.0,
        "files": [
          {
            "id": "file_1",
            "name": "document.pdf",
            "size": 1024000
          },
          {
            "id": "file_2",
            "name": "document_copy.pdf",
            "size": 1024000
          }
        ]
      }
    ]
  }
}
```

## Storage Analysis

Analyze storage usage.

```
GET /api/v1/analyze/storage
```

### Query Parameters

- `groupBy` - Group by (type, folder, size)

### Response

```json
{
  "success": true,
  "data": {
    "total": 1048576000,
    "used": 524288000,
    "available": 524288000,
    "breakdown": [
      {
        "category": "pdf",
        "size": 262144000,
        "count": 50,
        "percentage": 50
      }
    ]
  }
}
```

## Category Analysis

Analyze file categories.

```
GET /api/v1/analyze/categories
```

### Response

```json
{
  "success": true,
  "data": {
    "categories": [
      {
        "name": "Documents",
        "fileCount": 150,
        "totalSize": 314572800
      },
      {
        "name": "Images",
        "fileCount": 500,
        "totalSize": 209715200
      }
    ]
  }
}
```

______________________________________________________________________

See [API Reference](index.md) for more information.
