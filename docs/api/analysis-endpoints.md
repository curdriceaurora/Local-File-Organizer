# Analysis Endpoints

API endpoints for file analysis operations.

## Detect Duplicates

Scan directory for duplicates.

```text
POST /api/v1/dedupe/scan
```

### Request Body

```json
{
  "path": "/documents",
  "type": "image"
}
```

### Response

```json
{
  "success": true,
  "data": {
    "job_id": "job_234",
    "status": "pending"
  }
}
```

## Storage Analysis

Analyze storage usage.

```text
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

```text
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
