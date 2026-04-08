# B2: Browser E2E — Auth Lifecycle Coverage

**Issue:** #1155
**Date:** 2026-04-08
**Status:** Approved

---

## Problem

The Playwright suite has no tests for the authenticated-user lifecycle. The web
UI auth system (cookie-based, `fo_session`) is exercised by unit tests only.
B3 and B4 also need a reusable "logged-in page" fixture that this issue
introduces.

---

## Scope

- Upgrade the existing live server fixture to run with `auth_enabled=True`
- Add two fixtures to `conftest.py`: `registered_user` and `authed_page`
- Add `tests/playwright/test_auth_lifecycle.py` with four lifecycle tests
- No changes to any existing test files

### Out of scope

- Settings/marketplace interactions post-login (B3, B4)
- CSRF protocol unit tests
- Password reset flow

---

## Key Finding: Single Server Is Sufficient

All non-auth test routes (`/ui/files`, `/ui/organize`, `/ui/settings`,
`/ui/marketplace`, `/ui/setup`) have zero auth checks in their handlers. No
global auth middleware blocks them. Changing `live_server_url` from
`auth_enabled=False` to `auth_enabled=True` is safe — all existing tests
continue to pass unchanged.

This eliminates the need for a second live server or separate CI shard.

---

## Architecture

### 1. Server change (`conftest.py:203`)

```python
# Before
auth_enabled=False,

# After
auth_enabled=True,
```

The session-scoped tmp `auth.db` (already isolated per session via
`playwright_allowed_root`) ensures a clean slate each run.

### 2. New fixtures (`conftest.py`)

#### `registered_user` — session-scoped

Creates one user per test session via `POST /api/v1/auth/register` using
`httpx`. Returns a `_UserCreds` dataclass with `username`, `password`,
`email`. Username is uuid-suffixed to prevent cross-run collisions.

Password satisfies default policy (≥12 chars, uppercase, number, special
char): `"TestPass1!xyz"` pattern.

Depends on `live_server_url` to guarantee the server is accepting connections
before the registration request fires.

#### `authed_page` — function-scoped

Depends on `page` + `registered_user`. Navigates to `/ui/profile/login`,
fills the form with `registered_user` credentials, submits, and waits for
the redirect to land on `/ui/profile`. Returns `page` (now holding the
`fo_session` session cookie).

This is the reusable primitive for B3 and B4 — they depend on `authed_page`
and receive a logged-in browser without caring how auth works.

### 3. `tests/playwright/test_auth_lifecycle.py`

`TestAuthLifecycle` class, marked `e2e`, `playwright`, `timeout(60)`.

| Test | Fixtures | Action | Assertion |
|------|----------|--------|-----------|
| `test_register_new_user` | `page` | Fill `/ui/profile/register` with fresh uuid-user, submit | Redirected to `/ui/profile/login` |
| `test_login_lands_on_authenticated_page` | `page`, `registered_user` | Fill `/ui/profile/login`, submit | URL is `/ui/profile`, username visible on page |
| `test_access_protected_route_while_logged_in` | `authed_page` | GET `/ui/profile/edit` | Edit form visible, no error text |
| `test_logout_blocks_protected_route` | `authed_page` | POST logout, then GET `/ui/profile/edit` | `<p class="error-text">Not authenticated.</p>` visible |

#### Note on "redirect/denied" semantics

`_require_web_user` (`profile_routes.py:107`) returns
`HTMLResponse('<p class="error-text">Not authenticated.</p>')` — a `200`
with error HTML, not an HTTP redirect. The post-logout assertion checks DOM
content, not response status. This is the actual behaviour of the app; the
issue's "redirect/denied" language is intentionally loose.

#### Protected route choice

`/ui/profile/edit` is the protected route used for tests 3 and 4. It calls
`_require_web_user`, has a clear authenticated state (edit form rendered) and
a clear unauthenticated state (error paragraph), and is stable across B3/B4.

---

## Data Flow

```
Session start
  └── live_server_url (auth_enabled=True, fresh auth.db)
        └── registered_user (POST /api/v1/auth/register via httpx)

Per-test
  └── authed_page
        ├── page (Playwright browser page)
        └── registered_user (credentials)
              → page.goto("/ui/profile/login")
              → fill + submit form
              → wait for /ui/profile
              → return page (fo_session cookie set)
```

---

## File Changeset

| File | Change |
|------|--------|
| `tests/playwright/conftest.py` | `auth_enabled=False` → `True`; add `_UserCreds`, `registered_user`, `authed_page` |
| `tests/playwright/test_auth_lifecycle.py` | New file — `TestAuthLifecycle` with 4 tests |

---

## Definition of Done

- All four lifecycle tests pass under chromium, firefox, webkit
- `authed_page` fixture is documented in `conftest.py` module docstring
  and importable by B3/B4 test modules
- Existing smoke, file browser, organize workflow, setup wizard, and desktop
  API contract tests continue to pass with `auth_enabled=True`
- `live_server_url` docstring updated to reflect `auth_enabled=True`

---

## Dependencies

- `httpx` (for `registered_user` fixture) — verify it is in the dev
  dependencies (`pyproject.toml`); add if missing

---

## References

- `src/file_organizer/web/profile_routes.py` — `login_submit`, `register_submit`, `logout`, `_require_web_user`
- `src/file_organizer/api/routers/auth.py` — `register_user` endpoint
- `src/file_organizer/api/config.py` — `ApiSettings` password policy defaults
- `tests/playwright/conftest.py` — existing fixture structure
- Issue #1150 — parent epic (B3, B4 depend on `authed_page` from this issue)
