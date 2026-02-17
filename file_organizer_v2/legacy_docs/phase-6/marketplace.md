# Plugin Marketplace (Phase 6 Task #240)

## Why We Added a Marketplace Layer

The plugin architecture (Task #239) solved loading and lifecycle management, but it did not solve distribution.
The marketplace layer separates package discovery and installation concerns from runtime plugin execution so we can:

- browse/search installable plugins without touching active runtime state
- verify package checksums before extraction
- keep installation metadata and user reviews in dedicated stores
- expose the same operations via CLI, API, and web UI

## Components

- `src/file_organizer/plugins/marketplace/repository.py`
  - reads `index.json` from configured marketplace repository
  - supports local file repositories and HTTP(S) repositories
  - validates package metadata schema
- `src/file_organizer/plugins/marketplace/installer.py`
  - installs, uninstalls, updates plugins
  - enforces checksum validation
  - uses safe ZIP extraction guards to prevent path traversal/symlink issues
- `src/file_organizer/plugins/marketplace/metadata.py`
  - local metadata cache for search/filter
- `src/file_organizer/plugins/marketplace/reviews.py`
  - local review persistence and aggregate rating operations
- `src/file_organizer/plugins/marketplace/service.py`
  - orchestration facade used by CLI/API/web routes

## Interfaces

### CLI

- `file-organizer marketplace list`
- `file-organizer marketplace search <query>`
- `file-organizer marketplace install <name>`
- `file-organizer marketplace uninstall <name>`
- `file-organizer marketplace update <name>`
- `file-organizer marketplace installed`
- `file-organizer marketplace updates`
- `file-organizer marketplace review <name> --user ... --rating ... --title ... --content ...`

### API

Marketplace API routes are available under `/api/v1/marketplace/*`:

- `GET /api/v1/marketplace/plugins`
- `GET /api/v1/marketplace/plugins/{name}`
- `POST /api/v1/marketplace/plugins/{name}/install`
- `DELETE /api/v1/marketplace/plugins/{name}`
- `POST /api/v1/marketplace/plugins/{name}/update`
- `GET /api/v1/marketplace/installed`
- `GET /api/v1/marketplace/updates`
- `GET /api/v1/marketplace/plugins/{name}/reviews`
- `POST /api/v1/marketplace/plugins/{name}/reviews`

### Web UI

- `GET /ui/marketplace`
- install/update/uninstall actions are available from the marketplace table

## Configuration

- `FO_MARKETPLACE_HOME`: local storage for installed metadata/reviews/plugins
  - default: `~/.config/file-organizer/marketplace`
- `FO_MARKETPLACE_REPO_URL`: repository location
  - supports local path, `file://`, `http://`, and `https://`
  - default: `<FO_MARKETPLACE_HOME>/repository`

## Gotchas

- Missing local repository index is treated as an empty marketplace.
- Installation only accepts safe archive layouts:
  - `plugin.py` at archive root, or
  - one top-level directory containing `plugin.py`
- ZIP extraction rejects `..` traversal paths and symlink entries.
