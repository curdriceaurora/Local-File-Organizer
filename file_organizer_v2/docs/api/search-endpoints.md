# Search Endpoints

!!! warning "Coming Soon"
The Search API is currently under development and not yet available.
The endpoints documented below represent the planned API surface.

## Planned Endpoints

The following endpoints are planned for a future release:

- `GET /api/v1/search` — Full-text search across files
- `POST /api/v1/search/advanced` — Advanced search with filters
- `GET /api/v1/search/saved` — Retrieve saved searches

## Planned Query Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `q` | string | Search query (required) |
| `type` | string | Filter by file type |
| `size` | string | Filter by size range |
| `date` | string | Filter by date range |
| `page` | integer | Page number |
| `limit` | integer | Results per page |

## Planned Response Format

```json
{
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
```

______________________________________________________________________

See [API Reference](index.md) for currently available endpoints.
