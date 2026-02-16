# Plugin API Reference

This reference is generated from FastAPI OpenAPI schema and filtered to plugin endpoints.

## Regenerate

From `file_organizer_v2/` run:

```bash
python scripts/generate_plugin_openapi.py
```

Generated artifact:

- `docs/phase-6/plugin-development/api/openapi-plugin.json`

## Endpoint Groups

- `GET /api/v1/plugins/files/list`
- `GET /api/v1/plugins/files/metadata`
- `POST /api/v1/plugins/files/organize`
- `GET /api/v1/plugins/config/get`
- `POST /api/v1/plugins/hooks/register`
- `POST /api/v1/plugins/hooks/unregister`
- `GET /api/v1/plugins/hooks`
- `POST /api/v1/plugins/hooks/trigger`

Use the generated JSON file as the source of truth for exact schema fields.
