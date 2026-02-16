# Plugin API Architecture

## Design Intent

The architecture splits responsibilities so plugins can use a narrow, testable API boundary:

- `src/file_organizer/plugins/api/endpoints.py`: HTTP contract for plugin clients
- `src/file_organizer/plugins/api/hooks.py`: event enum, local hooks, webhook dispatch
- `src/file_organizer/plugins/sdk/`: developer SDK for plugin authors

This avoids coupling plugin code to internal API router implementations.

## Request/Execution Flow

1. Plugin authenticates with bearer token.
2. Plugin calls `/api/v1/plugins/*` endpoints.
3. Router validates paths via `resolve_path(...)` and allowed roots.
4. Hook registration is persisted in process memory.
5. Event trigger dispatches local hooks and outbound webhooks.

## Failure Strategy

- Router returns stable API errors for invalid paths and config keys.
- Hook dispatch does not fail globally when one webhook endpoint fails.
- SDK raises explicit auth vs request errors.

## Tradeoff

Webhook registrations are in-memory today. This keeps implementation simple and safe for local single-process usage, but does not persist across restarts.
