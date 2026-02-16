# API Client Libraries

The project ships official client libraries under:

- Python: `src/file_organizer/client/`
- TypeScript: `src/file_organizer/client/typescript/`
- CLI wrapper: `file-organizer api ...`

## Why clients exist

- Keep API consumption type-safe and consistent.
- Centralize authentication/token handling and error translation.
- Reduce duplicated request logic across scripts, tools, and integrations.

## Python client quick start

```python
from file_organizer.client import FileOrganizerClient

with FileOrganizerClient(base_url="http://localhost:8000") as client:
    tokens = client.login("username", "password")
    me = client.me()
    stats = client.system_stats(path=".")
    print(me.username, stats.file_count)
    client.logout(tokens.refresh_token)
```

Async equivalent:

```python
from file_organizer.client import AsyncFileOrganizerClient

async def run() -> None:
    async with AsyncFileOrganizerClient(base_url="http://localhost:8000") as client:
        await client.login("username", "password")
        health = await client.health()
        print(health.status)
```

## TypeScript client quick start

```ts
import { FileOrganizerClient } from "./client";

const client = new FileOrganizerClient({ baseUrl: "http://localhost:8000" });
const tokens = await client.login("username", "password");
const status = await client.systemStatus(".");
const stats = await client.systemStats({ path: "." });
await client.logout(tokens.refresh_token);
```

## CLI wrapper quick start

```bash
file-organizer api health
file-organizer api login --username user --password pass --save-token .tmp/tokens.json
file-organizer api me --token "<access-token>"
file-organizer api system-stats . --token "<access-token>"
```

## Endpoint coverage

The Python and TypeScript clients cover all v1 REST endpoints:

- Auth: login/register/refresh/logout/me
- Files: list/info/content/move/delete
- Organize: scan/preview/execute/status
- Dedupe: scan/preview/execute
- System: status/stats/config(get/patch)
- Health

## Error model and pitfalls

- HTTP 401/403 -> `AuthenticationError`
- HTTP 404 -> `NotFoundError`
- HTTP 422 -> `ValidationError` (Python client)
- HTTP 5xx -> `ServerError`

Pitfalls:

- `logout` requires both current access token and a refresh token.
- `system/config` patch requires an admin account.
- File/path endpoints enforce API allowed path restrictions; local absolute paths
  outside allowed roots will fail with API validation errors.
