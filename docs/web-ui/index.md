# Web UI Guide

This guide documents the currently implemented browser interface mounted at **`/ui/`**.

## Access and first run

- Start the app server: `file-organizer serve` (or `fo serve`)
- Open: `http://localhost:8000/ui/`
- On first run (when setup is incomplete), `/ui/` redirects to **`/ui/setup`**
- When API docs are enabled, they are available at **`/docs`** and **`/redoc`**

## Implemented top navigation

The top nav is currently implementation-backed by the web templates and `NAV_ITEMS`:

- **Home** (`/ui/`)
- **Files** (`/ui/files`)
- **Organize** (`/ui/organize`)
- **Marketplace** (`/ui/marketplace`)
- **Settings** (`/ui/settings`)
- **Profile** (`/ui/profile`)

## What each surface covers

### Home

Landing page with quick links into Files, Organize, and Settings.

### Files

Directory tree + file results panel with:

- grid/list view
- search and type filters
- sorting
- upload
- preview panel
- thumbnail generation for image/PDF/video
- desktop-only “Reveal in Files” action through the desktop bridge

### Organize

Organization dashboard with:

- scan + plan generation
- methodology selection
- run controls
- progress updates
- history and stats panels
- report export endpoints

### Settings

Tabbed settings UI for:

- General
- Models
- Organization
- Appearance
- Advanced

Includes import/export/reset flows and section-level saves.

### Profile

Account/auth and collaboration surface, including:

- login/register/forgot/reset password
- profile details and avatar
- workspace management and switching
- team invite/role updates
- shared folders
- activity + notifications
- account security options (password / 2FA)
- user API key generation/revocation

## Related guides

- [Web UI Getting Started](getting-started.md)
- [File Management](file-management.md)
- [Organization Workflows](organization.md)
- [Analysis & Search Reality Check](analysis-search.md)
- [Settings & Profile](settings.md)
