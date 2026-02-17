# Search Endpoints

> **Note:** The Search API is currently under development.

## Search Files (Coming Soon)

Future endpoints will support:

- `GET /api/v1/search` - Search files
- `POST /api/v1/search/advanced` - Advanced search

---

See [API Reference](index.md) for available endpoints.

### Query Parameters

- `q` - Search query (required)
- `type` - Filter by file type
- `size` - Filter by size range
- `date` - Filter by date range
- `page` - Page number
- `limit` - Results per page

### Response

```json
{
  "success": true,
  "data": {
    "results": [
      {
        "id": "file_1",
        "name": "report.pdf",
        "relevance": 0.95
      }
    ],
    "total": 10,
    "page": 1
  }
}
```

## Advanced Search

Perform advanced search with multiple criteria.

```
POST /api/v1/search/advanced
```

### Request Body

```json
{
  "query": "report",
  "filters": {
    "type": "pdf",
    "size": {
      "min": 1000000,
      "max": 104857600
    },
    "date": {
      "from": "2024-01-01",
      "to": "2024-12-31"
    }
  }
}
```

### Response

```json
{
  "success": true,
  "data": {
    "results": [
      {
        "id": "file_1",
        "name": "quarterly_report.pdf",
        "relevance": 0.98,
        "size": 2097152,
        "modified": "2024-02-15T14:20:00Z"
      }
    ],
    "total": 5
  }
}
```

## Get Saved Searches

List saved searches.

```
GET /api/v1/search/saved
```

### Response

```json
{
  "success": true,
  "data": {
    "searches": [
      {
        "id": "search_1",
        "name": "Recent Reports",
        "query": "type:pdf AND date:>30days",
        "createdAt": "2024-02-10T10:00:00Z"
      }
    ]
  }
}
```

______________________________________________________________________

See [API Reference](index.md) for more information.
