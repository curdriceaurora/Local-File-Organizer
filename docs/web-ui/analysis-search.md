# Analysis & Search in the Current Web Surface

This page clarifies what is currently implemented in the web interface versus what is available through API/CLI.

## Search currently available in Web UI

Within **Files** (`/ui/files`), you can:

- search by filename/path segment
- filter by file type
- sort and refine visible results
- load more results incrementally

This is the implementation-backed search experience in the web UI today.

## Analysis currently visible in Web UI

Within **Organize** (`/ui/organize`), you can view:

- organization job progress
- organization job history
- basic run statistics

## What is not a dedicated web page today

There is no separate first-class “Analysis dashboard” route in the web nav at this time.

If you need advanced analysis/search workflows, use:

- API endpoints under `/api/v1/` (see API docs at `/docs` and `/redoc`)
- CLI commands (`search`, `analyze`, `dedupe`, `analytics`)

## Related pages

- [File Management](file-management.md)
- [Organization Workflows](organization.md)
- [Settings & Profile](settings.md)
