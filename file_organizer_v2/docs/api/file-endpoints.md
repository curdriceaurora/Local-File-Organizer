# File Management Endpoints

API endpoints for file listing, content reading, moving, and deletion.

## List Files

List files in a directory.

```
GET /api/v1/files
```

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | string | *(required)* | Directory or file path to list |
| `recursive` | boolean | `false` | Include files in subdirectories |
| `include_hidden` | boolean | `false` | Include hidden files |
| `file_type` | string | `null` | Comma-separated extensions or groups (`text`, `image`, `video`, `audio`, `cad`) |
| `sort_by` | string | `name` | Sort field: `name`, `size`, `created`, `modified` |
| `sort_order` | string | `asc` | Sort order: `asc`, `desc` |
| `skip` | integer | `0` | Number of items to skip (pagination offset) |
| `limit` | integer | `100` | Items per page (1–1000) |

### Response

```json
{
  "items": [
    {
      "path": "/documents/report.pdf",
      "name": "report.pdf",
      "size": 1024000,
      "created": "2024-02-01T10:30:00Z",
      "modified": "2024-02-15T14:20:00Z",
      "file_type": "pdf",
      "mime_type": "application/pdf"
    }
  ],
  "total": 150,
  "skip": 0,
  "limit": 100
}
```

## Get File Info

Get detailed information about a specific file.

```
GET /api/v1/files/info
```

### Query Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `path` | string | *(required)* Path to the file |

### Response

```json
{
  "path": "/documents/report.pdf",
  "name": "report.pdf",
  "size": 1024000,
  "created": "2024-02-01T10:30:00Z",
  "modified": "2024-02-15T14:20:00Z",
  "file_type": "pdf",
  "mime_type": "application/pdf"
}
```

## Read File Content

Read the text content of a file.

```
GET /api/v1/files/content
```

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `path` | string | *(required)* | Path to the file |
| `max_bytes` | integer | `200000` | Max bytes to read (1–5,000,000) |
| `encoding` | string | `utf-8` | Text encoding |

### Response

```json
{
  "path": "/documents/report.txt",
  "content": "File content here...",
  "encoding": "utf-8",
  "truncated": false,
  "size": 5120,
  "mime_type": "text/plain"
}
```

## Move File

Move or rename a file.

```
POST /api/v1/files/move
```

### Request Body

```json
{
  "source": "/downloads/report.pdf",
  "destination": "/documents/report.pdf",
  "overwrite": false,
  "allow_directory_overwrite": false,
  "dry_run": false
}
```

### Response

```json
{
  "source": "/downloads/report.pdf",
  "destination": "/documents/report.pdf",
  "moved": true,
  "dry_run": false
}
```

## Delete File

Delete a file (moves to trash by default).

```
DELETE /api/v1/files
```

### Request Body

```json
{
  "path": "/documents/old-report.pdf",
  "permanent": false,
  "dry_run": false
}
```

### Response

```json
{
  "path": "/documents/old-report.pdf",
  "deleted": true,
  "dry_run": false,
  "trashed_path": "/home/user/.config/file-organizer/trash/old-report.pdf"
}
```

Set `permanent: true` to bypass trash and permanently delete the file.

______________________________________________________________________

See [API Reference](index.md) for more endpoints.
