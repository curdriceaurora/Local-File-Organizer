# B2: Auth Lifecycle E2E Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add browser E2E coverage for the full authenticated-user lifecycle and introduce the `authed_page` fixture that B3/B4 depend on.

**Architecture:** Flip the shared live server to `auth_enabled=True` (safe for all existing test routes), add `registered_user` (session-scoped, creates a user via REST API) and `authed_page` (function-scoped, logs in via the web form) fixtures to `conftest.py`, then write four lifecycle tests in a new `TestAuthLifecycle` class.

**Tech Stack:** Python, pytest, Playwright (sync API), httpx, FastAPI test server (uvicorn in-process)

---

## File Map

| File | Action | What changes |
|------|--------|--------------|
| `tests/playwright/conftest.py` | Modify | Flip `auth_enabled`, update docstrings, add `dataclass` + `httpx` imports, add `_UserCreds`, `registered_user`, `authed_page` |
| `tests/playwright/test_auth_lifecycle.py` | Create | `TestAuthLifecycle` with 4 tests |

---

## Task 1: Flip `auth_enabled` and update docstrings

**Files:**
- Modify: `tests/playwright/conftest.py`

- [ ] **Step 1: Change `auth_enabled=False` to `auth_enabled=True`**

In `tests/playwright/conftest.py` find the `ApiSettings(...)` call inside `live_server_url` (currently line ~203). Change:

```python
        settings = ApiSettings(
            allowed_paths=[str(playwright_allowed_root)],
            auth_enabled=False,
            auth_db_path=str(playwright_allowed_root / "auth.db"),
            security_headers_enabled=False,  # CSP blocks the inline CSRF script; disable for tests
        )
```

to:

```python
        settings = ApiSettings(
            allowed_paths=[str(playwright_allowed_root)],
            auth_enabled=True,
            auth_db_path=str(playwright_allowed_root / "auth.db"),
            security_headers_enabled=False,  # CSP blocks the inline CSRF script; disable for tests
        )
```

- [ ] **Step 2: Update the `live_server_url` fixture docstring**

Find the line in the `live_server_url` docstring that reads:

```
    localhost.  ``auth_enabled=False`` removes the login gate so tests
    can reach protected pages without credentials.
```

Replace with:

```
    localhost.  ``auth_enabled=True`` — all non-profile routes (files,
    organize, settings, marketplace, setup) have no auth checks and are
    unaffected.  Profile routes enforce auth; the ``authed_page`` fixture
    provides a logged-in page for tests that need it.
```

- [ ] **Step 3: Update the module-level docstring**

At the top of `tests/playwright/conftest.py`, in the `Fixtures` section, add after the `playwright_allowed_root` entry:

```
registered_user : _UserCreds  (session-scoped)
    Creates one test user per session via ``POST /api/v1/auth/register``.
    Returns a ``_UserCreds`` dataclass with ``username``, ``password``,
    ``email``.  Used by ``authed_page`` and auth lifecycle tests.

authed_page : Page  (function-scoped)
    Navigates to ``/ui/profile/login``, fills the form with
    ``registered_user`` credentials, submits, and waits for the redirect
    to ``/ui/profile``.  Returns the Playwright ``Page`` holding a valid
    ``fo_session`` cookie.  This is the reusable primitive for B3 and B4.
```

- [ ] **Step 4: Run the existing Playwright suite to confirm no regression**

```bash
pytest tests/playwright/ -k "not test_auth_lifecycle" \
    --browser chromium --override-ini='addopts=' -v
```

Expected: all existing tests pass (smoke, file_browser, organize_workflow, setup_wizard, desktop_api_contract). Zero failures.

- [ ] **Step 5: Commit**

```bash
git add tests/playwright/conftest.py
git commit -m "test(playwright): flip live server to auth_enabled=True

All non-profile routes are unaffected by auth enforcement.
Profile-adjacent smoke tests (login, register pages) remain
public and still return 2xx.

Refs #1155"
```

---

## Task 2: Add `_UserCreds` dataclass and `registered_user` fixture

**Files:**
- Modify: `tests/playwright/conftest.py`

- [ ] **Step 1: Add imports**

In the imports block at the top of `tests/playwright/conftest.py`, add:

```python
from dataclasses import dataclass

import httpx
```

Place `from dataclasses import dataclass` with the stdlib imports and `import httpx` with the third-party imports (after `import pytest`, before `from file_organizer...`).

- [ ] **Step 2: Add the `_UserCreds` dataclass**

Add this block in a new section immediately after the existing helpers section (after `_wait_for_port`, before the `# Session-scoped live server` comment):

```python
# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


@dataclass
class _UserCreds:
    """Credentials for the session-scoped test user.

    Created once per session by ``registered_user`` and consumed by
    ``authed_page`` and any test that needs pre-existing credentials.
    """

    username: str
    password: str
    email: str
```

- [ ] **Step 3: Add the `registered_user` fixture**

Add this fixture immediately after the `live_server_url` fixture (after its `finally` block, before the `# Override pytest-playwright's base_url` comment):

```python
@pytest.fixture(scope="session")
def registered_user(live_server_url: str) -> _UserCreds:
    """Create one test user per session via the REST API.

    Posts to ``/api/v1/auth/register`` (API-exempt from CSRF middleware)
    using ``httpx``.  The username is uuid-suffixed so parallel or
    repeated runs never collide in the shared ``auth.db``.

    Asserts 201 + username roundtrip so any contract mismatch causes an
    immediate, loud fixture error rather than a silent downstream failure.

    Returns:
        ``_UserCreds`` with the created user's credentials.

    Raises:
        AssertionError: If registration returns a non-201 status or the
            response body does not contain the expected username.
    """
    import uuid as _uuid

    suffix = _uuid.uuid4().hex[:8]
    creds = _UserCreds(
        username=f"testuser_{suffix}",
        password="TestPass1!xyz",
        email=f"testuser_{suffix}@example.com",
    )
    response = httpx.post(
        f"{live_server_url}/api/v1/auth/register",
        json={
            "username": creds.username,
            "email": creds.email,
            "password": creds.password,
            "full_name": "Test User",
        },
    )
    assert response.status_code == 201, (
        f"registered_user: expected 201, got {response.status_code}: {response.text}"
    )
    assert response.json()["username"] == creds.username, (
        f"registered_user: username mismatch in response: {response.json()}"
    )
    return creds
```

- [ ] **Step 4: Commit**

```bash
git add tests/playwright/conftest.py
git commit -m "test(playwright): add _UserCreds dataclass and registered_user fixture

Session-scoped fixture creates one test user per run via the REST
API. Asserts 201 + username roundtrip for loud failure on contract
mismatch.

Refs #1155"
```

---

## Task 3: Add `authed_page` fixture

**Files:**
- Modify: `tests/playwright/conftest.py`

- [ ] **Step 1: Add the `authed_page` fixture**

Add this fixture immediately after the `base_url` fixture:

```python
@pytest.fixture
def authed_page(page: "Page", registered_user: _UserCreds) -> "Page":
    """Return a Playwright Page with a valid ``fo_session`` session cookie.

    Navigates to ``/ui/profile/login``, fills the form with
    ``registered_user`` credentials, submits, and waits for the
    redirect to ``/ui/profile``.

    This is the reusable entry point for B3 and B4 test modules — they
    declare ``authed_page`` as a fixture parameter and receive a
    logged-in browser page without coupling to the auth implementation.

    Returns:
        The Playwright ``Page`` after successful login (``fo_session``
        cookie set in the browser context).
    """
    page.goto("/ui/profile/login")
    page.locator("#login-username").fill(registered_user.username)
    page.locator("#login-password").fill(registered_user.password)
    page.get_by_role("button", name="Log in").click()
    page.wait_for_url("**/ui/profile")
    return page
```

- [ ] **Step 2: Commit**

```bash
git add tests/playwright/conftest.py
git commit -m "test(playwright): add authed_page fixture

Function-scoped fixture that logs in via the web form and returns
a Page with fo_session cookie set. Reusable entry point for B3/B4.

Refs #1155"
```

---

## Task 4: Create `test_auth_lifecycle.py` and write `test_register_new_user`

**Files:**
- Create: `tests/playwright/test_auth_lifecycle.py`

- [ ] **Step 1: Create the file with boilerplate and the first test**

Create `tests/playwright/test_auth_lifecycle.py` with this content:

```python
"""Browser E2E tests for the authenticated-user lifecycle.

Covers the full auth lifecycle: register → login → access protected route
→ logout → access denied.

Fixtures
--------
registered_user : _UserCreds  (session-scoped, from conftest)
    Pre-created test user. Used by login and protected-route tests.

authed_page : Page  (function-scoped, from conftest)
    Playwright page with a valid fo_session cookie. Used by tests that
    need to start already logged in. Reusable by B3 and B4.
"""

from __future__ import annotations

import uuid

import pytest

try:
    from playwright.sync_api import Page, expect
except ImportError as _exc:
    raise ImportError(
        "playwright not installed — run: pip install -e '.[dev]' && playwright install chromium"
    ) from _exc

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.playwright,
    pytest.mark.timeout(60),
]

_TEST_PASSWORD = "TestPass1!xyz"


class TestAuthLifecycle:
    """Full authenticated-user lifecycle: register → login → protected → logout."""

    def test_register_new_user(self, page: Page) -> None:
        """Register a fresh user via the web form.

        Uses a uuid-suffixed username independent of ``registered_user``
        so this test does not depend on session fixture ordering.
        Asserts the form redirects to the login page on success.
        """
        suffix = uuid.uuid4().hex[:8]
        page.goto("/ui/profile/register")
        page.locator("#reg-username").fill(f"newuser_{suffix}")
        page.locator("#reg-email").fill(f"newuser_{suffix}@example.com")
        page.locator("#reg-password").fill(_TEST_PASSWORD)
        page.get_by_role("button", name="Create account").click()
        page.wait_for_url("**/ui/profile/login")
```

- [ ] **Step 2: Run to verify the test passes**

```bash
pytest tests/playwright/test_auth_lifecycle.py::TestAuthLifecycle::test_register_new_user \
    --browser chromium --override-ini='addopts=' -v
```

Expected output:

```
PASSED tests/playwright/test_auth_lifecycle.py::TestAuthLifecycle::test_register_new_user[chromium]
```

- [ ] **Step 3: Commit**

```bash
git add tests/playwright/test_auth_lifecycle.py
git commit -m "test(playwright): add test_register_new_user

First lifecycle test: fill register form, assert redirect to login.

Refs #1155"
```

---

## Task 5: Write `test_login_lands_on_authenticated_page`

**Files:**
- Modify: `tests/playwright/test_auth_lifecycle.py`

- [ ] **Step 1: Add the test method to `TestAuthLifecycle`**

Add inside the `TestAuthLifecycle` class, after `test_register_new_user`:

```python
    def test_login_lands_on_authenticated_page(
        self, page: Page, registered_user: object
    ) -> None:
        """Fill the login form and assert the profile page shows the user's name.

        ``registered_user`` was created with ``full_name="Test User"``.
        The profile ``<h1>`` renders ``user.full_name or user.username``,
        so "Test User" is the expected text after a successful login.
        """
        page.goto("/ui/profile/login")
        page.locator("#login-username").fill(registered_user.username)  # type: ignore[union-attr]
        page.locator("#login-password").fill(registered_user.password)  # type: ignore[union-attr]
        page.get_by_role("button", name="Log in").click()
        page.wait_for_url("**/ui/profile")
        expect(page.locator("h1.page-title")).to_have_text("Test User")
```

- [ ] **Step 2: Run to verify the test passes**

```bash
pytest tests/playwright/test_auth_lifecycle.py::TestAuthLifecycle::test_login_lands_on_authenticated_page \
    --browser chromium --override-ini='addopts=' -v
```

Expected output:

```
PASSED tests/playwright/test_auth_lifecycle.py::TestAuthLifecycle::test_login_lands_on_authenticated_page[chromium]
```

- [ ] **Step 3: Commit**

```bash
git add tests/playwright/test_auth_lifecycle.py
git commit -m "test(playwright): add test_login_lands_on_authenticated_page

Refs #1155"
```

---

## Task 6: Write `test_access_protected_route_while_logged_in`

**Files:**
- Modify: `tests/playwright/test_auth_lifecycle.py`

- [ ] **Step 1: Add the test method to `TestAuthLifecycle`**

Add inside the `TestAuthLifecycle` class, after `test_login_lands_on_authenticated_page`:

```python
    def test_access_protected_route_while_logged_in(self, authed_page: Page) -> None:
        """/ui/profile/edit renders the edit form for an authenticated user.

        ``/ui/profile/edit`` is an HTMX partial endpoint. Navigating to it
        directly returns the raw HTML fragment. When authenticated the
        fragment contains a ``<form>``; the error paragraph is absent.
        """
        authed_page.goto("/ui/profile/edit")
        expect(authed_page.locator("form")).to_be_visible()
        expect(authed_page.locator("p.error-text")).to_have_count(0)
```

- [ ] **Step 2: Run to verify the test passes**

```bash
pytest tests/playwright/test_auth_lifecycle.py::TestAuthLifecycle::test_access_protected_route_while_logged_in \
    --browser chromium --override-ini='addopts=' -v
```

Expected output:

```
PASSED tests/playwright/test_auth_lifecycle.py::TestAuthLifecycle::test_access_protected_route_while_logged_in[chromium]
```

- [ ] **Step 3: Commit**

```bash
git add tests/playwright/test_auth_lifecycle.py
git commit -m "test(playwright): add test_access_protected_route_while_logged_in

Refs #1155"
```

---

## Task 7: Write `test_logout_blocks_protected_route`

**Files:**
- Modify: `tests/playwright/test_auth_lifecycle.py`

- [ ] **Step 1: Add the test method to `TestAuthLifecycle`**

Add inside the `TestAuthLifecycle` class, after `test_access_protected_route_while_logged_in`:

```python
    def test_logout_blocks_protected_route(self, authed_page: Page) -> None:
        """After logout, /ui/profile/edit returns the unauthenticated error partial.

        Logout is performed via ``page.request.post()`` which shares the
        browser context's cookie jar.  The server's ``delete_cookie``
        response clears ``fo_session`` before the next navigation.

        CSRF: ``/ui/profile/logout`` is not API-exempt so the double-submit
        cookie pattern applies.  ``page.context.cookies()`` returns httpOnly
        cookies (Playwright has privileged access), giving us the
        ``_csrf_token`` value to send as the ``x-csrf-token`` header.
        """
        cookies = authed_page.context.cookies()
        csrf_token = next(
            c["value"] for c in cookies if c["name"] == "_csrf_token"
        )
        authed_page.request.post(
            "/ui/profile/logout",
            headers={"x-csrf-token": csrf_token},
        )
        authed_page.goto("/ui/profile/edit")
        expect(authed_page.locator("p.error-text")).to_have_text("Not authenticated.")
```

- [ ] **Step 2: Run to verify the test passes**

```bash
pytest tests/playwright/test_auth_lifecycle.py::TestAuthLifecycle::test_logout_blocks_protected_route \
    --browser chromium --override-ini='addopts=' -v
```

Expected output:

```
PASSED tests/playwright/test_auth_lifecycle.py::TestAuthLifecycle::test_logout_blocks_protected_route[chromium]
```

- [ ] **Step 3: Commit**

```bash
git add tests/playwright/test_auth_lifecycle.py
git commit -m "test(playwright): add test_logout_blocks_protected_route

Uses page.request.post() + x-csrf-token header to log out within
the shared browser context, then asserts the protected partial
returns the error text.

Refs #1155"
```

---

## Task 8: Full Verification

- [ ] **Step 1: Run all four lifecycle tests together**

```bash
pytest tests/playwright/test_auth_lifecycle.py \
    --browser chromium --override-ini='addopts=' -v
```

Expected: 4 passed.

- [ ] **Step 2: Regression check — existing modules with auth_enabled=True**

```bash
pytest tests/playwright/ -k "not test_auth_lifecycle" \
    --browser chromium --override-ini='addopts=' -v
```

Expected: all existing tests pass unchanged.

- [ ] **Step 3: Cross-browser matrix**

```bash
pytest tests/playwright/ --browser firefox  --override-ini='addopts='
pytest tests/playwright/ --browser webkit   --override-ini='addopts='
```

Expected: 0 failures on both browsers.

- [ ] **Step 4: Final commit (update issue hygiene)**

```bash
git commit --allow-empty -m "test(playwright): B2 auth lifecycle complete

All four lifecycle tests pass (chromium, firefox, webkit).
Existing suite unaffected by auth_enabled=True flip.
authed_page fixture ready for B3/B4.

Closes #1155
Refs #1150"
```
