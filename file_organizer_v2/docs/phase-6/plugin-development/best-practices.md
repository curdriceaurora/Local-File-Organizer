# Plugin Best Practices

## Design Rules

- Keep plugin logic idempotent where possible.
- Validate payload keys/types before use.
- Fail gracefully: return structured status rather than throwing for expected conditions.
- Keep long-running work out of request-time callbacks.

## Security Rules

- Only operate on paths passed through trusted API boundaries.
- Avoid direct shell execution from plugin callbacks.
- Store sensitive tokens in config, not source files.

## Operational Rules

- Emit explicit return payloads for observability.
- Prefer small, composable hooks over one large callback.
- Version plugin metadata and document behavior changes.
