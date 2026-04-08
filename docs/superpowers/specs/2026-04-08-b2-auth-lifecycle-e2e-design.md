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

- Modify `tests/playwright/conftest.py`: flip `auth_enabled=False` → `True`,
  update the `live_server_url` docstring, add `registered_user` and
  `authed_page` fixtures
- Add `tests/playwright/test_auth_lifecycle.py` with four lifecycle tests
- No changes to any existing test modules (`test_smoke.py`,
  `test_file_browser_desktop.py`, `test_organize_workflow.py`,
  `test_setup_wizard_flow.py`, `test_desktop_api_contract.py`)

### Out of scope

- Settings/marketplace interactions post-login (B3, B4)
- CSRF protocol unit tests
- Password reset flow

---

## Key Finding: Single Server Is Sufficient

All non-auth test routes (`/ui/files`, `/ui/organize`, `/ui/settings`,
`/ui/marketplace`, `/ui/setup`) have zero auth checks in their handlers. No
global auth middleware blocks them. Changing `live_server_url` from
`auth_enabled=False` to `auth_enabled=True` is safe for all five existing
test files.

**Precise scope of "unchanged":** The smoke suite visits `/ui/profile/login`
and `/ui/profile/register` (both public, both return 2xx regardless of
`auth_enabled`). It does NOT visit `/ui/profile` itself. The `/ui/profile`
index page renders differently under `auth_enabled=True` (HTMX-loads the
login panel) versus `auth_enabled=False` ("Authentication is disabled."),
but no existing test asserts on that page, so no existing test regresses.
Any future smoke test added for `/ui/profile` must assert against the
enabled-auth behaviour (login panel present, not the "disabled" message).

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

Depends on `live_server_url` to guarantee the server is accepting connections
before the registration request fires.

**Exact request payload** (all fields required by `register_user` in
`api/routers/auth.py`):

```python
{
    "username": f"testuser_{uuid4().hex[:8]}",
    "email":    f"testuser_{uuid4().hex[:8]}@example.com",
    "password": "TestPass1!xyz",   # satisfies all default policy rules:
                                   # ≥12 chars, uppercase, number, special char
    "full_name": "Test User",      # optional; included for completeness
}
```

**Response contract:** assert `response.status_code == 201` and that the
JSON body contains `"username"` matching the sent value. Any other status
(400 username taken, 422 validation error) raises immediately so the fixture
fails loudly rather than silently creating a broken test session.

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
| `test_logout_blocks_protected_route` | `authed_page` | `page.request.post("/ui/profile/logout")`, then `page.goto("/ui/profile/edit")` | `<p class="error-text">Not authenticated.</p>` visible |

#### Logout mechanism

`profile/index.html` contains `<form method="post" action="/ui/profile/logout">`.
The test uses `page.request.post("/ui/profile/logout")` rather than
navigating to the profile page and clicking the button. `page.request` in
Playwright shares the same cookie storage as the page context, so the
`Set-Cookie: fo_session=; Max-Age=0` response from the logout handler
clears the session cookie in the browser before the next `page.goto()`.
This avoids depending on the profile page rendering correctly just to reach
the logout button, and is directly analogous to what a browser does when the
form submits.

#### Note on "redirect/denied" semantics

`_require_web_user` (`profile_routes.py:107`) returns
`HTMLResponse('<p class="error-text">Not authenticated.</p>')` — a `200`
with error HTML, not an HTTP redirect. The post-logout assertion checks DOM
content, not response status. This is the actual behaviour of the app; the
issue's "redirect/denied" language is intentionally loose.

#### Protected route choice and assertion surface

`/ui/profile/edit` is an **HTMX partial endpoint** — it returns an HTML
fragment, not a full page. Both tests navigate to it directly with
`page.goto("/ui/profile/edit")`, which loads the raw partial as the page
body. This is intentional: it tests the auth enforcement at the handler
level, not the HTMX integration (which belongs in B3/B4).

Concrete assertions for each state:

- **Authenticated (test 3):** `expect(page.locator("form")).to_be_visible()`
  — the edit partial renders a `<form>` element. Also assert
  `expect(page.locator("p.error-text")).not_to_be_visible()` to confirm no
  error state leaked through.

- **Unauthenticated (test 4):** `expect(page.locator("p.error-text")).to_have_text("Not authenticated.")`
  — matches the exact string returned by `_require_web_user`. This is
  tighter than checking visibility alone and guards against the partial shape
  changing silently.

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

### Verification commands

Run in this order to prove the DoD:

```bash
# 1. New auth lifecycle tests — all four pass on chromium
pytest tests/playwright/test_auth_lifecycle.py \
    --browser chromium --override-ini='addopts='

# 2. Regression check — existing test modules unchanged by the server flip
pytest tests/playwright/ -k "not test_auth_lifecycle" \
    --browser chromium --override-ini='addopts='

# 3. Full cross-browser matrix (matches CI playwright job)
pytest tests/playwright/ --browser chromium --override-ini='addopts='
pytest tests/playwright/ --browser firefox  --override-ini='addopts='
pytest tests/playwright/ --browser webkit   --override-ini='addopts='
```

All three steps must exit 0 before the branch is considered done.

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
