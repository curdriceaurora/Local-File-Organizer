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

from tests.playwright.conftest import _UserCreds

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

    def test_login_lands_on_authenticated_page(
        self, page: Page, registered_user: _UserCreds
    ) -> None:
        """
        Log in with the provided credentials and assert the profile page displays the user's full name.

        The `registered_user` fixture is created with `full_name = "Test User"`, so the test verifies that the profile page title equals "Test User" after successful login.
        """
        page.goto("/ui/profile/login")
        page.locator("#login-username").fill(registered_user.username)
        page.locator("#login-password").fill(registered_user.password)
        page.get_by_role("button", name="Log in").click()
        page.wait_for_url("**/ui/profile")
        expect(page.locator("h1.page-title")).to_have_text("Test User")

    def test_access_protected_route_while_logged_in(self, authed_page: Page) -> None:
        """
        Navigate to /ui/profile/edit and verify the profile edit form is rendered for an authenticated user.

        This endpoint is an HTMX partial that returns an HTML fragment; when the user is authenticated the fragment contains the profile edit form and does not include the error paragraph.
        """
        authed_page.goto("/ui/profile/edit")
        expect(authed_page.locator('form[action="/ui/profile/edit"]')).to_be_visible()
        expect(authed_page.locator("p.error-text")).to_have_count(0)

    def test_logout_blocks_protected_route(self, authed_page: Page) -> None:
        """
        Logs out the authenticated browser session and verifies that the protected edit route is denied access.

        Extracts the `_csrf_token` cookie value and sends it as the `x-csrf-token` header in a POST to `/ui/profile/logout`, then navigates to `/ui/profile/edit` and asserts that `p.error-text` shows "Not authenticated."
        """
        cookies = authed_page.context.cookies()
        csrf_cookie = next((c for c in cookies if c["name"] == "_csrf_token"), None)
        assert csrf_cookie is not None, "CSRF token cookie not found"
        csrf_token = csrf_cookie["value"]
        response = authed_page.request.post(
            "/ui/profile/logout",
            headers={"x-csrf-token": csrf_token},
        )
        assert response.ok, f"Logout failed with status {response.status}"
        authed_page.goto("/ui/profile/edit")
        expect(authed_page.locator("p.error-text")).to_have_text("Not authenticated.")
