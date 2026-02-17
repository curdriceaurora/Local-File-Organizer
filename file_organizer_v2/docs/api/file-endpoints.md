# File Management Endpoints

API endpoints for file upload, listing, and management.

## Upload Files

Upload files to the system.

Files can be uploaded through the web UI by:

1. Opening the file browser
1. Clicking **Upload**
1. Selecting files
1. Clicking **Upload**

For programmatic uploads, use the web UI file upload form or consult the web framework documentation.

## Get File Details

Get detailed information about a file.

```
GET /api/v1/files/{file_id}
```

### Response

```json
{
  "success": true,
  "data": {
    "id": "file_123",
    "name": "document.pdf",
    "path": "/documents/",
    "size": 1024000,
    "type": "pdf",
    "created": "2024-02-01T10:30:00Z",
    "modified": "2024-02-15T14:20:00Z",
    "description": "AI-generated description",
    "tags": ["important", "project-x"],
    "duplicates": [
      {
        "id": "file_789",
        "similarity": 0.98
      }
    ]
  }
}
```

## Update File

Update file metadata.

```
PATCH /api/v1/files/{file_id}
```

### Request Body

```json
{
  "description": "Updated description",
  "tags": ["new-tag"],
  "name": "renamed.pdf"
}
```

### Response

```json
{
  "success": true,
  "data": {
    "id": "file_123",
    "name": "renamed.pdf",
    "description": "Updated description",
    "tags": ["new-tag"]
  }
}
```

## Delete File

Delete a file.

```
DELETE /api/v1/files/{file_id}
```

### Response

```json
{
  "success": true,
  "message": "File deleted successfully"
}
```

## Download File

Download a file.

```
GET /api/v1/files/{file_id}/download
```

### Response

Binary file content with appropriate headers.

## File Listing with Path

List files in a specific directory.

```
GET /api/v1/files
```

### Query Parameters

- `path` - Directory path to list (required)
- `page` - Page number (default: 1)
- `pageSize` - Items per page (default: 50)
- `sort` - Sort field (name, date, size)
- `order` - Sort order (asc, desc)
- `type` - Filter by file type

### Response

```json
{
  "success": true,
  "data": {
    "files": [...],
    "total": 150,
    "page": 1,
    "pageSize": 50
  }
}
```

## Batch Delete

Delete multiple files.

```
POST /api/v1/files/delete/batch
```

### Request Body

```json
{
  "file_ids": ["file_1", "file_2", "file_3"]
}
```

### Response

```json
{
  "success": true,
  "data": {
    "deleted": 3,
    "failed": 0
  }
}
```

______________________________________________________________________

See [API Reference](index.md) for more endpoints.
