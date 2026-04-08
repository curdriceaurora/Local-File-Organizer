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
