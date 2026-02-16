# Hooks and Events

## Supported Events

- `file.scanned`
- `file.organized`
- `file.duplicated`
- `file.deleted`
- `organization.started`
- `organization.completed`
- `organization.failed`
- `deduplication.started`
- `deduplication.completed`
- `deduplication.found`
- `para.categorized`
- `johnny_decimal.assigned`

## Local Hooks vs Webhooks

- Local hooks: in-process callbacks registered with `PluginHookManager.register_local_hook(...)`
- Webhooks: outbound HTTP callbacks registered via `/api/v1/plugins/hooks/register`

Both are triggered through `/api/v1/plugins/hooks/trigger`.

## Callback Payload Shape

```json
{
  "event": "file.organized",
  "payload": {
    "source_path": "...",
    "destination_path": "...",
    "triggered_by": "user_123"
  },
  "timestamp": "2026-02-16T00:00:00+00:00"
}
```

## Gotchas

- Webhook callbacks must use `http://` or `https://`.
- Duplicate webhook registrations are deduplicated by plugin + event + URL.
- Non-2xx webhook responses are reported as failed deliveries.
