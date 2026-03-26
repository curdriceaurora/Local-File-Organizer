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

**Response Schema:**

| Field | Type | Description |
|-------|------|-------------|
| `filename` | string | Base name of the file |
| `path` | string | Absolute path to the file |
| `score` | number | Relevance score (keyword: tier-based 0-4; semantic: RRF score 0-1) |
| `type` | string | File extension without leading dot |
| `size` | integer | File size in bytes |
| `created` | string | ISO 8601 timestamp of file creation |

**Error responses:**
- `400 Bad Request` — `q` parameter missing or empty
- `422 Unprocessable Entity` — Invalid parameter values (e.g., negative `limit` or `offset`)
- `500 Internal Server Error` — Search index unavailable or query processing failed

**Examples:**

```bash
# Basic keyword search
curl "http://localhost:8000/api/v1/search?q=report&limit=10"

# Semantic search with type filter
curl "http://localhost:8000/api/v1/search?q=quarterly+budget+forecast&semantic=true&type=txt"

# Paginated results
curl "http://localhost:8000/api/v1/search?q=invoice&limit=20&offset=40"

# Path-restricted search
curl "http://localhost:8000/api/v1/search?q=meeting&path=/home/user/documents/2026"

# Combined filters: type, path, and semantic
curl "http://localhost:8000/api/v1/search?q=contract&type=pdf&path=/home/user/legal&semantic=true&limit=5"

# Search with URL-encoded spaces and special characters
curl "http://localhost:8000/api/v1/search?q=Q1%202026%20sales&type=xlsx"

# Multiple file types (using OR logic on client side, separate requests)
curl "http://localhost:8000/api/v1/search?q=presentation&type=pptx"
curl "http://localhost:8000/api/v1/search?q=presentation&type=pdf"

# Pretty-printed JSON response with jq
curl "http://localhost:8000/api/v1/search?q=budget&semantic=true" | jq '.'
```

**Python Client Usage:**

```python
import requests

# Basic search
response = requests.get(
    "http://localhost:8000/api/v1/search",
    params={"q": "report", "limit": 10}
)
results = response.json()
for file in results:
    print(f"{file['filename']} - Score: {file['score']}")

# Semantic search with filters
response = requests.get(
    "http://localhost:8000/api/v1/search",
    params={
        "q": "quarterly budget forecast",
        "semantic": True,
        "type": "txt",
        "path": "/home/user/financial"
    }
)
results = response.json()

# Paginated search with error handling
def search_all(query, page_size=50):
    """Fetch all results for a query using pagination."""
    all_results = []
    offset = 0

    while True:
        try:
            response = requests.get(
                "http://localhost:8000/api/v1/search",
                params={"q": query, "limit": page_size, "offset": offset},
                timeout=10
            )
            response.raise_for_status()

            batch = response.json()
            if not batch:
                break

            all_results.extend(batch)
            offset += page_size

            # Stop if we got fewer results than requested (last page)
            if len(batch) < page_size:
                break

        except requests.exceptions.HTTPError as e:
            if response.status_code == 400:
                print(f"Bad request: {response.json()}")
            elif response.status_code == 422:
                print(f"Invalid parameters: {response.json()}")
            else:
                print(f"HTTP error: {e}")
            break
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            break

    return all_results

# Usage
all_invoices = search_all("invoice")
print(f"Found {len(all_invoices)} invoice files")

# Semantic search with result filtering
response = requests.get(
    "http://localhost:8000/api/v1/search",
    params={"q": "machine learning research", "semantic": True, "type": "pdf"}
)

if response.status_code == 200:
    results = response.json()
    # Filter by score threshold on client side
    high_relevance = [r for r in results if r['score'] > 0.02]
    print(f"High relevance results: {len(high_relevance)}")
else:
    print(f"Error {response.status_code}: {response.text}")
```

---

See [API Reference](index.md) for authentication and other endpoints.
