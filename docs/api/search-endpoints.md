# Search Endpoints

## `GET /api/v1/search`

Search for files by keyword or hybrid BM25+vector semantic relevance.

**Query Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `q` | string | Yes | Search query |
| `type` | string | No | Filter by file extension (e.g. `pdf`, `.txt`) |
| `limit` | integer | No | Maximum results to return |
| `offset` | integer | No | Pagination offset |
| `path` | string | No | Restrict search to a specific directory |
| `semantic` | boolean | No | Use hybrid BM25+vector search (default: `false`) |

**Keyword search** (`semantic=false`, default): ranks results by filename and
path relevance using scoring tiers (exact match → stem contains → extension
match → path contains).

**Semantic search** (`semantic=true`): indexes file content using BM25 and
TF-IDF vector representations, then fuses both rankings with Reciprocal Rank
Fusion (RRF, k=60) to return content-relevant results. The `score` field
contains the RRF score.

**Response:** `200 OK` — array of search result objects.

```json
[
  {
    "filename": "quarterly_budget.txt",
    "path": "/home/user/docs/quarterly_budget.txt",
    "score": 0.030769,
    "type": "txt",
    "size": 4096,
    "created": "2026-01-15T10:30:00Z"
  }
]
```

**Error responses:**
- `400 Bad Request` — `q` parameter missing or empty

**Examples:**

```bash
# Keyword search
curl "http://localhost:8000/api/v1/search?q=report&limit=10"

# Semantic search with type filter
curl "http://localhost:8000/api/v1/search?q=quarterly+budget+forecast&semantic=true&type=txt"

# Paginated results
curl "http://localhost:8000/api/v1/search?q=invoice&limit=20&offset=40"
```

---

See [API Reference](index.md) for authentication and other endpoints.
