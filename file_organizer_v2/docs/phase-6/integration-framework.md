# Phase 6: Third-Party Integration Framework

## Why This Exists

Phase 6 needs a stable integration contract so new external tools can be added
without duplicating transport logic in API handlers. The framework separates:

- Adapter lifecycle and file delivery (`connect`, `send_file`, `disconnect`)
- Integration registry/orchestration (`IntegrationManager`)
- Browser-extension token/config concerns (`BrowserExtensionManager`)
- API-facing control plane (`/api/v1/integrations/*`)

This keeps external integration behavior consistent while allowing each connector
(Obsidian, VS Code, workflow tools) to evolve independently.

## Implemented Adapters

- `obsidian`: copies files into a vault and writes metadata notes.
- `vscode`: writes command payloads (`vscode://file/...`) for a local companion.
- `workflow`: exports Alfred/Raycast JSON payloads for launcher automation.

All adapters implement the same base contract in
`src/file_organizer/integrations/base.py`.

## API Surface

- `GET /api/v1/integrations`: list configured adapter status.
- `POST /api/v1/integrations/{name}/settings`: update adapter settings.
- `POST /api/v1/integrations/{name}/connect`: validate and connect adapter.
- `POST /api/v1/integrations/{name}/disconnect`: disconnect adapter.
- `POST /api/v1/integrations/{name}/send`: send a file to adapter.
- `GET /api/v1/integrations/browser/config`: browser-extension bootstrap config.
- `POST /api/v1/integrations/browser/token`: issue extension token.
- `POST /api/v1/integrations/browser/verify`: validate extension token.

## Security Model

- API `send` and path-like settings are validated against `allowed_paths`.
- Browser tokens are short-lived and verified server-side.
- Adapters do not execute arbitrary user commands; they only export payloads.

## Operational Gotchas

- Obsidian integration requires an existing vault directory.
- VS Code integration writes command JSON; a client/extension must consume it.
- Workflow exports are file-based and should be cleaned up by external jobs if
  high-volume usage is expected.

## Test Coverage

- Unit tests for adapters and manager:
  - `tests/integrations/test_adapters.py`
  - `tests/integrations/test_manager.py`
- API tests:
  - `tests/test_api_integrations.py`

These tests validate lifecycle behavior, path enforcement, token issuance, and
cross-adapter file send flows.
