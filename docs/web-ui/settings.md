# Settings & Profile (Web UI)

This page summarizes the currently implemented **Settings** and **Profile** surfaces.

## Settings (`/ui/settings`)

The settings UI is tabbed and currently includes:

- **General**: language, timezone, default input/output directories
- **Models**: Ollama URL, text model, vision model, connectivity test
- **Organization**: default methodology, rules, auto-organize, notifications, glob filter
- **Appearance**: theme and custom theme name
- **Advanced**: log level, cache, debug mode, performance mode

Additional flows available from Settings:

- import settings
- export settings
- reset defaults
- settings section search

## Profile (`/ui/profile`)

Profile is a first-class web surface in the current nav and routes.

### Auth/account entry flows

- login
- register
- forgot password
- reset password
- logout

### Profile management

- edit profile details
- avatar upload/serve
- workspace list/create/switch
- team invite and role updates
- shared folder add/remove
- activity view
- notifications + mark-read
- account settings (password + 2FA toggle)
- API key generate/revoke

## API key note

Profile API keys are managed in the Profile area (`/ui/profile/api-keys`) and are separate from generic app configuration docs.

## Desktop bridge note

When running inside the desktop app, some UI controls use `window.pywebview.api` wrappers from `desktop_api.js`. In browser mode those controls safely no-op or fall back where possible.
