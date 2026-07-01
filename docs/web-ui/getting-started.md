# Getting Started with the Web UI

## 1. Launch the server

```bash
file-organizer serve
# or: fo serve
```

The server prints the Web UI entry URL as `http://<host>:<port>/ui/`.

## 2. Open the correct path

Use the **`/ui/`** prefix:

```text
http://localhost:8000/ui/
```

If setup has not been completed yet, the app redirects to:

```text
http://localhost:8000/ui/setup
```

## 3. Understand key paths

- Web UI: `/ui/`
- API base: `/api/v1/`
- API docs, when enabled (Swagger): `/docs`
- API docs, when enabled (ReDoc): `/redoc`

## 4. Navigate core surfaces

After setup/login, use the top nav:

- Home
- Files
- Organize
- Marketplace
- Settings
- Profile

## 5. First practical workflow

1. Go to **Files** and choose an allowed root.
2. Upload a few files (browse or drag/drop).
3. Use search/type filters to narrow results.
4. Open **Organize** and generate a plan from input/output directories.
5. Review plan details before running a job.

## Next steps

- [File Management](file-management.md)
- [Organization Workflows](organization.md)
- [Settings & Profile](settings.md)
